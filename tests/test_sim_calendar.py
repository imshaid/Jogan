import numpy as np
import pandas as pd
import pytest

from jogan.sim.calendar import build_calendar, month_bounds
from jogan.sim.config import SETTINGS, load_config
from jogan.sim.demand import hour_weights, opening_hours


@pytest.fixture(scope="module")
def cal() -> pd.DataFrame:
    cfg = load_config("tiny")
    return build_calendar(cfg.calendar, cfg.start, cfg.end)


def test_bank_days_follow_weekend_and_holidays(cal: pd.DataFrame) -> None:
    day = cal.set_index("date")
    assert len(cal) == 28
    assert not day.loc["2026-03-06", "bank_open"]  # Friday
    assert not day.loc["2026-03-07", "bank_open"]  # Saturday
    assert day.loc["2026-03-08", "bank_open"]  # Sunday
    assert not day.loc["2026-03-26", "bank_open"]  # Independence Day, a Thursday
    assert day.loc["2026-03-26", "holiday_en"] == "Independence Day"


def test_eid_and_ramadan_columns(cal: pd.DataFrame) -> None:
    day = cal.set_index("date")
    assert day.loc["2026-03-21", "eid"] == "fitr"
    assert day.loc["2026-03-18", "days_to_eid"] == 3
    assert day.loc["2026-03-23", "days_since_eid"] == 2
    assert day.loc["2026-03-22", "next_eid"] == "azha"
    assert day.loc["2026-03-20", "is_ramadan"]
    assert not day.loc["2026-03-21", "is_ramadan"]


def test_month_bounds() -> None:
    assert [d.isoformat() for d in month_bounds("2026-02")] == ["2026-02-01", "2026-02-28"]


@pytest.mark.parametrize("setting", SETTINGS)
def test_hour_weights_sum_to_one_inside_opening_hours(cal: pd.DataFrame, setting: str) -> None:
    cfg = load_config("tiny")
    weights = hour_weights(cal, cfg, setting)
    assert np.allclose(weights.sum(axis=1), 1.0)
    assert (weights[~opening_hours(cal, cfg, setting)] == 0).all()
