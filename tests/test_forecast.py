"""Drain forecast: leakage, labels and censoring, conformal calibration, backtest, CLI."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from jogan.forecast.__main__ import main as forecast_main
from jogan.forecast.backtest import (
    Dataset,
    Forecaster,
    build_dataset,
    censoring_report,
    evaluate,
    fit_forecaster,
    predict_all,
    split_of_origins,
    truth_panels,
)
from jogan.forecast.config import SPLITS, load_forecast_config
from jogan.forecast.features import build_features, nan_quantiles, origin_grid
from jogan.forecast.model import calibrate, stockout_probability, to_tk
from jogan.forecast.panel import NEVER, Panel, panel_from_frame, panel_from_history
from jogan.forecast.targets import drain_path, peak_drains
from jogan.ops.__main__ import main as ops_main
from jogan.ops.env import Episode
from jogan.ops.io import observed_hourly, truth_hourly_frame
from jogan.ops.policies import STATUS_QUO
from jogan.sim.__main__ import main as sim_main
from jogan.sim.config import CONFIG_DIR
from jogan.sim.world import World
from tests.test_ops_costs import _untagged

FAST = {"lightgbm": {"num_boost_round": 30, "num_threads": 4}}


@pytest.fixture(scope="session")
def tiny_episode(tiny_episodes: dict[str, Episode]) -> Episode:
    return tiny_episodes[STATUS_QUO]


@pytest.fixture(scope="session")
def tiny_panel(tiny_episode: Episode) -> Panel:
    ep = tiny_episode
    ids = ep.ctx.agents["agent_id"].tolist()
    return panel_from_frame(observed_hourly(ep), ids, ep.world.config.start, ep.n_hours)


@pytest.fixture(scope="session")
def tiny_truth(tiny_episode: Episode) -> dict:
    ep = tiny_episode
    ids = ep.ctx.agents["agent_id"].tolist()
    return truth_panels(truth_hourly_frame(ep), ids, ep.world.config.start, ep.n_hours)


@pytest.fixture(scope="session")
def tiny_dataset(tiny_world: World, tiny_panel: Panel) -> Dataset:
    cfg = load_forecast_config(FAST)
    w = tiny_world
    return build_dataset(tiny_panel, w.calendar, w.agents, cfg, cfg.splits["tiny"], w.config.start)


@pytest.fixture(scope="session")
def tiny_forecaster(tiny_dataset: Dataset) -> Forecaster:
    return fit_forecaster(tiny_dataset)


def test_forecast_config_loads_and_validates() -> None:
    cfg = load_forecast_config()
    assert cfg.config_hash() == load_forecast_config().config_hash()
    assert cfg.intervals()[-1] == (0.05, 0.95)
    overlap = {"train": ["2026-03-01", "2026-03-10"], "calibration": ["2026-03-10", "2026-03-12"]}
    with pytest.raises(ValidationError):
        load_forecast_config({"splits": {"tiny": overlap}})
    with pytest.raises(ValidationError):
        load_forecast_config({"quantiles": [0.9, 0.5]})
    with pytest.raises(ValidationError):
        load_forecast_config({"censoring": {"strategy": "guess"}})


def test_every_forecast_number_is_tagged() -> None:
    assert _untagged(CONFIG_DIR / "forecast" / "base.yaml") == []


def test_peak_drain_matches_a_hand_example() -> None:
    # cash-outs minus cash-ins per hour: the path is 100, -200, 0, 50
    net = np.array([[100.0, -300.0, 200.0, 50.0]])
    path = drain_path(net, np.array([0]), 4)
    assert path.tolist() == [[[100.0, -200.0, 0.0, 50.0]]]
    peaks = peak_drains(path, 4)
    assert peaks["cash"].tolist() == [[100.0]]
    assert peaks["efloat"].tolist() == [[200.0]]
    assert peak_drains(path, 1)["efloat"].tolist() == [[0.0]]


def test_nan_quantiles_match_numpy() -> None:
    rng = np.random.default_rng(0)
    a = rng.gamma(2.0, 100.0, (50, 28))
    a[rng.random(a.shape) < 0.2] = np.nan
    levels = (0.05, 0.5, 0.9, 0.99)
    q, count = nan_quantiles(a, levels)
    assert np.allclose(q, np.nanquantile(a, levels, axis=1).T)
    assert (count == (~np.isnan(a)).sum(axis=1)).all()


def test_panel_matches_the_simulation_history(tiny_episode: Episode, tiny_panel: Panel) -> None:
    """The file path and the in-simulation path give the same panel (no train/serve skew)."""
    live = panel_from_history(tiny_episode.history)
    for name in ("co_n", "co_tk", "ci_n", "ci_tk", "cash", "efloat", "arrive"):
        assert np.array_equal(getattr(live, name), getattr(tiny_panel, name), equal_nan=True), name
    gone = tiny_episode.history.missing
    assert (tiny_panel.arrive[gone] == NEVER).all()
    assert np.isnan(tiny_panel.cash[gone]).all()


def test_panel_refuses_ground_truth(tiny_episode: Episode) -> None:
    ep = tiny_episode
    frame = observed_hourly(ep).assign(req_co_tk=0)
    with pytest.raises(ValueError, match="unexpected columns"):
        panel_from_frame(frame, ep.ctx.agents["agent_id"].tolist(), ep.world.config.start, 1)


def _perturbed(panel: Panel, cut: int, rng: np.random.Generator) -> Panel:
    """Every record that arrives after ``cut`` gets other values and a later arrival."""
    late = panel.arrive > cut
    fields = {}
    for name in ("co_n", "co_tk", "ci_n", "ci_tk", "cash", "efloat"):
        x = getattr(panel, name).copy()
        x[late] = rng.integers(0, 10**6, late.sum())  # whole Tk, like the log
        fields[name] = x
    arrive = panel.arrive.copy()
    arrive[late & (arrive < NEVER)] += rng.integers(0, 30, (late & (arrive < NEVER)).sum())
    return Panel(arrive=arrive, **fields)


@pytest.mark.parametrize("pick", [0, 1, 2])
def test_features_never_use_a_record_before_it_arrives(
    tiny_world: World, tiny_panel: Panel, pick: int
) -> None:
    cfg = load_forecast_config()
    w = tiny_world
    origins = origin_grid(w.config.n_days, cfg.origin_hours, cfg.max_horizon)
    hours = np.arange(tiny_panel.n_hours)[None, :]
    late = tiny_panel.received & (tiny_panel.arrive > hours + 1)
    late_days = np.unique(np.nonzero(late)[1] // 24)
    late_days = late_days[(late_days >= 7) & (late_days < w.config.n_days - 2)]
    day = late_days[pick * (len(late_days) - 1) // 2]
    cut = (day + 1) * 24 + cfg.origin_hours[2]  # the next day, before the late day arrives
    delayed = (hours < cut) & (tiny_panel.arrive > cut) & (tiny_panel.arrive < NEVER)
    assert delayed.any()
    rng = np.random.default_rng(pick)
    a = build_features(tiny_panel, w.calendar, w.agents, cfg, origins)
    b = build_features(_perturbed(tiny_panel, cut, rng), w.calendar, w.agents, cfg, origins)
    rows = a.origin_of_row <= cut
    for h in cfg.horizons_hours:
        pd.testing.assert_frame_equal(a.matrix(h)[rows], b.matrix(h)[rows])
        for side in ("cash", "efloat"):
            assert np.array_equal(a.empirical[h][side][rows], b.empirical[h][side][rows], True)
            assert np.array_equal(a.naive[h][side][rows], b.naive[h][side][rows], True)
    later = a.origin_of_row > cut + 24
    assert not a.matrix(24)[later].equals(b.matrix(24)[later])  # the perturbation bites


def test_features_hold_no_ground_truth(tiny_world: World, tiny_dataset: Dataset) -> None:
    truth_names = set(tiny_world.agent_truth.columns) | set(tiny_world.demand.columns)
    truth_names |= {"req_co_tk", "req_ci_tk", "lost_co_n", "lost_ci_n", "cash_tk", "efloat_tk"}
    truth_names -= {"agent_id"}
    columns = set(tiny_dataset.features.matrix(24).columns)
    assert not columns & truth_names
    assert "agent_id" not in columns


def test_splits_keep_every_window_inside(tiny_world: World) -> None:
    cfg = load_forecast_config()
    start = tiny_world.config.start
    splits = cfg.splits["tiny"]
    origins = origin_grid(tiny_world.config.n_days, cfg.origin_hours, cfg.max_horizon)
    which = split_of_origins(origins, start, splits, cfg)
    for name in SPLITS:
        first, last = getattr(splits, name)
        lo = (first - start).days * 24 + (cfg.warmup_days * 24 if name == "train" else 0)
        hi = ((last - start).days + 1) * 24
        t = origins[which == name]
        assert len(t) > 0
        assert (t >= lo).all()
        assert (t + cfg.max_horizon <= hi).all()


def test_censoring_flags_find_lost_hours_and_cut_the_bias(
    tiny_dataset: Dataset, tiny_truth: dict
) -> None:
    true = {}
    for h in tiny_dataset.cfg.horizons_hours:
        net = tiny_truth["req_co_tk"] - tiny_truth["req_ci_tk"]
        path = drain_path(net, tiny_dataset.features.origins, h)
        true[h] = {s: v.T.ravel() for s, v in peak_drains(path, h).items()}
    report = censoring_report(tiny_dataset, tiny_truth, true)
    for side in ("cash", "efloat"):
        assert report["flags"][side]["recall"] > 0.6
        bias = report["label_bias"][side]["24"]["all"]
        assert bias["served"]["relative"] < -0.15  # served flows hide demand
        # tiny is the Eid-ul-Fitr month, the hardest case: about 30% of the Tk asked is lost
        assert abs(bias["estimated"]["relative"]) < 0.6 * abs(bias["served"]["relative"])


def test_conformal_shifts_reach_nominal_coverage() -> None:
    rng = np.random.default_rng(1)
    levels = (0.05, 0.5, 0.9, 0.99)
    cfg = load_forecast_config({"conformal": {"min_group_rows": 500}})

    def draw(n: int) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        setting = rng.choice(["urban", "rural"], n, p=[0.9, 0.1])
        size = rng.choice(["small", "large"], n)
        scale = np.where(setting == "rural", 2.0, 1.0)  # rural is noisier than the model knows
        log_y = rng.normal(5.0, 0.5 * scale)
        pred = np.tile(5.0 + 0.5 * np.array([-1.0, 0.0, 1.0, 1.5]), (n, 1))  # miscalibrated
        return pred, log_y, pd.DataFrame({"setting": setting, "size_class": size})

    calib = calibrate(*draw(4000), levels, cfg.conformal)
    assert set(calib.by_group) == {"urban|small", "urban|large"}  # rural falls back to pooled
    pred, log_y, groups = draw(40000)
    q = calib.apply(pred, groups)
    urban = (groups["setting"] == "urban").to_numpy()
    coverage = (log_y[urban, None] <= q[urban]).mean(axis=0)
    assert np.allclose(coverage, levels, atol=0.02)
    assert (np.diff(to_tk(q), axis=1) >= 0).all()


def test_stockout_probability_reads_the_quantile_grid() -> None:
    levels = (0.1, 0.5, 0.9)
    q = np.array([[100.0, 200.0, 400.0]] * 6)
    balance = np.array([0.0, 50.0, 100.0, 200.0, 300.0, 1000.0])
    p = stockout_probability(q, levels, balance)
    assert np.allclose(p, [1.0, 0.95, 0.9, 0.5, 0.3, 0.05])
    assert (np.diff(p) <= 0).all()


def test_backtest_predicts_monotone_quantiles_and_scores_every_method(
    tiny_dataset: Dataset, tiny_forecaster: Forecaster, tiny_truth: dict
) -> None:
    ds, cfg = tiny_dataset, tiny_dataset.cfg
    train, cal, test = (ds.split == s for s in SPLITS)
    assert not (train & cal).any()
    assert not (cal & test).any()
    assert not (train & test).any()
    preds = predict_all(ds, tiny_forecaster, test)
    for p in preds.values():
        assert np.isfinite(p["model_cqr"]).all()
        for name in ("model", "model_cqr", "naive_cqr"):
            q = p[name][np.isfinite(p[name]).all(axis=1)]  # naive: no window a week or a day ago
            assert (q >= 0).all(), name
            assert (np.diff(q, axis=1) >= 0).all(), name
    result = evaluate(ds, tiny_forecaster, tiny_truth)
    entry = result["forecast"]["cash"]["24"]
    assert set(entry["methods"]) == {"model", "model_cqr", "empirical", "naive_cqr"}
    assert set(entry["intervals"]["truth"]) == {"50", "80", "90"}
    assert set(entry["groups"]["size_class"]) == {"small", "medium", "large"}
    assert 0.0 <= entry["stockout"]["model_cqr"]["brier"] <= 1.0
    # the calibration split is covered at least nominally for upper levels, by construction
    x = ds.features.matrix(24)[cal]
    model = tiny_forecaster.models[24, "cash"]
    q = model.predict(x, ds.groups[cal])
    y = ds.labels[24]["cash"][cal]
    upper = [i for i, lv in enumerate(cfg.quantiles) if lv >= 0.5]
    for i in upper:
        assert (y <= q[:, i]).mean() >= cfg.quantiles[i] - 0.02


def test_training_is_deterministic(tiny_dataset: Dataset, tiny_forecaster: Forecaster) -> None:
    again = fit_forecaster(tiny_dataset)
    test = tiny_dataset.split == "test"
    first, second = (
        predict_all(tiny_dataset, tiny_forecaster, test),
        predict_all(tiny_dataset, again, test),
    )
    for key, p in first.items():
        assert np.array_equal(p["model_cqr"], second[key]["model_cqr"]), key


def test_cli_writes_metrics(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    sim_main(["--profile", "tiny", "--seed", "2", "--out", str(tmp_path / "tiny" / "seed2")])
    ops_main(["--profile", "tiny", "--seed", "2", "--write", "--root", str(tmp_path)])
    forecast_main(["--profile", "tiny", "--seed", "2", "--rounds", "5", "--root", str(tmp_path)])
    out = tmp_path / "tiny" / "seed2" / "forecast" / "metrics_impute.json"
    body = json.loads(out.read_text())
    assert body["meta"]["censoring"] == "impute"
    assert body["meta"]["rows"]["test"] > 0
    assert set(body["forecast"]) == {"cash", "efloat"}
    assert "label bias" in capsys.readouterr().out
