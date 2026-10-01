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
from jogan.explain.config import load_explain_config
from jogan.explain.narrator import Narrator
from jogan.explain.template import anomaly_items, facts, render, risk_percent

bearer = HTTPBearer(auto_error=False)


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=NOTE_MAX)


def token_of(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
    if creds is None or not creds.credentials:
        raise HTTPException(401, "sign in first", headers={"WWW-Authenticate": "Bearer"})
    return creds.credentials


Token = Annotated[str, Depends(token_of)]
Lang = Literal["en", "bn"]


def with_explanation(row: dict) -> dict:
    return {**row, "explanation": {lang: render(row, lang) for lang in ("en", "bn")}}


def create_app(
    bundle: Bundle,
    store: Store,
    cors_origins: list[str] | None = None,
    cors_origin_regex: str | None = None,
    narrator: Narrator | None = None,
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
        rows = [with_explanation(r) for r in store.queue(token, bundle.bundle_id, day)]
        return {"bundle_id": bundle.bundle_id, "plan_date": day.isoformat(), "items": rows}

    @app.get("/v1/recommendations/{rec_id}/explanation")
    def explanation(rec_id: int, token: Token, lang: Lang = "en") -> dict:
        """The template explanation, reworded by Gemini when it passes every check."""
        staff_role(token)
        rec = store.recommendation(token, rec_id)
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

    @app.get("/v1/anomalies/{day}")
    def anomalies(day: dt.date, token: Token) -> dict:
        """Advisory flags raised on the morning of ``day``, for a person to look at."""
        staff_role(token)
        if day not in bundle.plan_dates:
            raise HTTPException(404, f"no plan for {day.isoformat()}")
        items = [
            {**f, "text": {lang: anomaly_items(f["items"], lang) for lang in ("en", "bn")}}
            for f in bundle.anomaly_flags(day)
        ]
        return {"plan_date": day.isoformat(), "advisory": True, "items": items}

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
    ``analyst`` and ``approver``, for running the web app locally without Supabase. Without
    ``GEMINI_API_KEY`` every explanation is the template.
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
    cfg = load_explain_config().narrator
    models = {
        "primary": env.get("GEMINI_MODEL_PRIMARY") or cfg.primary,
        "fallback": env.get("GEMINI_MODEL_FALLBACK") or cfg.fallback,
    }
    narrator = Narrator(cfg.model_copy(update=models), env.get("GEMINI_API_KEY") or None)
    origins = _origins(env.get("JOGAN_CORS_ORIGINS", ""))
    regex = env.get("JOGAN_CORS_ORIGIN_REGEX") or None
    return create_app(bundle, store, origins, regex, narrator)
