"""One seed of the evaluation: status-quo log → forecast → every policy on the test window.

1. The status quo runs over the whole simulated period; its observed log is the only training
   input (D-018). The forecaster trains on the log's training split and calibrates on its
   calibration split, and its scores on the test split come from
   :func:`jogan.forecast.backtest.evaluate` (D-020).
2. Every other policy runs on the same world, switched on at the start of the test window
   (:class:`~jogan.ops.policies.Deployed`), so all of them start from the status quo's state
   and face the same customers (D-017). Jogan runs once per lost-customer value of the sweep,
   and once per ablation at its configured value: the greedy round instead of the program, and
   the two-sided newsvendor split instead of the typical one.
3. Each episode is summarised on the test window and on the Eid days inside it (ten days before
   an Eid to three days after, as the forecast scores them), with the known cost at the low,
   middle and high runner salary.
4. The advisory anomaly flag is fit on the status-quo log's training days and scored on its
   test days against the injected anomalies (:func:`jogan.detect.anomaly.evaluate`).

Nothing here reads files: the world is rebuilt from its seed and the log is taken from the
simulation, which a test shows equals the written log (D-020).
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

import numpy as np
import pandas as pd

from jogan.detect.anomaly import evaluate as evaluate_anomalies
from jogan.eval.config import EvalConfig
from jogan.explain.config import load_explain_config
from jogan.forecast.backtest import build_dataset, evaluate, fit_forecaster
from jogan.forecast.config import load_forecast_config
from jogan.forecast.panel import panel_from_history
from jogan.ops.config import Costs, load_ops_config
from jogan.ops.costs import salary_tk_per_month
from jogan.ops.env import LOST, SERVED, SERVED_ON_RETRY, Episode, simulate
from jogan.ops.metrics import summarize, truth_hourly
from jogan.ops.policies import BASELINES, STATUS_QUO, UPPER_BOUND, Deployed, make_policy
from jogan.plan.config import load_plan_config
from jogan.plan.policy import Jogan, JoganMidday
from jogan.sim.config import SimConfig, load_config
from jogan.sim.world import World, build_world

EID_BEFORE_DAYS, EID_AFTER_DAYS = 10, 3  # as jogan.forecast.backtest scores the Eid period


ABLATIONS = {
    "greedy": {"dispatch": "greedy"},  # same forecast and levels, M3's greedy round
    "two_sided": {"newsvendor": {"split": "two_sided"}},  # split at the two-sided optimum
}


def jogan_key(value_tk: float, ablation: str | None = None) -> str:
    """``jogan@20`` for Jogan at Tk 20 per lost customer, ``jogan_greedy@20`` for an ablation."""
    return f"jogan{'_' + ablation if ablation else ''}@{value_tk:g}"


def jogan_runs(ecfg: EvalConfig, value_tk: float) -> dict[str, dict]:
    """Plan-config overrides of every Jogan run: the sweep, then the ablations at ``value_tk``."""
    runs = {jogan_key(v): {"lost_customer_value_tk": v} for v in ecfg.lost_customer_values_tk}
    for name, overrides in ABLATIONS.items():
        runs[jogan_key(value_tk, name)] = {"lost_customer_value_tk": value_tk, **overrides}
    return runs


def eid_window(calendar: pd.DataFrame, window: tuple[dt.date, dt.date]) -> tuple | None:
    """First and last Eid-period day inside ``window``, or ``None`` when it holds none."""
    to = calendar["days_to_eid"].astype("Float64").fillna(99).to_numpy(dtype=float)
    since = calendar["days_since_eid"].astype("Float64").fillna(99).to_numpy(dtype=float)
    dates = calendar["date"].dt.date.to_numpy()
    near = (to <= EID_BEFORE_DAYS) | (since <= EID_AFTER_DAYS)
    inside = near & (dates >= window[0]) & (dates <= window[1])
    if not inside.any():
        return None
    days = dates[inside]
    return days[0], days[-1]


def truth_of(ep: Episode) -> dict[str, np.ndarray]:
    """The evaluation-only panels :func:`~jogan.forecast.backtest.evaluate` needs."""
    hourly = truth_hourly(ep)
    names = ("req_co_tk", "req_ci_tk", "lost_co_n", "lost_ci_n")
    out = {name: hourly[name].astype(float) for name in names}
    return {**out, "cash_tk": ep.cash.astype(float), "efloat_tk": ep.efloat.astype(float)}


def split_served(ep: Episode, sim: SimConfig, window: tuple[dt.date, dt.date]) -> list[int]:
    """Injected split cash-outs inside ``window`` that were served, and all of them.

    Evaluation only. The injected amounts sit just under a round number (``anomalies.split``
    in ``configs/sim``); ordinary tickets above ৳1,000 are rounded to ৳100 or ৳500, so the
    amount alone marks them. A split cash-out that finds the drawer short is turned away and
    never reaches the observed log, so no detector on that log can see it.
    """
    first = (window[0] - sim.start).days * 86400
    last = ((window[1] - sim.start).days + 1) * 86400
    mask = (
        (ep.side == 0)
        & np.isin(ep.amount, sim.anomalies.split.amounts)
        & (ep.t >= first)
        & (ep.t < last)
    )
    served = np.isin(ep.outcome[mask], (SERVED, SERVED_ON_RETRY))
    return [int(served.sum()), int(mask.sum())]


DAY_TYPES = ("eid", "pre_eid", "payday", "holiday", "bank_weekend", "ordinary")


def day_types(calendar: pd.DataFrame, sim: SimConfig) -> np.ndarray:
    """Each calendar day's Bangladesh event type: the first of :data:`DAY_TYPES` that applies.

    ``eid``: Eid day and the days of its drop (``festival.eid_drop``); ``pre_eid``: the festival
    ramp before Eid (bonuses, remittances); ``payday``: day 1 to ``payday.last_day`` of the month
    (wages, Labour Act s.123, and month-start remittances); ``holiday``: other bank holidays;
    ``bank_weekend``: other days the banks are shut (Friday, Saturday); ``ordinary``: the rest.
    """
    to = calendar["days_to_eid"].astype("Float64").fillna(99).to_numpy(dtype=float)
    since = calendar["days_since_eid"].astype("Float64").fillna(99).to_numpy(dtype=float)
    rules = [
        ("eid", since < len(sim.festival.eid_drop)),
        ("pre_eid", (to >= 1) & (to <= sim.festival.ramp_days)),
        ("payday", calendar["day"].to_numpy() <= sim.payday.last_day),
        ("holiday", calendar["holiday_en"].notna().to_numpy()),
        ("bank_weekend", ~calendar["bank_open"].to_numpy(dtype=bool)),
    ]
    out = np.full(len(calendar), "ordinary", dtype=object)
    for name, mask in reversed(rules):
        out[mask] = name
    return out


def by_day_type(ep: Episode, window: tuple[dt.date, dt.date]) -> dict[str, dict]:
    """Requests, lost requests, runner visits and agents' bank trips per day type in ``window``."""
    sim = ep.world.config
    types = day_types(ep.world.calendar, sim)
    d0, d1 = (window[0] - sim.start).days, (window[1] - sim.start).days + 1
    day = ep.t // 86400
    refill_day = ep.refills["t"].to_numpy() // 86400
    rd = ep.runner_days
    out = {}
    for name in DAY_TYPES:
        days = np.flatnonzero(types[d0:d1] == name) + d0
        if not len(days):
            continue
        inside = np.isin(day, days)
        requests, lost = int(inside.sum()), int((inside & (ep.outcome == LOST)).sum())
        out[name] = {
            "days": len(days),
            "requests": requests,
            "lost": lost,
            "lost_per_1000": round(1000 * lost / requests, 3) if requests else 0.0,
            "runner_visits": int(rd.loc[rd["day"].isin(days), "visits"].sum()),
            "self_refills": int(np.isin(refill_day, days).sum()),
        }
    return out


def record(ep: Episode, windows: dict[str, tuple[dt.date, dt.date]], costs: Costs) -> dict:
    """Service, operations, costs (at three salaries) and groups per evaluation window."""
    mid = salary_tk_per_month(costs)
    low, high = costs.runner.salary_tk_per_month
    out = {}
    for name, (start, end) in windows.items():
        s = summarize(ep, costs, start, end)
        cost = s["cost_tk"]
        other = cost["known_total"] - cost["runner_time"]  # runner time scales with salary
        cost["known_total_by_salary"] = {
            k: round(other + cost["runner_time"] * salary / mid, 2)
            for k, salary in (("low", low), ("mid", mid), ("high", high))
        }
        out[name] = {k: s[k] for k in ("window", "service", "operations", "cost_tk", "groups")}
        out[name]["by_day_type"] = by_day_type(ep, (start, end))
    return out


def _deploy(world: World, policy, start_hour: int, ops) -> Episode:
    return simulate(world, Deployed(policy, start_hour), ops)


def run_seed(
    profile: str, seed: int, ecfg: EvalConfig, forecast_overrides: dict | None = None
) -> dict[str, Any]:
    """Forecast scores and every policy's record for one world."""
    started = time.perf_counter()
    sim = load_config(profile)
    world = build_world(sim, seed)
    ops = load_ops_config()
    fcfg = load_forecast_config(
        {"lightgbm": {"num_threads": ecfg.lightgbm_threads}} | (forecast_overrides or {})
    )
    pcfg = load_plan_config()
    xcfg = load_explain_config()
    if profile not in fcfg.splits:
        raise ValueError(f"no forecast splits for profile {profile!r}")
    splits = fcfg.splits[profile]
    windows = {"test": splits.test}
    if (eid := eid_window(world.calendar, splits.test)) is not None:
        windows["eid"] = eid
    timing: dict[str, float] = {}

    status_quo = simulate(world, make_policy(STATUS_QUO, world), ops)
    panel = panel_from_history(status_quo.history)
    ds = build_dataset(panel, world.calendar, world.agents, fcfg, splits, sim.start)
    fc = fit_forecaster(ds)
    forecast = evaluate(ds, fc, truth_of(status_quo))
    del ds
    timing["forecast_s"] = time.perf_counter() - started
    anomaly = evaluate_anomalies(
        panel, world.agents, world.anomalies, sim.start, splits.train, splits.test, xcfg.anomaly
    )
    del panel
    anomaly["split_served"] = split_served(status_quo, sim, splits.test)

    policies = {STATUS_QUO: record(status_quo, windows, ops.costs)}
    del status_quo
    start_hour = (splits.test[0] - sim.start).days * 24
    for name in (*BASELINES[1:], UPPER_BOUND):
        policies[name] = record(
            _deploy(world, make_policy(name, world), start_hour, ops), windows, ops.costs
        )
    diagnostics = {}
    for key, overrides in jogan_runs(ecfg, pcfg.lost_customer_value_tk).items():
        t0 = time.perf_counter()
        jogan = Jogan(fc, load_plan_config(overrides))
        policies[key] = record(_deploy(world, jogan, start_hour, ops), windows, ops.costs)
        diagnostics[key] = {
            "seconds": round(time.perf_counter() - t0, 2),
            "programs": jogan.log.programs,
            "fallbacks": jogan.log.fallbacks,
            "solver_seconds": round(jogan.log.seconds, 3),
            "dropped_stops": jogan.log.dropped,
            "filled_stops": jogan.log.filled,
        }
    # the midday check for surprise rushes, a variant at the plan's value (D-036)
    key = jogan_key(pcfg.lost_customer_value_tk, "midday")
    midday = JoganMidday(fc, load_plan_config())
    policies[key] = record(_deploy(world, midday, start_hour, ops), windows, ops.costs)
    diagnostics[key] = {"midday_visits": midday.midday_sent}
    timing["total_s"] = time.perf_counter() - started
    return {
        "profile": profile,
        "seed": seed,
        "agents": len(world.agents),
        "windows": {k: [d.isoformat() for d in v] for k, v in windows.items()},
        "forecast": forecast,
        "anomaly": anomaly,
        "policies": policies,
        "jogan_diagnostics": diagnostics,
        "timing_s": {k: round(v, 1) for k, v in timing.items()},
        "config_hashes": {
            "sim": sim.config_hash(),
            "ops": ops.config_hash(),
            "forecast": fcfg.config_hash(),
            "plan": pcfg.config_hash(),
            "explain": xcfg.config_hash(),
            "eval": ecfg.config_hash(),
        },
    }


def run_seed_job(job: tuple[str, int, EvalConfig, dict]) -> dict[str, Any]:
    """:func:`run_seed` on one tuple, for a process pool (importable by spawned workers)."""
    return run_seed(*job)
