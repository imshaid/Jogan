"""Evaluation: paired statistics, break-even intervals, the report and the CLI."""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from jogan.eval.__main__ import main as eval_main
from jogan.eval.config import load_eval_config
from jogan.eval.report import mean_tree
from jogan.eval.run import eid_window, jogan_key, jogan_runs
from jogan.eval.stats import break_even, fieller, mean_interval, paired
from jogan.ops.policies import BASELINES
from jogan.plan.config import load_plan_config
from jogan.sim.config import CONFIG_DIR
from jogan.sim.world import World
from tests.test_ops_costs import _untagged


def test_eval_config_loads_and_is_tagged() -> None:
    cfg = load_eval_config()
    assert len(cfg.seeds) == 10
    assert min(cfg.seeds) >= 1000  # evaluation seeds, apart from development seeds (D-010)
    assert load_plan_config().lost_customer_value_tk in cfg.lost_customer_values_tk
    assert _untagged(CONFIG_DIR / "eval" / "base.yaml") == []


def test_mean_interval_matches_scipy() -> None:
    x = np.array([1.0, 3.0, 2.5, 4.0, 2.0])
    out = mean_interval(x, 0.95)
    low, high = stats.t.interval(0.95, len(x) - 1, loc=x.mean(), scale=stats.sem(x))
    assert out["low"] == pytest.approx(low, abs=1e-4)
    assert out["high"] == pytest.approx(high, abs=1e-4)
    assert mean_interval([5.0], 0.95)["low"] is None
    assert paired([3.0, 3.1, 2.9], [1.0, 1.1, 0.9], 0.95)["sign"] == "higher"


def test_fieller_interval_covers_the_ratio_and_can_be_unbounded() -> None:
    rng = np.random.default_rng(0)
    den = rng.normal(10.0, 1.0, 10)
    num = 3.0 * den + rng.normal(0.0, 0.5, 10)
    out = fieller(num, den, 0.95)
    assert out["bounded"]
    assert out["low"] < out["value"] < out["high"]
    assert out["low"] < 3.0 < out["high"]
    noisy = fieller(num, rng.normal(0.0, 5.0, 10), 0.95)  # denominator not away from zero
    assert not noisy["bounded"]
    assert noisy["low"] is None


def test_break_even_verdicts() -> None:
    # A costs Tk 100 more and loses 10 fewer requests on every seed: cheaper above Tk 10
    out = break_even([200.0, 210.0, 190.0], [5, 6, 4], [100.0, 110.0, 90.0], [15, 16, 14], 0.95)
    assert out["verdict"] == "a cheaper above the value"
    assert out["value"] == pytest.approx(10.0)
    dominated = break_even([90.0, 95.0], [5, 6], [100.0, 110.0], [15, 16], 0.95)
    assert dominated["verdict"] == "a cheaper at every value"
    assert dominated["value"] is None
    assert dominated["seeds_a_cheaper_and_fewer_lost"] == 2


def test_runs_and_windows(tiny_world: World) -> None:
    cfg = load_eval_config({"lost_customer_values_tk": [0, 20]})
    runs = jogan_runs(cfg, 20)
    assert list(runs) == ["jogan@0", "jogan@20", "jogan_greedy@20", "jogan_two_sided@20"]
    assert jogan_key(5.5) == "jogan@5.5"
    # tiny's test window starts two days after Eid-ul-Fitr (21 March 2026)
    first, last = eid_window(tiny_world.calendar, (tiny_world.config.start, tiny_world.config.end))
    assert (first.isoformat(), last.isoformat()) == ("2026-03-11", "2026-03-24")


def test_mean_tree_averages_numbers_and_drops_lists() -> None:
    trees = [{"a": 1, "b": {"c": 2.0, "d": [1]}, "e": "x"}, {"a": 3, "b": {"c": 4.0, "d": [2]}}]
    assert mean_tree(trees) == {"a": 2.0, "b": {"c": 3.0}}


def test_cli_writes_the_report(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    out = tmp_path / "metrics.json"
    args = ["--profile", "tiny", "--seeds", "0", "1", "--rounds", "20", "--values", "0", "20"]
    eval_main([*args, "--workers", "1", "--out", str(out)])
    body = json.loads(out.read_text())
    assert body["meta"]["seeds"] == [0, 1]
    assert set(body["policies"]) >= {*BASELINES, "oracle", "jogan@20", "jogan_greedy@20"}
    test = body["policies"]["jogan@20"]["test"]
    assert test["lost_per_1000"]["n"] == 2
    assert set(test["known_cost_tk"]) == {"low", "mid", "high"}
    by_value = body["comparison"]["by_value"]
    assert set(by_value) == {"0", "20"}
    assert set(by_value["20"]) == set(BASELINES)
    be = by_value["20"]["fixed_round"]["test"]["break_even_tk"]["mid"]
    assert be["verdict"]
    assert set(body["hypotheses"]) == {"H1", "H2", "H3", "H4"}
    assert isinstance(body["does_not_win"], list)
    for case in body["does_not_win"]:
        assert case["scope"] in {"period", "cost setting", "agent group"}
    assert body["fairness"]["best_baseline"] in BASELINES
    assert "cash" in body["forecast"]["forecast"]
    assert "wrote" in capsys.readouterr().out
