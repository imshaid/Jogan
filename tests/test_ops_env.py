"""Operations environment invariants: balances, conservation, common customers, logs."""

import datetime as dt

import numpy as np
import pytest
from pydantic import ValidationError

from jogan.ops.config import load_ops_config
from jogan.ops.costs import commission_rate
from jogan.ops.env import LOST, SERVED, SERVED_ON_RETRY, Episode, simulate
from jogan.ops.io import observed_hourly, visits_frame
from jogan.ops.metrics import summarize, truth_hourly
from jogan.ops.policies import POLICIES, STATUS_QUO, make_policy
from jogan.sim.world import World


def test_ops_config_loads_and_validates() -> None:
    ops = load_ops_config()
    assert ops.config_hash() == load_ops_config().config_hash()
    assert ops.env.retry.prob == 0.0
    with pytest.raises(ValidationError):
        load_ops_config({"costs": {"agent_commission_per_1000_tk": {"CO": -1}}})
    with pytest.raises(ValidationError):
        load_ops_config({"costs": {"runner": {"salary_tk_per_month": [17000, 13000]}}})
    unordered = [["2026-02-01", 116], ["2026-01-01", 118]]
    with pytest.raises(ValidationError):
        load_ops_config({"costs": {"runner": {"petrol_tk_per_litre": unordered}}})


@pytest.mark.parametrize("policy", POLICIES)
def test_balances_never_go_negative(tiny_episodes: dict[str, Episode], policy: str) -> None:
    ep = tiny_episodes[policy]
    assert ep.cash.min() >= 0
    assert ep.efloat.min() >= 0


@pytest.mark.parametrize("policy", POLICIES)
def test_liquidity_is_conserved(tiny_episodes: dict[str, Episode], policy: str) -> None:
    """Customers, visits and bank trips only move money between cash and e-float."""
    ep = tiny_episodes[policy]
    total = (ep.ctx.opening_cash + ep.ctx.opening_efloat)[:, None]
    assert ((ep.cash + ep.efloat) == total).all()
    bag = ep.visits["bag_after"].to_numpy(dtype=float)
    assert ((bag >= 0) & (bag <= ep.world.config.runners.bag_capacity_tk)).all()
    assert (ep.visits["cash_delta"].abs() % 100 == 0).all()


def test_every_policy_faces_the_same_customers(
    tiny_world: World, tiny_episodes: dict[str, Episode]
) -> None:
    first = tiny_episodes[STATUS_QUO]
    assert np.array_equal(np.sort(first.row), np.arange(len(tiny_world.demand)))
    requests = {k: v for k, v in truth_hourly(first).items() if k.startswith("req")}
    for ep in tiny_episodes.values():
        for name in ("t", "agent", "side", "amount"):
            assert np.array_equal(getattr(ep, name), getattr(first, name)), name
        for name, panel in requests.items():
            assert np.array_equal(truth_hourly(ep)[name], panel), name


@pytest.mark.parametrize("policy", POLICIES)
def test_outcomes_match_the_observed_ledger(tiny_episodes: dict[str, Episode], policy: str) -> None:
    ep = tiny_episodes[policy]
    assert set(np.unique(ep.outcome)) <= {LOST, SERVED, SERVED_ON_RETRY}
    served = ep.outcome != LOST
    for side, (n, tk) in enumerate(
        ((ep.history.co_n, ep.history.co_tk), (ep.history.ci_n, ep.history.ci_tk))
    ):
        pick = served & (ep.side == side)
        assert n.sum() == pick.sum()
        assert tk.sum() == ep.amount[pick].sum()
    s = summarize(ep)["service"]
    assert s["requests"] == len(ep.outcome)
    assert s["lost"] == (ep.outcome == LOST).sum()


@pytest.mark.parametrize("policy", POLICIES)
def test_runner_visits_respect_the_roster_and_shift(
    tiny_world: World, tiny_episodes: dict[str, Episode], policy: str
) -> None:
    ep = tiny_episodes[policy]
    assert ep.rejected == 0  # plans made on the fleet copy always fit the real fleet
    days = ep.runner_days
    assert (days["visits"] <= tiny_world.config.runners.max_visits).all()
    assert (days.loc[~days["on_duty"], "visits"] == 0).all()
    v = ep.visits
    start, end = tiny_world.config.runners.shift
    second = v["t"] % 86400
    assert ((second >= start * 3600) & (second < end * 3600)).all()
    terr = np.array(ep.ctx.network.territory)
    runner_terr = tiny_world.runners["territory"].to_numpy()
    codes = np.array(ep.ctx.network.territory_codes)
    assert (codes[terr[v["agent"].to_numpy(dtype=int)]] == runner_terr[v["runner"]]).all()


@pytest.mark.parametrize("policy", POLICIES)
def test_self_refills_only_in_bank_hours(
    tiny_world: World, tiny_episodes: dict[str, Episode], policy: str
) -> None:
    refills = tiny_episodes[policy].refills
    assert not refills.empty
    day, second = refills["t"] // 86400, refills["t"] % 86400
    assert tiny_world.calendar["bank_open"].to_numpy()[day].all()
    b0, b1 = load_ops_config().env.self_refill.bank_hours
    assert ((second >= b0 * 3600) & (second < b1 * 3600)).all()


def test_observation_log_hides_failures_and_has_gaps(tiny_episodes: dict[str, Episode]) -> None:
    ep = tiny_episodes["fixed_round"]
    obs = observed_hourly(ep)
    assert set(obs.columns) == {
        "agent_id",
        "ts",
        "co_n",
        "co_tk",
        "ci_n",
        "ci_tk",
        "efloat_tk",
        "cash_est_tk",
        "available_at",
    }
    panel = len(ep.ctx.agents) * ep.n_hours
    assert 0.005 < 1 - len(obs) / panel < 0.015
    lag = obs["available_at"] - obs["ts"]
    assert (lag >= np.timedelta64(1, "h")).all()
    assert (lag > np.timedelta64(24, "h")).mean() > 0  # some late days
    assert obs["co_tk"].sum() <= ep.amount[ep.side == 0].sum()


def test_history_never_shows_the_future(tiny_episodes: dict[str, Episode]) -> None:
    hist = tiny_episodes[STATUS_QUO].history
    now = 30 * 24 // 2
    visible = hist.available(now, 0, hist.missing.shape[1])
    assert not visible[:, now:].any()
    assert visible[:, : now - 48].mean() > 0.97


def test_simulation_is_deterministic(tiny_world: World, tiny_episodes: dict[str, Episode]) -> None:
    again = simulate(tiny_world, make_policy("fixed_round", tiny_world))
    before = tiny_episodes["fixed_round"]
    assert np.array_equal(again.outcome, before.outcome)
    assert visits_frame(again).equals(visits_frame(before))
    assert summarize(again) == summarize(before)


def test_retry_option_recovers_some_requests(
    tiny_world: World, tiny_episodes: dict[str, Episode]
) -> None:
    ops = load_ops_config({"env": {"retry": {"prob": 0.3}}})
    ep = simulate(tiny_world, make_policy("fixed_round", tiny_world), ops)
    s = summarize(ep)["service"]
    assert s["served_on_retry"] > 0
    assert s["failed_attempts"] > s["lost"]
    assert ep.cash.min() >= 0
    assert ep.efloat.min() >= 0
    assert s["requests"] == summarize(tiny_episodes["fixed_round"])["service"]["requests"]


def test_costs_add_up_and_split_by_window(tiny_episodes: dict[str, Episode]) -> None:
    ep = tiny_episodes["fixed_round"]
    whole = summarize(ep)
    cost = whole["cost_tk"]
    parts = ("lost_commission", "runner_fuel", "runner_time", "idle_liquidity")
    assert cost["known_total"] == pytest.approx(sum(cost[p] for p in parts), abs=0.05)
    rates = commission_rate(ep.ctx.ops.costs)
    lost_tk = whole["service"]["lost_tk"]
    assert cost["lost_commission"] == pytest.approx(
        lost_tk["CO"] * rates["CO"] + lost_tk["CI"] * rates["CI"], abs=0.01
    )

    start = ep.world.config.start
    mid = start + dt.timedelta(days=13)
    a = summarize(ep, start=start, end=mid)
    b = summarize(ep, start=mid + dt.timedelta(days=1))
    for group, key in (
        ("service", "requests"),
        ("service", "lost"),
        ("operations", "runner_visits"),
    ):
        assert a[group][key] + b[group][key] == whole[group][key]
    assert a["window"]["days"] + b["window"]["days"] == ep.world.config.n_days
