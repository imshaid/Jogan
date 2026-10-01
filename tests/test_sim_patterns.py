"""The injected demand patterns are recoverable from the generated attempts.

Each test pools four tiny seeds, so a pattern must be clearly present, not luckily drawn.
"""

import pandas as pd
import pytest

from jogan.sim.world import World

from .conftest import normal_demand


@pytest.fixture(scope="module")
def attempts(tiny_worlds: list[World]) -> pd.DataFrame:
    return normal_demand(tiny_worlds)


def _daily(attempts: pd.DataFrame, territory: str) -> pd.DataFrame:
    d = attempts[attempts["agent_id"].str.startswith(territory)]
    return d.groupby(["date", "tx_type"], observed=True).size().unstack(fill_value=0)


def _sum(daily: pd.DataFrame, first: str, last: str, side: str) -> float:
    return float(daily.loc[first:last, side].sum())


def test_payday_lifts_cash_out_in_gazipur(attempts: pd.DataFrame) -> None:
    daily = _daily(attempts, "GZP")
    # Days 5-7 vs the same weekdays a week later; cash-in is the within-day control.
    peak = _sum(daily, "2026-03-05", "2026-03-07", "CO") / _sum(
        daily, "2026-03-05", "2026-03-07", "CI"
    )
    later = _sum(daily, "2026-03-12", "2026-03-14", "CO") / _sum(
        daily, "2026-03-12", "2026-03-14", "CI"
    )
    assert peak / later > 1.3


def test_hat_days_lift_rangpur_agents(attempts: pd.DataFrame, tiny_worlds: list[World]) -> None:
    masks = pd.concat(
        [
            w.agents.assign(agent_id="s" + str(w.seed) + "/" + w.agents["agent_id"].astype(str))
            for w in tiny_worlds
        ]
    ).set_index("agent_id")["hat_mask"]
    d = attempts[attempts["agent_id"].str.startswith("RNG") & (attempts["date"] <= "2026-03-12")]
    per_day = (
        d.assign(agent_id="s" + d["seed"].astype(str) + "/" + d["agent_id"])
        .groupby(["agent_id", "date"])
        .size()
        .rename("n")
        .reset_index()
    )
    mask = per_day["agent_id"].map(masks).to_numpy(dtype=int)
    per_day["hat"] = (mask >> per_day["date"].dt.weekday.to_numpy()) & 1 == 1
    means = per_day.groupby("hat")["n"].mean()
    assert means[True] / means[False] > 1.3


@pytest.mark.parametrize("territory", ["GZP", "RNG"])
def test_pre_eid_surge_and_eid_day_drop(attempts: pd.DataFrame, territory: str) -> None:
    daily = _daily(attempts, territory)
    baseline = _sum(daily, "2026-03-11", "2026-03-14", "CO") / 4
    assert _sum(daily, "2026-03-18", "2026-03-20", "CO") / 3 / baseline > 1.35
    assert daily.loc["2026-03-21", "CO"] / baseline < 0.5


def test_tickets_grow_before_eid(attempts: pd.DataFrame) -> None:
    co = attempts[attempts["tx_type"] == "CO"].set_index("date")["amount_tk"].sort_index()
    surge = co.loc["2026-03-18":"2026-03-20"].mean() / co.loc["2026-03-01":"2026-03-08"].mean()
    assert surge > 1.25


def test_ramadan_moves_activity_to_the_evening(attempts: pd.DataFrame) -> None:
    evening = attempts["hour"] >= 18
    ramadan = attempts["date"] <= "2026-03-17"
    after = attempts["date"] >= "2026-03-24"
    assert evening[ramadan].mean() > evening[after].mean() + 0.05


def test_rural_agents_lean_to_cash_out(attempts: pd.DataFrame) -> None:
    is_co = attempts["tx_type"] == "CO"
    territory = attempts["agent_id"].str[:3]
    share = is_co.groupby(territory).mean()
    assert share["RNG"] > share["GZP"] + 0.05
