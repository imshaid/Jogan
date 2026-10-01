"""Baseline policies: what they may see, what they achieve, and the status-quo log."""

import dataclasses
import json
from pathlib import Path

import pandas as pd
import pytest

from jogan.ops.__main__ import main
from jogan.ops.env import Context, Episode, Observation, simulate
from jogan.ops.fleet import Visit
from jogan.ops.metrics import summarize
from jogan.ops.policies import BASELINES, POLICIES, STATUS_QUO, UPPER_BOUND, Planned, make_policy
from jogan.sim.config import load_config
from jogan.sim.world import World, build_world


@pytest.mark.parametrize("seed", [0, 1])
def test_oracle_loses_fewer_requests_than_every_baseline(seed: int) -> None:
    world = build_world(load_config("tiny"), seed)
    lost = {
        name: summarize(simulate(world, make_policy(name, world)))["service"]["lost"]
        for name in POLICIES
    }
    oracle = lost.pop(UPPER_BOUND)
    assert set(lost) == set(BASELINES)
    assert oracle < min(lost.values())


def test_status_quo_rarely_turns_customers_away(tiny_episodes: dict[str, Episode]) -> None:
    """Shape of the ANA Bangladesh finding: a median of zero denials per agent-day (D-016)."""
    s = summarize(tiny_episodes[STATUS_QUO])["service"]
    assert s["median_lost_per_agent_day"] == 0
    assert 0.1 < s["agent_days_with_loss_share"] < 0.6


def test_fixed_round_reaches_every_agent(tiny_episodes: dict[str, Episode]) -> None:
    v = tiny_episodes["fixed_round"].visits
    rounds = v[v["reason"] == "round"]
    assert set(rounds["agent"]) == set(range(len(tiny_episodes["fixed_round"].ctx.agents)))
    assert {"round", "call"} <= set(v["reason"])


class _Spy(Planned):
    """Records what the environment hands a policy."""

    name = "spy"

    def reset(self, ctx: Context) -> None:
        super().reset(ctx)
        self.context_fields = {f.name for f in dataclasses.fields(ctx)}
        self.leaks: list[int] = []

    def decide(self, obs: Observation) -> list[Visit]:
        visible = obs.history.available(obs.hour, 0, obs.history.missing.shape[1])
        if visible[:, obs.hour :].any() or obs.history.co_n[:, obs.hour :].any():
            self.leaks.append(obs.hour)
        return super().decide(obs)


def test_policies_see_no_ground_truth_or_future(tiny_world: World) -> None:
    spy = _Spy()
    simulate(tiny_world, spy)
    assert not spy.leaks
    assert not spy.context_fields & {"demand", "agent_truth", "anomalies", "disruptions"}
    assert {f.name for f in dataclasses.fields(Observation)} == {
        "hour",
        "cash_est",
        "efloat",
        "pending",
        "fleet",
        "history",
    }


def test_unknown_policy_is_rejected(tiny_world: World) -> None:
    for name in ("jogan", "none", "reactive"):
        with pytest.raises(ValueError, match="unknown policy"):
            make_policy(name, tiny_world)


def test_cli_writes_the_status_quo_log(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    main(["--profile", "tiny", "--seed", "0", "--write", "--root", str(tmp_path / "a")])
    main(["--profile", "tiny", "--seed", "0", "--write", "--root", str(tmp_path / "b")])
    assert "fixed_round" in capsys.readouterr().out
    run = Path("tiny") / "seed0" / "ops" / STATUS_QUO
    out = tmp_path / "a" / run
    for name in (
        "summary.json",
        "obs/hourly.parquet",
        "obs/visits.parquet",
        "truth/hourly.parquet",
    ):
        assert (out / name).read_bytes() == (tmp_path / "b" / run / name).read_bytes(), name
    obs = pd.read_parquet(out / "obs" / "hourly.parquet")
    assert not any(c.startswith(("req_", "lost_")) for c in obs.columns)
    truth = pd.read_parquet(out / "truth" / "hourly.parquet")
    assert {"req_co_n", "lost_co_n", "cash_tk"} <= set(truth.columns)
    summary = json.loads((out / "summary.json").read_text())
    assert summary["meta"]["policy"] == STATUS_QUO
    assert summary["service"]["requests"] > 0
