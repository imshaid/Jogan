"""Determinism, sanity and leakage checks for generated worlds (tiny profile)."""

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from jogan.sim.__main__ import main
from jogan.sim.config import load_config
from jogan.sim.io import PUBLIC_TABLES, read_world, write_world
from jogan.sim.world import World, build_world, haversine_km

from .conftest import normal_demand


def _digests(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_same_seed_gives_byte_identical_files(tiny_world: World, tmp_path: Path) -> None:
    write_world(tiny_world, tmp_path / "a")
    write_world(build_world(load_config("tiny"), seed=0), tmp_path / "b")
    first, second = _digests(tmp_path / "a"), _digests(tmp_path / "b")
    assert len(first) == 10
    assert first == second


def test_different_seed_gives_different_demand(tiny_world: World) -> None:
    other = build_world(load_config("tiny"), seed=1)
    assert not tiny_world.demand.equals(other.demand)
    pd.testing.assert_frame_equal(tiny_world.calendar, other.calendar)


def test_public_tables_hold_no_ground_truth(tiny_world: World, tmp_path: Path) -> None:
    truth_columns = set(tiny_world.agent_truth.columns) - {"agent_id"}
    assert not truth_columns & set(tiny_world.agents.columns)
    for name in PUBLIC_TABLES:
        columns = set(getattr(tiny_world, name).columns)
        assert not {"pattern", "base_volume", "co_share", "cash0_tk"} & columns, name
    write_world(tiny_world, tmp_path)
    assert set(read_world(tmp_path)) == set(PUBLIC_TABLES)
    assert "truth/anomalies" in read_world(tmp_path, truth=True)


def test_opening_hours_are_respected(tiny_world: World) -> None:
    d = normal_demand(tiny_world)
    night_agents = tiny_world.anomalies.loc[tiny_world.anomalies["pattern"] == "night", "agent_id"]
    assert not d["agent_id"].isin(night_agents).any()
    d = d.merge(tiny_world.agents[["agent_id", "open_hour", "close_hour"]], on="agent_id")
    eid_days = tiny_world.calendar.loc[tiny_world.calendar["eid"].notna(), "date"]
    on_eid = d["date"].isin(eid_days)
    eid_open, eid_close = tiny_world.config.agents.eid_day_hours
    assert d.loc[on_eid, "hour"].between(eid_open, eid_close - 1).all()
    normal = d[~on_eid]
    assert ((normal["hour"] >= normal["open_hour"]) & (normal["hour"] < normal["close_hour"])).all()


def test_amounts_are_rounded_positive_and_capped(tiny_world: World) -> None:
    d = normal_demand(tiny_world)
    limits = tiny_world.config.calibration.customer_daily_limits_tk
    assert (d["amount_tk"] >= tiny_world.config.tickets.min_tk).all()
    assert (d["amount_tk"] % 50 == 0).all()
    assert (d.loc[d["tx_type"] == "CO", "amount_tk"] <= limits.cash_out).all()
    assert (d.loc[d["tx_type"] == "CI", "amount_tk"] <= limits.cash_in).all()
    assert (d.loc[d["amount_tk"] >= 10_000, "amount_tk"] % 500 == 0).all()


def test_demand_is_sorted_and_inside_the_window(tiny_world: World) -> None:
    d = tiny_world.demand
    cfg = tiny_world.config
    assert d["ts"].min() >= pd.Timestamp(cfg.start)
    assert d["ts"].max() < pd.Timestamp(cfg.end) + pd.Timedelta(days=1)
    keys = pd.DataFrame({"a": d["agent_id"].cat.codes, "t": d["ts"]})
    assert keys.equals(keys.sort_values(["a", "t"], kind="stable"))


def test_agents_are_synthetic_and_near_their_hub(tiny_world: World) -> None:
    agents = tiny_world.agents.merge(
        tiny_world.territories[["territory", "lat", "lon", "radius_km"]],
        on="territory",
        suffixes=("", "_hub"),
    )
    assert agents["agent_id"].str.fullmatch(r"[A-Z]{3}-\d{3}").all()
    km = haversine_km(agents["lat"], agents["lon"], agents["lat_hub"], agents["lon_hub"])
    assert (km <= agents["radius_km"] * 1.01).all()


def test_size_classes_follow_quantiles(tiny_world: World) -> None:
    counts = tiny_world.agents["size_class"].value_counts()
    assert (counts["small"], counts["medium"], counts["large"]) == (20, 14, 6)


def test_starting_balances_are_positive(tiny_world: World) -> None:
    truth = tiny_world.agent_truth
    floor = tiny_world.config.agents.min_start_balance_tk
    assert (truth["cash0_tk"] >= floor).all()
    assert (truth["efloat0_tk"] >= floor).all()


def test_runners_are_off_on_eid_day(tiny_world: World) -> None:
    roster = tiny_world.roster
    eid_day = tiny_world.calendar.loc[tiny_world.calendar["eid"].notna(), "date"]
    assert not roster.loc[roster["date"].isin(eid_day), "on_duty"].any()
    assert roster["on_duty"].mean() > 0.9


def test_each_anomaly_pattern_is_present_and_visible(tiny_world: World) -> None:
    labels = tiny_world.anomalies.set_index("pattern")
    assert set(labels.index) == {"split", "spike", "night"}
    d = tiny_world.demand.assign(date=tiny_world.demand["ts"].dt.normalize())

    split = d[d["agent_id"] == labels.at["split", "agent_id"]]
    amounts = set(tiny_world.config.anomalies.split.amounts)
    assert split["amount_tk"].isin(amounts).sum() >= labels.at["split", "extra_attempts"] > 0

    night = d[d["agent_id"] == labels.at["night", "agent_id"]]
    assert (night["ts"].dt.hour < tiny_world.config.anomalies.night.hours[1]).any()

    spike = labels.loc["spike"]
    daily = d[d["agent_id"] == spike["agent_id"]].groupby("date").size()
    inside = daily.loc[spike["first_date"] : spike["last_date"]].mean()
    assert inside > 1.8 * daily.median()


@pytest.mark.parametrize("profile", ["tiny"])
def test_cli_writes_a_world(profile: str, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    main(["--profile", profile, "--seed", "3", "--out", str(tmp_path)])
    assert (tmp_path / "truth" / "demand.parquet").exists()
    assert "attempts" in capsys.readouterr().out
