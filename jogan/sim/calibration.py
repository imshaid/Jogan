"""Calibrate the simulator to Bangladesh Bank's agent cash-in/cash-out aggregates.

Targets are DERIVED from the official figures in ``configs/calibration/`` (D-011):

- volume per agent-day: reference-month agent transactions ÷ days ÷ total agents
- cash-out/cash-in count ratio and mean ticket sizes in the reference month
- Eid-month over base-month ratios of counts and amounts, per side

The solver works on the *expected* world: every territory in the geography config with equal
agent counts, using the same factor functions as the generator. Each calibrated quantity is a
one-dimensional monotone root, found by bisection, so the result is exact and deterministic.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from jogan.sim import demand
from jogan.sim.calendar import as_float, build_calendar, month_bounds
from jogan.sim.config import TX_TYPES, CalibrationConfig, SimConfig, TxType

_GH_NODES, _GH_WEIGHTS = np.polynomial.hermite_e.hermegauss(32)
_GH_WEIGHTS = _GH_WEIGHTS / _GH_WEIGHTS.sum()


@dataclasses.dataclass(frozen=True)
class Targets:
    volume_per_agent_day: float
    co_ci_count_ratio: float
    ticket: dict[TxType, float]
    eid_count_ratio: dict[TxType, float]
    eid_amount_ratio: dict[TxType, float]


@dataclasses.dataclass(frozen=True)
class Calibrated:
    level: float  # expected daily attempts of an average agent before patterns
    mix_centre: float  # log-odds of the cash-out share before setting tilts
    surge_count: dict[TxType, float]  # pre-Eid count surge amplitude per side
    surge_ticket: dict[TxType, float]  # pre-Eid ticket-size surge amplitude per side
    ticket_mu: dict[TxType, float]  # log-normal location of ticket sizes per side

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def derive_targets(cal: CalibrationConfig) -> Targets:
    ref = cal.agent_transactions[cal.months.reference]
    base = cal.agent_transactions[cal.months.eid_base]
    eid = cal.agent_transactions[cal.months.eid]
    first, last = month_bounds(cal.months.reference)
    days = (last - first).days + 1
    million = 1e6
    return Targets(
        volume_per_agent_day=(ref.cash_out_count + ref.cash_in_count)
        / days
        / cal.agents_total.count,
        co_ci_count_ratio=ref.cash_out_count / ref.cash_in_count,
        ticket={
            "CO": ref.cash_out_amount_mtk * million / ref.cash_out_count,
            "CI": ref.cash_in_amount_mtk * million / ref.cash_in_count,
        },
        eid_count_ratio={
            "CO": eid.cash_out_count / base.cash_out_count,
            "CI": eid.cash_in_count / base.cash_in_count,
        },
        eid_amount_ratio={
            "CO": eid.cash_out_amount_mtk / base.cash_out_amount_mtk,
            "CI": eid.cash_in_amount_mtk / base.cash_in_amount_mtk,
        },
    )


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x, dtype=float) / math.sqrt(2.0)))


def capped_lognormal_mean(mu: np.ndarray | float, sigma: float, cap: float) -> np.ndarray:
    """E[min(X, cap)] for X ~ LogNormal(mu, sigma)."""
    mu = np.asarray(mu, dtype=float)
    log_cap = math.log(cap)
    below = np.exp(mu + sigma**2 / 2) * _norm_cdf((log_cap - mu - sigma**2) / sigma)
    return below + cap * (1.0 - _norm_cdf((log_cap - mu) / sigma))


def caps(cfg: SimConfig) -> dict[TxType, int]:
    limits = cfg.calibration.customer_daily_limits_tk
    return {"CO": limits.cash_out, "CI": limits.cash_in}


def _bisect(f: Callable[[float], float], target: float, lo: float, hi: float, name: str) -> float:
    """Root of an increasing function ``f(x) = target`` on [lo, hi]."""
    if not f(lo) <= target <= f(hi):
        raise ValueError(f"cannot calibrate {name}: target {target:.6g} outside reach")
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def expected_cash_out_share(centre: float, tilt: float, sigma: float) -> float:
    """E[sigmoid(centre + tilt + sigma·Z)] for standard normal Z (Gauss-Hermite)."""
    return float(np.sum(_GH_WEIGHTS * demand.sigmoid(centre + tilt + sigma * _GH_NODES)))


class ExpectedNetwork:
    """The expected reference network: equal agents in every configured territory, one year."""

    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        year = cfg.calendar.year
        self.cal = build_calendar(cfg.calendar, dt.date(year, 1, 1), dt.date(year, 12, 31))
        self.territories = cfg.geo.territories
        zero = {"CO": 0.0, "CI": 0.0}
        g = demand.festival_shape(as_float(self.cal["days_to_eid"]), cfg.festival)
        self.g = g
        fest = cfg.festival
        self.base: dict[TxType, np.ndarray] = {}  # (territories, days) factors without surge
        self.surge_weight: dict[TxType, np.ndarray] = {}  # (territories, days) surge slope
        weights = {"CO": fest.cash_out_weight, "CI": fest.cash_in_weight}
        rows = [demand.territory_day_factors(self.cal, cfg, t, zero) for t in self.territories]
        for side in TX_TYPES:
            self.base[side] = np.stack([r[side] for r in rows])
            self.surge_weight[side] = np.stack(
                [weights[side][t.setting] * g for t in self.territories]
            )
        # Agent-independent multipliers: setting volume, average hat days, expected disruptions.
        scale = np.array([cfg.agents.volume_scale[t.setting] for t in self.territories])
        hat = np.array([demand.expected_hat_factor(cfg, t) for t in self.territories])
        loss = 1.0 - cfg.disruption.demand_factor
        disruption = np.stack(
            [1.0 - loss * demand.disruption_prob(self.cal, cfg, t) for t in self.territories]
        )
        self.weight = (scale * hat)[:, None] * disruption
        self.tilt = np.array([demand.mix_tilt(cfg, t) for t in self.territories])

    def month_mask(self, month: str) -> np.ndarray:
        first, last = month_bounds(month)
        dates = self.cal["date"]
        return ((dates >= pd.Timestamp(first)) & (dates <= pd.Timestamp(last))).to_numpy()

    def shares(self, centre: float) -> dict[TxType, np.ndarray]:
        co = np.array(
            [expected_cash_out_share(centre, tilt, self.cfg.mix.agent_sigma) for tilt in self.tilt]
        )
        return {"CO": co, "CI": 1.0 - co}

    def counts(self, side: TxType, centre: float, surge: float, level: float = 1.0) -> np.ndarray:
        """(territories, days) expected attempts per agent."""
        factor = self.base[side] * (1.0 + surge * self.surge_weight[side])
        return level * self.shares(centre)[side][:, None] * self.weight * factor

    def amounts(self, side: TxType, calibrated: Calibrated) -> np.ndarray:
        count = self.counts(
            side, calibrated.mix_centre, calibrated.surge_count[side], calibrated.level
        )
        mu = calibrated.ticket_mu[side] + np.log1p(calibrated.surge_ticket[side] * self.g)
        mean = capped_lognormal_mean(mu, self.cfg.tickets.sigma[side], caps(self.cfg)[side])
        return count * mean[None, :]


def calibrate(cfg: SimConfig) -> Calibrated:
    """Solve the calibrated parameters for a config."""
    targets = derive_targets(cfg.calibration)
    net = ExpectedNetwork(cfg)
    months = cfg.calibration.months
    ref, base, eid = (net.month_mask(m) for m in (months.reference, months.eid_base, months.eid))

    def count_ratio(centre: float) -> float:
        return (
            net.counts("CO", centre, 0.0)[:, ref].sum()
            / net.counts("CI", centre, 0.0)[:, ref].sum()
        )

    centre = _bisect(count_ratio, targets.co_ci_count_ratio, -10.0, 10.0, "cash-out mix")

    per_agent_day = sum(net.counts(side, centre, 0.0)[:, ref].mean() for side in TX_TYPES)
    level = targets.volume_per_agent_day / per_agent_day

    surge_count: dict[TxType, float] = {}
    for side in TX_TYPES:

        def eid_ratio(a: float, side: TxType = side) -> float:
            c = net.counts(side, centre, a)
            return c[:, eid].sum() / c[:, base].sum()

        surge_count[side] = _bisect(eid_ratio, targets.eid_count_ratio[side], 0.0, 50.0, side)

    ticket_mu: dict[TxType, float] = {}
    for side in TX_TYPES:

        def mean_ticket(mu: float, side: TxType = side) -> float:
            sigma = cfg.tickets.sigma[side]
            return float(capped_lognormal_mean(mu, sigma, caps(cfg)[side]))

        ticket_mu[side] = _bisect(mean_ticket, targets.ticket[side], 0.0, 15.0, f"{side} ticket")

    surge_ticket: dict[TxType, float] = {}
    for side in TX_TYPES:

        def amount_ratio(b: float, side: TxType = side) -> float:
            trial = Calibrated(level, centre, surge_count, {side: b}, ticket_mu)
            amount = net.amounts(side, trial)
            return amount[:, eid].sum() / amount[:, base].sum()

        surge_ticket[side] = _bisect(
            amount_ratio, targets.eid_amount_ratio[side], 0.0, 50.0, f"{side} ticket surge"
        )

    return Calibrated(level, centre, surge_count, surge_ticket, ticket_mu)


def achieved(cfg: SimConfig, calibrated: Calibrated) -> dict[str, float]:
    """The target quantities as the calibrated expected network produces them."""
    net = ExpectedNetwork(cfg)
    months = cfg.calibration.months
    ref, base, eid = (net.month_mask(m) for m in (months.reference, months.eid_base, months.eid))
    counts = {
        side: net.counts(
            side, calibrated.mix_centre, calibrated.surge_count[side], calibrated.level
        )
        for side in TX_TYPES
    }
    amounts = {side: net.amounts(side, calibrated) for side in TX_TYPES}
    out = {
        "volume_per_agent_day": sum(counts[s][:, ref].mean() for s in TX_TYPES),
        "co_ci_count_ratio": counts["CO"][:, ref].sum() / counts["CI"][:, ref].sum(),
    }
    for side in TX_TYPES:
        out[f"ticket_{side}"] = amounts[side][:, ref].sum() / counts[side][:, ref].sum()
        out[f"eid_count_ratio_{side}"] = counts[side][:, eid].sum() / counts[side][:, base].sum()
        out[f"eid_amount_ratio_{side}"] = amounts[side][:, eid].sum() / amounts[side][:, base].sum()
    return {k: float(v) for k, v in out.items()}


def targets_flat(cal: CalibrationConfig) -> dict[str, float]:
    t = derive_targets(cal)
    out = {"volume_per_agent_day": t.volume_per_agent_day, "co_ci_count_ratio": t.co_ci_count_ratio}
    for side in TX_TYPES:
        out[f"ticket_{side}"] = t.ticket[side]
        out[f"eid_count_ratio_{side}"] = t.eid_count_ratio[side]
        out[f"eid_amount_ratio_{side}"] = t.eid_amount_ratio[side]
    return out
