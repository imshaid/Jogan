"""Write an episode: the observation log Jogan may learn from, and the ground truth behind it.

Layout of ``data/<profile>/seed<seed>/ops/<policy>/``::

    summary.json             service and cost metrics (evaluation)
    obs/hourly.parquet       served flows, e-float and cash estimate per agent-hour, with
                             ``available_at``; agent-hours lost by the data feed are absent
    obs/visits.parquet       runner visits as the distributor logs them
    obs/refills.parquet      agents' own bank trips, seen by upay as e-float transfers
    obs/runner_days.parquet  runner duty, visits and km per day
    truth/hourly.parquet     every request and lost request, true balances

Feature code reads ``obs/`` only; ``truth/`` is for evaluation (D-014).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import jogan
from jogan.ops.env import Episode
from jogan.ops.metrics import summarize, truth_hourly
from jogan.sim.io import DATA_DIR, world_dir


def ops_dir(profile: str, seed: int, policy: str, root: Path = DATA_DIR) -> Path:
    return world_dir(profile, seed, root) / "ops" / policy


def _stamp(ep: Episode, seconds: np.ndarray) -> np.ndarray:
    return np.datetime64(ep.world.config.start, "s") + seconds.astype("timedelta64[s]")


def _agent_ids(ep: Episode, idx: np.ndarray) -> pd.Categorical:
    return pd.Categorical.from_codes(idx, categories=ep.ctx.agents["agent_id"].tolist())


def _panel_index(ep: Episode) -> tuple[np.ndarray, np.ndarray]:
    n = len(ep.ctx.agents)
    return np.repeat(np.arange(n), ep.n_hours), np.tile(np.arange(ep.n_hours), n)


def observed_hourly(ep: Episode) -> pd.DataFrame:
    """What upay's data feed delivers, one row per agent-hour that arrived."""
    hist = ep.history
    agent, hour = _panel_index(ep)
    keep = ~hist.missing.ravel()
    arrives = hist.arrives_at(0, ep.n_hours).ravel()
    frame = pd.DataFrame(
        {
            "agent_id": _agent_ids(ep, agent[keep]),
            "ts": _stamp(ep, hour[keep] * 3600),
            "co_n": hist.co_n.ravel()[keep],
            "co_tk": hist.co_tk.ravel()[keep],
            "ci_n": hist.ci_n.ravel()[keep],
            "ci_tk": hist.ci_tk.ravel()[keep],
            "efloat_tk": hist.efloat.ravel()[keep],
            "cash_est_tk": hist.cash_est.ravel()[keep],
            "available_at": _stamp(ep, arrives[keep] * 3600),
        }
    )
    return frame


def truth_hourly_frame(ep: Episode) -> pd.DataFrame:
    agent, hour = _panel_index(ep)
    panel = {name: values.ravel() for name, values in truth_hourly(ep).items()}
    return pd.DataFrame(
        {
            "agent_id": _agent_ids(ep, agent),
            "ts": _stamp(ep, hour * 3600),
            **panel,
            "cash_tk": ep.cash.ravel(),
            "efloat_tk": ep.efloat.ravel(),
        }
    )


def visits_frame(ep: Episode) -> pd.DataFrame:
    v = ep.visits
    runner_ids = ep.ctx.runners["runner_id"].to_numpy()
    return pd.DataFrame(
        {
            "ts": _stamp(ep, v["t"].to_numpy(dtype=np.int64)),
            "planned_at": _stamp(ep, v["planned_t"].to_numpy(dtype=np.int64)),
            "runner_id": runner_ids[v["runner"].to_numpy(dtype=int)],
            "agent_id": _agent_ids(ep, v["agent"].to_numpy(dtype=int)),
            "reason": v["reason"].astype(str),
            "target_cash_tk": v["target_cash"].to_numpy(dtype=np.int64),
            "cash_delta_tk": v["cash_delta"].to_numpy(dtype=np.int64),
            "km": v["km"].to_numpy(dtype=float).round(3),
            "bag_after_tk": v["bag_after"].to_numpy(dtype=np.int64),
        }
    )


def refills_frame(ep: Episode) -> pd.DataFrame:
    r = ep.refills
    return pd.DataFrame(
        {
            "ts": _stamp(ep, r["t"].to_numpy(dtype=np.int64)),
            "agent_id": _agent_ids(ep, r["agent"].to_numpy(dtype=int)),
            "cash_delta_tk": r["cash_delta"].to_numpy(dtype=np.int64),
        }
    )


def runner_days_frame(ep: Episode) -> pd.DataFrame:
    d = ep.runner_days
    return pd.DataFrame(
        {
            "date": ep.ctx.calendar["date"].to_numpy()[d["day"].to_numpy(dtype=int)],
            "runner_id": ep.ctx.runners["runner_id"].to_numpy()[d["runner"].to_numpy(dtype=int)],
            "on_duty": d["on_duty"].to_numpy(dtype=bool),
            "visits": d["visits"].to_numpy(dtype=np.int16),
            "km": d["km"].to_numpy(dtype=float).round(3),
        }
    )


def episode_meta(ep: Episode) -> dict[str, Any]:
    cfg = ep.world.config
    return {
        "profile": cfg.name,
        "seed": ep.world.seed,
        "policy": ep.policy,
        "sim_config_hash": cfg.config_hash(),
        "ops_config_hash": ep.ctx.ops.config_hash(),
        "jogan_version": jogan.__version__,
    }


def write_summary(ep: Episode, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "summary.json"
    body = {"meta": episode_meta(ep), **summarize(ep)}
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return path


def write_episode(ep: Episode, out: Path) -> list[Path]:
    """Write the summary, the observation log and the truth panel; bytes depend only on inputs."""
    (out / "obs").mkdir(parents=True, exist_ok=True)
    (out / "truth").mkdir(parents=True, exist_ok=True)
    tables = {
        out / "obs" / "hourly.parquet": observed_hourly(ep),
        out / "obs" / "visits.parquet": visits_frame(ep),
        out / "obs" / "refills.parquet": refills_frame(ep),
        out / "obs" / "runner_days.parquet": runner_days_frame(ep),
        out / "truth" / "hourly.parquet": truth_hourly_frame(ep),
    }
    for path, frame in tables.items():
        frame.to_parquet(path, index=False, compression="zstd")
    return [write_summary(ep, out), *tables]
