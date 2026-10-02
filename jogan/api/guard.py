"""Rate limits, request size and response headers, in front of every route (D-024).

Limits are token buckets kept in memory, so each Cloud Run instance counts on its own (at most
2 instances, D-022). Every request spends a token from its client address's bucket before
anything else runs; signed-in requests also spend one from the user's bucket, and deciding and
AI rewording from their own (``jogan.api.app``). A refusal is a 429 with ``Retry-After``.

Behind Cloud Run the client address is not the socket peer: Google's front end appends it to
``X-Forwarded-For``. Anything to its left was written by the client and can be forged, so the
address is read ``proxy_hops`` entries from the right (``JOGAN_TRUSTED_PROXY_HOPS``; 0 means
no proxy, use the socket peer).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterable

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from jogan.api.config import ApiConfig, Bucket
from jogan.api.errors import problem

BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class RateLimited(Exception):
    def __init__(self, scope: str, retry_after_s: int) -> None:
        super().__init__(scope)
        self.scope, self.retry_after_s = scope, retry_after_s


class Limiter:
    """Token buckets per ``(scope, key)``; ``buckets`` maps a scope to its size and rate."""

    def __init__(
        self,
        buckets: dict[str, Bucket],
        max_keys: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.buckets, self.max_keys, self.clock = buckets, max_keys, clock
        self._state: dict[tuple[str, str], tuple[float, float]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg: ApiConfig, clock: Callable[[], float] = time.monotonic) -> Limiter:
        r = cfg.rate_limit
        buckets = {"ip": r.ip, "user": r.user, "decision": r.decision, "explanation": r.explanation}
        return cls(buckets, r.max_keys, clock)

    def _level(self, scope: str, tokens: float, at: float, now: float) -> float:
        b = self.buckets[scope]
        return min(b.burst, tokens + (now - at) * b.per_minute / 60)

    def hit(self, scope: str, key: str) -> None:
        """Spend one token, or raise :class:`RateLimited` with the seconds until one is back."""
        b = self.buckets[scope]
        with self._lock:
            now = self.clock()
            tokens, at = self._state.get((scope, key), (b.burst, now))
            tokens = self._level(scope, tokens, at, now)
            if tokens < 1:
                self._state[(scope, key)] = (tokens, now)
                raise RateLimited(scope, math.ceil((1 - tokens) * 60 / b.per_minute))
            self._state[(scope, key)] = (tokens - 1, now)
            if len(self._state) > self.max_keys:
                self._prune(now)

    def _prune(self, now: float) -> None:
        """Drop buckets that have refilled (they equal a fresh one), then the oldest."""
        full = [
            k
            for k, (tokens, at) in self._state.items()
            if self._level(k[0], tokens, at, now) >= self.buckets[k[0]].burst
        ]
        for k in full:
            del self._state[k]
        if len(self._state) > self.max_keys:
            oldest = sorted(self._state, key=lambda k: self._state[k][1])
            for k in oldest[: len(self._state) - self.max_keys // 2]:
                del self._state[k]


def client_ip(forwarded_for: Iterable[str], peer: str | None, proxy_hops: int) -> str:
    """The client address: ``proxy_hops`` entries from the right of ``X-Forwarded-For``."""
    if proxy_hops > 0:
        hops = [h.strip() for value in forwarded_for for h in value.split(",") if h.strip()]
        if len(hops) >= proxy_hops:
            return hops[-proxy_hops]
    return peer or "unknown"


def limited(e: RateLimited) -> JSONResponse:
    retry = str(e.retry_after_s)
    detail = f"too many requests; try again in {retry} s"
    return problem(429, detail, {"Retry-After": retry}, retry_after_s=e.retry_after_s)


class Guard:
    """ASGI middleware: the per-address limit, the body size limit and safe response headers."""

    def __init__(self, app: ASGIApp, limiter: Limiter, proxy_hops: int, max_body: int) -> None:
        self.app, self.limiter, self.proxy_hops, self.max_body = app, limiter, proxy_hops, max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        peer = scope["client"][0] if scope.get("client") else None
        ip = client_ip(headers.getlist("x-forwarded-for"), peer, self.proxy_hops)
        try:
            self.limiter.hit("ip", ip)
        except RateLimited as e:
            await limited(e)(scope, receive, send)
            return
        if scope["method"] in BODY_METHODS:
            length = headers.get("content-length")
            if length is None:
                await problem(411, "send a Content-Length header")(scope, receive, send)
                return
            if not length.isdigit() or int(length) > self.max_body:
                detail = f"request body over {self.max_body} bytes"
                await problem(413, detail)(scope, receive, send)
                return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h.setdefault("X-Content-Type-Options", "nosniff")
                h.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)
