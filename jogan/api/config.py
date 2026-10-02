"""Typed configuration of the API guards, from ``configs/api/base.yaml`` (D-024)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from jogan.sim.config import CONFIG_DIR, Positive, Strict, _merge, _read_yaml


class Auth(Strict):
    algorithms: tuple[str, ...] = Field(min_length=1)
    audience: str
    role: str
    jwks_ttl_s: Positive
    jwks_min_refetch_s: float = Field(ge=0.0)
    jwks_timeout_s: Positive
    leeway_s: float = Field(ge=0.0)
    max_token_chars: int = Field(ge=256)


class Bucket(Strict):
    per_minute: Positive
    burst: int = Field(ge=1)


class RateLimit(Strict):
    ip: Bucket
    user: Bucket
    decision: Bucket
    explanation: Bucket
    max_keys: int = Field(ge=100)


class Health(Strict):
    db_cache_s: float = Field(ge=0.0)


class Request(Strict):
    max_body_bytes: int = Field(ge=1024)
    gzip_min_bytes: int = Field(ge=0)


class ApiConfig(Strict):
    auth: Auth
    rate_limit: RateLimit
    health: Health
    request: Request


def load_api_config(
    overrides: dict[str, Any] | None = None, config_dir: Path | None = None
) -> ApiConfig:
    """Load ``configs/api/base.yaml``; ``overrides`` merge on top."""
    data = _read_yaml((config_dir or CONFIG_DIR) / "api" / "base.yaml")
    return ApiConfig.model_validate(_merge(data, overrides or {}))
