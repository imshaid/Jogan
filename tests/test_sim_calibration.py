import numpy as np
import pytest

from jogan.sim.calendar import as_float
from jogan.sim.calibration import (
    achieved,
    calibrate,
    capped_lognormal_mean,
    derive_targets,
    targets_flat,
)
from jogan.sim.config import TX_TYPES, load_config
from jogan.sim.demand import festival_shape
from jogan.sim.world import World

from .conftest import normal_demand


def test_targets_are_derived_from_official_figures() -> None:
    cal = load_config("tiny").calibration
    t = derive_targets(cal)
    jul = cal.agent_transactions["2026-07"]
    assert t.ticket["CO"] == pytest.approx(jul.cash_out_amount_mtk * 1e6 / jul.cash_out_count)
    assert t.co_ci_count_ratio == pytest.approx(jul.cash_out_count / jul.cash_in_count)
    # Order-of-magnitude guards against a unit slip (million Tk vs Tk).
    assert 1_000 < t.ticket["CO"] < t.ticket["CI"] < 5_000
    assert 5 < t.volume_per_agent_day < 15
    assert t.eid_amount_ratio["CO"] > t.eid_count_ratio["CO"] > 1


def test_solver_hits_every_target_in_the_expected_network() -> None:
    cfg = load_config("tiny")
    got = achieved(cfg, calibrate(cfg))
    for key, target in targets_flat(cfg.calibration).items():
        assert got[key] == pytest.approx(target, rel=1e-6), key


def test_capped_lognormal_mean_matches_monte_carlo() -> None:
    rng = np.random.default_rng(0)
    x = rng.lognormal(7.0, 0.9, 400_000)
    assert float(capped_lognormal_mean(7.0, 0.9, 3_000)) == pytest.approx(
        np.minimum(x, 3_000).mean(), rel=0.01
    )


def test_realized_attempts_match_expected_intensity(tiny_world: World) -> None:
    normal = ~tiny_world.agents["agent_id"].isin(tiny_world.anomalies["agent_id"]).to_numpy()
    expected = tiny_world.expected[normal].sum()
    assert len(normal_demand(tiny_world)) == pytest.approx(expected, rel=0.04)


@pytest.mark.parametrize("side", TX_TYPES)
def test_realized_tickets_match_bb_means_outside_eid_surge(dev_world: World, side: str) -> None:
    cfg = dev_world.config
    g = festival_shape(as_float(dev_world.calendar["days_to_eid"]), cfg.festival)
    plain_days = dev_world.calendar.loc[g == 0, "date"]
    d = normal_demand(dev_world)
    d = d[d["date"].isin(plain_days) & (d["tx_type"] == side)]
    target = derive_targets(cfg.calibration).ticket[side]
    assert d["amount_tk"].mean() == pytest.approx(target, rel=0.03)
