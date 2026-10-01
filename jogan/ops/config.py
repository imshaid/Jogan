"""Typed configuration of the operations environment, loaded from ``configs/ops/``.

Three files: ``costs.yaml`` (money), ``env.yaml`` (agent self-refill, retries, observation gaps)
and ``policies.yaml`` (baseline parameters). Runner shifts, visits and bag size live in the
simulator config (``configs/sim/base.yaml``), because the world's roster depends on them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import Field, model_validator

from jogan.sim.config import (
    CONFIG_DIR,
    SETTINGS,
    Positive,
    Prob,
    Setting,
    Strict,
    TxType,
    _merge,
    _ordered_pair,
    _read_yaml,
)

NonNeg = Annotated[float, Field(ge=0.0)]


# --- Costs ----------------------------------------------------------------------------------


class RunnerCost(Strict):
    petrol_tk_per_litre: list[tuple[dt.date, Positive]]
    km_per_litre: dict[Setting, Positive]
    salary_tk_per_month: tuple[Positive, Positive]
    hours_per_week: Positive

    @model_validator(mode="after")
    def _valid(self) -> Self:
        dates = [d for d, _ in self.petrol_tk_per_litre]
        if not dates or dates != sorted(set(dates)):
            raise ValueError("petrol prices need strictly increasing dates")
        if set(self.km_per_litre) != set(SETTINGS):
            raise ValueError(f"km_per_litre must cover {SETTINGS}")
        _ordered_pair(self.salary_tk_per_month, "salary_tk_per_month")
        return self


class IdleCost(Strict):
    rate_per_year: NonNeg
    need_days: NonNeg


class Costs(Strict):
    """Prices behind the total liquidity cost; each value is tagged in ``costs.yaml``."""

    sources: dict[str, str]
    agent_commission_per_1000_tk: dict[TxType, NonNeg]
    runner: RunnerCost
    idle: IdleCost


# --- Environment ----------------------------------------------------------------------------


class SelfRefill(Strict):
    trigger_days: Positive
    delay_hours: tuple[float, float]
    bank_hours: tuple[int, int]

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        _ordered_pair(self.delay_hours, "delay_hours")
        if not 0 <= self.bank_hours[0] < self.bank_hours[1] <= 24:
            raise ValueError("bad bank hours")
        return self


class Retry(Strict):
    prob: Prob
    within_hours: Positive


class Observation(Strict):
    missing_hour_prob: Prob
    late_day_prob: Prob


class EnvParams(Strict):
    self_refill: SelfRefill
    retry: Retry
    runner_bag_start_tk: int = Field(ge=0)
    observation: Observation


# --- Policies -------------------------------------------------------------------------------


class Typical(Strict):
    history_days: int = Field(ge=1)
    min_days: int = Field(ge=1)
    cold_start_balance_days: Positive


class Calls(Strict):
    call_days: Positive


class Threshold(Strict):
    min_days: Positive


class SafetyStock(Strict):
    service_level: float = Field(gt=0.5, lt=1.0)
    history_days: int = Field(ge=1)
    min_days: int = Field(ge=1)


class Oracle(Strict):
    horizon_hours: int = Field(ge=1)


class PolicyParams(Strict):
    plan_hour: int = Field(ge=0, le=23)
    call_reserve_visits: int = Field(ge=0)
    typical: Typical
    calls: Calls
    threshold: Threshold
    safety_stock: SafetyStock
    oracle: Oracle


class OpsConfig(Strict):
    costs: Costs
    env: EnvParams
    policies: PolicyParams

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


def load_ops_config(
    overrides: dict[str, Any] | None = None, config_dir: Path | None = None
) -> OpsConfig:
    """Load ``configs/ops/{costs,env,policies}.yaml``; ``overrides`` merge on top."""
    root = (config_dir or CONFIG_DIR) / "ops"
    data = {name: _read_yaml(root / f"{name}.yaml") for name in ("costs", "env", "policies")}
    return OpsConfig.model_validate(_merge(data, overrides or {}))
