import pandas as pd
import pytest

from jogan.ops.env import Episode, simulate
from jogan.ops.policies import POLICIES, make_policy
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
