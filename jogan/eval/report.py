"""Aggregate the per-seed records into ``artifacts/metrics.json``.

Sections:

- ``forecast``: every scalar score of :func:`jogan.forecast.backtest.evaluate`, averaged over
  seeds (reliability bins are kept per seed only);
- ``policies``: each policy's service, operations and known cost per window, with intervals;
- ``comparison``: Jogan at each lost-customer value against each baseline, paired over seeds:
  lost requests, runner km, known cost, total cost at that value for the low, middle and high
  salary, and the break-even value with Fieller's interval (D-019);
- ``ablations`` and ``oracle_gap``: Jogan against its own variants and the upper bound;
- ``fairness``: lost requests per 1,000 by agent group against the best baseline;
- ``hypotheses``: H1-H4 of ``docs/01-logic-chain.md`` §6, each with what decided it;
- ``does_not_win``: every baseline, period, agent group and cost setting in which a baseline
  does as well or better, or the difference is not significant (D-019);
- ``anomaly``: the advisory anomaly flag on the test window, per seed and pooled over seeds:
  precision at k (per seed, then averaged), flags and their precision, and how many injected
  anomaly windows got at least one flag, by pattern (D-023).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from jogan.eval.business import business_kpis, events
from jogan.eval.run import ABLATIONS, jogan_key
from jogan.eval.stats import break_even, mean_interval, paired
from jogan.ops.policies import BASELINES, UPPER_BOUND

COVERAGE_TOLERANCE = 0.05  # H3: within ±5 percentage points of nominal (logic chain §6)
SALARIES = ("low", "mid", "high")
GROUP_COLUMNS = ("setting", "size_class", "territory")


def mean_tree(trees: list[Any]) -> Any:
    """Average numeric leaves over seeds; lists are dropped, other leaves kept from the first."""
    first = trees[0]
    if isinstance(first, dict):
        keys = [k for k in first if all(isinstance(t, dict) and k in t for t in trees)]
        out = {k: mean_tree([t[k] for t in trees]) for k in keys}
        return {k: v for k, v in out.items() if v is not None}
    if isinstance(first, bool) or not isinstance(first, int | float):
        return None if isinstance(first, list) else first
    return round(float(np.mean([float(t) for t in trees])), 4)


class Records:
    """Per-seed values of one policy and window, as arrays over seeds."""

    def __init__(self, seeds: list[dict], policy: str, window: str) -> None:
        self.rows = [s["policies"][policy][window] for s in seeds]

    def service(self, name: str) -> np.ndarray:
        return np.array([r["service"][name] for r in self.rows], dtype=float)

    def operations(self, name: str) -> np.ndarray:
        return np.array([r["operations"][name] for r in self.rows], dtype=float)

    def lost_tk(self, side: str | None = None) -> np.ndarray:
        """Value of the lost requests: cash-out (``CO``), cash-in (``CI``) or both."""
        sides = (side,) if side else ("CO", "CI")
        return np.array([sum(r["service"]["lost_tk"][x] for x in sides) for r in self.rows])

    def known(self, salary: str = "mid") -> np.ndarray:
        return np.array([r["cost_tk"]["known_total_by_salary"][salary] for r in self.rows])

    def cost(self, name: str) -> np.ndarray:
        return np.array([r["cost_tk"][name] for r in self.rows], dtype=float)

    def total(self, value_tk: float, salary: str = "mid") -> np.ndarray:
        """Known cost plus ``value_tk`` per lost request."""
        return self.known(salary) + value_tk * self.service("lost")

    def group_rate(self, column: str, group: str) -> np.ndarray:
        return np.array([r["groups"][column][group]["lost_per_1000"] for r in self.rows])


def policy_table(seeds: list[dict], names: list[str], windows: list[str], level: float) -> dict:
    out: dict[str, Any] = {}
    for name in names:
        for w in windows:
            r = Records(seeds, name, w)
            entry = {
                "lost_per_1000": mean_interval(r.service("lost_per_1000"), level, 3),
                "lost": mean_interval(r.service("lost"), level, 1),
                "requests": mean_interval(r.service("requests"), level, 1),
                "runner_visits": mean_interval(r.operations("runner_visits"), level, 1),
                "runner_km": mean_interval(r.operations("runner_km"), level, 1),
                "runner_busy_hours": mean_interval(r.operations("runner_busy_hours"), level, 1),
                "self_refills": mean_interval(r.operations("self_refills"), level, 1),
                "lost_tk": mean_interval(r.lost_tk(), level, 0),
                "lost_cash_out_tk": mean_interval(r.lost_tk("CO"), level, 0),
                "agent_days_with_loss_share": mean_interval(
                    r.service("agent_days_with_loss_share"), level, 4
                ),
                "known_cost_tk": {s: mean_interval(r.known(s), level, 1) for s in SALARIES},
                "cost_tk": {
                    c: mean_interval(r.cost(c), level, 1)
                    for c in ("lost_commission", "runner_fuel", "runner_time", "idle_liquidity")
                },
            }
            out.setdefault(name, {})[w] = entry
    return out


def compare(a: Records, b: Records, value_tk: float, level: float) -> dict:
    """Policy A against B, paired over seeds; positive differences mean A is higher."""
    return {
        "lost_per_1000": paired(a.service("lost_per_1000"), b.service("lost_per_1000"), level, 3),
        "lost": paired(a.service("lost"), b.service("lost"), level, 1),
        "runner_km": paired(a.operations("runner_km"), b.operations("runner_km"), level, 1),
        "self_refills": paired(
            a.operations("self_refills"), b.operations("self_refills"), level, 1
        ),
        "known_cost_tk": {s: paired(a.known(s), b.known(s), level, 1) for s in SALARIES},
        "total_cost_tk": {
            s: paired(a.total(value_tk, s), b.total(value_tk, s), level, 1) for s in SALARIES
        },
        "break_even_tk": {
            s: break_even(a.known(s), a.service("lost"), b.known(s), b.service("lost"), level)
            for s in SALARIES
        },
    }


def _not_better(diff: dict) -> str | None:
    """Why a lower-is-better difference (Jogan minus baseline) is no win, else ``None``."""
    if diff["mean"] is not None and diff["mean"] >= 0:
        return "baseline as good or better"
    if diff["high"] is None or diff["high"] >= 0:
        return "no significant difference"
    return None


def build_report(
    seeds: list[dict], values: tuple[float, ...], default_tk: float, level: float
) -> dict:
    windows = list(seeds[0]["windows"])
    jogan = jogan_key(default_tk)
    names = [*BASELINES, UPPER_BOUND, *(jogan_key(v) for v in values)]
    names += [jogan_key(default_tk, a) for a in ABLATIONS]
    midday_key = jogan_key(default_tk, "midday")
    names += [midday_key]
    policies = policy_table(seeds, names, windows, level)

    comparison: dict[str, Any] = {}
    for v in values:
        for base in BASELINES:
            for w in windows:
                entry = compare(Records(seeds, jogan_key(v), w), Records(seeds, base, w), v, level)
                comparison.setdefault(f"{v:g}", {}).setdefault(base, {})[w] = entry

    test = windows[0]
    j = Records(seeds, jogan, test)
    ablations = {
        a: {
            w: compare(
                Records(seeds, jogan, w),
                Records(seeds, jogan_key(default_tk, a), w),
                default_tk,
                level,
            )
            for w in windows
        }
        for a in ABLATIONS
    }
    oracle = {
        w: compare(Records(seeds, jogan, w), Records(seeds, UPPER_BOUND, w), default_tk, level)
        for w in windows
    }
    # the midday check (D-036): the variant minus Jogan, and minus the status quo
    midday: dict[str, Any] = {
        "key": midday_key,
        "visits_per_seed": mean_interval(
            [s["jogan_diagnostics"][midday_key]["midday_visits"] for s in seeds], level, 1
        ),
    }
    for w in windows:
        m = Records(seeds, midday_key, w)
        midday[w] = {
            "vs_jogan": compare(m, Records(seeds, jogan, w), default_tk, level)
            | {
                "runner_visits": paired(
                    m.operations("runner_visits"),
                    Records(seeds, jogan, w).operations("runner_visits"),
                    level,
                    1,
                )
            },
            "vs_status_quo": compare(m, Records(seeds, BASELINES[0], w), default_tk, level),
        }

    best = min(BASELINES, key=lambda b: Records(seeds, b, test).service("lost_per_1000").mean())
    fairness: dict[str, Any] = {"best_baseline": best, "groups": {}}
    groups = seeds[0]["policies"][jogan][test]["groups"]
    for col in GROUP_COLUMNS:
        for g in sorted(groups[col]):
            row = {
                name: mean_interval(Records(seeds, name, test).group_rate(col, g), level, 3)
                for name in (jogan, *BASELINES)
            }
            row["jogan_minus_best"] = paired(
                j.group_rate(col, g), Records(seeds, best, test).group_rate(col, g), level, 3
            )
            fairness["groups"].setdefault(col, {})[g] = row

    does_not_win = _does_not_win(seeds, values, windows, level, comparison)
    forecast = mean_tree([s["forecast"] for s in seeds])
    hypotheses = _hypotheses(seeds, comparison, fairness, forecast, default_tk, best, level)
    return {
        "policies": policies,
        "comparison": {"jogan_value_tk": default_tk, "by_value": comparison},
        "ablations": ablations,
        "oracle_gap": oracle,
        "fairness": fairness,
        "hypotheses": hypotheses,
        "does_not_win": does_not_win,
        "forecast": forecast,
        "anomaly": anomaly_summary([s["anomaly"] for s in seeds]),
        "business": business_kpis(seeds, jogan, BASELINES, windows, level),
        "events": events(seeds, jogan, BASELINES, test, level),
        "midday": midday,
    }


def _mean_known(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(float(np.mean(known)), 4) if known else None


def anomaly_summary(per_seed: list[dict]) -> dict:
    """Pooled counts over seeds, precision at k averaged over seeds (the base rate is tiny)."""
    total = {k: sum(s[k] for s in per_seed) for k in
             ("agent_days", "anomalous_agent_days", "flagged", "flagged_true", "windows",
              "windows_detected")}  # fmt: skip
    patterns = sorted({p for s in per_seed for p in s["windows_by_pattern"]})
    by_pattern = {
        p: {
            "detected": sum(s["windows_by_pattern"].get(p, [0, 0])[0] for s in per_seed),
            "windows": sum(s["windows_by_pattern"].get(p, [0, 0])[1] for s in per_seed),
        }
        for p in patterns
    }
    ks = list(per_seed[0]["precision_at_k"])
    return {
        **total,
        "base_rate": round(total["anomalous_agent_days"] / max(total["agent_days"], 1), 4),
        "flag_precision": round(total["flagged_true"] / total["flagged"], 4)
        if total["flagged"]
        else None,
        "window_recall": round(total["windows_detected"] / total["windows"], 4)
        if total["windows"]
        else None,
        "precision_at_k_mean": {
            k: _mean_known([s["precision_at_k"][k] for s in per_seed]) for k in ks
        },
        "windows_by_pattern": by_pattern,
        # injected split cash-outs served (a turned-away one is never logged), pooled (D-032)
        "split_served": [sum(s["split_served"][i] for s in per_seed) for i in (0, 1)],
        "per_seed": per_seed,
    }


def _does_not_win(seeds, values, windows, level, comparison) -> list[dict]:
    out = []
    test = windows[0]
    for v in values:
        for base in BASELINES:
            for w in windows:
                c = comparison[f"{v:g}"][base][w]
                if why := _not_better(c["lost_per_1000"]):
                    out.append(
                        {
                            "jogan_value_tk": v,
                            "baseline": base,
                            "scope": "period",
                            "period": w,
                            "metric": "lost_per_1000",
                            "why": why,
                            "difference": c["lost_per_1000"],
                        }
                    )
                for s in SALARIES:
                    if w == test and (why := _not_better(c["total_cost_tk"][s])):
                        out.append(
                            {
                                "jogan_value_tk": v,
                                "baseline": base,
                                "scope": "cost setting",
                                "salary": s,
                                "metric": "total_cost_tk",
                                "why": why,
                                "difference": c["total_cost_tk"][s],
                            }
                        )
            j = Records(seeds, jogan_key(v), test)
            b = Records(seeds, base, test)
            groups = seeds[0]["policies"][base][test]["groups"]
            for col in GROUP_COLUMNS:
                for g in sorted(groups[col]):
                    d = paired(j.group_rate(col, g), b.group_rate(col, g), level, 3)
                    if why := _not_better(d):
                        out.append(
                            {
                                "jogan_value_tk": v,
                                "baseline": base,
                                "scope": "agent group",
                                "column": col,
                                "group": g,
                                "metric": "lost_per_1000",
                                "why": why,
                                "difference": d,
                            }
                        )
    return out


def _coverage_misses(forecast: dict) -> list[dict]:
    misses = []
    for side, by_h in forecast["forecast"].items():
        for h, e in by_h.items():
            cells = [("all", "", e["intervals"]["truth"])]
            for col, by_g in e["groups"].items():
                cells += [(col, g, x["intervals_truth"]) for g, x in by_g.items()]
            for col, g, intervals in cells:
                for nominal, iv in intervals.items():
                    gap = iv["coverage"] - int(nominal) / 100
                    if abs(gap) > COVERAGE_TOLERANCE:
                        misses.append(
                            {
                                "side": side,
                                "horizon_h": int(h),
                                "group": f"{col}={g}",
                                "interval": int(nominal),
                                "coverage": iv["coverage"],
                            }
                        )
    return misses


def _hypotheses(seeds, comparison, fairness, forecast, default_tk, best, level) -> dict:
    by_value = comparison[f"{default_tk:g}"]
    h1 = {}
    for base in BASELINES:
        c = by_value[base]["test"]
        h1[base] = {
            "known_cost_tk": c["known_cost_tk"]["mid"],
            "lost": c["lost"],
            "break_even_tk": c["break_even_tk"]["mid"],
        }
    test = next(iter(seeds[0]["windows"]))
    vs_best = by_value[best][test]
    fewer = vs_best["lost_per_1000"]["sign"] == "lower"
    km_ok = vs_best["runner_km"]["mean"] <= 0
    misses = _coverage_misses(forecast)
    worse = [
        f"{col}={g}"
        for col, by_g in fairness["groups"].items()
        for g, row in by_g.items()
        if row["jogan_minus_best"]["sign"] == "higher"
    ]
    return {
        "H1": {
            "statement": "cheaper at every value, or break-even reported with an interval",
            "jogan_value_tk": default_tk,
            "by_baseline": h1,
        },
        "H2": {
            "statement": "fewer failed requests than the best baseline without more runner km",
            "best_baseline": best,
            "holds": bool(fewer and km_ok),
            "lost_per_1000": vs_best["lost_per_1000"],
            "runner_km": vs_best["runner_km"],
        },
        "H3": {
            "statement": "interval coverage within ±5 points of nominal, overall and by group",
            "holds": not misses,
            "misses": misses,
        },
        "H4": {
            "statement": "no agent group significantly worse served than under the best baseline",
            "best_baseline": best,
            "holds": not worse,
            "worse_groups": worse,
        },
    }
