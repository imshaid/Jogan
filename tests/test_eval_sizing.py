"""Size of the problem from Bangladesh Bank figures (``make sizing``)."""

import json

from jogan.eval.sizing import SIZING, build, month_sizing
from jogan.sim.config import CONFIG_DIR
from tests.test_ops_costs import _untagged


def test_sizing_config_is_tagged() -> None:
    assert _untagged(CONFIG_DIR / "sizing" / "base.yaml") == []


def test_turned_away_comes_on_top_of_the_served_total() -> None:
    tx = {
        "cash_out_count": 99,
        "cash_out_amount_mtk": 9.9,
        "cash_in_count": 0,
        "cash_in_amount_mtk": 0.0,
    }
    out = month_sizing(tx, [0.01], {"CO": 4.0, "CI": 4.0})["by_rate"]["0.01"]
    # 99 served and 1 turned away is 1% of 100 attempts
    assert out["requests"] == 1
    assert out["tk"] == 100_000
    assert out["agent_commission_tk"] == 400


def test_committed_sizing_matches_the_configs() -> None:
    assert json.loads(SIZING.read_text()) == build(), "stale: run `make sizing`"
