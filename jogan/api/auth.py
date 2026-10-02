"""Who is calling: the API checks every bearer token itself before any database call (D-024).

Supabase signs access tokens with an asymmetric key and publishes the public keys as a JWK set.
:class:`JwksVerifier` keeps that set in memory, refetches it when it is older than the
configured lifetime or when a token names an unknown key (at most once per
``jwks_min_refetch_s``, so made-up key ids cannot flood Supabase), and checks the signature,
algorithm, issuer, audience, expiry, subject and role. The store still sends the token on to
PostgREST, so row-level security checks it a second time.

:class:`StaticVerifier` maps opaque tokens to user ids, for tests and ``make api``.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import threading
import time
from collections.abc import Callable, Mapping

import httpx2 as httpx
import jwt

from jogan.api.config import Auth

log = logging.getLogger("jogan.api")


class AuthError(Exception):
    """A refused sign-in; ``status`` is 401, or 503 when the keys cannot be fetched."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


@dataclasses.dataclass(frozen=True)
class Caller:
    token: str
    user_id: str


INVALID = "invalid sign-in token"


class StaticVerifier:
    """Opaque tokens for tests and local runs: ``users`` maps a token to a user id."""

    def __init__(self, users: Mapping[str, str]) -> None:
        self.users = dict(users)

    def verify(self, token: str) -> Caller:
        if token not in self.users:
            raise AuthError(401, INVALID)
        return Caller(token, self.users[token])


class JwksVerifier:
    """Supabase access tokens, checked against the project's published keys."""

    def __init__(
        self,
        supabase_url: str,
        cfg: Auth,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cfg = cfg
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self.http = httpx.Client(timeout=cfg.jwks_timeout_s, transport=transport)
        self.clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = -math.inf
        self._tried_at = -math.inf
        self._lock = threading.Lock()

    def _fetch(self) -> dict[str, jwt.PyJWK]:
        r = self.http.get(self.jwks_url)
        r.raise_for_status()
        keys = {}
        for raw in r.json().get("keys", []):
            try:
                key = jwt.PyJWK(raw)
            except jwt.PyJWTError:
                continue  # a key type this library cannot use
            if key.key_id and key.algorithm_name in self.cfg.algorithms:
                keys[key.key_id] = key
        return keys

    def _key(self, kid: str) -> jwt.PyJWK | None:
        with self._lock:
            now = self.clock()
            stale = now - self._fetched_at >= self.cfg.jwks_ttl_s
            if (stale or kid not in self._keys) and (
                now - self._tried_at >= self.cfg.jwks_min_refetch_s
            ):
                self._tried_at = now
                try:
                    self._keys, self._fetched_at = self._fetch(), now
                except (httpx.HTTPError, ValueError) as e:
                    # keep the keys we have; the next try waits jwks_min_refetch_s
                    log.warning("could not fetch the sign-in keys: %s", e)
            if not self._keys:
                raise AuthError(503, "sign-in keys are unavailable; try again shortly")
            return self._keys.get(kid)

    def verify(self, token: str) -> Caller:
        if len(token) > self.cfg.max_token_chars:
            raise AuthError(401, INVALID)
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise AuthError(401, INVALID) from None
        kid, alg = header.get("kid"), header.get("alg")
        if not isinstance(kid, str) or alg not in self.cfg.algorithms:
            raise AuthError(401, INVALID)
        key = self._key(kid)
        if key is None:
            raise AuthError(401, INVALID)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self.cfg.algorithms),
                audience=self.cfg.audience,
                issuer=self.issuer,
                leeway=self.cfg.leeway_s,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthError(401, "session expired; sign in again") from None
        except jwt.PyJWTError:
            raise AuthError(401, INVALID) from None
        sub = claims.get("sub")
        if claims.get("role") != self.cfg.role or not isinstance(sub, str) or not sub:
            raise AuthError(401, INVALID)
        return Caller(token, sub)
