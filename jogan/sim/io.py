"""Write and read a generated world as parquet files.

Layout of ``data/<profile>/seed<seed>/``::

    meta.json                  profile, seed, config hash, calibration
    calendar.parquet           public
    territories.parquet        public
    agents.parquet             public agent master data
    runners.parquet            public
    roster.parquet             public
    truth/demand.parquet       every customer attempt (never shown to Jogan directly)
    truth/agents.parquet       true agent parameters and starting balances
    truth/anomalies.parquet    anomaly labels
    truth/disruptions.parquet  disrupted territory-days
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from jogan.sim.world import World

DATA_DIR = Path("data")
PUBLIC_TABLES = ("calendar", "territories", "agents", "runners", "roster")
TRUTH_TABLES = {
    "demand": "demand",
    "agent_truth": "agents",
    "anomalies": "anomalies",
    "disruptions": "disruptions",
}


def world_dir(profile: str, seed: int, root: Path = DATA_DIR) -> Path:
    return root / profile / f"seed{seed}"


def write_world(world: World, out: Path) -> list[Path]:
    """Write every table and ``meta.json``; the bytes depend only on config and seed."""
    (out / "truth").mkdir(parents=True, exist_ok=True)
    written = []
    tables = {name: (out / f"{name}.parquet", getattr(world, name)) for name in PUBLIC_TABLES}
    for attr, name in TRUTH_TABLES.items():
        tables[f"truth/{name}"] = (out / "truth" / f"{name}.parquet", getattr(world, attr))
    for path, frame in tables.values():
        frame.to_parquet(path, index=False, compression="zstd")
        written.append(path)
    meta = out / "meta.json"
    meta.write_text(json.dumps(world.meta(), indent=2, sort_keys=True, default=str) + "\n")
    written.append(meta)
    return written


def read_world(path: Path, truth: bool = False) -> dict[str, pd.DataFrame]:
    """Read the public tables, plus ``truth/*`` only when ``truth`` is set (evaluation code)."""
    tables = {name: pd.read_parquet(path / f"{name}.parquet") for name in PUBLIC_TABLES}
    if truth:
        for name in TRUTH_TABLES.values():
            tables[f"truth/{name}"] = pd.read_parquet(path / "truth" / f"{name}.parquet")
    return tables


def read_meta(path: Path) -> dict:
    return json.loads((path / "meta.json").read_text())
