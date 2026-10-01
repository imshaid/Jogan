"""Typed configuration of the drain forecast, loaded from ``configs/forecast/base.yaml``."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from jogan.sim.config import CONFIG_DIR, Positive, Strict, _merge, _ordered_pair, _read_yaml

SPLITS = ("train", "calibration", "test")
SIDES = ("cash", "efloat")
GroupColumn = Literal["setting", "size_class", "territory"]


class Splits(Strict):
    train: tuple[dt.date, dt.date]
    calibration: tuple[dt.date, dt.date]
    test: tuple[dt.date, dt.date]

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        last = None
        for name in SPLITS:
            first, end = getattr(self, name)
            if end < first:
                raise ValueError(f"{name} ends before it starts")
            if last is not None and first <= last:
                raise ValueError(f"{name} overlaps the split before it")
            last = end
        return self


class Features(Strict):
    recent_hours: tuple[int, ...] = Field(min_length=1)
    profile_days: int = Field(ge=1)
    history_windows: int = Field(ge=2)
    lag_days: tuple[int, ...] = Field(min_length=1)


class Censoring(Strict):
    strategy: Literal["impute", "ignore", "drop"]
    low_balance_tickets: float = Field(ge=0.0)
    clean_balance_tickets: float = Field(ge=0.0)
    lift: Literal["max", "add"]
    day_factor_clip: tuple[Positive, Positive]

    @model_validator(mode="after")
    def _clip(self) -> Self:
        _ordered_pair(self.day_factor_clip, "day_factor_clip")
        return self


class Conformal(Strict):
    groups: tuple[GroupColumn, ...]
    min_group_rows: int = Field(ge=1)


class LightGBM(Strict):
    num_boost_round: int = Field(ge=1)
    learning_rate: Positive
    num_leaves: int = Field(ge=2)
    min_data_in_leaf: int = Field(ge=1)
    feature_fraction: float = Field(gt=0.0, le=1.0)
    lambda_l2: float = Field(ge=0.0)
    max_bin: int = Field(ge=2)
    seed: int
    num_threads: int = Field(ge=0)

    def params(self, alpha: float) -> dict[str, Any]:
        """Booster parameters for the quantile ``alpha``; deterministic for the same data."""
        return {
            "objective": "quantile",
            "alpha": alpha,
            "learning_rate": self.learning_rate,
            "num_leaves": self.num_leaves,
            "min_data_in_leaf": self.min_data_in_leaf,
            "feature_fraction": self.feature_fraction,
            "lambda_l2": self.lambda_l2,
            "max_bin": self.max_bin,
            "seed": self.seed,
            "num_threads": self.num_threads,
            "deterministic": True,
            "force_row_wise": True,
            "verbosity": -1,
        }


class ForecastConfig(Strict):
    origin_hours: tuple[int, ...] = Field(min_length=1)
    horizons_hours: tuple[int, ...] = Field(min_length=1)
    quantiles: tuple[float, ...] = Field(min_length=2)
    warmup_days: int = Field(ge=1)
    splits: dict[str, Splits]
    features: Features
    censoring: Censoring
    conformal: Conformal
    lightgbm: LightGBM

    @model_validator(mode="after")
    def _grids(self) -> Self:
        for name in ("origin_hours", "horizons_hours", "quantiles"):
            values = getattr(self, name)
            if list(values) != sorted(set(values)):
                raise ValueError(f"{name} must be strictly increasing")
        if not all(0 <= h <= 23 for h in self.origin_hours):
            raise ValueError("origin_hours must be hours of the day")
        if not all(1 <= h <= 24 for h in self.horizons_hours):
            raise ValueError("horizons_hours must be 1 to 24")
        if not all(0.0 < q < 1.0 for q in self.quantiles):
            raise ValueError("quantiles must lie strictly between 0 and 1")
        return self

    @property
    def max_horizon(self) -> int:
        return self.horizons_hours[-1]

    def intervals(self) -> list[tuple[float, float]]:
        """Central intervals from symmetric pairs of quantile levels, narrowest first."""
        levels = set(self.quantiles)
        pairs = [(q, round(1 - q, 10)) for q in self.quantiles if q < 0.5]
        return sorted((p for p in pairs if p[1] in levels), key=lambda p: p[1] - p[0])

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


def load_forecast_config(
    overrides: dict[str, Any] | None = None, config_dir: Path | None = None
) -> ForecastConfig:
    """Load ``configs/forecast/base.yaml``; ``overrides`` merge on top."""
    data = _read_yaml((config_dir or CONFIG_DIR) / "forecast" / "base.yaml")
    return ForecastConfig.model_validate(_merge(data, overrides or {}))
