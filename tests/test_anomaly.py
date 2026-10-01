"""Anomaly flag on a synthetic log: patterns found, territory-wide days ignored, no leak."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from jogan.detect.anomaly import day_features, evaluate, fit_detector
from jogan.explain.config import load_explain_config
from jogan.forecast.panel import NEVER, Panel

CFG = load_explain_config().anomaly
N_AGENTS, N_DAYS = 60, 50
START = dt.date(2026, 1, 1)
TRAIN, TEST = np.arange(0, 40), np.arange(40, 50)
NIGHT, SPIKE, TICKET = 3, 7, 11
DAY, PAYDAY = 45, 46  # injected patterns; territory T2's payday


def hours_of(day: int, h0: int, h1: int) -> slice:
    return slice(day * 24 + h0, day * 24 + h1)


@pytest.fixture(scope="module")
def agents() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "agent_id": [f"A-{i:03d}" for i in range(N_AGENTS)],
            "territory": ["T1"] * 30 + ["T2"] * 30,
            "setting": "rural",
            "open_hour": 8,
            "close_hour": 20,
        }
    )


@pytest.fixture(scope="module")
def panel() -> Panel:
    rng = np.random.default_rng(0)
    n_hours = N_DAYS * 24
    open_ = np.tile((np.arange(24) >= 8) & (np.arange(24) < 20), N_DAYS)
    scale = rng.uniform(0.5, 2.0, (N_AGENTS, 1))
    co_n = rng.poisson(2.0 * scale * open_).astype(float)
    ci_n = rng.poisson(1.5 * scale * open_).astype(float)
    co_n[NIGHT, hours_of(DAY, 2, 3)] = 3
    co_n[SPIKE, hours_of(DAY, 8, 20)] *= 4
    ci_n[SPIKE, hours_of(DAY, 8, 20)] *= 4
    co_n[30:, hours_of(PAYDAY, 8, 20)] *= 2
    ci_n[30:, hours_of(PAYDAY, 8, 20)] *= 2
    # an agent's mean cash-out varies from day to day, and from hour to hour within a day
    daily = np.repeat(rng.lognormal(0.0, 0.25, (N_AGENTS, N_DAYS)), 24, axis=1)
    ticket = rng.uniform(800, 3000, (N_AGENTS, 1)) * daily * rng.uniform(0.8, 1.2, daily.shape)
    co_tk = co_n * ticket
    co_tk[TICKET, hours_of(DAY, 0, 24)] *= 5
    arrive = np.tile(np.arange(1, n_hours + 1), (N_AGENTS, 1))
    return Panel(co_n, co_tk, ci_n, ci_n * 1500, np.ones_like(co_n), np.ones_like(co_n), arrive)


def test_injected_patterns_are_flagged_and_explained(panel: Panel, agents: pd.DataFrame) -> None:
    feats = day_features(panel, agents, CFG)
    det = fit_detector(feats, agents, TRAIN, CFG)
    flags = det.flags(feats, DAY, START + dt.timedelta(DAY))
    assert {NIGHT, SPIKE, TICKET} <= set(flags)
    assert len(flags) <= 5  # at most two others among 60
    assert flags[NIGHT]["items"][0] == {"feature": "night_n", "value": 3.0}
    assert "volume" in {i["feature"] for i in flags[SPIKE]["items"]}
    assert "ticket" in {i["feature"] for i in flags[TICKET]["items"]}
    assert flags[NIGHT]["date"] == "2026-02-15"
    assert flags[NIGHT]["score"] > 1  # rule hits rank above every forest score

    # a payday that doubles a whole territory is not unusual for any one agent in it
    assert len(det.flags(feats, PAYDAY, START + dt.timedelta(PAYDAY))) <= 2


def test_features_use_only_records_that_have_arrived(panel: Panel, agents: pd.DataFrame) -> None:
    day = DAY
    now = (day + 1) * 24 + 8  # the next morning's plan hour
    late = (5, day * 24 + 12)  # a record of that day that arrives after the plan hour
    arrive = panel.arrive.copy()
    arrive[late] = now + 3
    base = Panel(panel.co_n, panel.co_tk, panel.ci_n, panel.ci_tk, panel.cash, panel.efloat, arrive)
    before = day_features(base, agents, CFG, now=now)

    co_n, co_tk = panel.co_n.copy(), panel.co_tk.copy()
    co_n[:, now:], co_tk[:, now:] = 50, 10**6  # the future
    co_n[late], co_tk[late] = 99, 10**7  # the late record
    moved = Panel(co_n, co_tk, panel.ci_n, panel.ci_tk, panel.cash, panel.efloat, arrive)
    after = day_features(moved, agents, CFG, now=now)
    for name, x in before.values.items():
        np.testing.assert_array_equal(x[:, : day + 1], after.values[name][:, : day + 1], name)
    np.testing.assert_array_equal(before.valid[:, : day + 1], after.valid[:, : day + 1])

    missing = arrive.copy()
    missing[7, hours_of(day, 0, 24)] = NEVER  # a lost day is not scored
    gone = Panel(
        panel.co_n, panel.co_tk, panel.ci_n, panel.ci_tk, panel.cash, panel.efloat, missing
    )
    assert not day_features(gone, agents, CFG, now=now).valid[7, day]


def test_evaluation_scores_the_test_days_against_the_injected_truth(
    panel: Panel, agents: pd.DataFrame
) -> None:
    date = START + dt.timedelta(DAY)
    truth = pd.DataFrame(
        {
            "agent_id": [f"A-{i:03d}" for i in (NIGHT, SPIKE, TICKET)],
            "pattern": ["night", "spike", "split"],
            "first_date": [date] * 3,
            "last_date": [date] * 3,
        }
    )
    window = lambda days: (START + dt.timedelta(int(days[0])), START + dt.timedelta(int(days[-1])))  # noqa: E731
    out = evaluate(panel, agents, truth, START, window(TRAIN), window(TEST), CFG)
    assert out["anomalous_agent_days"] == 3
    assert out["precision_at_k"]["5"] >= 0.6
    assert out["windows"] == 3
    assert out["windows_detected"] == 3
    assert out["windows_by_pattern"] == {"night": [1, 1], "spike": [1, 1], "split": [1, 1]}
    assert out["flagged_true"] == 3
