"""Drivers of a forecast from LightGBM's built-in TreeSHAP (``pred_contrib``, D-002 #5).

The boosters are trained on ``log1p`` of the peak drain, so a row's contributions plus the
expected value (the last column) sum to the raw log prediction of that quantile. A feature
with contribution ``φ`` multiplies ``1 + drain`` by ``exp(φ)``: its effect is reported as
``exp(φ) - 1`` in percent, relative to the model's average prediction over the training rows.
The conformal shift (:mod:`jogan.forecast.model`) is one constant per agent group, the same for
every feature, so it is not a driver.
"""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from jogan.explain.config import Drivers


def contributions(booster: lgb.Booster, x: pd.DataFrame) -> np.ndarray:
    """TreeSHAP values in log space: rows by (features + expected value)."""
    if len(x) == 0:
        return np.zeros((0, x.shape[1] + 1))
    return np.asarray(booster.predict(x, pred_contrib=True), dtype=float)


def feature_value(x: Any) -> Any:
    """A JSON-ready feature value: categories as text, NaN as None, numbers rounded."""
    if x is None or (isinstance(x, (float, np.floating)) and np.isnan(x)):
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return round(float(x), 4)
    return str(x)


def top_drivers(contrib: np.ndarray, x: pd.DataFrame, cfg: Drivers) -> list[list[dict]]:
    """Per row, the ``top_k`` features with the largest effect of at least ``min_effect_pct``."""
    names = list(x.columns)
    phi = contrib[:, : len(names)]
    out = []
    for i in range(len(phi)):
        items = []
        for j in np.argsort(-np.abs(phi[i]), kind="stable"):
            effect = float(np.expm1(phi[i, j]) * 100)
            if abs(effect) < cfg.min_effect_pct:
                continue
            items.append(
                {
                    "feature": names[j],
                    "value": feature_value(x.iat[i, j]),
                    "effect_pct": round(effect),
                }
            )
            if len(items) == cfg.top_k:
                break
        out.append(items)
    return out
