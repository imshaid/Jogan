"""Stress check: Jogan's morning for 10,000 agents (``make stress`` → ``artifacts/stress.json``).

The ``stress`` profile replicates each of the six hubs as 10 distributor areas: 10,000 agents,
60 territories, 18 to 31 May 2026 (D-015). Fourteen days are too few to train on, so the models
are the demo bundle's, fitted on ``full`` seed 42 exactly as ``make bundle`` does
(:func:`jogan.api.bundle.fit_models`). The forecaster takes an agent's territory as a feature
and as a conformal group, so it sees each distributor area as the hub it replicates, whose
demand pattern the area copies. Runners, routes and the programs keep the 60 areas.

The status quo runs ``warmup_days``; then every morning runs the served pipeline
(:class:`jogan.api.bundle.Recorder`): features, forecast, newsvendor levels, the value of each
visit, one program per territory, TreeSHAP drivers, guardrails and anomaly flags. The file
records how long each part took and on what machine. With at most 13 days of history behind the
features, nothing is scored: this is timing only (D-026).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import resource
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import lightgbm
import numpy as np
import scipy
import sklearn

import jogan
from jogan.api.bundle import Models, Recorder, fit_models
from jogan.eval.config import StressConfig, load_stress_config
from jogan.explain.config import ExplainConfig, load_explain_config
from jogan.forecast.backtest import GROUP_COLUMNS
from jogan.forecast.config import load_forecast_config
from jogan.ops.config import load_ops_config
from jogan.ops.env import Context, Observation, simulate
from jogan.ops.fleet import Visit
from jogan.ops.policies import STATUS_QUO, Deployed, make_policy
from jogan.plan.config import PlanConfig, load_plan_config
from jogan.plan.policy import Jogan
from jogan.sim.config import CONFIG_DIR, SimConfig, load_config
from jogan.sim.world import build_world

ARTIFACTS = CONFIG_DIR.parent / "artifacts"


def hub_of(territories: Iterable[str], sim: SimConfig) -> dict[str, str]:
    """Each distributor area's hub: areas are named ``<hub><nn>`` when hubs are replicated."""
    out = {}
    for code in territories:
        hub = code if sim.replicas == 1 else code[:-2]
        if hub not in sim.territories:
            raise ValueError(f"territory {code!r} is not a replica of a configured hub")
        out[code] = hub
    return out


class _Timed(Jogan):
    """Times :meth:`Jogan.plan` (features, forecast, levels, values, programs) in a morning."""

    def plan(self, obs: Observation) -> list[Visit]:
        started = time.perf_counter()
        visits = super().plan(obs)
        self.plan_s = time.perf_counter() - started
        return visits


class Stress(Recorder, _Timed):
    """The served morning with the forecaster seeing hubs, and how long each part took."""

    def __init__(
        self, models: Models, cfg: PlanConfig, explain: ExplainConfig, hub: dict[str, str]
    ) -> None:
        super().__init__(models.forecaster, cfg, explain, models.ranges, models.detector)
        self.hub = hub

    def reset(self, ctx: Context) -> None:
        super().reset(ctx)
        agents = ctx.agents.assign(territory=ctx.agents["territory"].map(self.hub))
        self.hub_ctx = dataclasses.replace(ctx, agents=agents)
        self.groups = agents[list(GROUP_COLUMNS)].astype(str).reset_index(drop=True)
        # the detector keeps one forest per setting; its agents are this world's
        self.detector = dataclasses.replace(
            self.detector, groups=agents["setting"].astype(str).to_numpy()
        )
        self.mornings: list[dict[str, Any]] = []

    def plan(self, obs: Observation) -> list[Visit]:
        before = dataclasses.replace(self.log)
        flags = len(self.flags)
        real, self.ctx = self.ctx, self.hub_ctx
        started = time.perf_counter()
        try:
            visits = super().plan(obs)
        finally:
            self.ctx = real
        morning = time.perf_counter() - started
        reviews = self.plans[-1]["review"].dropna().map(lambda r: json.loads(r)["flag"])
        self.mornings.append(
            {
                "date": self.dates[obs.day].isoformat(),
                "morning_s": round(morning, 3),
                "plan_s": round(self.plan_s, 3),
                "solver_s": round(self.log.seconds - before.seconds, 3),
                "explain_s": round(morning - self.plan_s, 3),
                "programs": self.log.programs - before.programs,
                "fallbacks": self.log.fallbacks - before.fallbacks,
                "candidates": int(self.last["candidate"].sum()) if self.last is not None else 0,
                "visits": len(visits),
                "manual_review": int(reviews.sum()),
                "anomaly_flags": len(self.flags) - flags,
            }
        )
        return visits


def _machine() -> dict[str, Any]:
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return {
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "memory_gb": round(memory / 2**30, 1),
        "os": f"{platform.system()} {platform.release()}",
    }


def _spread(values: list[float]) -> dict[str, float]:
    return {"mean": round(float(np.mean(values)), 3), "max": round(float(np.max(values)), 3)}


def run_stress(
    cfg: StressConfig,
    sim_overrides: dict | None = None,
    forecast_overrides: dict | None = None,
) -> dict[str, Any]:
    """Fit the models, then time the status quo and Jogan's mornings on the stress world."""
    started = time.perf_counter()
    ops = load_ops_config()
    fcfg = load_forecast_config(forecast_overrides)
    pcfg = load_plan_config()
    xcfg = load_explain_config()
    seconds: dict[str, float] = {}

    train_sim = load_config(cfg.models.profile)
    sim = load_config(cfg.profile, sim_overrides)
    if not set(sim.territories) <= set(train_sim.territories):
        raise ValueError("the models were not trained on every hub of the stress world")
    if not 0 < cfg.warmup_days < (sim.end - sim.start).days + 1:
        raise ValueError("warmup_days must leave at least one plan morning")
    t0 = time.perf_counter()
    models = fit_models(
        build_world(train_sim, cfg.models.seed),
        ops,
        fcfg,
        xcfg,
        fcfg.splits[cfg.models.profile],
        pcfg.horizon_hours,
    )
    seconds["fit_models"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    world = build_world(sim, cfg.seed)
    seconds["build_world"] = time.perf_counter() - t0
    hub = hub_of(world.territories["territory"], sim)

    t0 = time.perf_counter()
    simulate(world, make_policy(STATUS_QUO, world), ops)
    seconds["status_quo_run"] = time.perf_counter() - t0
    policy = Stress(models, pcfg, xcfg, hub)
    t0 = time.perf_counter()
    simulate(world, Deployed(policy, cfg.warmup_days * 24), ops)
    seconds["jogan_run"] = time.perf_counter() - t0
    seconds["total"] = time.perf_counter() - started

    mornings = policy.mornings
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KiB on Linux
    return {
        "meta": {
            "generated_by": "make stress (python -m jogan.eval.stress)",
            "timing_only": True,
            "profile": cfg.profile,
            "seed": cfg.seed,
            "warmup_days": cfg.warmup_days,
            "models": {"profile": cfg.models.profile, "seed": cfg.models.seed},
            "config_hashes": {
                "sim": sim.config_hash(),
                "ops": ops.config_hash(),
                "forecast": fcfg.config_hash(),
                "plan": pcfg.config_hash(),
                "explain": xcfg.config_hash(),
            },
            "lightgbm_threads": fcfg.lightgbm.num_threads,
            "milp_time_limit_s": pcfg.milp.time_limit_s,
            "versions": {
                "jogan": jogan.__version__,
                "python": platform.python_version(),
                "lightgbm": lightgbm.__version__,
                "scipy": scipy.__version__,
                "scikit-learn": sklearn.__version__,
            },
            "machine": _machine(),
        },
        "world": {
            "agents": len(world.agents),
            "runners": len(world.runners),
            "territories": len(world.territories),
            "hubs": len(set(hub.values())),
            "days": len(world.calendar),
            "plan_mornings": len(mornings),
        },
        "seconds": {k: round(v, 1) for k, v in seconds.items()},
        "summary": {
            "morning_s": _spread([m["morning_s"] for m in mornings]),
            "plan_s": _spread([m["plan_s"] for m in mornings]),
            "solver_s": _spread([m["solver_s"] for m in mornings]),
            "explain_s": _spread([m["explain_s"] for m in mornings]),
            "programs": sum(m["programs"] for m in mornings),
            "fallbacks": sum(m["fallbacks"] for m in mornings),
            "visits": sum(m["visits"] for m in mornings),
            "peak_memory_mb": round(peak_mb),
        },
        "mornings": mornings,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ARTIFACTS / "stress.json")
    args = parser.parse_args(argv)
    result = run_stress(load_stress_config())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    w, s = result["world"], result["summary"]
    print(
        f"stress: {w['agents']} agents, {w['territories']} territories, "
        f"{w['plan_mornings']} mornings; morning mean {s['morning_s']['mean']} s, "
        f"max {s['morning_s']['max']} s (solver max {s['solver_s']['max']} s); "
        f"{s['fallbacks']} fallbacks → {args.out}"
    )


if __name__ == "__main__":
    main()
