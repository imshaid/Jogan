import pandas as pd
import pytest

from jogan.api.bundle import Bundle, build_bundle
from jogan.forecast.backtest import Dataset, Forecaster, build_dataset, fit_forecaster, truth_panels
from jogan.forecast.config import load_forecast_config
from jogan.forecast.panel import Panel, panel_from_frame
from jogan.ops.env import Episode, simulate
from jogan.ops.io import observed_hourly, truth_hourly_frame
from jogan.ops.policies import POLICIES, STATUS_QUO, make_policy
from jogan.sim.config import load_config
from jogan.sim.world import World, build_world


@pytest.fixture(scope="session")
def tiny_world() -> World:
    return build_world(load_config("tiny"), seed=0)


@pytest.fixture(scope="session")
def tiny_worlds() -> list[World]:
    """Several tiny seeds, pooled by pattern tests so one lucky draw cannot pass them."""
    return [build_world(load_config("tiny"), seed=seed) for seed in range(4)]


@pytest.fixture(scope="session")
def dev_world() -> World:
    return build_world(load_config("dev"), seed=0)


def normal_demand(world: World | list[World]) -> pd.DataFrame:
    """Attempts of agents without an injected anomaly, with day and hour columns.

    Given several worlds, their attempts are stacked with a ``seed`` column to tell them apart.
    """
    if isinstance(world, list):
        parts = [normal_demand(w).assign(seed=w.seed) for w in world]
        out = pd.concat(parts, ignore_index=True)
        out["agent_id"] = out["agent_id"].astype(str)
        return out
    d = world.demand[~world.demand["agent_id"].isin(world.anomalies["agent_id"])].copy()
    d["date"] = d["ts"].dt.normalize()
    d["hour"] = d["ts"].dt.hour
    return d


@pytest.fixture(scope="session")
def tiny_episodes(tiny_world: World) -> dict[str, Episode]:
    """Every baseline and the oracle, run once on the tiny world (seed 0)."""
    return {name: simulate(tiny_world, make_policy(name, tiny_world)) for name in POLICIES}


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


@pytest.fixture(scope="session")
def tiny_bundle() -> Bundle:
    """The served bundle on the tiny world (seed 0), shared by the API tests."""
    return build_bundle("tiny", 0, FAST)
