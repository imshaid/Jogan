"""FastAPI app: the day's recommendations, approve or reject, and the audit log (D-022).

Run with ``uvicorn --factory jogan.api.app:from_env``. Settings come from the environment
(``.env.example`` lists them). The API is stateless with respect to simulated time: the client
asks for a plan date, and the bundle (:mod:`jogan.api.bundle`) holds every test day's plan.

A day's recommendations are written to the store the first time a signed-in user with a role
asks for that day (``publish_plan`` ignores a second publish), then read back with the user's
own token so row-level security applies. Deciding goes through one database function that
updates the recommendation and appends the audit row in the same transaction.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import jogan
from jogan.api.bundle import Bundle, load_bundle
from jogan.api.store import NOTE_MAX, MemoryStore, Store, StoreError, SupabaseConfig, SupabaseStore

bearer = HTTPBearer(auto_error=False)


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=NOTE_MAX)


def token_of(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
    if creds is None or not creds.credentials:
        raise HTTPException(401, "sign in first", headers={"WWW-Authenticate": "Bearer"})
    return creds.credentials


Token = Annotated[str, Depends(token_of)]


def create_app(
    bundle: Bundle,
    store: Store,
    cors_origins: list[str] | None = None,
    cors_origin_regex: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Jogan API",
        version=jogan.__version__,
        description="Agent liquidity copilot. All data is simulated.",
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

    @app.exception_handler(StoreError)
    def _store_error(_: Request, e: StoreError) -> JSONResponse:
        return JSONResponse({"detail": e.message}, status_code=e.status)

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
            "simulated": True,
        }

    @app.get("/v1/me")
    def me(token: Token) -> dict:
        return {"role": store.role(token)}

    @app.get("/v1/plans/{day}")
    def plan(day: dt.date, token: Token) -> dict:
        staff_role(token)
        if day not in bundle.plan_dates:
            raise HTTPException(404, f"no plan for {day.isoformat()}")
        if day not in published:
            store.publish(bundle.bundle_id, day, bundle.recommendations(day), bundle.trace(day))
            published.add(day)
        rows = store.queue(token, bundle.bundle_id, day)
        return {"bundle_id": bundle.bundle_id, "plan_date": day.isoformat(), "items": rows}

    @app.post("/v1/recommendations/{rec_id}/decision")
    def decide(rec_id: int, body: DecisionIn, token: Token) -> dict:
        return store.decide(token, rec_id, body.decision, body.note)

    @app.get("/v1/audit")
    def audit(token: Token, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict:
        staff_role(token)
        return {"items": store.audit(token, limit)}

    return app


def _origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


def from_env() -> FastAPI:
    """The app as deployed: bundle from ``JOGAN_BUNDLE_DIR``, Supabase from the environment.

    ``JOGAN_STORE=memory`` (development only) uses :class:`MemoryStore` with the tokens
    ``analyst`` and ``approver``, for running the web app locally without Supabase.
    """
    env = os.environ
    bundle = load_bundle(Path(env.get("JOGAN_BUNDLE_DIR", "bundle")))
    kind = env.get("JOGAN_STORE", "supabase")
    if kind == "memory":
        if env.get("JOGAN_ENV", "development") != "development":
            raise RuntimeError("JOGAN_STORE=memory is for development only")
        store: Store = MemoryStore(
            {"analyst": ("dev-analyst", "analyst"), "approver": ("dev-approver", "approver")}
        )
    else:
        store = SupabaseStore(
            SupabaseConfig(
                url=env["SUPABASE_URL"],
                publishable_key=env["SUPABASE_PUBLISHABLE_KEY"],
                secret_key=env["SUPABASE_SECRET_KEY"],
            )
        )
    origins = _origins(env.get("JOGAN_CORS_ORIGINS", ""))
    return create_app(bundle, store, origins, env.get("JOGAN_CORS_ORIGIN_REGEX") or None)
