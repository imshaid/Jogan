"""Run policies on a simulated world: ``python -m jogan.ops --profile dev --seed 0``.

``--policy all`` runs the three baselines and the oracle, and prints for each the break-even
value per lost customer against the status quo (D-019). ``--write`` also writes the
observation log and ground truth (``make history`` does this for the status quo, the log M4
trains on).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from jogan.ops.costs import break_even
from jogan.ops.env import simulate
from jogan.ops.io import ops_dir, write_episode, write_summary
from jogan.ops.metrics import summarize
from jogan.ops.policies import POLICIES, STATUS_QUO, make_policy
from jogan.sim.config import load_config
from jogan.sim.io import DATA_DIR
from jogan.sim.world import build_world

COLUMNS = ("lost/1000", "lost", "visits", "km", "fuel ৳", "time ৳", "known ৳", "sec")


def _break_even_text(summary: dict, base: dict) -> str:
    """How the policy compares with the status quo once a lost customer has a value."""
    if summary["policy"] == base["policy"]:
        return "status quo"
    result = break_even(
        summary["cost_tk"]["known_total"],
        summary["service"]["lost"],
        base["cost_tk"]["known_total"],
        base["service"]["lost"],
    )
    value, cheaper = result["value_tk"], result["cheaper"]
    if value is None:
        return {"a": "cheaper", "b": "dearer"}.get(cheaper, "same") + " at every value"
    return (
        f"cheaper if a lost customer is worth {'>' if cheaper == 'a above' else '<'} ৳{value:,.2f}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m jogan.ops", description=__doc__)
    parser.add_argument("--profile", default="dev", help="configs/sim/<profile>.yaml")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--policy", default=STATUS_QUO, help=f"one of {POLICIES} or 'all'")
    parser.add_argument("--write", action="store_true", help="also write obs/ and truth/ logs")
    parser.add_argument("--root", type=Path, default=DATA_DIR, help="data root (default data/)")
    args = parser.parse_args(argv)

    names = POLICIES if args.policy == "all" else (args.policy,)
    cfg = load_config(args.profile)
    world = build_world(cfg, args.seed)
    print(f"{cfg.name} seed {args.seed}: {len(world.agents)} agents, {cfg.n_days} days")
    print(f"  {'policy':<13}" + "".join(f"{c:>11}" for c in COLUMNS) + "   vs status quo")
    summaries = {}
    for name in names:
        started = time.perf_counter()
        ep = simulate(world, make_policy(name, world))
        seconds = time.perf_counter() - started
        out = ops_dir(args.profile, args.seed, name, args.root)
        files = write_episode(ep, out) if args.write else [write_summary(ep, out)]
        s = summaries[name] = summarize(ep)
        sv, op, cost = s["service"], s["operations"], s["cost_tk"]
        row = (
            f"{sv['lost_per_1000']:.1f}",
            f"{sv['lost']:,}",
            f"{op['runner_visits']:,}",
            f"{op['runner_km']:,.0f}",
            f"{cost['runner_fuel']:,.0f}",
            f"{cost['runner_time']:,.0f}",
            f"{cost['known_total']:,.0f}",
            f"{seconds:.1f}",
        )
        versus = _break_even_text(s, summaries[STATUS_QUO]) if STATUS_QUO in summaries else ""
        print(f"  {name:<13}" + "".join(f"{v:>11}" for v in row) + f"   {versus}")
    print(f"  wrote {len(files)} file(s) per policy under {out.parent}")


if __name__ == "__main__":
    main()
