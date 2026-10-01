"""Forecast target: the peak cumulative drain of cash and of e-float (D-002 #3).

From a forecast origin ``t``, the cash drain after ``k`` hours is the net cash leaving the
drawer, cash-outs minus cash-ins, summed over hours ``t … t+k-1``. Its largest value inside
the window is the cash an agent must hold at ``t`` to serve every customer without a top-up;
the largest negative value is the same for e-float. P(stock-out) = P(peak drain > balance).

Served flows hide demand during a stock-out (the customer leaves), so labels built from them
are censored. :func:`demand_estimate` marks the hours in which a side was probably empty and,
with the ``impute`` strategy, lifts them to the agent's expected flow; hours the data feed
lost are filled the same way. Everything here is computed from the log after the fact, so a
real analyst could build the same labels; ground truth is only used to measure the bias.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from jogan.forecast.config import Censoring
from jogan.forecast.panel import Panel


def drain_path(net: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
    """Cumulative cash drain (agents by origins by hours) for hourly net cash outflow ``net``."""
    return net[:, origins[:, None] + np.arange(horizon)].cumsum(axis=2)


def peak_drains(path: np.ndarray, horizon: int) -> dict[str, np.ndarray]:
    """Peak cash and e-float drain over the first ``horizon`` hours of each path."""
    p = path[:, :, :horizon]
    return {"cash": np.maximum(p.max(axis=2), 0.0), "efloat": np.maximum(-p.min(axis=2), 0.0)}


def window_any(flags: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
    """Whether any hour of each window ``[t, t+horizon)`` is flagged (agents by origins)."""
    c = np.concatenate([np.zeros((flags.shape[0], 1)), flags.cumsum(axis=1)], axis=1)
    return c[:, origins + horizon] - c[:, origins] > 0


@dataclasses.dataclass(frozen=True)
class Demand:
    """Hourly demand per side as the log lets us estimate it (agents by hours)."""

    co: np.ndarray
    ci: np.ndarray
    censored_co: np.ndarray  # cash was probably empty: cash-outs under-reported
    censored_ci: np.ndarray  # e-float was probably empty: cash-ins under-reported
    expected_co: np.ndarray
    expected_ci: np.ndarray

    @property
    def net(self) -> np.ndarray:
        return self.co - self.ci

    @property
    def censored(self) -> np.ndarray:
        return self.censored_co | self.censored_ci


def mean_tickets(panel: Panel, days: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Each agent's mean served ticket per side over ``days``, pooled where it has none."""
    h0, h1 = days[0] * 24, days[1] * 24
    out = []
    for n, tk in ((panel.co_n, panel.co_tk), (panel.ci_n, panel.ci_tk)):
        count, total = n[:, h0:h1].sum(axis=1), tk[:, h0:h1].sum(axis=1)
        pooled = total.sum() / max(count.sum(), 1.0)
        out.append(np.where(count > 0, total / np.maximum(count, 1.0), pooled))
    return out[0], out[1]


def low_balance_hours(
    panel: Panel, tickets: tuple[np.ndarray, np.ndarray], k: float
) -> tuple[np.ndarray, np.ndarray]:
    """Hours whose cash (resp. e-float) at the start or end was below ``k`` mean tickets."""
    flags = []
    for balance, ticket in ((panel.cash, tickets[0]), (panel.efloat, tickets[1])):
        start = np.concatenate([np.full((panel.n_agents, 1), np.nan), balance[:, :-1]], axis=1)
        with np.errstate(invalid="ignore"):
            flags.append(np.fmin(start, balance) < k * ticket[:, None])
    return flags[0], flags[1]


def _hour_of_day_mean(flow: np.ndarray, usable: np.ndarray, days: tuple[int, int]) -> np.ndarray:
    """Mean of ``flow`` per agent and hour of day over the usable hours of ``days``."""
    h0, h1 = days[0] * 24, days[1] * 24
    w = usable[:, h0:h1].reshape(flow.shape[0], -1, 24)
    total = (flow[:, h0:h1].reshape(w.shape) * w).sum(axis=1)
    return total / np.maximum(w.sum(axis=1), 1.0)


def _day_factor(
    flow: np.ndarray,
    expected: np.ndarray,
    usable: np.ndarray,
    territory: np.ndarray,
    clip: tuple[float, float],
) -> np.ndarray:
    """Each territory's demand level per day relative to the profile, from usable hours."""
    n_days = flow.shape[1] // 24
    served = (flow * usable).reshape(-1, n_days, 24).sum(axis=2)
    base = (expected * usable).reshape(-1, n_days, 24).sum(axis=2)
    n_terr = int(territory.max()) + 1
    num, den = np.zeros((n_terr, n_days)), np.zeros((n_terr, n_days))
    np.add.at(num, territory, served)
    np.add.at(den, territory, base)
    factor = np.where(den > 0, num / np.maximum(den, 1e-9), 1.0)
    return np.clip(factor, *clip)[territory]  # agents by days


def _start_balance(panel: Panel) -> tuple[np.ndarray, np.ndarray]:
    """Cash and e-float at the start of each hour (the previous hour's end; NaN if unknown)."""
    pad = np.full((panel.n_agents, 1), np.nan)
    return (
        np.concatenate([pad, panel.cash[:, :-1]], axis=1),
        np.concatenate([pad, panel.efloat[:, :-1]], axis=1),
    )


def demand_estimate(
    panel: Panel, censoring: Censoring, profile_days: tuple[int, int], territory: np.ndarray
) -> Demand:
    """Hourly demand per side under the configured censoring strategy.

    ``profile_days`` (day indices ``[d0, d1)``, the training split) give each agent's mean
    ticket and hour-of-day profile; ``territory`` holds integer territory codes per agent.
    The profile and each territory's daily level come from *clean* hours only, whose side
    started with at least ``clean_balance_tickets`` mean tickets, because even hours that
    never ran dry lose the large tickets. Lost records are always filled with the expected
    flow. ``impute`` also lifts censored hours (``lift``: to at least the expected flow, or
    by the expected flow on top of what was served); ``ignore`` and ``drop`` keep served
    flows (``drop`` removes censored windows later).
    """
    tickets = mean_tickets(panel, profile_days)
    cens_co, cens_ci = low_balance_hours(panel, tickets, censoring.low_balance_tickets)
    start_cash, start_ef = _start_balance(panel)
    received = panel.received
    n_days = panel.n_hours // 24
    flows, expected = [], []
    sides = (
        (panel.co_tk, cens_co, start_cash, tickets[0]),
        (panel.ci_tk, cens_ci, start_ef, tickets[1]),
    )
    for flow, cens, start, ticket in sides:
        with np.errstate(invalid="ignore"):
            clean = received & (start >= censoring.clean_balance_tickets * ticket[:, None])
        profile = _hour_of_day_mean(flow, clean, profile_days)
        typical = np.tile(profile, n_days)
        level = _day_factor(flow, typical, clean, territory, censoring.day_factor_clip)
        exp = typical * np.repeat(level, 24, axis=1)
        est = np.where(received, flow, exp)
        if censoring.strategy == "impute":
            lifted = flow + exp if censoring.lift == "add" else np.maximum(flow, exp)
            est = np.where(received & cens, lifted, est)
        flows.append(est)
        expected.append(exp)
    return Demand(
        co=flows[0],
        ci=flows[1],
        censored_co=cens_co,
        censored_ci=cens_ci,
        expected_co=expected[0],
        expected_ci=expected[1],
    )
