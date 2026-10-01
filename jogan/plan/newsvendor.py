"""Newsvendor level per side and the value of a runner visit, from calibrated quantiles.

The forecast gives quantiles of the peak drain of cash and of e-float over the next hours on a
grid of levels (D-020). Between grid levels the quantile function is linear; below the lowest
level it falls linearly to zero at level 0, as :func:`jogan.forecast.model.stockout_probability`
assumes; above the highest it continues with the slope of its last segment up to level 1
(ASSUMPTION: the grid says nothing beyond its top level).

Costs per Tk, for one side over the horizon:

- **underage** (a Tk of drain the side cannot serve): the agent's lost commission per Tk plus
  the operator's value of a lost customer divided by the agent's mean ticket on that side (a
  mean ticket short counts as one lost request, ASSUMPTION);
- **overage** (a Tk held that was not needed): money idle for the horizon at the policy rate
  (``configs/ops/costs.yaml``).

A side needs the quantile at the critical ratio ``cu / (cu + co)``. A visit cannot add
liquidity, only move it between the sides (D-017), so with ``L = cash + e-float``:

- when both needs fit (``need_cash + need_efloat ≤ L``), the target cash level is the middle of
  the band of levels that meets both;
- otherwise Jogan splits the liquidity in proportion to the sides' typical outflow, as every
  baseline does (``split: typical``). The alternative, the two-sided newsvendor optimum at which
  one more Tk is worth the same on either side,
  ``cu_cash · P(D_cash > c) = cu_efloat · P(D_efloat > L - c)`` (``split: two_sided``), lost
  more requests on development seeds: the forecast's peak drain comes from hourly totals and
  misses the dips inside an hour (D-020), which a split by gross outflow keeps a buffer for
  (D-021).

A visit is worth the expected shortage cost it avoids: the cost at today's balances minus the
cost at the target, each ``cu · E[(D - balance)+]`` summed over the sides.
"""

from __future__ import annotations

import numpy as np


def _extended(q: np.ndarray, levels: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
    """The quantile grid with level 0 (drain 0) and level 1 (last slope extended) added."""
    lv = np.asarray(levels, dtype=float)
    slope = (q[:, -1] - q[:, -2]) / (lv[-1] - lv[-2])
    top = q[:, -1] + slope * (1.0 - lv[-1])
    return np.column_stack([np.zeros(len(q)), q, top]), np.concatenate([[0.0], lv, [1.0]])


def _segments(lv: np.ndarray, tau: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Segment index and position inside it for each level ``tau``."""
    j = np.clip(np.searchsorted(lv, tau, side="right") - 1, 0, len(lv) - 2)
    return j, (tau - lv[j]) / (lv[j + 1] - lv[j])


def quantile_at(q: np.ndarray, levels: tuple[float, ...], tau: np.ndarray | float) -> np.ndarray:
    """The quantile at level ``tau`` (one per row, or one for all) by linear interpolation."""
    qe, lv = _extended(q, levels)
    tau = np.clip(np.broadcast_to(np.asarray(tau, dtype=float), (len(q),)), 0.0, 1.0)
    j, frac = _segments(lv, tau)
    rows = np.arange(len(q))
    return qe[rows, j] + frac * (qe[rows, j + 1] - qe[rows, j])


def exceedance(q: np.ndarray, levels: tuple[float, ...], balance: np.ndarray) -> np.ndarray:
    """``P(D > balance)`` under the same piecewise-linear quantile function."""
    qe, lv = _extended(q, levels)
    b = np.asarray(balance, dtype=float)
    k = (qe <= b[:, None]).sum(axis=1)
    j = np.clip(k - 1, 0, len(lv) - 2)
    rows = np.arange(len(b))
    lo, hi = qe[rows, j], qe[rows, j + 1]
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(hi > lo, (b - lo) / (hi - lo), 1.0)
    cdf = lv[j] + np.clip(frac, 0.0, 1.0) * (lv[j + 1] - lv[j])
    cdf = np.where(k >= len(lv), 1.0, np.where(b < 0, 0.0, cdf))
    return 1.0 - cdf


def expected_shortfall(
    q: np.ndarray, levels: tuple[float, ...], balance: np.ndarray, points: int
) -> np.ndarray:
    """``E[(D - balance)+]`` in Tk: the quantile function averaged over ``points`` slices."""
    qe, lv = _extended(q, levels)
    j, frac = _segments(lv, (np.arange(points) + 0.5) / points)
    grid = qe[:, j] * (1.0 - frac) + qe[:, j + 1] * frac  # rows by slices
    return np.maximum(grid - np.asarray(balance, dtype=float)[:, None], 0.0).mean(axis=1)


def critical_ratio(underage: np.ndarray | float, overage: float) -> np.ndarray:
    return np.asarray(underage, dtype=float) / (np.asarray(underage, dtype=float) + overage)


def target_cash(
    q_cash: np.ndarray,
    q_efloat: np.ndarray,
    levels: tuple[float, ...],
    total: np.ndarray,
    under_cash: np.ndarray,
    under_efloat: np.ndarray,
    overage: float,
    fallback: np.ndarray | None = None,
    iterations: int = 40,
) -> dict[str, np.ndarray]:
    """Cash level to leave after a visit, the needs behind it, and whether both needs fit.

    Where the needs do not fit, the target is ``fallback`` when given, else the two-sided split.
    """
    total = np.asarray(total, dtype=float)
    need_c = quantile_at(q_cash, levels, critical_ratio(under_cash, overage))
    need_e = quantile_at(q_efloat, levels, critical_ratio(under_efloat, overage))
    fits = need_c + need_e <= total
    band = (need_c + total - need_e) / 2
    if fallback is not None:
        target = np.where(fits, band, np.clip(fallback, 0.0, total))
        return {"target": target, "need_cash": need_c, "need_efloat": need_e, "fits": fits}
    # g(c) = cu_c·P(D_c > c) - cu_e·P(D_e > L - c) falls as c grows: bisect for its zero
    lo, hi = np.zeros_like(total), total.copy()
    for _ in range(iterations):
        mid = (lo + hi) / 2
        g = under_cash * exceedance(q_cash, levels, mid) - under_efloat * exceedance(
            q_efloat, levels, total - mid
        )
        lo, hi = np.where(g > 0, mid, lo), np.where(g > 0, hi, mid)
    split = (lo + hi) / 2
    return {
        "target": np.where(fits, band, split),
        "need_cash": need_c,
        "need_efloat": need_e,
        "fits": fits,
    }


def shortage_cost(
    q_cash: np.ndarray,
    q_efloat: np.ndarray,
    levels: tuple[float, ...],
    cash: np.ndarray,
    efloat: np.ndarray,
    under_cash: np.ndarray,
    under_efloat: np.ndarray,
    points: int,
) -> np.ndarray:
    """Expected cost in Tk of the drain the two balances cannot serve over the horizon."""
    return under_cash * expected_shortfall(
        q_cash, levels, cash, points
    ) + under_efloat * expected_shortfall(q_efloat, levels, efloat, points)
