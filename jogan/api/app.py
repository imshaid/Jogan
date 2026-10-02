"""FastAPI app: the day's recommendations, approve or reject, and the audit log (D-022).

Run with ``uvicorn --factory jogan.api.app:from_env``. Settings come from the environment
(``.env.example`` lists them). The API is stateless with respect to simulated time: the client
asks for a plan date, and the bundle (:mod:`jogan.api.bundle`) holds every test day's plan.

A day's recommendations are written to the store the first time a signed-in user with a role
asks for that day (``publish_plan`` ignores a second publish), then read back with the user's
own token so row-level security applies. Deciding goes through one database function that
updates the recommendation and appends the audit row in the same transaction; a recommendation
flagged for manual review needs a note to be approved.

Each queue row carries its template explanation in English and Bangla, written from the stored
evidence (:mod:`jogan.explain.template`). ``/explanation`` asks Gemini to reword one of them
(:mod:`jogan.explain.narrator`) and falls back to the template; the advisory anomaly flags of a
day come from the bundle (D-023).

Every bearer token is checked by the API itself (:mod:`jogan.api.auth`) before the store sends
it on to PostgREST, requests are rate-limited per client address and per user
(:mod:`jogan.api.guard`), every refusal has the same body (:mod:`jogan.api.errors`), and
``/trace`` returns what each layer produced for one recommendation (:mod:`jogan.api.trace`)
(D-024).

``/network`` (every agent of a plan day, for the map) and ``/agents`` (one agent over the test
window) are read-only views of the bundle (:mod:`jogan.api.views`, D-025).
"""

from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata
from pathlib import Path
from typing import Annotated, Literal, Protocol

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

import jogan
from jogan.api.auth import AuthError, Caller, JwksVerifier, StaticVerifier
from jogan.api.bundle import Bundle, load_bundle
from jogan.api.config import ApiConfig, load_api_config
from jogan.api.errors import problem, validation_errors
from jogan.api.guard import Guard, Limiter, RateLimited, limited
from jogan.api.store import NOTE_MAX, MemoryStore, Store, StoreError, SupabaseConfig, SupabaseStore
from jogan.api.trace import decision_trace
from jogan.api.views import agent, annotate, day_counts, network
from jogan.explain.config import load_explain_config
from jogan.explain.narrator import Narrator
from jogan.explain.template import anomaly_items, facts, render, risk_percent

bearer = HTTPBearer(auto_error=False)

BIGINT_MAX = 2**63 - 1  # ids are Postgres bigint
AUDIT_PER_RECOMMENDATION = 50  # a recommendation has one decision row; room for later actions


def _iso_date(v: object) -> object:
    """Only ``YYYY-MM-DD``: pydantic would also take a Unix time or a datetime as a date."""
    if isinstance(v, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ValueError("use a date as YYYY-MM-DD")
    return v


Day = Annotated[dt.date, BeforeValidator(_iso_date)]
RecId = Annotated[int, PathParam(ge=1, le=BIGINT_MAX)]
AgentId = Annotated[str, PathParam(pattern=r"^[A-Z]{3}-\d{3,5}$")]
Lang = Literal["en", "bn"]


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=NOTE_MAX)

    @field_validator("note")
    @classmethod
    def _printable(cls, v: str | None) -> str | None:
        if v is not None and any(
            unicodedata.category(ch) == "Cc" and ch not in "\n\r\t" for ch in v
        ):
            raise ValueError("the note has control characters")
        return v


class Verifier(Protocol):
    def verify(self, token: str) -> Caller: ...


def signed_in(
    request: Request, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> Caller:
    """The verified caller, after spending a token from the user's rate-limit bucket."""
    if creds is None or not creds.credentials:
        raise HTTPException(401, "sign in first", headers={"WWW-Authenticate": "Bearer"})
    caller = request.app.state.verifier.verify(creds.credentials)
    request.app.state.limiter.hit("user", caller.user_id)
    return caller


User = Annotated[Caller, Depends(signed_in)]


def with_explanation(row: dict) -> dict:
    """A queue row with its template explanations and the display text of its evidence."""
    explanation = {lang: render(row, lang) for lang in ("en", "bn")}
    return {**row, "evidence": annotate(row["evidence"]), "explanation": explanation}


def create_app(
    bundle: Bundle,
    store: Store,
    verifier: Verifier,
    cors_origins: list[str] | None = None,
    cors_origin_regex: str | None = None,
    narrator: Narrator | None = None,
    config: ApiConfig | None = None,
    limiter: Limiter | None = None,
    proxy_hops: int = 0,
) -> FastAPI:
    cfg = config or load_api_config()
    limiter = limiter or Limiter.from_config(cfg)
    app = FastAPI(
        title="Jogan API",
        version=jogan.__version__,
        description="Agent liquidity copilot. All data is simulated.",
    )
    app.state.verifier, app.state.limiter = verifier, limiter
    # the map's day of 600 agents is 172 KB of JSON (16 KB gzipped); Cloud Run does not compress
    app.add_middleware(GZipMiddleware, minimum_size=cfg.request.gzip_min_bytes)
    # the guard runs inside CORS, so its refusals still carry the CORS headers
    app.add_middleware(
        Guard, limiter=limiter, proxy_hops=proxy_hops, max_body=cfg.request.max_body_bytes
    )
    if cors_origins or cors_origin_regex:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins or [],
            allow_origin_regex=cors_origin_regex,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )
    published: set[dt.date] = set()
    days = day_counts(bundle)

    @app.exception_handler(StoreError)
    def _store_error(_: Request, e: StoreError) -> JSONResponse:
        return problem(e.status, e.message)

    @app.exception_handler(AuthError)
    def _auth_error(_: Request, e: AuthError) -> JSONResponse:
        headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'} if e.status == 401 else {}
        return problem(e.status, e.message, headers)

    @app.exception_handler(RateLimited)
    def _rate_limited(_: Request, e: RateLimited) -> JSONResponse:
        return limited(e)

    @app.exception_handler(StarletteHTTPException)
    def _http_error(_: Request, e: StarletteHTTPException) -> JSONResponse:
        return problem(e.status_code, str(e.detail), e.headers)

    @app.exception_handler(RequestValidationError)
    def _invalid(_: Request, e: RequestValidationError) -> JSONResponse:
        detail, errors = validation_errors(list(e.errors()))
        return problem(422, detail, errors=errors)

    @app.exception_handler(Exception)
    def _crash(_: Request, e: Exception) -> JSONResponse:
        # Starlette re-raises after this answer, so the server logs the traceback
        return problem(500, "internal error")

    def staff_role(token: str) -> str:
        role = store.role(token)
        if role is None:
            raise HTTPException(403, "this account has no Jogan role")
        return role

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": jogan.__version__, "bundle_id": bundle.bundle_id}

    @app.get("/v1/meta")
    def meta() -> dict:
        m = bundle.meta
        keys = ("bundle_id", "profile", "seed", "test_window", "plan_dates", "plan_hour")
        return {
            **{k: m[k] for k in keys},
            "counts": m["counts"],
            "lost_customer_value_tk": m["lost_customer_value_tk"],
            "territories": bundle.territories.to_dict("records"),
            "days": days,
            "simulated": True,
        }

    @app.get("/v1/me")
    def me(user: User) -> dict:
        return {"user_id": user.user_id, "role": store.role(user.token)}

    @app.get("/v1/plans/{day}")
    def plan(day: Day, user: User) -> dict:
        token = user.token
        staff_role(token)
        if day not in bundle.plan_dates:
            raise HTTPException(404, f"no plan for {day.isoformat()}")
        if day not in published:
            store.publish(bundle.bundle_id, day, bundle.recommendations(day), bundle.trace(day))
            published.add(day)
        rows = [with_explanation(r) for r in store.queue(token, bundle.bundle_id, day)]
        return {"bundle_id": bundle.bundle_id, "plan_date": day.isoformat(), "items": rows}

    @app.get("/v1/recommendations/{rec_id}/explanation")
    def explanation(rec_id: RecId, user: User, lang: Lang = "en") -> dict:
        """The template explanation, reworded by Gemini when it passes every check."""
        staff_role(user.token)
        limiter.hit("explanation", user.user_id)
        rec = store.recommendation(user.token, rec_id)
        if rec is None:
            raise HTTPException(404, f"recommendation {rec_id} not found")
        template = render(rec, lang)
        out = {"recommendation_id": rec_id, "lang": lang, "template": template}
        if narrator is None:
            return {**out, "text": template, "source": "template", "model": None,
                    "note": "narrator is off"}  # fmt: skip
        key = (rec["bundle_id"], rec_id, lang)
        n = narrator.narrate(key, template, facts(rec, lang), lang, {risk_percent(rec)})
        return {**out, "text": n.text, "source": n.source, "model": n.model, "note": n.note}

    @app.get("/v1/recommendations/{rec_id}/trace")
    def trace(rec_id: RecId, user: User) -> dict:
        """What each layer produced for one recommendation, the stored trace and its audit rows."""
        staff_role(user.token)
        rec = store.recommendation(user.token, rec_id)
        if rec is None:
            raise HTTPException(404, f"recommendation {rec_id} not found")
        rows = store.audit(user.token, AUDIT_PER_RECOMMENDATION, recommendation_id=rec_id)
        return decision_trace({**rec, "evidence": annotate(rec["evidence"])}, rows, bundle)

    @app.get("/v1/network/{day}")
    def network_day(day: Day, user: User) -> dict:
        """Every agent on the morning of ``day`` with its stock-out chance and planned visit."""
        staff_role(user.token)
        if day not in bundle.plan_dates:
            raise HTTPException(404, f"no plan for {day.isoformat()}")
        return {"plan_date": day.isoformat(), "agents": network(bundle, day)}

    @app.get("/v1/agents/{agent_id}")
    def agent_detail(agent_id: AgentId, user: User) -> dict:
        """One agent's evidence on every plan day, with its advisory anomaly flags."""
        staff_role(user.token)
        found = agent(bundle, agent_id)
        if found is None:
            raise HTTPException(404, f"agent {agent_id} not found")
        return {"bundle_id": bundle.bundle_id, **found}

    @app.get("/v1/anomalies/{day}")
    def anomalies(day: Day, user: User) -> dict:
        """Advisory flags raised on the morning of ``day``, for a person to look at."""
        staff_role(user.token)
        if day not in bundle.plan_dates:
            raise HTTPException(404, f"no plan for {day.isoformat()}")
        items = [
            {**f, "text": {lang: anomaly_items(f["items"], lang) for lang in ("en", "bn")}}
            for f in bundle.anomaly_flags(day)
        ]
        return {"plan_date": day.isoformat(), "advisory": True, "items": items}

    @app.post("/v1/recommendations/{rec_id}/decision")
    def decide(rec_id: RecId, body: DecisionIn, user: User) -> dict:
        limiter.hit("decision", user.user_id)
        return store.decide(user.token, rec_id, body.decision, body.note)

    @app.get("/v1/audit")
    def audit(
        user: User,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        recommendation_id: Annotated[int | None, Query(ge=1, le=BIGINT_MAX)] = None,
    ) -> dict:
        staff_role(user.token)
        return {"items": store.audit(user.token, limit, recommendation_id)}

    return app


def _origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


def from_env() -> FastAPI:
    """The app as deployed: bundle from ``JOGAN_BUNDLE_DIR``, Supabase from the environment.

    ``JOGAN_STORE=memory`` (development only) uses :class:`MemoryStore` with the tokens
    ``analyst`` and ``approver``, for running the web app locally without Supabase. Without
    ``GEMINI_API_KEY`` every explanation is the template. ``JOGAN_TRUSTED_PROXY_HOPS`` is the
    number of proxies that append to ``X-Forwarded-For`` (1 on Cloud Run, 0 locally).
    """
    env = os.environ
    bundle = load_bundle(Path(env.get("JOGAN_BUNDLE_DIR", "bundle")))
    api_cfg = load_api_config()
    kind = env.get("JOGAN_STORE", "supabase")
    verifier: Verifier
    if kind == "memory":
        if env.get("JOGAN_ENV", "development") != "development":
            raise RuntimeError("JOGAN_STORE=memory is for development only")
        users = {"analyst": ("dev-analyst", "analyst"), "approver": ("dev-approver", "approver")}
        store: Store = MemoryStore(users)
        verifier = StaticVerifier({token: user for token, (user, _) in users.items()})
    else:
        store = SupabaseStore(
            SupabaseConfig(
                url=env["SUPABASE_URL"],
                publishable_key=env["SUPABASE_PUBLISHABLE_KEY"],
                secret_key=env["SUPABASE_SECRET_KEY"],
            )
        )
        verifier = JwksVerifier(env["SUPABASE_URL"], api_cfg.auth)
    cfg = load_explain_config().narrator
    models = {
        "primary": env.get("GEMINI_MODEL_PRIMARY") or cfg.primary,
        "fallback": env.get("GEMINI_MODEL_FALLBACK") or cfg.fallback,
    }
    narrator = Narrator(cfg.model_copy(update=models), env.get("GEMINI_API_KEY") or None)
    origins = _origins(env.get("JOGAN_CORS_ORIGINS", ""))
    regex = env.get("JOGAN_CORS_ORIGIN_REGEX") or None
    hops = int(env.get("JOGAN_TRUSTED_PROXY_HOPS", "0"))
    return create_app(
        bundle, store, verifier, origins, regex, narrator, config=api_cfg, proxy_hops=hops
    )
