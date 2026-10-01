"""Demand intensity: the multiplicative patterns of docs/02-data-assumptions.md §5.

The expected hourly attempts of agent ``i`` on day ``d``, hour ``h`` and side ``τ`` are

    base_i · share_iτ · territory_dayτ[d] · hat_i[d] · disruption[d] · day_noise · hours[d, h]
    · hour_noise

``territory_day`` holds every pattern shared by a territory (weekday, payday, remittance,
pre-Eid surge, Eid-day drop, cattle markets). The same functions feed the generator and the
calibration solver, so the calibrated world and the generated world cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from jogan.sim.calendar import as_float
from jogan.sim.config import WEEKDAYS, Festival, Setting, SimConfig, Territory, TxType


def festival_shape(days_to_eid: np.ndarray, fest: Festival) -> np.ndarray:
    """Pre-Eid bump in [0, 1]: peaks ``peak_days_before`` days ahead, zero beyond the ramp."""
    k = np.nan_to_num(days_to_eid, nan=np.inf)
    bump = np.exp(-(((k - fest.peak_days_before) / fest.width_days) ** 2))
    return np.where((k >= 1) & (k <= fest.ramp_days), bump, 0.0)


def eid_drop(days_since_eid: np.ndarray, fest: Festival) -> np.ndarray:
    """Volume multiplier on Eid day and the days right after it."""
    out = np.ones_like(days_since_eid, dtype=float)
    for offset, factor in enumerate(fest.eid_drop):
        out[days_since_eid == offset] = factor
    return out


def weekday_factor(cal: pd.DataFrame, cfg: SimConfig) -> np.ndarray:
    table = np.array([cfg.weekday.get(name, 1.0) for name in WEEKDAYS])
    return table[cal["weekday"].to_numpy()]


def payday_factor(day_of_month: np.ndarray, cfg: SimConfig) -> np.ndarray:
    p = cfg.payday
    bump = 1.0 + (p.peak - 1.0) * np.exp(-(((day_of_month - p.peak_day) / p.width_days) ** 2))
    return np.where(day_of_month <= p.last_day, bump, 1.0)


def remittance_factor(cal: pd.DataFrame, cfg: SimConfig) -> np.ndarray:
    r = cfg.remittance
    day = cal["day"].to_numpy()
    k = np.nan_to_num(as_float(cal["days_to_eid"]), nan=np.inf)
    month_start = np.where(day <= r.month_start.last_day, r.month_start.factor, 1.0)
    ramp = 1.0 + (r.pre_eid.peak - 1.0) * (1.0 - (k - 1.0) / r.pre_eid.days)
    pre_eid = np.where((k >= 1) & (k <= r.pre_eid.days), ramp, 1.0)
    return month_start * pre_eid


def cattle_factor(cal: pd.DataFrame, cfg: SimConfig) -> np.ndarray:
    k = np.nan_to_num(as_float(cal["days_to_eid"]), nan=np.inf)
    before_azha = (cal["next_eid"] == "azha").to_numpy() & (k >= 1) & (k <= cfg.cattle.days)
    return np.where(before_azha, cfg.cattle.factor, 1.0)


def territory_day_factors(
    cal: pd.DataFrame, cfg: SimConfig, territory: Territory, surge: Mapping[TxType, float]
) -> dict[TxType, np.ndarray]:
    """Per-day multipliers shared by every agent of a territory, for cash-out and cash-in."""
    g = festival_shape(as_float(cal["days_to_eid"]), cfg.festival)
    common = weekday_factor(cal, cfg) * eid_drop(as_float(cal["days_since_eid"]), cfg.festival)
    fest = cfg.festival
    co = common * (1.0 + surge["CO"] * fest.cash_out_weight[territory.setting] * g)
    ci = common * (1.0 + surge["CI"] * fest.cash_in_weight[territory.setting] * g)
    if "payday" in territory.patterns:
        co = co * payday_factor(cal["day"].to_numpy(), cfg)
    if "remittance" in territory.patterns:
        co = co * remittance_factor(cal, cfg)
    if "cattle" in territory.patterns:
        co = co * cattle_factor(cal, cfg)
    return {"CO": co, "CI": ci}


def ticket_scale(
    cal: pd.DataFrame, cfg: SimConfig, surge: Mapping[TxType, float]
) -> dict[TxType, np.ndarray]:
    """Per-day multiplier on ticket sizes: people withdraw and deposit more before Eid."""
    g = festival_shape(as_float(cal["days_to_eid"]), cfg.festival)
    return {side: 1.0 + surge[side] * g for side in ("CO", "CI")}


def disruption_prob(cal: pd.DataFrame, cfg: SimConfig, territory: Territory) -> np.ndarray:
    by_month = territory.disruption_prob_by_month
    return np.array([by_month.get(int(m), cfg.disruption.prob) for m in cal["month"]])


def expected_hat_factor(cfg: SimConfig, territory: Territory) -> float:
    """Average hat multiplier over the week, for a cluster with an average number of hat days."""
    if "hat" not in territory.patterns:
        return 1.0
    lo, hi = cfg.agents.hat_days_per_cluster
    return 1.0 + (cfg.hat.factor - 1.0) * (lo + hi) / 2.0 / 7.0


def mix_tilt(cfg: SimConfig, territory: Territory) -> float:
    """Log-odds tilt of the cash-out share for a territory."""
    extra = cfg.mix.remittance_tilt if "remittance" in territory.patterns else 0.0
    return cfg.mix.tilt[territory.setting] + extra


def sigmoid(x: np.ndarray | float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def opening_hours(cal: pd.DataFrame, cfg: SimConfig, setting: Setting) -> np.ndarray:
    """Boolean (days, 24) mask of the hours an agent of this setting is open."""
    hours = np.arange(24)
    open_h, close_h = cfg.agents.hours[setting]
    eid_open, eid_close = cfg.agents.eid_day_hours
    is_eid = cal["eid"].notna().to_numpy()[:, None]
    normal = (hours >= open_h) & (hours < close_h)
    eid = (hours >= eid_open) & (hours < eid_close)
    return np.where(is_eid, eid[None, :], normal[None, :])


def hour_weights(cal: pd.DataFrame, cfg: SimConfig, setting: Setting) -> np.ndarray:
    """(days, 24) share of a day's attempts in each hour; each row sums to 1."""
    hp = cfg.hour_profile
    mid = np.arange(24) + 0.5
    ramadan = cal["is_ramadan"].to_numpy()[:, None]
    friday = (cal["weekday"].to_numpy() == WEEKDAYS.index("Fri"))[:, None]

    m_weight = hp.morning.weight * np.where(ramadan, hp.ramadan.morning_factor, 1.0)
    e_weight = hp.evening.weight * np.where(ramadan, hp.ramadan.evening_factor, 1.0)
    e_centre = hp.evening.centre[setting] + np.where(ramadan, hp.ramadan.evening_shift_h, 0.0)
    morning = m_weight * np.exp(-(((mid - hp.morning.centre) / hp.morning.width) ** 2))
    evening = e_weight * np.exp(-(((mid - e_centre) / hp.evening.width) ** 2))
    weights = hp.floor + morning + evening

    fr = hp.friday
    hours = np.arange(24)
    fri_factor = np.where(hours < fr.morning_before, fr.morning_factor, 1.0)
    fri_factor = np.where(
        (hours >= fr.prayer[0]) & (hours < fr.prayer[1]), fr.prayer_factor, fri_factor
    )
    weights = weights * np.where(friday, fri_factor[None, :], 1.0)
    weights = weights * opening_hours(cal, cfg, setting)
    return weights / weights.sum(axis=1, keepdims=True)
