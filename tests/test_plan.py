"""Jogan's policy: newsvendor levels, the dispatch program, the policy in the environment."""

import numpy as np
import pytest
from pydantic import ValidationError

from jogan.forecast.backtest import Forecaster
from jogan.ops.dispatch import plan_rounds
from jogan.ops.env import Episode, simulate
from jogan.ops.fleet import Fleet, Network
from jogan.ops.policies import Deployed, FixedRound, make_policy
from jogan.plan.config import load_plan_config
from jogan.plan.dispatch import SolveLog, milp_rounds
from jogan.plan.newsvendor import (
    critical_ratio,
    exceedance,
    expected_shortfall,
    quantile_at,
    target_cash,
)
from jogan.plan.policy import Jogan
from jogan.sim.config import CONFIG_DIR
from jogan.sim.world import World
from tests.test_ops_costs import _untagged

LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)


def uniform(top: float, rows: int = 1) -> np.ndarray:
    """Quantiles of a uniform drain on [0, top]: linear, so interpolation is exact."""
    return np.tile(np.array(LEVELS) * top, (rows, 1))


def test_plan_config_loads_and_is_tagged() -> None:
    cfg = load_plan_config()
    assert cfg.config_hash() == load_plan_config().config_hash()
    assert cfg.newsvendor.split in {"typical", "two_sided"}
    with pytest.raises(ValidationError):
        load_plan_config({"dispatch": "random"})
    assert _untagged(CONFIG_DIR / "plan" / "base.yaml") == []


def test_quantile_function_is_exact_for_a_uniform_drain() -> None:
    q = uniform(1000.0, 3)
    tau = np.array([0.01, 0.3, 0.995])
    assert np.allclose(quantile_at(q, LEVELS, tau), 1000 * tau)
    assert np.allclose(exceedance(q, LEVELS, np.array([0.0, 250.0, 2000.0])), [1.0, 0.75, 0.0])
    # E[(D - b)+] = (1000 - b)² / 2000 for D uniform on [0, 1000]
    es = expected_shortfall(q, LEVELS, np.array([0.0, 300.0, 1200.0]), points=2000)
    assert np.allclose(es, [500.0, 245.0, 0.0], atol=0.5)


def test_newsvendor_level_is_the_critical_quantile() -> None:
    assert float(critical_ratio(0.9, 0.1)) == pytest.approx(0.9)
    q = uniform(1000.0)
    total = np.array([3000.0])
    out = target_cash(q, q, LEVELS, total, np.array([0.9]), np.array([0.5]), 0.1)
    assert out["need_cash"][0] == pytest.approx(900.0)
    assert out["need_efloat"][0] == pytest.approx(1000 * 0.5 / 0.6)
    assert out["fits"][0]
    # the middle of the band of cash levels that meets both needs
    assert out["target"][0] == pytest.approx((900 + 3000 - out["need_efloat"][0]) / 2)


def test_short_liquidity_uses_the_split() -> None:
    q_cash, q_ef = uniform(1000.0), uniform(3000.0)
    total = np.array([1000.0])
    under = np.array([1.0])
    two_sided = target_cash(q_cash, q_ef, LEVELS, total, under, under, 0.01)
    assert not two_sided["fits"][0]
    c = two_sided["target"][0]
    # equal costs: the split equalises the stock-out probabilities of the two sides
    p_cash = exceedance(q_cash, LEVELS, np.array([c]))[0]
    p_ef = exceedance(q_ef, LEVELS, total - c)[0]
    assert p_cash == pytest.approx(p_ef, abs=1e-6)
    typical = target_cash(
        q_cash, q_ef, LEVELS, total, under, under, 0.01, fallback=np.array([400.0])
    )
    assert typical["target"][0] == 400.0
    clipped = target_cash(q_cash, q_ef, LEVELS, total, under, under, 0.01, fallback=np.array([5e3]))
    assert clipped["target"][0] == total[0]


def _fresh_fleet(world: World, day: int) -> Fleet:
    fleet = Fleet(world, Network(world.agents, world.territories))
    n = len(world.runners)
    fleet.start_day(day, [True] * n, [1.0] * n, 150000)
    return fleet


def test_dispatch_program_respects_the_fleet(tiny_world: World) -> None:
    day, reserve = 3, 4
    fleet = _fresh_fleet(tiny_world, day)
    now = day * 86400 + 8 * 3600
    n = len(tiny_world.agents)
    value = np.random.default_rng(0).uniform(0, 400, n)
    log = SolveLog()
    agents = list(range(n))
    visits = milp_rounds(
        agents,
        value,
        fleet,
        now,
        lambda a, _: 1000.0,
        np.full(len(fleet.loc), 2.6),
        1.2,
        reserve,
        load_plan_config().milp,
        log,
    )
    assert log.programs == len(set(fleet.network.territory))
    assert log.fallbacks == 0
    visited = [v.agent for v in visits]
    assert len(visited) == len(set(visited))  # every agent at most once
    for r in range(len(fleet.loc)):
        mine = [v for v in visits if v.runner == r]
        assert len(mine) <= fleet.max_visits - reserve
        assert all(fleet.territory[r] == fleet.network.territory[v.agent] for v in mine)
        assert fleet.visits[r] == len(mine)  # every visit was committed on the fleet
        assert fleet.free_at[r] <= fleet.shift_end_s
    # nothing is worth a trip when no visit has value
    fleet = _fresh_fleet(tiny_world, day)
    none = milp_rounds(
        agents,
        np.zeros(n),
        fleet,
        now,
        lambda a, _: 0.0,
        np.full(len(fleet.loc), 2.6),
        1.2,
        reserve,
        load_plan_config().milp,
    )
    assert none == []


def test_dispatch_program_collects_at_least_the_greedy_value(tiny_world: World) -> None:
    """With costs near zero the program is a capacity-limited pick; it must not do worse."""
    day, reserve = 5, 4
    n = len(tiny_world.agents)
    value = np.random.default_rng(1).gamma(1.0, 100.0, n)
    now = day * 86400 + 8 * 3600
    ranked = [int(a) for a in np.argsort(-value)]
    greedy = plan_rounds(ranked, _fresh_fleet(tiny_world, day), now, lambda a, _: 0.0, reserve)
    fleet = _fresh_fleet(tiny_world, day)
    milp = milp_rounds(
        ranked,
        value,
        fleet,
        now,
        lambda a, _: 0.0,
        np.full(len(fleet.loc), 1e-6),
        1e-6,
        reserve,
        load_plan_config().milp,
    )
    assert sum(value[v.agent] for v in milp) >= sum(value[v.agent] for v in greedy) - 1e-6


def test_deployed_is_the_status_quo_until_it_switches(
    tiny_world: World, tiny_episodes: dict[str, Episode]
) -> None:
    status_quo = tiny_episodes["fixed_round"]
    same = simulate(tiny_world, Deployed(FixedRound(), 10 * 24))
    assert same.visits.equals(status_quo.visits)
    switched = simulate(tiny_world, Deployed(make_policy("threshold", tiny_world), 10 * 24))
    before = switched.visits["planned_t"] < 10 * 24 * 3600
    assert switched.visits[before].equals(
        status_quo.visits[status_quo.visits["planned_t"] < 864000]
    )
    assert not switched.visits.equals(status_quo.visits)


@pytest.fixture(scope="module")
def jogan_episode(tiny_world: World, tiny_forecaster: Forecaster) -> tuple[Jogan, Episode]:
    jogan = Jogan(tiny_forecaster)
    return jogan, simulate(tiny_world, Deployed(jogan, 20 * 24))


def test_jogan_plans_from_the_forecast(jogan_episode: tuple[Jogan, Episode]) -> None:
    jogan, ep = jogan_episode
    trace = jogan.last
    assert trace is not None
    assert len(trace) == len(ep.ctx.agents)
    assert trace["hour"].iloc[0] % 24 == ep.ctx.ops.policies.plan_hour
    total = trace["cash_tk"] + trace["efloat_tk"]
    assert ((trace["target_cash_tk"] >= 0) & (trace["target_cash_tk"] <= total + 1e-6)).all()
    assert trace[["p_stockout_cash", "p_stockout_efloat"]].stack().between(0, 1).all()
    sent = trace["runner_id"].notna()
    assert trace.loc[sent, "candidate"].all()  # only candidates get a round visit
    rounds = ep.visits[(ep.visits["reason"] == "round") & (ep.visits["planned_t"] >= 20 * 86400)]
    assert len(rounds) > 0
    assert jogan.log.programs > 0
    assert jogan.log.fallbacks == 0
    assert ep.rejected == 0  # every planned visit fitted in execution


def test_jogan_is_deterministic(
    tiny_world: World, tiny_forecaster: Forecaster, jogan_episode: tuple[Jogan, Episode]
) -> None:
    again = simulate(tiny_world, Deployed(Jogan(tiny_forecaster), 20 * 24))
    assert again.visits.equals(jogan_episode[1].visits)
    assert np.array_equal(again.outcome, jogan_episode[1].outcome)


def test_jogan_needs_a_forecast_for_its_horizon(tiny_forecaster: Forecaster) -> None:
    with pytest.raises(ValueError, match="horizon"):
        Jogan(tiny_forecaster, load_plan_config({"horizon_hours": 7}))
