"""Typed configuration of the final evaluation, loaded from ``configs/eval/base.yaml``."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Self

from pydantic import Field, model_validator

from jogan.sim.config import CONFIG_DIR, Strict, _merge, _read_yaml


class EvalConfig(Strict):
    profile: str
    seeds: tuple[int, ...] = Field(min_length=1)
    lost_customer_values_tk: tuple[float, ...] = Field(min_length=1)
    interval_level: float = Field(gt=0.5, lt=1.0)
    workers: int = Field(ge=1)
    lightgbm_threads: int = Field(ge=1)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be distinct")
        values = self.lost_customer_values_tk
        if list(values) != sorted(set(values)) or values[0] < 0:
            raise ValueError("lost_customer_values_tk must be increasing and non-negative")
        return self

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


def load_eval_config(
    overrides: dict[str, Any] | None = None, config_dir: Path | None = None
) -> EvalConfig:
    """Load ``configs/eval/base.yaml``; ``overrides`` merge on top."""
    data = _read_yaml((config_dir or CONFIG_DIR) / "eval" / "base.yaml")
    return EvalConfig.model_validate(_merge(data, overrides or {}))
