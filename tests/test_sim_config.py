import datetime as dt

import pytest
from pydantic import ValidationError

from jogan.sim.config import load_config

PROFILES = {"tiny": (28, 40), "dev": (60, 150), "full": (150, 600), "stress": (14, 10_000)}


@pytest.mark.parametrize(("profile", "expected"), PROFILES.items())
def test_profiles_load(profile: str, expected: tuple[int, int]) -> None:
    cfg = load_config(profile)
    assert (cfg.n_days, cfg.n_agents) == expected
    assert cfg.name == profile


def test_full_profile_covers_both_eids_and_all_territories() -> None:
    cfg = load_config("full")
    assert all(cfg.start <= eid.date <= cfg.end for eid in cfg.calendar.eids)
    assert set(cfg.territories) == {t.code for t in cfg.geo.territories}


def test_calendar_weekdays_match_sources() -> None:
    cal = load_config("tiny").calendar
    eids = {e.key: e.date for e in cal.eids}
    assert eids["fitr"].strftime("%a") == "Sat"
    assert eids["azha"].strftime("%a") == "Thu"
    assert (cal.ramadan.end - cal.ramadan.start).days + 1 == 30


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        load_config("tiny", {"payday": {"peek": 2.0}})


def test_unknown_territory_is_rejected() -> None:
    with pytest.raises(ValidationError):
        load_config("tiny", {"territories": ["XYZ"]})


def test_ramadan_must_end_before_fitr() -> None:
    with pytest.raises(ValidationError):
        load_config("tiny", {"calendar": {"ramadan": {"end": dt.date(2026, 3, 19)}}})


def test_config_hash_is_stable_and_sensitive() -> None:
    base = load_config("tiny").config_hash()
    assert base == load_config("tiny").config_hash()
    assert base != load_config("tiny", {"hat": {"factor": 1.4}}).config_hash()
