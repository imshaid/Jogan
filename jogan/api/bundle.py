"""The served bundle: one demo world, its forecaster and Jogan's plan for every test day.

The API never trains or simulates. :func:`build_bundle` runs once, at Docker build time
(D-002 #7, D-022): it builds the world from its seed, runs the status quo over the whole period,
trains the forecaster on that log exactly as the evaluation does
(:func:`jogan.eval.run.run_seed`), and switches Jogan on at the start of the test window. Each
morning's evidence (:attr:`jogan.plan.policy.Jogan.last`) is recorded, so the API can serve any
test day's recommendations, with their decision trace, from a few parquet files.

The replay does not react to approvals: it shows what Jogan would have planned on that day of
the simulated world. Usage: ``python -m jogan.api.bundle --profile full --seed 42 --out bundle``.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import lightgbm
import numpy as np
import pandas as pd

import jogan
from jogan.forecast.backtest import build_dataset, fit_forecaster
from jogan.forecast.config import load_forecast_config
from jogan.forecast.panel import panel_from_history
from jogan.ops.config import load_ops_config
from jogan.ops.env import Context, Observation, simulate
from jogan.ops.fleet import Visit
from jogan.ops.policies import STATUS_QUO, Deployed, make_policy
from jogan.plan.config import load_plan_config
from jogan.plan.policy import Jogan
from jogan.sim.config import load_config
from jogan.sim.world import build_world

AGENT_COLUMNS = ["agent_id", "territory", "setting", "size_class", "lat", "lon", "hub_road_km"]
TERRITORY_COLUMNS = ["territory", "district_en", "district_bn", "setting", "lat", "lon"]


class Recorder(Jogan):
    """Jogan that keeps every morning's evidence instead of only the last one."""

    def reset(self, ctx: Context) -> None:
        super().reset(ctx)
        self.plans: list[pd.DataFrame] = []

    def plan(self, obs: Observation) -> list[Visit]:
        visits = super().plan(obs)
        self.plans.append(self.last.assign(day=obs.day))
        return visits


@dataclasses.dataclass(frozen=True)
class Bundle:
    """What the API serves: meta, agents, territories and the per-day plans."""

    meta: dict[str, Any]
    agents: pd.DataFrame
    territories: pd.DataFrame
    plans: pd.DataFrame  # one row per (plan_date, agent)

    @property
    def bundle_id(self) -> str:
        return self.meta["bundle_id"]

    @property
    def plan_dates(self) -> list[dt.date]:
        return [dt.date.fromisoformat(d) for d in self.meta["plan_dates"]]

    def plan(self, day: dt.date) -> pd.DataFrame:
        """Every agent's evidence on ``day`` (empty when ``day`` is not a plan day)."""
        return self.plans[self.plans["plan_date"] == day]

    def recommendations(self, day: dt.date) -> list[dict[str, Any]]:
        """The visits Jogan planned on ``day``, highest value first, as rows for the queue."""
        rows = self.plan(day)
        rows = rows[rows["runner_id"].notna()].sort_values("value_tk", ascending=False)
        territory = self.agents.set_index("agent_id")["territory"]
        out = []
        for r in rows.itertuples(index=False):
            evidence = {c: _plain(getattr(r, c)) for c in EVIDENCE_COLUMNS}
            out.append(
                {
                    "agent_id": r.agent_id,
                    "territory": territory[r.agent_id],
                    "runner_id": r.runner_id,
                    "target_cash_tk": round(float(r.target_cash_tk), 2),
                    "value_tk": round(float(r.value_tk), 2),
                    "evidence": evidence,
                }
            )
        return out

    def trace(self, day: dt.date) -> dict[str, Any]:
        """Decision trace stored with every recommendation of ``day``."""
        m = self.meta
        return {
            "bundle_id": m["bundle_id"],
            "plan_date": day.isoformat(),
            "plan_hour": m["plan_hour"],
            "profile": m["profile"],
            "seed": m["seed"],
            "lost_customer_value_tk": m["lost_customer_value_tk"],
            "config_hashes": m["config_hashes"],
            "versions": m["versions"],
        }


EVIDENCE_COLUMNS = [
    "cash_tk",
    "efloat_tk",
    "p_stockout_cash",
    "p_stockout_efloat",
    "drain_cash_q50",
    "drain_cash_q90",
    "drain_cash_q99",
    "drain_efloat_q50",
    "drain_efloat_q90",
    "drain_efloat_q99",
    "need_cash_tk",
    "need_efloat_tk",
    "needs_fit",
]


def _plain(x: Any) -> Any:
    """A JSON-ready scalar: numpy types to Python, Tk and probabilities rounded."""
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return round(float(x), 4)
    return x


def _bundle_id(profile: str, seed: int, hashes: dict[str, str]) -> str:
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:8]
    return f"{profile}-s{seed}-{digest}"


def build_bundle(profile: str, seed: int, forecast_overrides: dict | None = None) -> Bundle:
    """Simulate, train and replay Jogan over the test window of one world (see module doc)."""
    started = time.perf_counter()
    sim = load_config(profile)
    world = build_world(sim, seed)
    ops = load_ops_config()
    fcfg = load_forecast_config(forecast_overrides)
    pcfg = load_plan_config()
    if profile not in fcfg.splits:
        raise ValueError(f"no forecast splits for profile {profile!r}")
    splits = fcfg.splits[profile]

    status_quo = simulate(world, make_policy(STATUS_QUO, world), ops)
    panel = panel_from_history(status_quo.history)
    ds = build_dataset(panel, world.calendar, world.agents, fcfg, splits, sim.start)
    forecaster = fit_forecaster(ds)
    del ds, status_quo

    start_hour = (splits.test[0] - sim.start).days * 24
    jogan_policy = Recorder(forecaster, pcfg)
    simulate(world, Deployed(jogan_policy, start_hour), ops)

    dates = world.calendar["date"].dt.date.to_numpy()
    plans = pd.concat(jogan_policy.plans, ignore_index=True)
    plans.insert(0, "plan_date", dates[plans.pop("day").to_numpy()])
    plans = plans.drop(columns=["hour"])
    plans["agent_id"] = plans["agent_id"].astype(str)
    plans["runner_id"] = plans["runner_id"].astype(object).where(plans["runner_id"].notna(), None)

    hashes = {
        "sim": sim.config_hash(),
        "ops": ops.config_hash(),
        "forecast": fcfg.config_hash(),
        "plan": pcfg.config_hash(),
    }
    plan_dates = sorted({d.isoformat() for d in plans["plan_date"]})
    meta = {
        "bundle_id": _bundle_id(profile, seed, hashes),
        "profile": profile,
        "seed": seed,
        "start": sim.start.isoformat(),
        "end": sim.end.isoformat(),
        "test_window": [d.isoformat() for d in splits.test],
        "plan_dates": plan_dates,
        "plan_hour": ops.policies.plan_hour,
        "lost_customer_value_tk": pcfg.lost_customer_value_tk,
        "counts": {
            "agents": len(world.agents),
            "runners": len(world.runners),
            "territories": len(world.territories),
            "recommendations": int(plans["runner_id"].notna().sum()),
        },
        "config_hashes": hashes,
        "versions": {"jogan": jogan.__version__, "lightgbm": lightgbm.__version__},
        "build_seconds": round(time.perf_counter() - started, 1),
        "simulated": True,
    }
    agents = world.agents[AGENT_COLUMNS].assign(
        agent_id=lambda d: d["agent_id"].astype(str),
        size_class=lambda d: d["size_class"].astype(str),
    )
    territories = world.territories[TERRITORY_COLUMNS].copy()
    return Bundle(meta, agents.reset_index(drop=True), territories, plans)


def save_bundle(bundle: Bundle, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(bundle.meta, indent=2) + "\n")
    bundle.agents.to_parquet(out / "agents.parquet", index=False)
    bundle.territories.to_parquet(out / "territories.parquet", index=False)
    bundle.plans.to_parquet(out / "plans.parquet", index=False)


def load_bundle(path: Path) -> Bundle:
    meta = json.loads((path / "meta.json").read_text())
    plans = pd.read_parquet(path / "plans.parquet")
    plans["plan_date"] = pd.to_datetime(plans["plan_date"]).dt.date
    plans["runner_id"] = plans["runner_id"].astype(object).where(plans["runner_id"].notna(), None)
    return Bundle(
        meta,
        pd.read_parquet(path / "agents.parquet"),
        pd.read_parquet(path / "territories.parquet"),
        plans,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", default="full")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threads", type=int, default=0, help="LightGBM threads (0: config)")
    parser.add_argument("--out", type=Path, default=Path("bundle"))
    args = parser.parse_args(argv)
    overrides = {"lightgbm": {"num_threads": args.threads}} if args.threads else None
    bundle = build_bundle(args.profile, args.seed, overrides)
    save_bundle(bundle, args.out)
    m = bundle.meta
    print(
        f"bundle {m['bundle_id']}: {len(m['plan_dates'])} plan days, "
        f"{m['counts']['recommendations']} recommendations, {m['build_seconds']} s → {args.out}"
    )


if __name__ == "__main__":
    main()
