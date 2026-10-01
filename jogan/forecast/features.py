"""Features at forecast origins, built only from records usable at each origin.

A feature at origin ``t`` (the start of hour ``t``) may use a record only if it arrived by
``t`` (D-018). Window sums come from prefix sums over every received record, minus the
records that were delayed and had not arrived yet; a past window counts only when every one
of its hours had arrived. The leakage test perturbs every record that arrives after ``t`` and
checks that no feature at ``t`` moves.

Feature groups:

- **agent master data:** territory, setting, size class, road km to the hub, opening hours;
- **calendar** (public, known ahead): hour, weekday, day of month (payday), Ramadan, days to
  and since Eid, bank open and holidays today and tomorrow, the agent's hat day;
- **recent served flows** per side over the last 3, 24 and 168 hours, the trend of the last
  day against the last week, and the agent's mean liquidity (cash + e-float) over the week;
- **per horizon:** open hours in the window; the agent's 28-day hour-of-day profile summed
  over the window and its peak drain; peak drains of the same window 1 and 7 days earlier;
  the median and 90th percentile of the last 28 same-hour windows.

Liquidity enters as the total only, not the current cash/e-float split: the split mostly
records when the status quo's runner came, and the forecast is of demand (D-020).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from jogan.forecast.config import SIDES, ForecastConfig
from jogan.forecast.panel import Panel
from jogan.forecast.targets import drain_path, peak_drains
from jogan.sim.config import SETTINGS
from jogan.sim.world import SIZE_CLASSES

STATIC_NUMERIC = ("hub_road_km", "open_hour", "close_hour")
CATEGORICAL = ("territory", "setting", "size_class")


def origin_grid(n_days: int, origin_hours: tuple[int, ...], max_horizon: int) -> np.ndarray:
    """Origin hours ``24·day + hour`` whose longest window ends inside the simulated period."""
    t = (np.arange(n_days)[:, None] * 24 + np.array(origin_hours)[None, :]).ravel()
    return t[t + max_horizon <= n_days * 24]


def nan_quantiles(a: np.ndarray, levels: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Quantiles along the last axis ignoring NaN (numpy's linear method), and the counts."""
    s = np.sort(a, axis=-1)  # NaN sorts last
    count = (~np.isnan(a)).sum(axis=-1)
    out = np.full((*a.shape[:-1], len(levels)), np.nan)
    for j, q in enumerate(levels):
        pos = q * np.maximum(count - 1, 0)
        lo = np.floor(pos).astype(np.int64)
        hi = np.minimum(lo + 1, np.maximum(count - 1, 0))
        v_lo = np.take_along_axis(s, lo[..., None], axis=-1)[..., 0]
        v_hi = np.take_along_axis(s, hi[..., None], axis=-1)[..., 0]
        out[..., j] = np.where(count > 0, v_lo + (pos - lo) * (v_hi - v_lo), np.nan)
    return out, count


class _Usable:
    """Sums over records usable at each origin: arrived by then, and before it."""

    def __init__(self, panel: Panel, origins: np.ndarray) -> None:
        self.panel, self.origins = panel, origins
        self.received = panel.received
        hours = np.arange(panel.n_hours)
        a, h = np.nonzero(self.received & (panel.arrive > hours[None, :] + 1))
        arrive = panel.arrive[a, h]
        # (record, origin) pairs where the record lies before the origin but arrives after it
        lo = np.searchsorted(origins, h, side="right")
        k = np.maximum(np.searchsorted(origins, arrive, side="left") - lo, 0)
        rec = np.repeat(np.arange(len(a)), k)
        step = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
        self.p_origin = np.repeat(lo, k) + step
        self.p_agent, self.p_hour = a[rec], h[rec]

    def _clean(self, x: np.ndarray) -> np.ndarray:
        return np.where(self.received, x, 0.0)

    def _pending(self, back: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pick = self.p_hour >= self.origins[self.p_origin] - back
        return self.p_origin[pick], self.p_agent[pick], self.p_hour[pick]

    def window(self, x: np.ndarray, hours: int) -> np.ndarray:
        """Sum of ``x`` over the usable records of hours ``[t - hours, t)`` (origins by agents)."""
        x = self._clean(x)
        c = np.concatenate([np.zeros((x.shape[0], 1)), x.cumsum(axis=1)], axis=1)
        t = self.origins
        s = (c[:, t] - c[:, np.maximum(t - hours, 0)]).T.copy()
        o, a, h = self._pending(hours)
        np.subtract.at(s, (o, a), x[a, h])
        return s

    def hour_of_day(self, x: np.ndarray, days: int) -> np.ndarray:
        """Sums per hour of day over the last ``days`` days before each origin (o by a by 24)."""
        x = self._clean(x)
        n, n_days = x.shape[0], x.shape[1] // 24
        c = np.concatenate([np.zeros((n, 1, 24)), x.reshape(n, n_days, 24).cumsum(axis=1)], axis=1)
        t = self.origins
        hod = np.arange(24)
        end = t[:, None] // 24 + (hod[None, :] < t[:, None] % 24)
        s = (c[:, end, hod] - c[:, np.maximum(end - days, 0), hod]).transpose(1, 0, 2).copy()
        o, a, h = self._pending(24 * days)
        np.subtract.at(s, (o, a, h % 24), x[a, h])
        return s


@dataclasses.dataclass(frozen=True)
class FeatureSet:
    """Feature rows for origins by agents (origin-major), shared and per horizon.

    ``empirical`` and ``naive`` are the statistical baselines computed on the way: the
    quantiles of the last same-hour windows (rows by levels) and the peak of the same window
    a week earlier (a day earlier when that is missing), per horizon and side.
    """

    origins: np.ndarray
    n_agents: int
    base: pd.DataFrame
    by_horizon: dict[int, pd.DataFrame]
    empirical: dict[int, dict[str, np.ndarray]]
    naive: dict[int, dict[str, np.ndarray]]

    def matrix(self, horizon: int) -> pd.DataFrame:
        return pd.concat([self.base, self.by_horizon[horizon]], axis=1)

    @property
    def origin_of_row(self) -> np.ndarray:
        return np.repeat(self.origins, self.n_agents)

    @property
    def agent_of_row(self) -> np.ndarray:
        return np.tile(np.arange(self.n_agents), len(self.origins))


def _mean(total: np.ndarray, count: np.ndarray) -> np.ndarray:
    """``total / count``, NaN where nothing was usable."""
    return np.where(count > 0.5, total / np.maximum(count, 1.0), np.nan)


def _flat(x: np.ndarray) -> np.ndarray:
    """origins by agents → one value per row."""
    return np.ascontiguousarray(x).ravel()


def _calendar(calendar: pd.DataFrame, agents: pd.DataFrame, origins: np.ndarray) -> dict:
    n_days = len(calendar)
    day = origins // 24

    def col(name: str, shift: int = 0) -> np.ndarray:
        values = calendar[name].astype("Float64").to_numpy(dtype=float, na_value=np.nan)
        return np.append(values, np.nan)[np.minimum(day + shift, n_days)]

    holiday = calendar["holiday_en"].notna().astype(float)
    calendar = calendar.assign(holiday=holiday)
    weekday = calendar["weekday"].to_numpy(dtype=np.int64)
    hat = agents["hat_mask"].to_numpy(dtype=np.int64)
    out = {
        "hour": (origins % 24).astype(float),
        "weekday": col("weekday"),
        "day_of_month": col("day"),
        "is_ramadan": col("is_ramadan"),
        "days_to_eid": col("days_to_eid"),
        "days_since_eid": col("days_since_eid"),
        "bank_open": col("bank_open"),
        "bank_open_next": col("bank_open", 1),
        "holiday": col("holiday"),
        "holiday_next": col("holiday", 1),
    }
    rows = {k: np.repeat(v, len(agents)) for k, v in out.items()}
    for name, shift in (("hat_day", 0), ("hat_day_next", 1)):
        wd = np.append(weekday, -1)[np.minimum(day + shift, n_days)]
        on = (hat[None, :] >> np.maximum(wd, 0)[:, None]) & 1
        rows[name] = _flat(np.where(wd[:, None] >= 0, on, np.nan).astype(float))
    return rows


def _static(agents: pd.DataFrame, n_origins: int) -> dict:
    cats = {
        "territory": sorted(agents["territory"].unique()),
        "setting": list(SETTINGS),
        "size_class": list(SIZE_CLASSES),
    }
    rows = {}
    for name in CATEGORICAL:
        values = np.tile(agents[name].astype(str).to_numpy(), n_origins)
        rows[name] = pd.Categorical(values, categories=cats[name])
    for name in STATIC_NUMERIC:
        rows[name] = np.tile(agents[name].to_numpy(dtype=float), n_origins)
    return rows


def _recent(use: _Usable, panel: Panel, hours: tuple[int, ...]) -> dict:
    ones = np.ones(panel.co_tk.shape)
    rows, means = {}, {}
    for w in hours:
        count = use.window(ones, w)
        for side, x in (("co", panel.co_tk), ("ci", panel.ci_tk)):
            means[side, w] = _mean(use.window(x, w), count)
            rows[f"{side}_{w}h"] = _flat(means[side, w] * w)
    week, day = max(hours), min((h for h in hours if h >= 24), default=max(hours))
    for side in ("co", "ci"):
        with np.errstate(invalid="ignore", divide="ignore"):
            rows[f"{side}_trend"] = _flat(means[side, day] / means[side, week])
    liquidity = panel.cash + panel.efloat
    rows["liquidity"] = _flat(_mean(use.window(liquidity, week), use.window(ones, week)))
    return rows


def _profile(use: _Usable, panel: Panel, agents: pd.DataFrame, cfg: ForecastConfig) -> dict:
    """Per horizon: open hours, and the hour-of-day profile's window sums and peak drains."""
    days = cfg.features.profile_days
    count = use.hour_of_day(np.ones(panel.co_tk.shape), days)
    mean_co = _mean(use.hour_of_day(panel.co_tk, days), count)
    mean_ci = _mean(use.hour_of_day(panel.ci_tk, days), count)
    del count
    h_max = cfg.max_horizon
    hods = (use.origins[:, None] + np.arange(h_max)) % 24  # origins by hours ahead
    idx = np.broadcast_to(hods[:, None, :], (len(use.origins), panel.n_agents, h_max))
    co = np.take_along_axis(mean_co, idx, axis=2).cumsum(axis=2)
    ci = np.take_along_axis(mean_ci, idx, axis=2).cumsum(axis=2)
    del mean_co, mean_ci
    path = co - ci
    open_h, close_h = agents["open_hour"].to_numpy(), agents["close_hour"].to_numpy()
    is_open = (idx >= open_h[None, :, None]) & (idx < close_h[None, :, None])
    open_hours = is_open.cumsum(axis=2)
    out = {}
    for h in cfg.horizons_hours:
        p = path[:, :, :h]
        out[h] = {
            "open_hours": _flat(open_hours[:, :, h - 1].astype(float)),
            "prof_co": _flat(co[:, :, h - 1]),
            "prof_ci": _flat(ci[:, :, h - 1]),
            "prof_peak_cash": _flat(np.maximum(p.max(axis=2), 0.0)),
            "prof_peak_efloat": _flat(np.maximum(-p.min(axis=2), 0.0)),
        }
    return out


def _past_windows(
    panel: Panel, origins: np.ndarray, cfg: ForecastConfig
) -> tuple[dict, dict, dict]:
    """Peak drains of earlier windows at the same hour, where every hour had arrived by ``t``.

    Returns per-horizon feature columns, the empirical-quantile baseline and the seasonal
    naive baseline.
    """
    fc = cfg.features
    back = np.arange(1, max(fc.history_windows, *fc.lag_days) + 1)
    starts_all = origins[:, None] - 24 * back[None, :]  # origins by days back
    starts = np.unique(starts_all[starts_all >= 0])
    h_max = cfg.max_horizon
    span = starts[:, None] + np.arange(h_max)
    net = panel.co_tk - panel.ci_tk  # served flows, lost records count as 0 until checked
    path = drain_path(net, starts, h_max)  # agents by starts by hours
    complete = np.maximum.accumulate(panel.arrive[:, span], axis=2)  # last arrival so far
    pos = np.searchsorted(starts, np.maximum(starts_all, 0))
    valid = starts_all >= 0
    feats, empirical, naive = {}, {}, {}
    for h in cfg.horizons_hours:
        peaks = peak_drains(path, h)
        ready = complete[:, :, h - 1]  # agents by starts
        # origins by agents by days back; NaN where the window is not usable at the origin
        ok = valid[:, None, :] & (ready[:, pos].transpose(1, 0, 2) <= origins[:, None, None])
        cols, empirical[h], naive[h] = {}, {}, {}
        for side in SIDES:
            past = np.where(ok, peaks[side][:, pos].transpose(1, 0, 2), np.nan)
            for k in fc.lag_days:
                cols[f"lag{k}_peak_{side}"] = _flat(past[:, :, k - 1])
            q, n_win = nan_quantiles(past[:, :, : fc.history_windows], cfg.quantiles)
            q = q.reshape(-1, len(cfg.quantiles))
            empirical[h][side] = q
            levels = list(cfg.quantiles)
            cols[f"hist_q50_{side}"] = q[:, levels.index(0.5)] if 0.5 in levels else np.nan
            cols[f"hist_q90_{side}"] = q[:, levels.index(0.9)] if 0.9 in levels else np.nan
            week = past[:, :, 6] if past.shape[2] >= 7 else np.full(past.shape[:2], np.nan)
            naive[h][side] = _flat(np.where(np.isnan(week), past[:, :, 0], week))
        cols["hist_windows"] = _flat(n_win.astype(float))
        feats[h] = cols
    return feats, empirical, naive


def build_features(
    panel: Panel,
    calendar: pd.DataFrame,
    agents: pd.DataFrame,
    cfg: ForecastConfig,
    origins: np.ndarray,
) -> FeatureSet:
    """Features for every origin and agent; inputs are the observed panel and public tables."""
    origins = np.asarray(origins, dtype=np.int64)
    if (np.diff(origins) <= 0).any():
        raise ValueError("origins must be strictly increasing")
    use = _Usable(panel, origins)
    base = {
        **_static(agents, len(origins)),
        **_calendar(calendar, agents, origins),
        **_recent(use, panel, cfg.features.recent_hours),
    }
    profile = _profile(use, panel, agents, cfg)
    past, empirical, naive = _past_windows(panel, origins, cfg)
    by_horizon = {h: pd.DataFrame({**profile[h], **past[h]}) for h in cfg.horizons_hours}
    return FeatureSet(
        origins=origins,
        n_agents=panel.n_agents,
        base=pd.DataFrame(base),
        by_horizon=by_horizon,
        empirical=empirical,
        naive=naive,
    )
