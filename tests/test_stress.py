"""Stress check: config, hub mapping and a run on a replicated tiny world (D-026)."""

import pytest

from jogan.eval.config import load_stress_config
from jogan.eval.stress import hub_of, run_stress
from jogan.sim.config import CONFIG_DIR, load_config
from tests.conftest import FAST
from tests.test_ops_costs import _untagged


def test_stress_config_loads_and_is_tagged() -> None:
    cfg = load_stress_config()
    sim = load_config(cfg.profile)
    assert len(sim.territories) * sim.replicas == 60
    assert cfg.warmup_days < (sim.end - sim.start).days
    assert cfg.models.profile == "full"  # the demo bundle's models (D-022)
    assert _untagged(CONFIG_DIR / "eval" / "stress.yaml") == []


def test_hub_of_maps_replicas_and_refuses_strangers() -> None:
    sim = load_config("stress")
    assert hub_of(["DHK01", "DHK10", "KUR03"], sim) == {
        "DHK01": "DHK",
        "DHK10": "DHK",
        "KUR03": "KUR",
    }
    assert hub_of(["GZP"], load_config("tiny")) == {"GZP": "GZP"}
    with pytest.raises(ValueError, match="replica"):
        hub_of(["XYZ01"], sim)


def test_stress_times_every_morning_on_a_replicated_world() -> None:
    cfg = load_stress_config(
        {"profile": "tiny", "seed": 1, "warmup_days": 24, "models": {"profile": "tiny", "seed": 0}}
    )
    out = run_stress(cfg, {"replicas": 2, "n_agents": 60}, FAST)  # not the 40 trained on
    world, mornings = out["world"], out["mornings"]
    assert (world["territories"], world["hubs"], world["plan_mornings"]) == (4, 2, 4)
    assert [m["date"] for m in mornings] == ["2026-03-25", "2026-03-26", "2026-03-27", "2026-03-28"]
    for m in mornings:
        assert m["morning_s"] >= m["plan_s"] >= m["solver_s"] >= 0
        assert m["programs"] <= world["territories"]
        assert m["visits"] <= m["candidates"]
    assert out["summary"]["visits"] > 0
    assert out["summary"]["fallbacks"] == 0
    assert out["meta"]["timing_only"] is True


def test_stress_refuses_hubs_the_models_never_saw() -> None:
    cfg = load_stress_config(
        {"profile": "dev", "seed": 0, "warmup_days": 24, "models": {"profile": "tiny", "seed": 0}}
    )
    with pytest.raises(ValueError, match="every hub"):
        run_stress(cfg, None, FAST)
