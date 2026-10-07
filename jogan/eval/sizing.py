"""Size of the problem from official figures: ``python -m jogan.eval.sizing`` (``make sizing``).

Bangladesh Bank publishes how much agents pay out and take in each month, but not how often a
customer is turned away for lack of cash or e-float. This turns the published monthly totals
into what each turned-away rate in ``configs/sizing/base.yaml`` would mean nationally: requests,
taka and agent commission. The rate itself is the unknown that step 0 of the pilot measures on
upay's logs (``docs/07-product-readiness.md``). Writes ``artifacts/sizing.json``.

Two assumptions, both in the output: a turned-away request has the month's average size, and
the published totals are the served requests only, so ``turned away = served * r / (1 - r)``
for a rate ``r`` of all attempts. A customer who comes back later is not netted out.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from jogan.ops.config import load_ops_config
from jogan.sim.config import CONFIG_DIR

ROOT = CONFIG_DIR.parent
SIZING = ROOT / "artifacts" / "sizing.json"
CALIBRATION = CONFIG_DIR / "calibration" / "bb_mfs_2026.yaml"
SIDES = {"CO": "cash_out", "CI": "cash_in"}


def _read(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def month_sizing(tx: dict[str, float], rates: list[float], commission: dict[str, float]) -> dict:
    """Served totals of one month and, per rate, what was turned away on top of them."""
    count = {s: tx[f"{name}_count"] for s, name in SIDES.items()}
    tk = {s: tx[f"{name}_amount_mtk"] * 1e6 for s, name in SIDES.items()}
    out: dict[str, Any] = {
        "served": {
            "requests": sum(count.values()),
            "tk": sum(tk.values()),
            "cash_out_requests": count["CO"],
            "cash_out_tk": tk["CO"],
        },
        "by_rate": {},
    }
    for r in rates:
        f = r / (1 - r)
        out["by_rate"][f"{r:g}"] = {
            "requests": round(f * sum(count.values())),
            "tk": round(f * sum(tk.values())),
            "cash_out_requests": round(f * count["CO"]),
            "cash_out_tk": round(f * tk["CO"]),
            "agent_commission_tk": round(sum(f * tk[s] * commission[s] / 1000 for s in tk)),
        }
    return out


def build(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    cal = _read(config_dir / "calibration" / CALIBRATION.name)
    rates = [float(r) for r in _read(config_dir / "sizing" / "base.yaml")["turned_away_rates"]]
    commission = load_ops_config(config_dir=config_dir).costs.agent_commission_per_1000_tk
    agents = cal["agents_total"]
    months = {role: cal["months"][role] for role in ("reference", "eid")}
    by_month = {
        m: month_sizing(cal["agent_transactions"][m], rates, commission) for m in months.values()
    }
    ref = by_month[months["reference"]]["served"]
    return {
        "meta": {
            "generated_by": "make sizing (python -m jogan.eval.sizing)",
            "sources": {**cal["sources"], "commission": "configs/ops/costs.yaml"},
            "assumptions": [
                "turned-away rates are a sensitivity, not a measurement",
                "a turned-away request has the month's average size",
                "published totals are served requests only (turned away = served * r / (1 - r))",
                "a customer who comes back later is not netted out",
            ],
        },
        "rates": rates,
        "months": months,
        "agents": agents,
        "requests_per_agent_month": round(ref["requests"] / agents["count"], 1),
        "commission_per_1000_tk": dict(commission),
        "by_month": by_month,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=SIZING)
    args = parser.parse_args(argv)
    body = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"  wrote {args.out}")


if __name__ == "__main__":
    main()
