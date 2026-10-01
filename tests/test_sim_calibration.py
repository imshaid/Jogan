import numpy as np
import pytest

from jogan.sim.calibration import (
    achieved,
    calibrate,
    capped_lognormal_mean,
    derive_targets,
    targets_flat,
)
from jogan.sim.config import load_config


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
