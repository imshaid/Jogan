"""The impact page's numbers: a projection of ``artifacts/metrics.json`` for the web app (D-025).

``python -m jogan.eval.web`` (``make impact``) copies the sections the web app shows into
``web/lib/impact.json``. Nothing is estimated here: every value is a copy of a value that
``make eval`` wrote (the only arithmetic is counting list entries), so the UI shows exactly
what the evaluation found. A test regenerates the projection and compares it with the
committed file, so a stale copy fails CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jogan.sim.config import CONFIG_DIR

ROOT = CONFIG_DIR.parent
METRICS = ROOT / "artifacts" / "metrics.json"
OUT = ROOT / "web" / "lib" / "impact.json"

BASELINES = ("fixed_round", "threshold", "safety_stock")
POLICY_METRICS = ("lost_per_1000", "lost", "requests", "runner_km", "runner_visits")
WINDOWS = ("test", "eid")
SALARY = "mid"  # the middle runner salary of the three priced (configs/ops/costs.yaml)


def _policy(row: dict) -> dict:
    out = {k: row[k] for k in POLICY_METRICS}
    out["known_cost_tk"] = row["known_cost_tk"][SALARY]
    return out


def project(m: dict[str, Any]) -> dict[str, Any]:
    """The web app's view of the evaluation report."""
    meta = m["meta"]
    value = m["comparison"]["jogan_value_tk"]
    jogan = f"jogan@{value:g}"
    versus = m["comparison"]["by_value"][f"{value:g}"]
    names = (*BASELINES, jogan, "oracle")
    return {
        "source": "artifacts/metrics.json",
        "generated_by": meta["generated_by"],
        "profile": meta["profile"],
        "seeds": meta["seeds"],
        "interval_level": meta["interval_level"],
        "windows": meta["windows"],
        "config_hashes": meta["config_hashes"],
        "lost_customer_values_tk": meta["lost_customer_values_tk"],
        "jogan_value_tk": value,
        "jogan": jogan,
        "baselines": list(BASELINES),
        "policies": {n: {w: _policy(m["policies"][n][w]) for w in WINDOWS} for n in names},
        "versus": {
            b: {
                w: {
                    "lost_per_1000": versus[b][w]["lost_per_1000"],
                    "runner_km": versus[b][w]["runner_km"],
                    "known_cost_tk": versus[b][w]["known_cost_tk"][SALARY],
                    "total_cost_tk": versus[b][w]["total_cost_tk"][SALARY],
                    "break_even": versus[b][w]["break_even_tk"][SALARY]["verdict"],
                }
                for w in WINDOWS
            }
            for b in BASELINES
        },
        "by_value": {
            v: {b: rows[b]["test"]["total_cost_tk"][SALARY] for b in BASELINES}
            for v, rows in m["comparison"]["by_value"].items()
        },
        "events": {
            kind: {
                "days": e["days"],
                "policies": {p: e["policies"][p] for p in ("fixed_round", jogan)},
                "versus_quo": e["versus"]["fixed_round"],
            }
            for kind, e in m["events"]["types"].items()
        },
        "business": {
            "agents": m["business"]["agents"],
            "versus": {b: {w: m["business"]["versus"][b][w] for w in WINDOWS} for b in BASELINES},
        },
        "ablations": {
            k: {"lost_per_1000": a["test"]["lost_per_1000"], "runner_km": a["test"]["runner_km"]}
            for k, a in m["ablations"].items()
        },
        # H1 has a verdict per baseline (in "versus") instead of one "holds"
        "hypotheses": {
            k: {"holds": h.get("holds"), "statement": h["statement"]}
            for k, h in m["hypotheses"].items()
        },
        "fairness": {
            "best_baseline": m["fairness"]["best_baseline"],
            "groups": {
                col: {
                    g: {
                        "jogan": row[jogan],
                        "best": row[m["fairness"]["best_baseline"]],
                        "difference": row["jogan_minus_best"],
                    }
                    for g, row in groups.items()
                }
                for col, groups in m["fairness"]["groups"].items()
            },
            "worse_groups": m["hypotheses"]["H4"]["worse_groups"],
        },
        "does_not_win": {
            "cases": len(m["does_not_win"]),
            "scopes": sorted({d["scope"] for d in m["does_not_win"]}),
        },
        "coverage_misses": {
            "cells": len(m["hypotheses"]["H3"]["misses"]),
            "overall": sum(x["group"] == "all=" for x in m["hypotheses"]["H3"]["misses"]),
            "by_interval": {
                str(i): sum(x["interval"] == i for x in m["hypotheses"]["H3"]["misses"])
                for i in sorted({x["interval"] for x in m["hypotheses"]["H3"]["misses"]})
            },
        },
        "oracle_gap": m["oracle_gap"]["test"]["lost_per_1000"],
        "forecast": {
            side: {
                "intervals_truth": f["24"]["intervals"]["truth"],
                "stockout": f["24"]["stockout"],
            }
            for side, f in m["forecast"]["forecast"].items()
        },
        "censoring": {
            side: m["forecast"]["censoring"]["label_bias"][side]["24"]["all"]
            for side in m["forecast"]["censoring"]["label_bias"]
        },
        "anomaly": {
            k: m["anomaly"][k]
            for k in (
                "agent_days",
                "flagged",
                "flagged_true",
                "flag_precision",
                "base_rate",
                "precision_at_k_mean",
                "windows",
                "windows_detected",
                "windows_by_pattern",
            )
        },
    }


def render(m: dict[str, Any]) -> str:
    return json.dumps(project(m), indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--metrics", type=Path, default=METRICS)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    args.out.write_text(render(json.loads(args.metrics.read_text())))
    print(f"{args.metrics} → {args.out}")


if __name__ == "__main__":
    main()
