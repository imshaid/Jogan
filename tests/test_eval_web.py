"""The web app's impact numbers are an up-to-date copy of artifacts/metrics.json (D-025)."""

import json

from jogan.eval.web import METRICS, OUT, project, render


def test_the_committed_impact_file_matches_the_evaluation() -> None:
    assert OUT.read_text() == render(json.loads(METRICS.read_text())), "run `make impact`"


def test_every_projected_number_is_copied_from_the_evaluation() -> None:
    m = json.loads(METRICS.read_text())
    p = project(m)
    jogan = p["jogan"]
    assert (
        p["policies"][jogan]["test"]["lost_per_1000"]
        == m["policies"][jogan]["test"]["lost_per_1000"]
    )
    assert (
        p["versus"]["threshold"]["test"]["lost_per_1000"] == m["hypotheses"]["H2"]["lost_per_1000"]
    )
    assert p["oracle_gap"] == m["oracle_gap"]["test"]["lost_per_1000"]
    assert p["coverage_misses"]["cells"] == len(m["hypotheses"]["H3"]["misses"])
    assert set(p["hypotheses"]) == {"H1", "H2", "H3", "H4"}
    for b in p["baselines"]:
        verdict = m["hypotheses"]["H1"]["by_baseline"][b]["break_even_tk"]["verdict"]
        assert p["versus"][b]["test"]["break_even"] == verdict
