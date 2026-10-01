"""Typed configuration of Jogan's morning round, loaded from ``configs/plan/base.yaml``."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from jogan.sim.config import CONFIG_DIR, Positive, Strict, _merge, _read_yaml


class Newsvendor(Strict):
    integration_points: int = Field(ge=10)
    split: Literal["typical", "two_sided"]
    split_iterations: int = Field(ge=10)


class Milp(Strict):
    time_limit_s: Positive
    mip_rel_gap: float = Field(ge=0.0)


class PlanConfig(Strict):
    horizon_hours: int = Field(ge=1, le=24)
    lost_customer_value_tk: float = Field(ge=0.0)
    dispatch: Literal["milp", "greedy"]
    newsvendor: Newsvendor
    milp: Milp

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


def load_plan_config(
    overrides: dict[str, Any] | None = None, config_dir: Path | None = None
) -> PlanConfig:
    """Load ``configs/plan/base.yaml``; ``overrides`` merge on top."""
    data = _read_yaml((config_dir or CONFIG_DIR) / "plan" / "base.yaml")
    return PlanConfig.model_validate(_merge(data, overrides or {}))
