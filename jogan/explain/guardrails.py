"""Guardrails: when a recommendation needs a human's closer look (manual review).

The model proposes; every visit is approved or rejected by a person anyway. A guardrail marks
the cases where the evidence itself is weak, so the approver must write a note to approve
(``supabase/migrations/``, D-023):

- ``out_of_range``: one of the agent's own amounts (``range_features``) lies outside the range
  seen in training. Trees do not extrapolate, so the forecast flattens there.
- ``wide_interval``: the 90% quantile of the side at risk is many times its median (low
  confidence).
- ``data_gap``: too few of the agent's last 24 hourly records had arrived at the plan hour.
- ``short_history``: too few past same-hour windows behind the features.
- ``anomaly``: the advisory anomaly flag fired on the agent's last scored day.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from jogan.explain.config import Guardrails
from jogan.explain.drivers import feature_value

MAX_RANGE_REASONS = 3


@dataclasses.dataclass(frozen=True)
class TrainingRange:
    """Per numeric feature, the smallest and largest value in the training rows."""

    columns: tuple[str, ...]
    low: np.ndarray
    high: np.ndarray

    @classmethod
    def fit(cls, x: pd.DataFrame, columns: tuple[str, ...]) -> TrainingRange:
        missing = sorted(set(columns) - set(x.columns))
        if missing:
            raise ValueError(f"range features not among the forecast features: {missing}")
        values = x[list(columns)].to_numpy(dtype=float)
        if np.isnan(values).all(axis=0).any():
            raise ValueError("a range feature has no value in the training rows")
        return cls(tuple(columns), np.nanmin(values, axis=0), np.nanmax(values, axis=0))

    def outside(self, x: pd.DataFrame) -> list[list[dict]]:
        """Per row, the features out of range, the farthest (relative to the range) first."""
        values = x[list(self.columns)].to_numpy(dtype=float)
        span = np.maximum(self.high - self.low, 1e-9)
        with np.errstate(invalid="ignore"):
            excess = np.maximum(self.low - values, values - self.high) / span
        out = []
        for i in range(len(values)):
            hits = np.flatnonzero(excess[i] > 0)
            hits = hits[np.argsort(-excess[i, hits], kind="stable")][:MAX_RANGE_REASONS]
            out.append(
                [
                    {
                        "code": "out_of_range",
                        "feature": self.columns[j],
                        "value": feature_value(values[i, j]),
                        "low": feature_value(self.low[j]),
                        "high": feature_value(self.high[j]),
                    }
                    for j in hits
                ]
            )
        return out


def arrived_share(available: np.ndarray) -> np.ndarray:
    """Share of each agent's records (rows of a boolean agents-by-hours mask) that arrived."""
    return available.mean(axis=1) if available.shape[1] else np.ones(len(available))


def review(
    range_reasons: list[dict],
    q90: float,
    q50: float,
    arrived: float,
    hours: int,
    history_windows: float,
    anomaly: dict | None,
    cfg: Guardrails,
) -> dict:
    """The manual-review flag of one recommendation and every reason behind it."""
    reasons = list(range_reasons)
    ratio = q90 / max(q50, 1.0)
    if ratio > cfg.max_q90_to_q50:
        reasons.append({"code": "wide_interval", "ratio": round(ratio, 1)})
    if arrived < cfg.min_arrived_share:
        reasons.append({"code": "data_gap", "arrived": round(arrived * hours), "hours": hours})
    if not np.isfinite(history_windows) or history_windows < cfg.min_history_windows:
        windows = int(history_windows) if np.isfinite(history_windows) else 0
        reasons.append({"code": "short_history", "windows": windows})
    if anomaly is not None:
        reasons.append({"code": "anomaly", **anomaly})
    return {"flag": bool(reasons), "reasons": reasons}
