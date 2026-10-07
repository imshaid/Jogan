"""Business KPIs: paired differences, scaled to 1,000 agents and 30 days (D-033)."""

import pytest

from jogan.eval.business import business_kpis, events


def _row(lost: int, km: float, days: int = 15) -> dict:
    return {
        "window": {"days": days},
        "service": {"lost": lost, "lost_tk": {"CO": 100 * lost, "CI": 50 * lost}},
        "operations": {"runner_km": km, "self_refills": 3},
        "cost_tk": {
            "lost_commission": 0.6 * lost,
            "runner_time": 10.0,
            "runner_fuel": 2 * km,
            "known_total_by_salary": {"low": 0.0, "mid": 0.6 * lost + 10 + 2 * km, "high": 0.0},
        },
    }


def _seed(jogan: int, quo: int, agents: int = 500) -> dict:
    return {
        "agents": agents,
        "policies": {
            "jogan@20": {"test": _row(jogan, 90.0)},
            "fixed_round": {"test": _row(quo, 100.0)},
        },
    }


def test_kpis_are_paired_differences_scaled_to_1000_agents_a_month() -> None:
    seeds = [_seed(10, 14), _seed(11, 14), _seed(9, 14)]
    out = business_kpis(seeds, "jogan@20", ("fixed_round",), ["test"], 0.95)
    kpis = out["versus"]["fixed_round"]["test"]["kpis"]
    assert kpis["failed_requests"]["window"]["mean"] == pytest.approx(-4.0)
    assert kpis["failed_requests"]["window"]["sign"] == "lower"
    # 1,000 / 500 agents x 30 / 15 days = 4
    assert kpis["failed_requests"]["per_1000_agents_month"]["mean"] == pytest.approx(-16.0)
    assert kpis["value_turned_away_tk"]["window"]["mean"] == pytest.approx(-600.0)
    assert kpis["runner_cost_tk"]["window"]["mean"] == pytest.approx(-20.0)
    assert kpis["agents_own_bank_trips"]["window"]["sign"] == "no significant difference"


def test_seeds_must_agree_on_the_agent_count() -> None:
    with pytest.raises(ValueError, match="agent count"):
        business_kpis([_seed(1, 2), _seed(1, 2, agents=600)], "jogan@20", ("fixed_round",),
                      ["test"], 0.95)  # fmt: skip


def test_events_compare_visits_and_losses_per_day_type() -> None:
    def seed(jogan_visits: int) -> dict:
        def by(visits: int, lost: float) -> dict:
            row = {"days": 2, "requests": 100, "lost": 1, "lost_per_1000": lost,
                   "runner_visits": visits, "self_refills": 4}  # fmt: skip
            return {"test": {"by_day_type": {"eid": row}}}

        return {"policies": {"jogan@20": by(jogan_visits, 50.0), "fixed_round": by(10, 80.0)}}

    out = events([seed(20), seed(22), seed(18)], "jogan@20", ("fixed_round",), "test", 0.95)
    eid = out["types"]["eid"]
    assert eid["days"] == 2
    assert eid["policies"]["jogan@20"]["visits_per_day"]["mean"] == pytest.approx(10.0)
    assert eid["policies"]["fixed_round"]["own_bank_trips_per_day"]["mean"] == pytest.approx(2.0)
    assert eid["versus"]["fixed_round"]["visits_per_day"]["mean"] == pytest.approx(5.0)
    assert eid["versus"]["fixed_round"]["lost_per_1000"]["mean"] == pytest.approx(-30.0)
