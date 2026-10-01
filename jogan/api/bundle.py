"""The served bundle: one demo world, its forecaster and Jogan's plan for every test day.

The API never trains or simulates. :func:`build_bundle` runs once, at Docker build time
(D-002 #7, D-022): it builds the world from its seed, runs the status quo over the whole period,
trains the forecaster on that log exactly as the evaluation does
(:func:`jogan.eval.run.run_seed`), fits the anomaly detector on the same training days, and
switches Jogan on at the start of the test window. Each morning's evidence
(:attr:`jogan.plan.policy.Jogan.last`) is recorded with, for every planned visit, the side at
risk, its TreeSHAP drivers and its guardrail review (:mod:`jogan.explain`), and the day's
advisory anomaly flags (:mod:`jogan.detect.anomaly`). The API serves any test day's
recommendations, with their decision trace, from a few parquet files and never loads a model.

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
import sklearn

import jogan
from jogan.detect.anomaly import Detector, day_features, fit_detector
from jogan.explain.config import ExplainConfig, load_explain_config
from jogan.explain.drivers import contributions, top_drivers
from jogan.explain.guardrails import TrainingRange, arrived_share, review
from jogan.forecast.backtest import Forecaster, build_dataset, fit_forecaster
from jogan.forecast.config import load_forecast_config
from jogan.forecast.panel import panel_from_history
from jogan.ops.config import load_ops_config
from jogan.ops.env import Context, Observation, simulate
from jogan.ops.fleet import Visit
from jogan.ops.policies import STATUS_QUO, Deployed, make_policy
from jogan.plan.config import PlanConfig, load_plan_config
from jogan.plan.policy import Jogan
from jogan.sim.config import load_config
from jogan.sim.world import build_world

AGENT_COLUMNS = ["agent_id", "territory", "setting", "size_class", "lat", "lon", "hub_road_km"]
TERRITORY_COLUMNS = ["territory", "district_en", "district_bn", "setting", "lat", "lon"]


class Recorder(Jogan):
    """Jogan that keeps every morning's evidence, explained, instead of only the last one."""

    def __init__(
        self,
        forecaster: Forecaster,
        cfg: PlanConfig,
        explain: ExplainConfig,
        ranges: TrainingRange,
        detector: Detector,
    ) -> None:
        super().__init__(forecaster, cfg)
        self.explain, self.ranges, self.detector = explain, ranges, detector
        self.level = forecaster.cfg.quantiles.index(explain.drivers.level)

    def reset(self, ctx: Context) -> None:
        super().reset(ctx)
        self.plans: list[pd.DataFrame] = []
        self.flags: list[dict] = []

    def plan(self, obs: Observation) -> list[Visit]:
        visits = super().plan(obs)
        if self.last is None or self.last_inputs is None:
            raise RuntimeError("Jogan.plan kept no evidence")
        panel, x = self.last_inputs
        ev = self.last
        n = len(ev)

        # advisory anomaly flags on yesterday, from the records that have arrived by now
        flagged: dict[int, dict] = {}
        if obs.day > 0:
            feats = day_features(panel, self.ctx.agents, self.explain.anomaly, now=obs.hour)
            flagged = self.detector.flags(feats, obs.day - 1, self.dates[obs.day - 1])
        ids = self.ctx.agents["agent_id"].astype(str).to_numpy()
        self.flags += [{"day": obs.day, "agent_id": ids[a], **f} for a, f in flagged.items()]

        rows = np.flatnonzero(ev["runner_id"].notna().to_numpy())
        side = np.where(
            ev["p_stockout_cash"].to_numpy() >= ev["p_stockout_efloat"].to_numpy(), "cash", "efloat"
        )
        drivers: list[list[dict]] = [[] for _ in range(n)]
        for s in ("cash", "efloat"):
            mine = rows[side[rows] == s]
            booster = self.forecaster.models[self.cfg.horizon_hours, s].boosters[self.level]
            sub = x.iloc[mine]
            for a, d in zip(
                mine,
                top_drivers(contributions(booster, sub), sub, self.explain.drivers),
                strict=True,
            ):
                drivers[a] = d
        hours = min(24, obs.hour)
        hist = obs.history.available(obs.hour, obs.hour - hours, obs.hour)
        arrived = arrived_share(hist)
        outside = self.ranges.outside(x.iloc[rows])
        windows = x["hist_windows"].to_numpy(dtype=float)
        reviews: list[dict | None] = [None] * n
        for k, a in enumerate(rows):
            q90 = float(ev[f"drain_{side[a]}_q90"].iat[a])
            q50 = float(ev[f"drain_{side[a]}_q50"].iat[a])
            reviews[a] = review(
                outside[k], q90, q50, float(arrived[a]), hours, windows[a],
                flagged.get(int(a)), self.explain.guardrails,
            )  # fmt: skip
        sent = ev["runner_id"].notna().to_numpy()
        self.plans.append(
            ev.assign(
                day=obs.day,
                side=np.where(sent, side, None),
                drivers=[json.dumps(d) if sent[a] else None for a, d in enumerate(drivers)],
                review=[json.dumps(r) if r is not None else None for r in reviews],
            )
        )
        return visits


@dataclasses.dataclass(frozen=True)
class Bundle:
    """What the API serves: meta, agents, territories and the per-day plans."""

    meta: dict[str, Any]
    agents: pd.DataFrame
    territories: pd.DataFrame
    plans: pd.DataFrame  # one row per (plan_date, agent)
    anomalies: pd.DataFrame  # one row per advisory flag, raised on plan_date about date

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
            evidence["side"] = r.side
            evidence["drivers"] = json.loads(r.drivers)
            evidence["review"] = json.loads(r.review)
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

    def anomaly_flags(self, day: dt.date) -> list[dict[str, Any]]:
        """Advisory anomaly flags raised on the morning of ``day``, strangest first."""
        rows = self.anomalies[self.anomalies["plan_date"] == day].sort_values(
            "score", ascending=False
        )
        territory = self.agents.set_index("agent_id")["territory"]
        return [
            {
                "agent_id": r.agent_id,
                "territory": territory[r.agent_id],
                "date": r.date,
                "score": round(float(r.score), 4),
                "items": json.loads(r.items),
            }
            for r in rows.itertuples(index=False)
        ]

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
    ecfg = load_explain_config()
    if profile not in fcfg.splits:
        raise ValueError(f"no forecast splits for profile {profile!r}")
    if ecfg.drivers.level not in fcfg.quantiles:
        raise ValueError(f"drivers.level {ecfg.drivers.level} is not a forecast quantile")
    splits = fcfg.splits[profile]

    status_quo = simulate(world, make_policy(STATUS_QUO, world), ops)
    panel = panel_from_history(status_quo.history)
    ds = build_dataset(panel, world.calendar, world.agents, fcfg, splits, sim.start)
    forecaster = fit_forecaster(ds)
    h = pcfg.horizon_hours
    ranges = TrainingRange.fit(
        ds.features.matrix(h)[ds.rows("train", h)], ecfg.guardrails.range_features
    )
    train_days = np.arange(
        (splits.train[0] - sim.start).days, (splits.train[1] - sim.start).days + 1
    )
    feats = day_features(panel, world.agents, ecfg.anomaly)
    detector = fit_detector(feats, world.agents, train_days, ecfg.anomaly)
    del ds, status_quo, panel, feats

    start_hour = (splits.test[0] - sim.start).days * 24
    jogan_policy = Recorder(forecaster, pcfg, ecfg, ranges, detector)
    simulate(world, Deployed(jogan_policy, start_hour), ops)

    dates = world.calendar["date"].dt.date.to_numpy()
    plans = pd.concat(jogan_policy.plans, ignore_index=True)
    plans.insert(0, "plan_date", dates[plans.pop("day").to_numpy()])
    plans = plans.drop(columns=["hour"])
    plans["agent_id"] = plans["agent_id"].astype(str)
    plans["runner_id"] = plans["runner_id"].astype(object).where(plans["runner_id"].notna(), None)
    flags = pd.DataFrame(jogan_policy.flags, columns=["day", "agent_id", "date", "score", "items"])
    flags.insert(0, "plan_date", dates[flags.pop("day").to_numpy(dtype=int)])
    flags["items"] = flags["items"].map(json.dumps)
    reviewed = plans["review"].dropna().map(lambda r: json.loads(r)["flag"])

    hashes = {
        "sim": sim.config_hash(),
        "ops": ops.config_hash(),
        "forecast": fcfg.config_hash(),
        "plan": pcfg.config_hash(),
        "explain": ecfg.config_hash(),
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
            "manual_review": int(reviewed.sum()),
            "anomaly_flags": len(flags),
        },
        "config_hashes": hashes,
        "versions": {
            "jogan": jogan.__version__,
            "lightgbm": lightgbm.__version__,
            "scikit-learn": sklearn.__version__,
        },
        "build_seconds": round(time.perf_counter() - started, 1),
        "simulated": True,
    }
    agents = world.agents[AGENT_COLUMNS].assign(
        agent_id=lambda d: d["agent_id"].astype(str),
        size_class=lambda d: d["size_class"].astype(str),
    )
    territories = world.territories[TERRITORY_COLUMNS].copy()
    return Bundle(meta, agents.reset_index(drop=True), territories, plans, flags)


def save_bundle(bundle: Bundle, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(bundle.meta, indent=2) + "\n")
    bundle.agents.to_parquet(out / "agents.parquet", index=False)
    bundle.territories.to_parquet(out / "territories.parquet", index=False)
    bundle.plans.to_parquet(out / "plans.parquet", index=False)
    bundle.anomalies.to_parquet(out / "anomalies.parquet", index=False)


def load_bundle(path: Path) -> Bundle:
    meta = json.loads((path / "meta.json").read_text())
    plans = pd.read_parquet(path / "plans.parquet")
    plans["plan_date"] = pd.to_datetime(plans["plan_date"]).dt.date
    plans["runner_id"] = plans["runner_id"].astype(object).where(plans["runner_id"].notna(), None)
    anomalies = pd.read_parquet(path / "anomalies.parquet")
    anomalies["plan_date"] = pd.to_datetime(anomalies["plan_date"]).dt.date
    return Bundle(
        meta,
        pd.read_parquet(path / "agents.parquet"),
        pd.read_parquet(path / "territories.parquet"),
        plans,
        anomalies,
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
        f"{m['counts']['recommendations']} recommendations "
        f"({m['counts']['manual_review']} for manual review), "
        f"{m['counts']['anomaly_flags']} anomaly flags, {m['build_seconds']} s → {args.out}"
    )


if __name__ == "__main__":
    main()
