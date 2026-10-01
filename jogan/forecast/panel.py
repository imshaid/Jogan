"""The observed log as agents by hours arrays: the only data the forecast learns from.

A panel is built from ``ops/<policy>/obs/hourly.parquet`` (or the same frame in memory, or a
running simulation's :class:`~jogan.ops.env.History`), never from ground truth. Each record
keeps the hour at which it became available: a record is usable at origin ``t`` (the start
of hour ``t``) only when it arrived by then (D-018).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from jogan.ops.env import History

NEVER = np.iinfo(np.int64).max // 4  # arrival hour of a record that never arrived
OBS_COLUMNS = (
    "agent_id",
    "ts",
    "co_n",
    "co_tk",
    "ci_n",
    "ci_tk",
    "efloat_tk",
    "cash_est_tk",
    "available_at",
)


@dataclasses.dataclass(frozen=True)
class Panel:
    """Served flows and hour-end balances per agent-hour, with each record's arrival hour.

    Flows are 0 and balances NaN where no record arrived; ``arrive`` says which is which.
    """

    co_n: np.ndarray
    co_tk: np.ndarray
    ci_n: np.ndarray
    ci_tk: np.ndarray
    cash: np.ndarray
    efloat: np.ndarray
    arrive: np.ndarray

    @property
    def n_agents(self) -> int:
        return self.co_tk.shape[0]

    @property
    def n_hours(self) -> int:
        return self.co_tk.shape[1]

    @property
    def received(self) -> np.ndarray:
        """Records that arrived at some point (the log as read after the fact)."""
        return self.arrive < NEVER


def panel_from_frame(
    obs: pd.DataFrame, agent_ids: list[str], start: dt.date, n_hours: int
) -> Panel:
    """Pivot the observed hourly log; any column outside :data:`OBS_COLUMNS` is refused."""
    extra = set(obs.columns) - set(OBS_COLUMNS)
    if extra:
        raise ValueError(f"not an observation log, unexpected columns: {sorted(extra)}")
    agent = pd.Categorical(obs["agent_id"].astype(str), categories=agent_ids).codes
    if (agent < 0).any():
        raise ValueError("log holds agents outside the agent table")
    origin = np.datetime64(start, "s")
    hour = (obs["ts"].to_numpy().astype("datetime64[s]") - origin).astype(np.int64)
    seconds = (obs["available_at"].to_numpy().astype("datetime64[s]") - origin).astype(np.int64)
    if (hour % 3600).any() or (hour < 0).any() or (hour >= n_hours * 3600).any():
        raise ValueError("log timestamps must be whole hours inside the window")
    hour //= 3600
    shape = (len(agent_ids), n_hours)
    out = {name: np.zeros(shape) for name in ("co_n", "co_tk", "ci_n", "ci_tk")}
    for name in out:
        out[name][agent, hour] = obs[name].to_numpy(dtype=float)
    cash, efloat = np.full(shape, np.nan), np.full(shape, np.nan)
    cash[agent, hour] = obs["cash_est_tk"].to_numpy(dtype=float)
    efloat[agent, hour] = obs["efloat_tk"].to_numpy(dtype=float)
    arrive = np.full(shape, NEVER, dtype=np.int64)
    arrive[agent, hour] = -(-seconds // 3600)  # a record is usable from the next whole hour
    return Panel(cash=cash, efloat=efloat, arrive=arrive, **out)


def panel_from_history(history: History) -> Panel:
    """The panel a policy sees inside a simulation; hours not yet run arrive in the future."""
    n_hours = history.co_tk.shape[1]
    arrive = np.where(history.missing, NEVER, history.arrives_at(0, n_hours)).astype(np.int64)
    gone = history.missing
    return Panel(
        co_n=np.where(gone, 0, history.co_n).astype(float),
        co_tk=np.where(gone, 0, history.co_tk).astype(float),
        ci_n=np.where(gone, 0, history.ci_n).astype(float),
        ci_tk=np.where(gone, 0, history.ci_tk).astype(float),
        cash=np.where(gone, np.nan, history.cash_est.astype(float)),
        efloat=np.where(gone, np.nan, history.efloat.astype(float)),
        arrive=arrive,
    )


def read_panel(obs_dir: Path, agent_ids: list[str], start: dt.date, n_hours: int) -> Panel:
    """Read ``obs/hourly.parquet`` of an episode written by ``make history``."""
    frame = pd.read_parquet(obs_dir / "hourly.parquet", columns=list(OBS_COLUMNS))
    return panel_from_frame(frame, agent_ids, start, n_hours)
