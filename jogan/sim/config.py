"""Typed simulator configuration, loaded from the YAML files under ``configs/``.

A profile (``configs/sim/<name>.yaml``) extends ``base.yaml``. The calendar, geography and
calibration files it names are loaded into the same model, so one validated ``SimConfig``
holds everything a world depends on, and its hash identifies that world's inputs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Setting = Literal["urban", "peri_urban", "rural"]
TxType = Literal["CO", "CI"]
Pattern = Literal["payday", "remittance", "hat", "cattle"]
Weekday = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

WEEKDAYS: tuple[Weekday, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SETTINGS: tuple[Setting, ...] = ("urban", "peri_urban", "rural")
TX_TYPES: tuple[TxType, ...] = ("CO", "CI")

_REPO_CONFIGS = Path(__file__).resolve().parents[2] / "configs"
CONFIG_DIR = Path(os.environ.get("JOGAN_CONFIG_DIR", _REPO_CONFIGS))

Prob = Annotated[float, Field(ge=0.0, le=1.0)]
Positive = Annotated[float, Field(gt=0.0)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _ordered_pair(pair: tuple[float, float], name: str) -> None:
    if pair[0] > pair[1]:
        raise ValueError(f"{name}: {pair[0]} > {pair[1]}")


# --- Calendar -------------------------------------------------------------------------------


class Holiday(Strict):
    date: dt.date
    end: dt.date | None = None
    name_en: str
    name_bn: str

    def days(self) -> list[dt.date]:
        last = self.end or self.date
        return [self.date + dt.timedelta(days=i) for i in range((last - self.date).days + 1)]


class Eid(Strict):
    key: Literal["fitr", "azha"]
    name_en: str
    name_bn: str
    date: dt.date
    holidays: tuple[dt.date, dt.date]

    @model_validator(mode="after")
    def _eid_inside_holidays(self) -> Self:
        if not self.holidays[0] <= self.date <= self.holidays[1]:
            raise ValueError(f"{self.key}: Eid day outside its holiday span")
        return self


class Ramadan(Strict):
    start: dt.date
    end: dt.date


class CalendarConfig(Strict):
    year: int
    timezone: str
    sources: dict[str, str]
    bank_weekend: list[Weekday]
    ramadan: Ramadan
    eids: list[Eid]
    holidays: list[Holiday]

    @model_validator(mode="after")
    def _ramadan_ends_before_fitr(self) -> Self:
        fitr = next(e for e in self.eids if e.key == "fitr")
        if self.ramadan.end != fitr.date - dt.timedelta(days=1):
            raise ValueError("Ramadan must end the day before Eid-ul-Fitr")
        if not 29 <= (self.ramadan.end - self.ramadan.start).days + 1 <= 30:
            raise ValueError("Ramadan must last 29 or 30 days")
        return self


# --- Geography ------------------------------------------------------------------------------


class SettingGeo(Strict):
    radius_km: Positive
    road_factor: float = Field(ge=1.0)
    runner_speed_kmh: Positive


class Territory(Strict):
    code: str = Field(pattern=r"^[A-Z]{3}$")
    district_en: str
    district_bn: str
    lat: float = Field(ge=20.5, le=26.7)  # Bangladesh bounding box
    lon: float = Field(ge=88.0, le=92.7)
    setting: Setting
    runners: int = Field(ge=1)
    patterns: list[Pattern] = []
    disruption_prob_by_month: dict[int, float] = {}


class GeoConfig(Strict):
    source: str
    settings: dict[Setting, SettingGeo]
    territories: list[Territory]

    @model_validator(mode="after")
    def _complete_and_unique(self) -> Self:
        if set(self.settings) != set(SETTINGS):
            raise ValueError(f"settings must define exactly {SETTINGS}")
        codes = [t.code for t in self.territories]
        if len(codes) != len(set(codes)):
            raise ValueError("territory codes must be unique")
        return self

    def territory(self, code: str) -> Territory:
        return next(t for t in self.territories if t.code == code)


# --- Calibration sources --------------------------------------------------------------------


class MonthAggregate(Strict):
    cash_in_count: int = Field(gt=0)
    cash_in_amount_mtk: Positive
    cash_out_count: int = Field(gt=0)
    cash_out_amount_mtk: Positive


class AgentsTotal(Strict):
    count: int = Field(gt=0)
    as_of: str


class Limits(Strict):
    cash_out: int = Field(gt=0)
    cash_in: int = Field(gt=0)


class CalibrationMonths(Strict):
    reference: str
    eid_base: str
    eid: str


class CalibrationConfig(Strict):
    sources: dict[str, str]
    agent_transactions: dict[str, MonthAggregate]
    agents_total: AgentsTotal
    customer_daily_limits_tk: Limits
    months: CalibrationMonths

    @model_validator(mode="after")
    def _months_present(self) -> Self:
        for month in (self.months.reference, self.months.eid_base, self.months.eid):
            if month not in self.agent_transactions:
                raise ValueError(f"no agent transactions for {month}")
        return self


# --- Simulator parameters (all ASSUMPTION) --------------------------------------------------


class AgentParams(Strict):
    volume_sigma: Positive
    volume_scale: dict[Setting, float]
    size_quantiles: tuple[float, float]
    hours: dict[Setting, tuple[int, int]]
    eid_day_hours: tuple[int, int]
    start_balance_days: tuple[float, float]
    min_start_balance_tk: int = Field(ge=0)
    hat_clusters: int = Field(ge=1)
    hat_days_per_cluster: tuple[int, int]

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        _ordered_pair(self.size_quantiles, "size_quantiles")
        _ordered_pair(self.eid_day_hours, "eid_day_hours")
        _ordered_pair(self.start_balance_days, "start_balance_days")
        _ordered_pair(self.hat_days_per_cluster, "hat_days_per_cluster")
        for setting, (open_h, close_h) in self.hours.items():
            if not 0 <= open_h < close_h <= 24:
                raise ValueError(f"bad opening hours for {setting}")
        return self


class MixParams(Strict):
    tilt: dict[Setting, float]
    remittance_tilt: float
    agent_sigma: float = Field(ge=0.0)


class Bump(Strict):
    centre: float
    width: Positive
    weight: float = Field(ge=0.0)


class EveningBump(Strict):
    centre: dict[Setting, float]
    width: Positive
    weight: float = Field(ge=0.0)


class RamadanHours(Strict):
    morning_factor: float = Field(ge=0.0)
    evening_shift_h: float
    evening_factor: float = Field(ge=0.0)


class FridayHours(Strict):
    morning_before: int
    morning_factor: float = Field(ge=0.0)
    prayer: tuple[int, int]
    prayer_factor: float = Field(ge=0.0)


class HourProfile(Strict):
    floor: float = Field(ge=0.0)
    morning: Bump
    evening: EveningBump
    ramadan: RamadanHours
    friday: FridayHours


class Payday(Strict):
    peak_day: int = Field(ge=1, le=28)
    width_days: Positive
    last_day: int = Field(ge=1, le=28)
    peak: float = Field(ge=1.0)


class MonthStart(Strict):
    last_day: int = Field(ge=1, le=28)
    factor: float = Field(ge=1.0)


class PreEid(Strict):
    days: int = Field(ge=1)
    peak: float = Field(ge=1.0)


class Remittance(Strict):
    month_start: MonthStart
    pre_eid: PreEid


class Hat(Strict):
    factor: float = Field(ge=1.0)


class Festival(Strict):
    ramp_days: int = Field(ge=1)
    peak_days_before: int = Field(ge=1)
    width_days: Positive
    cash_out_weight: dict[Setting, float]
    cash_in_weight: dict[Setting, float]
    eid_drop: list[float]


class Cattle(Strict):
    days: int = Field(ge=1)
    factor: float = Field(ge=1.0)


class Disruption(Strict):
    prob: Prob
    demand_factor: Prob
    speed_factor: Prob


class Noise(Strict):
    day_cv: float = Field(ge=0.0)
    hour_cv: float = Field(ge=0.0)


class Tickets(Strict):
    sigma: dict[TxType, float]
    min_tk: int = Field(gt=0)
    rounding: list[tuple[int | None, int]]

    @model_validator(mode="after")
    def _open_last_step(self) -> Self:
        if self.rounding[-1][0] is not None or any(b is None for b, _ in self.rounding[:-1]):
            raise ValueError("only the last rounding step may be open-ended")
        return self


class SplitAnomaly(Strict):
    days: tuple[int, int]
    bursts_per_day: tuple[int, int]
    burst_size: tuple[int, int]
    burst_minutes: int = Field(ge=1, le=59)
    amounts: list[int]


class SpikeAnomaly(Strict):
    days: tuple[int, int]
    factor: tuple[float, float]


class NightAnomaly(Strict):
    days: tuple[int, int]
    day_prob: Prob
    per_day: tuple[int, int]
    hours: tuple[int, int]


class Anomalies(Strict):
    share: Prob
    start_after_days: int = Field(ge=0)
    split: SplitAnomaly
    spike: SpikeAnomaly
    night: NightAnomaly


class Runners(Strict):
    shift: tuple[int, int]
    max_visits: int = Field(ge=1)
    bag_capacity_tk: int = Field(gt=0)
    visit_minutes: int = Field(gt=0)
    absence_prob: Prob
    off_on_eid_day: bool


class SimConfig(Strict):
    name: str
    start: dt.date
    end: dt.date
    n_agents: int = Field(ge=1)
    territories: list[str]
    replicas: int = Field(default=1, ge=1)

    calendar: CalendarConfig
    geo: GeoConfig
    calibration: CalibrationConfig

    agents: AgentParams
    mix: MixParams
    hour_profile: HourProfile
    weekday: dict[Weekday, float]
    payday: Payday
    remittance: Remittance
    hat: Hat
    festival: Festival
    cattle: Cattle
    disruption: Disruption
    noise: Noise
    tickets: Tickets
    anomalies: Anomalies
    runners: Runners

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.end < self.start:
            raise ValueError("end before start")
        if self.start.year != self.calendar.year or self.end.year != self.calendar.year:
            raise ValueError("the window must lie inside the calendar year")
        known = {t.code for t in self.geo.territories}
        unknown = set(self.territories) - known
        if unknown:
            raise ValueError(f"unknown territories: {sorted(unknown)}")
        if self.n_agents < len(self.territories) * self.replicas:
            raise ValueError("fewer agents than territories")
        return self

    @property
    def n_days(self) -> int:
        return (self.end - self.start).days + 1

    def config_hash(self) -> str:
        """Short SHA-256 of the fully resolved config; changes whenever any input changes."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


# --- Loading --------------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a mapping")
    return data


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _resolve_profile(path: Path) -> dict[str, Any]:
    data = _read_yaml(path)
    parent = data.pop("extends", None)
    if parent is None:
        return data
    return _merge(_resolve_profile(path.parent / parent), data)


def load_config(
    profile: str, overrides: dict[str, Any] | None = None, config_dir: Path | None = None
) -> SimConfig:
    """Load ``configs/sim/<profile>.yaml`` with its parents and referenced files."""
    root = config_dir or CONFIG_DIR
    data = _resolve_profile(root / "sim" / f"{profile}.yaml")
    for key in ("calendar", "geo", "calibration"):
        data[key] = _read_yaml(root / data[key])
    return SimConfig.model_validate(_merge(data, overrides or {}))
