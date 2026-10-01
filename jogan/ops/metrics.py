"""Outcomes and costs of an episode, from ground truth (evaluation code only).

Known cost = lost agent commission + runner fuel + runner time + idle liquidity, priced from
the sourced inputs in ``configs/ops/costs.yaml`` (D-019). The value of a customer lost after a
failed request is unknown and not priced; compare policies with
:func:`jogan.ops.costs.break_even`. Every cost is counted after the run, so a different cost
setting re-prices the same episode.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from jogan.ops import costs as pricing
from jogan.ops.config import Costs
from jogan.ops.env import LOST, SERVED_ON_RETRY, Episode

HOURS_PER_YEAR = 365 * 24  # 2026 is not a leap year


def hour_window(ep: Episode, start: dt.date | None, end: dt.date | None) -> tuple[int, int]:
    """Hour indices ``[h0, h1)`` of the dates ``start`` to ``end`` inclusive."""
    first = ep.world.config.start
    h0 = 0 if start is None else (start - first).days * 24
    h1 = ep.n_hours if end is None else ((end - first).days + 1) * 24
    if not 0 <= h0 < h1 <= ep.n_hours:
        raise ValueError(f"window {start} → {end} outside the simulated period")
    return h0, h1


def truth_hourly(ep: Episode) -> dict[str, np.ndarray]:
    """Requests and lost requests per (agent, hour) and side, by the hour of the first try."""
    n, n_hours = len(ep.ctx.agents), ep.n_hours
    cell = ep.agent * n_hours + ep.t // 3600
    lost = ep.outcome == LOST
    out = {}
    for s, side in enumerate(("co", "ci")):
        pick = ep.side == s
        for name, mask in (("req", pick), ("lost", pick & lost)):
            out[f"{name}_{side}_n"] = np.bincount(cell[mask], minlength=n * n_hours)
            out[f"{name}_{side}_tk"] = np.bincount(
                cell[mask], weights=ep.amount[mask], minlength=n * n_hours
            ).astype(np.int64)
    return {k: v.reshape(n, n_hours) for k, v in out.items()}


def _rate(lost: int, requests: int) -> float:
    return round(1000 * lost / requests, 3) if requests else 0.0


def summarize(
    ep: Episode,
    costs: Costs | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, Any]:
    """Service and cost metrics for the dates ``start`` to ``end`` (default: whole window)."""
    costs = costs or ep.ctx.ops.costs
    h0, h1 = hour_window(ep, start, end)
    hour = ep.t // 3600
    inside = (hour >= h0) & (hour < h1)
    lost = inside & (ep.outcome == LOST)

    lost_tk = {s: int(ep.amount[lost & (ep.side == i)].sum()) for i, s in enumerate(("CO", "CI"))}
    rate = pricing.commission_rate(costs)
    commission = sum(lost_tk[s] * rate[s] for s in lost_tk)

    days = ep.runner_days
    days = days[(days["day"] >= h0 // 24) & (days["day"] < h1 // 24)]
    km, n_visits = float(days["km"].sum()), int(days["visits"].sum())
    busy_min = float(days["busy_min"].sum())
    dates = ep.ctx.calendar["date"].dt.date.to_numpy()[days["day"].to_numpy(dtype=int)]
    setting_of = dict(
        zip(ep.ctx.territories["territory"], ep.ctx.territories["setting"], strict=True)
    )
    runner_setting = ep.ctx.runners["territory"].map(setting_of).to_numpy()
    fuel = 0.0
    for setting in np.unique(runner_setting):
        mine = runner_setting[days["runner"].to_numpy(dtype=int)] == setting
        tk_per_km = pricing.fuel_tk_per_km(costs, list(dates[mine]), setting)
        fuel += float((days["km"].to_numpy()[mine] * tk_per_km).sum())
    labour = busy_min * pricing.labour_tk_per_minute(costs)

    truth = ep.world.agent_truth
    need_c = costs.idle.need_days * truth["typical_co_tk"].to_numpy()[:, None]
    need_e = costs.idle.need_days * truth["typical_ci_tk"].to_numpy()[:, None]
    excess = np.maximum(ep.cash[:, h0:h1] - need_c, 0) + np.maximum(ep.efloat[:, h0:h1] - need_e, 0)
    idle = float(excess.sum()) * costs.idle.rate_per_year / HOURS_PER_YEAR

    refill_t = ep.refills["t"].to_numpy() // 3600
    agents = ep.ctx.agents
    groups = {}
    for col in ("setting", "size_class", "territory"):
        key = agents[col].astype(str).to_numpy()[ep.agent[inside]]
        req = pd.Series(1, index=key).groupby(level=0).sum()
        lst = pd.Series(ep.outcome[inside] == LOST, index=key).groupby(level=0).sum()
        groups[col] = {
            g: {
                "requests": int(req[g]),
                "lost": int(lst[g]),
                "lost_per_1000": _rate(lst[g], req[g]),
            }
            for g in req.index
        }

    # lost requests per agent-day: comparable with what agents report in surveys (D-016)
    n_agents, n_days = len(agents), (h1 - h0) // 24
    cell = ep.agent[lost] * n_days + (hour[lost] - h0) // 24
    per_agent_day = np.bincount(cell, minlength=n_agents * n_days)

    requests = int(inside.sum())
    known = commission + fuel + labour + idle
    return {
        "policy": ep.policy,
        "window": {
            "start": str(ep.world.config.start + dt.timedelta(days=h0 // 24)),
            "end": str(ep.world.config.start + dt.timedelta(days=h1 // 24 - 1)),
            "days": (h1 - h0) // 24,
        },
        "service": {
            "requests": requests,
            "lost": int(lost.sum()),
            "lost_per_1000": _rate(int(lost.sum()), requests),
            "served_on_retry": int((inside & (ep.outcome == SERVED_ON_RETRY)).sum()),
            "failed_attempts": int((inside & (ep.outcome != 1)).sum() + (lost & ep.retried).sum()),
            "lost_tk": lost_tk,
            "agent_days_with_loss_share": round(float(np.mean(per_agent_day >= 1)), 4),
            "median_lost_per_agent_day": float(np.median(per_agent_day)),
        },
        "operations": {
            "runner_visits": n_visits,
            "runner_km": round(km, 1),
            "runner_busy_hours": round(busy_min / 60, 1),
            "rejected_requests": ep.rejected,
            "self_refills": int(((refill_t >= h0) & (refill_t < h1)).sum()),
        },
        "cost_tk": {
            "lost_commission": round(commission, 2),
            "runner_fuel": round(fuel, 2),
            "runner_time": round(labour, 2),
            "idle_liquidity": round(idle, 2),
            "known_total": round(known, 2),
        },
        "groups": groups,
    }
