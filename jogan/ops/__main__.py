"""Run policies on a simulated world: ``python -m jogan.ops --profile dev --seed 0``.

``--policy all`` compares every baseline; ``--write`` also writes the observation log and
ground truth (``make history`` does this for the status quo, the log M4 trains on).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from jogan.ops.env import simulate
from jogan.ops.io import ops_dir, write_episode, write_summary
from jogan.ops.metrics import summarize
from jogan.ops.policies import BASELINES, STATUS_QUO, make_policy
from jogan.sim.config import load_config
from jogan.sim.io import DATA_DIR
from jogan.sim.world import build_world

COLUMNS = ("lost/1000", "lost", "visits", "km", "refills", "runner ৳", "total ৳", "sec")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m jogan.ops", description=__doc__)
    parser.add_argument("--profile", default="dev", help="configs/sim/<profile>.yaml")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--policy", default=STATUS_QUO, help=f"one of {BASELINES} or 'all'")
    parser.add_argument("--write", action="store_true", help="also write obs/ and truth/ logs")
    parser.add_argument("--root", type=Path, default=DATA_DIR, help="data root (default data/)")
    args = parser.parse_args(argv)

    names = BASELINES if args.policy == "all" else (args.policy,)
    cfg = load_config(args.profile)
    world = build_world(cfg, args.seed)
    print(f"{cfg.name} seed {args.seed}: {len(world.agents)} agents, {cfg.n_days} days")
    print(f"  {'policy':<13}" + "".join(f"{c:>11}" for c in COLUMNS))
    for name in names:
        started = time.perf_counter()
        ep = simulate(world, make_policy(name, world))
        seconds = time.perf_counter() - started
        out = ops_dir(args.profile, args.seed, name, args.root)
        files = write_episode(ep, out) if args.write else [write_summary(ep, out)]
        s = summarize(ep)
        sv, op, cost = s["service"], s["operations"], s["cost_tk"]
        row = (
            f"{sv['lost_per_1000']:.1f}",
            f"{sv['lost']:,}",
            f"{op['runner_visits']:,}",
            f"{op['runner_km']:,.0f}",
            f"{op['self_refills']:,}",
            f"{cost['runner']:,.0f}",
            f"{cost['total']:,.0f}",
            f"{seconds:.1f}",
        )
        print(f"  {name:<13}" + "".join(f"{v:>11}" for v in row))
    print(f"  wrote {len(files)} file(s) per policy under {out.parent}")


if __name__ == "__main__":
    main()
