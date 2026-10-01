"""LightGBM quantile models of the peak drain, calibrated with asymmetric CQR.

One booster per horizon, side and quantile level, trained on ``log1p`` of the peak drain:
quantiles are equivariant under monotone transforms, so back-transforming the predicted
quantile gives the quantile in Tk, and the conformal shifts become relative (large agents get
larger absolute shifts).

Calibration follows Romano, Patterson and Candès (2019, Theorem 2): each tail is shifted by
an empirical quantile of its own residuals on the calibration split, so a level ``τ`` above
the median gets ``P(y ≤ q'_τ) ≥ τ`` and one below it ``P(y ≥ q'_τ) ≥ 1 - τ``, provided the
calibration and new windows are exchangeable. Shifts are computed per agent group (setting
by size class by default), falling back to the pooled shift for small groups. Crossed
quantiles are sorted afterwards (rearrangement), which keeps every row monotone.
"""

from __future__ import annotations

import dataclasses
import math

import lightgbm as lgb
import numpy as np
import pandas as pd

from jogan.forecast.config import Conformal, LightGBM
from jogan.forecast.features import CATEGORICAL


def fit_quantiles(
    x: pd.DataFrame, y: np.ndarray, levels: tuple[float, ...], params: LightGBM
) -> list[lgb.Booster]:
    """One quantile booster per level on ``log1p(y)``."""
    cats = [c for c in CATEGORICAL if c in x.columns]
    data = lgb.Dataset(x, label=np.log1p(y), categorical_feature=cats, free_raw_data=False)
    return [
        lgb.train(params.params(q), data, num_boost_round=params.num_boost_round) for q in levels
    ]


def predict_log(boosters: list[lgb.Booster], x: pd.DataFrame) -> np.ndarray:
    """Raw predictions in log space (rows by levels), before calibration."""
    return np.column_stack([b.predict(x) for b in boosters])


def conformal_quantile(scores: np.ndarray, level: float) -> float:
    """The ``⌈(n+1)·level⌉``-th smallest score (the largest when that exceeds ``n``)."""
    n = len(scores)
    if n == 0:
        return 0.0
    k = min(math.ceil((n + 1) * level), n)
    return float(np.partition(scores, k - 1)[k - 1])


def _shifts(residual: np.ndarray, levels: tuple[float, ...]) -> np.ndarray:
    """Per-level shifts from residuals ``y - q̂`` (rows by levels)."""
    out = np.zeros(len(levels))
    for j, q in enumerate(levels):
        r = residual[:, j]
        out[j] = conformal_quantile(r, q) if q >= 0.5 else -conformal_quantile(-r, 1 - q)
    return out


def group_keys(groups: pd.DataFrame, columns: tuple[str, ...]) -> np.ndarray:
    """One string key per row from the group columns ("" when there are none)."""
    keys = pd.Series("", index=groups.index, dtype=object)
    for i, column in enumerate(columns):
        keys = keys + ("|" if i else "") + groups[column].astype(str)
    return keys.to_numpy()


@dataclasses.dataclass(frozen=True)
class Calibration:
    """Conformal shifts in log space: pooled, and per group where it has enough rows."""

    levels: tuple[float, ...]
    columns: tuple[str, ...]
    pooled: np.ndarray
    by_group: dict[str, np.ndarray]

    def apply(self, log_pred: np.ndarray, groups: pd.DataFrame) -> np.ndarray:
        keys = group_keys(groups, self.columns)
        names = list(self.by_group)
        table = np.vstack([*(self.by_group[k] for k in names), self.pooled])
        index = pd.Index(names).get_indexer(keys)  # -1 (pooled) for groups without own shifts
        return log_pred + table[index]


def calibrate(
    log_pred: np.ndarray,
    log_y: np.ndarray,
    groups: pd.DataFrame,
    levels: tuple[float, ...],
    conformal: Conformal,
) -> Calibration:
    """Asymmetric CQR shifts from the calibration split."""
    residual = log_y[:, None] - log_pred
    keys = group_keys(groups, conformal.groups)
    by_group = {}
    for key in np.unique(keys):
        pick = keys == key
        if pick.sum() >= conformal.min_group_rows:
            by_group[str(key)] = _shifts(residual[pick], levels)
    return Calibration(levels, conformal.groups, _shifts(residual, levels), by_group)


def to_tk(log_q: np.ndarray) -> np.ndarray:
    """Back to Tk: sort crossed levels, undo ``log1p``, never below zero."""
    return np.maximum(np.expm1(np.sort(log_q, axis=1)), 0.0)


@dataclasses.dataclass(frozen=True)
class QuantileModel:
    """Boosters and calibration for one horizon and side."""

    horizon: int
    side: str
    levels: tuple[float, ...]
    boosters: list[lgb.Booster]
    calibration: Calibration | None

    def predict(self, x: pd.DataFrame, groups: pd.DataFrame, calibrated: bool = True) -> np.ndarray:
        """Quantiles in Tk (rows by levels), conformal shifts applied unless told otherwise."""
        log_q = predict_log(self.boosters, x)
        if calibrated and self.calibration is not None:
            log_q = self.calibration.apply(log_q, groups)
        return to_tk(log_q)


def stockout_probability(
    quantiles: np.ndarray, levels: tuple[float, ...], balance: np.ndarray
) -> np.ndarray:
    """P(peak drain > balance) read from the quantile grid by linear interpolation.

    Below the lowest quantile the CDF falls linearly to 0 at a zero drain; above the highest,
    the remaining tail mass is halved (ASSUMPTION: the grid only says it is below
    ``1 - max(levels)``).
    """
    lv = np.asarray(levels)
    q, b = quantiles, np.asarray(balance, dtype=float)
    k = (q <= b[:, None]).sum(axis=1)
    kk = np.clip(k, 1, len(lv) - 1)
    rows = np.arange(len(b))
    lo, hi = q[rows, kk - 1], q[rows, kk]
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(hi > lo, (b - lo) / (hi - lo), 1.0)
        below = np.where(q[:, 0] > 0, lv[0] * b / q[:, 0], lv[0])
    inside = lv[kk - 1] + np.clip(frac, 0.0, 1.0) * (lv[kk] - lv[kk - 1])
    cdf = np.where(k == 0, below, np.where(k == len(lv), lv[-1] + (1 - lv[-1]) / 2, inside))
    return 1.0 - cdf
