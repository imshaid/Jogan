"""Final evaluation: ``python -m jogan.eval`` (``make eval``) → ``artifacts/metrics.json``.

Runs every seed of ``configs/eval/base.yaml`` (:func:`jogan.eval.run.run_seed`, seeds in
parallel processes), keeps each seed's full record under ``artifacts/eval/`` and writes the
aggregate (:func:`jogan.eval.report.build_report`). Every number in the README, report, UI and
video comes from that file.

Overriding the profile, the seeds or the boosting rounds is for development: such a run writes
``artifacts/eval/metrics_dev.json`` instead, so ``artifacts/metrics.json`` only ever holds the
configured evaluation seeds (D-010).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import lightgbm
import numpy as np
import pandas as pd
import scipy

import jogan
from jogan.eval.config import EvalConfig, load_eval_config
from jogan.eval.report import build_report
from jogan.eval.run import run_seed_job
from jogan.plan.config import load_plan_config
from jogan.sim.config import CONFIG_DIR

ARTIFACTS = CONFIG_DIR.parent / "artifacts"


def run(ecfg: EvalConfig, overrides: dict, out: Path, seed_dir: Path) -> dict:
    started = time.perf_counter()
    pcfg = load_plan_config()
    if pcfg.lost_customer_value_tk not in ecfg.lost_customer_values_tk:
        raise SystemExit("configs/plan lost_customer_value_tk must be one of the evaluated values")
    jobs = [(ecfg.profile, s, ecfg, overrides) for s in ecfg.seeds]
    if ecfg.workers > 1 and len(jobs) > 1:
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(min(ecfg.workers, len(jobs)), mp_context=ctx) as pool:
            seeds = list(pool.map(run_seed_job, jobs))
    else:
        seeds = [run_seed_job(job) for job in jobs]
    seed_dir.mkdir(parents=True, exist_ok=True)
    for s in seeds:
        path = seed_dir / f"{s['profile']}_seed{s['seed']}.json"
        path.write_text(json.dumps(s, indent=1, sort_keys=True, default=str) + "\n")

    report = build_report(
        seeds, ecfg.lost_customer_values_tk, pcfg.lost_customer_value_tk, ecfg.interval_level
    )
    meta = {
        "generated_by": "make eval (python -m jogan.eval)",
        "profile": ecfg.profile,
        "seeds": list(ecfg.seeds),
        "windows": seeds[0]["windows"],
        "interval_level": ecfg.interval_level,
        "lost_customer_values_tk": list(ecfg.lost_customer_values_tk),
        "config_hashes": seeds[0]["config_hashes"],
        "versions": {
            "jogan": jogan.__version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "lightgbm": lightgbm.__version__,
            "scipy": scipy.__version__,
        },
        "runtime_s": round(time.perf_counter() - started, 1),
        "seed_runtime_s": {str(s["seed"]): s["timing_s"] for s in seeds},
        "jogan_diagnostics": {str(s["seed"]): s["jogan_diagnostics"] for s in seeds},
    }
    body = {"meta": meta, **report}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return body


def _print(body: dict) -> None:
    meta, by_value = body["meta"], body["comparison"]["by_value"]
    value = body["comparison"]["jogan_value_tk"]
    print(f"{meta['profile']}, seeds {meta['seeds']}: {meta['runtime_s']:.0f} s")
    test = next(iter(meta["windows"]))
    print(f"  {test} window, mean over seeds (95% interval)")
    print(f"  {'policy':<22}{'lost/1000':>22}{'runner km':>12}{'known ৳ (mid)':>16}")
    for name, by_w in body["policies"].items():
        p = by_w[test]
        lost, km, known = p["lost_per_1000"], p["runner_km"], p["known_cost_tk"]["mid"]
        span = f"[{lost['low']}, {lost['high']}]" if lost["low"] is not None else ""
        row = f"{lost['mean']:>9.2f} {span:>12}{km['mean']:>12,.0f}{known['mean']:>16,.0f}"
        print(f"  {name:<22}{row}")
    print(f"  Jogan at ৳{value:g} per lost customer against each baseline ({test}):")
    for base, by_w in by_value[f"{value:g}"].items():
        c = by_w[test]
        be = c["break_even_tk"]["mid"]
        print(
            f"    {base:<14} lost/1000 {c['lost_per_1000']['mean']:+.2f} "
            f"({c['lost_per_1000']['sign']}), known ৳ {c['known_cost_tk']['mid']['mean']:+,.0f}, "
            f"{be['verdict']}"
            + (f" ৳{be['value']} [{be['low']}, {be['high']}]" if be["value"] is not None else "")
        )
    for name, h in body["hypotheses"].items():
        if "holds" in h:
            print(f"  {name}: {'holds' if h['holds'] else 'does not hold'}")
    print(f"  {len(body['does_not_win'])} cases where Jogan does not win (see does_not_win)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m jogan.eval", description=__doc__)
    parser.add_argument("--profile", default=None, help="development only: another profile")
    parser.add_argument("--seeds", type=int, nargs="+", default=None, help="development only")
    parser.add_argument(
        "--rounds", type=int, default=None, help="development only: boosting rounds"
    )
    parser.add_argument(
        "--values", type=float, nargs="+", default=None, help="lost-customer values"
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    overrides: dict = {}
    if args.profile:
        overrides["profile"] = args.profile
    if args.seeds:
        overrides["seeds"] = args.seeds
    if args.values:
        overrides["lost_customer_values_tk"] = args.values
    if args.workers:
        overrides["workers"] = args.workers
    ecfg = load_eval_config(overrides)
    forecast_overrides = {"lightgbm": {"num_boost_round": args.rounds}} if args.rounds else {}
    final = not (args.profile or args.seeds or args.rounds or args.values)
    out = args.out or (
        ARTIFACTS / "metrics.json" if final else ARTIFACTS / "eval" / "metrics_dev.json"
    )
    body = run(ecfg, forecast_overrides, out, ARTIFACTS / "eval")
    _print(body)
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
