"""Business KPIs (D-033) and the response to Bangladesh's calendar (D-035): Jogan against baselines.

Every KPI is a paired difference over the evaluation seeds of a quantity each seed already
recorded (``jogan.eval.run.record``): failed requests, the value and the agent commission they
carried, runner km and cost, agents' own bank trips and the known cost. Each is also scaled to
**1,000 agents and 30 days** with the simulated network's agent count and the window's length,
which is the only arithmetic here. The scaled known-cost saving against the status quo is the
break-even running cost: Jogan pays for itself while running it costs less than that.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from jogan.eval.stats import mean_interval, paired

SALARY = "mid"  # the middle runner salary of the three priced (configs/ops/costs.yaml)


def _kpis(row: dict) -> dict[str, float]:
    service, ops, cost = row["service"], row["operations"], row["cost_tk"]
    return {
        "failed_requests": service["lost"],
        "value_turned_away_tk": service["lost_tk"]["CO"] + service["lost_tk"]["CI"],
        "cash_out_turned_away_tk": service["lost_tk"]["CO"],
        "agent_commission_lost_tk": cost["lost_commission"],
        "runner_km": ops["runner_km"],
        "runner_cost_tk": cost["runner_time"] + cost["runner_fuel"],
        "agents_own_bank_trips": ops["self_refills"],
        "known_cost_tk": cost["known_total_by_salary"][SALARY],
    }


def _scaled(d: dict, factor: float) -> dict:
    """A paired interval multiplied by a positive factor (the sign verdict is unchanged)."""
    scale = {k: None if d[k] is None else round(d[k] * factor, 1) for k in ("mean", "low", "high")}
    return d | scale


def business_kpis(
    seeds: list[dict], jogan: str, baselines: tuple[str, ...], windows: list[str], level: float
) -> dict[str, Any]:
    agents = {s["agents"] for s in seeds}
    if len(agents) != 1:
        raise ValueError(f"seeds disagree on the agent count: {sorted(agents)}")
    n_agents = agents.pop()
    out: dict[str, Any] = {"agents": n_agents, "salary": SALARY, "versus": {}}
    for b in baselines:
        for w in windows:
            a = [_kpis(s["policies"][jogan][w]) for s in seeds]
            z = [_kpis(s["policies"][b][w]) for s in seeds]
            days = seeds[0]["policies"][jogan][w]["window"]["days"]
            factor = 1000 / n_agents * 30 / days
            entry = {}
            for k in a[0]:
                diff = paired(np.array([r[k] for r in a]), np.array([r[k] for r in z]), level, 1)
                entry[k] = {"window": diff, "per_1000_agents_month": _scaled(diff, factor)}
            out["versus"].setdefault(b, {})[w] = {"days": days, "kpis": entry}
    return out


def events(
    seeds: list[dict], jogan: str, baselines: tuple[str, ...], window: str, level: float
) -> dict[str, Any]:
    """How each policy meets Bangladesh's calendar: per day type (``jogan.eval.run.DAY_TYPES``),
    runner visits per day and requests turned away per 1,000, and Jogan minus each baseline."""

    def rows(policy: str, kind: str) -> list[dict]:
        return [s["policies"][policy][window]["by_day_type"][kind] for s in seeds]

    kinds = list(seeds[0]["policies"][jogan][window]["by_day_type"])
    out: dict[str, Any] = {"window": window, "types": {}}
    for kind in kinds:
        entry: dict[str, Any] = {"days": rows(jogan, kind)[0]["days"], "policies": {}, "versus": {}}
        per = {}
        for p in (*baselines, jogan):
            r = rows(p, kind)
            visits = np.array([x["runner_visits"] / x["days"] for x in r], dtype=float)
            lost = np.array([x["lost_per_1000"] for x in r], dtype=float)
            trips = np.array([x["self_refills"] / x["days"] for x in r], dtype=float)
            per[p] = (visits, lost)
            entry["policies"][p] = {
                "visits_per_day": mean_interval(visits, level, 1),
                "lost_per_1000": mean_interval(lost, level, 1),
                "own_bank_trips_per_day": mean_interval(trips, level, 1),
            }
        for b in baselines:
            entry["versus"][b] = {
                "visits_per_day": paired(per[jogan][0], per[b][0], level, 1),
                "lost_per_1000": paired(per[jogan][1], per[b][1], level, 1),
            }
        out["types"][kind] = entry
    return out
