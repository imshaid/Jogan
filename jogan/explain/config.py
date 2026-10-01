"""Typed configuration of explanations, guardrails, the narrator and the anomaly flag.

Parameters come from ``configs/explain/base.yaml``; the words shown to users, in English and
Bangla, from ``configs/explain/labels.yaml``.
"""

from __future__ import annotations

import functools
import hashlib
from pathlib import Path
from typing import Any

from pydantic import Field

from jogan.sim.config import CONFIG_DIR, Positive, Prob, Strict, _merge, _read_yaml

LANGS = ("en", "bn")


class Drivers(Strict):
    level: float = Field(gt=0.0, lt=1.0)
    top_k: int = Field(ge=1, le=10)
    min_effect_pct: float = Field(ge=0.0)


class Guardrails(Strict):
    range_features: tuple[str, ...] = Field(min_length=1)
    max_q90_to_q50: float = Field(gt=1.0)
    min_arrived_share: Prob
    min_history_windows: int = Field(ge=0)


class Narrator(Strict):
    primary: str
    fallback: str
    timeout_s: Positive
    temperature: float = Field(ge=0.0, le=2.0)
    max_chars: int = Field(ge=100)
    per_minute: int = Field(ge=1)
    cache_size: int = Field(ge=1)


class Anomaly(Strict):
    history_days: int = Field(ge=7)
    min_history_days: int = Field(ge=1)
    min_arrived_share: Prob
    n_estimators: int = Field(ge=10)
    max_samples: int = Field(ge=16)
    threshold_quantile: float = Field(gt=0.5, lt=1.0)
    precision_at_k: tuple[int, ...] = Field(min_length=1)
    seed: int


class ExplainConfig(Strict):
    drivers: Drivers
    guardrails: Guardrails
    narrator: Narrator
    anomaly: Anomaly

    def config_hash(self) -> str:
        """Hash of what the served bundle stores; narrator settings act only at request time."""
        stored = self.model_dump(exclude={"narrator"})
        return hashlib.sha256(repr(sorted(stored.items())).encode()).hexdigest()[:12]


def load_explain_config(
    overrides: dict[str, Any] | None = None, config_dir: Path | None = None
) -> ExplainConfig:
    """Load ``configs/explain/base.yaml``; ``overrides`` merge on top."""
    data = _read_yaml((config_dir or CONFIG_DIR) / "explain" / "base.yaml")
    return ExplainConfig.model_validate(_merge(data, overrides or {}))


@functools.cache
def load_labels(config_dir: Path | None = None) -> dict[str, Any]:
    """The user-facing words; every feature and copy entry has an ``en`` and a ``bn`` text."""
    labels = _read_yaml((config_dir or CONFIG_DIR) / "explain" / "labels.yaml")
    for section in ("features", "anomaly_features", "copy", "reasons"):
        for key, entry in labels[section].items():
            missing = [lang for lang in LANGS if lang not in entry]
            if missing:
                raise ValueError(f"labels.yaml {section}.{key} lacks {missing}")
    return labels
