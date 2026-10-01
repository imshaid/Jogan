"""Backtest the drain forecast on a status-quo log: ``python -m jogan.forecast --profile dev``.

Reads the public world tables and ``ops/fixed_round/obs/`` (``make history`` writes them),
trains on the training split, calibrates on the calibration split and scores the test
split, against the estimated labels and against true demand from ``ops/fixed_round/truth/``
(evaluation only). Writes ``forecast/metrics_<strategy>.json`` next to the world.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import lightgbm
import pandas as pd

import jogan
from jogan.forecast.backtest import build_dataset, evaluate, fit_forecaster, truth_panels
from jogan.forecast.config import SIDES, SPLITS, load_forecast_config
from jogan.forecast.panel import read_panel
from jogan.ops.config import load_ops_config
from jogan.ops.io import ops_dir
from jogan.ops.policies import STATUS_QUO
from jogan.sim.config import load_config
from jogan.sim.io import DATA_DIR, read_world, world_dir

TRUTH_COLUMNS = ["agent_id", "ts", "req_co_tk", "req_ci_tk", "lost_co_n", "lost_ci_n"]
TRUTH_COLUMNS += ["cash_tk", "efloat_tk"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m jogan.forecast", description=__doc__)
    parser.add_argument("--profile", default="dev", help="configs/sim/<profile>.yaml")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--censoring", choices=("impute", "ignore", "drop"), default=None)
    parser.add_argument("--rounds", type=int, default=None, help="boosting rounds (smoke runs)")
    parser.add_argument("--root", type=Path, default=DATA_DIR, help="data root (default data/)")
    args = parser.parse_args(argv)

    overrides: dict = {}
    if args.censoring:
        overrides["censoring"] = {"strategy": args.censoring}
    if args.rounds:
        overrides["lightgbm"] = {"num_boost_round": args.rounds}
    cfg = load_forecast_config(overrides)
    sim = load_config(args.profile)
    if args.profile not in cfg.splits:
        raise SystemExit(f"no forecast splits for profile {args.profile!r} in configs/forecast/")
    world = world_dir(args.profile, args.seed, args.root)
    log = ops_dir(args.profile, args.seed, STATUS_QUO, args.root)
    if not (log / "obs" / "hourly.parquet").exists():
        raise SystemExit(
            f"no status-quo log under {log}; run "
            f"`make data history PROFILE={args.profile} SEED={args.seed}` first"
        )

    started = time.perf_counter()
    public = read_world(world)
    ids = public["agents"]["agent_id"].tolist()
    panel = read_panel(log / "obs", ids, sim.start, sim.n_days * 24)
    splits = cfg.splits[args.profile]
    ds = build_dataset(panel, public["calendar"], public["agents"], cfg, splits, sim.start)
    built = time.perf_counter()
    fc = fit_forecaster(ds)
    fitted = time.perf_counter()
    truth_frame = pd.read_parquet(log / "truth" / "hourly.parquet", columns=TRUTH_COLUMNS)
    truth = truth_panels(truth_frame, ids, sim.start, sim.n_days * 24)
    result = evaluate(ds, fc, truth)
    scored = time.perf_counter()

    meta = {
        "profile": args.profile,
        "seed": args.seed,
        "policy_log": STATUS_QUO,
        "censoring": cfg.censoring.strategy,
        "sim_config_hash": sim.config_hash(),
        "ops_config_hash": load_ops_config().config_hash(),
        "forecast_config_hash": cfg.config_hash(),
        "lightgbm_version": lightgbm.__version__,
        "jogan_version": jogan.__version__,
        "splits": {k: [d.isoformat() for d in getattr(splits, k)] for k in SPLITS},
        "rows": {k: int((ds.split == k).sum()) for k in SPLITS},
        "quantiles": list(cfg.quantiles),
        "horizons_hours": list(cfg.horizons_hours),
    }
    out = world / "forecast" / f"metrics_{cfg.censoring.strategy}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, **result}, indent=2, sort_keys=True) + "\n")

    print(
        f"{args.profile} seed {args.seed}: {meta['rows']['train']:,} train, "
        f"{meta['rows']['calibration']:,} calibration, {meta['rows']['test']:,} test rows; "
        f"censoring {cfg.censoring.strategy}"
    )
    print(
        f"  features {built - started:.1f} s, fit {fitted - built:.1f} s, "
        f"score {scored - fitted:.1f} s"
    )
    print("  test split, scored against true demand: mean pinball loss (Tk) per method,")
    print("  coverage of the calibrated 90% and 80% intervals, Brier score of P(stock-out)")
    head = ("model", "cqr", "empirical", "naive", "90% cov", "80% cov", "brier")
    print(f"  {'side':<7}{'h':>3}  " + "  ".join(f"{c:>9}" for c in head))
    for side in SIDES:
        for h, e in result["forecast"][side].items():
            m, iv = e["methods"], e["intervals"]["truth"]
            row = [
                f"{m['model']['pinball_truth']:.0f}",
                f"{m['model_cqr']['pinball_truth']:.0f}",
                f"{m['empirical']['pinball_truth']:.0f}",
                f"{m['naive_cqr']['pinball_truth']:.0f}",
                f"{iv['90']['coverage']:.3f}" if "90" in iv else "-",
                f"{iv['80']['coverage']:.3f}" if "80" in iv else "-",
                f"{e['stockout']['model_cqr']['brier']:.4f}",
            ]
            print(f"  {side:<7}{h:>3}  " + "  ".join(f"{v:>9}" for v in row))
    bias = result["censoring"]["label_bias"]
    for side in SIDES:
        b = bias[side][str(cfg.max_horizon)]["all"]
        print(
            f"  label bias {side} {cfg.max_horizon} h: served {b['served']['relative']:+.1%}, "
            f"estimated {b['estimated']['relative']:+.1%} of true demand"
        )
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
