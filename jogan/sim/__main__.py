"""Generate a world: ``python -m jogan.sim --profile dev --seed 0``."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from jogan.sim.config import load_config
from jogan.sim.io import DATA_DIR, world_dir, write_world
from jogan.sim.world import build_world


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m jogan.sim", description=__doc__)
    parser.add_argument("--profile", default="dev", help="configs/sim/<profile>.yaml")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--out", type=Path, help="output folder (default data/<profile>/seed<seed>)"
    )
    args = parser.parse_args(argv)

    started = time.perf_counter()
    cfg = load_config(args.profile)
    world = build_world(cfg, args.seed)
    out = args.out or world_dir(args.profile, args.seed, DATA_DIR)
    files = write_world(world, out)
    seconds = time.perf_counter() - started

    d = world.demand
    per_day = len(d) / len(world.agents) / cfg.n_days
    sides = d["tx_type"].value_counts()
    print(f"{cfg.name} seed {args.seed} · config {cfg.config_hash()} · {seconds:.1f} s → {out}")
    print(
        f"  {len(world.territories)} territories, {len(world.agents)} agents, "
        f"{len(world.runners)} runners, {cfg.n_days} days ({cfg.start} → {cfg.end})"
    )
    print(
        f"  {len(d):,} attempts ({per_day:.1f} per agent-day), "
        f"cash-out/cash-in {sides['CO'] / sides['CI']:.2f}, "
        f"{len(world.anomalies)} anomalous agents, "
        f"{len(world.disruptions)} disrupted territory-days"
    )
    print(f"  {len(files)} files written")


if __name__ == "__main__":
    main()
