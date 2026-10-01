"""Where recommendations, decisions and the audit log live: Supabase, or memory in tests.

Supabase is reached over HTTPS (PostgREST), never with a direct database connection (D-002 #6).
Reads and decisions are sent with the signed-in user's JWT, so row-level security decides what
each role may see and do; the rules live in ``supabase/migrations/``. Only publishing a day's
plan uses the secret key, through ``publish_plan``, which the database lets no user call.

:class:`MemoryStore` implements the same rules for tests and local runs without Supabase.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import itertools
import threading
from typing import Any, Protocol

import httpx2 as httpx

ROLES = ("analyst", "approver")
DECISIONS = ("approved", "rejected")
NOTE_MAX = 500
REVIEW_NOTE = "a recommendation flagged for manual review needs a note to approve"


class StoreError(Exception):
    """A refused request; ``status`` is the HTTP status the API answers with."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


class Store(Protocol):
    def role(self, token: str) -> str | None: ...

    def publish(self, bundle_id: str, day: dt.date, rows: list[dict], trace: dict) -> int: ...

    def queue(self, token: str, bundle_id: str, day: dt.date) -> list[dict]: ...

    def recommendation(self, token: str, rec_id: int) -> dict | None: ...

    def decide(self, token: str, rec_id: int, decision: str, note: str | None) -> dict: ...

    def audit(self, token: str, limit: int) -> list[dict]: ...


# --- Supabase -------------------------------------------------------------------------------

# SQLSTATE raised by the database functions → HTTP status of the API
_SQLSTATE = {
    "42501": 403,  # insufficient_privilege: wrong role
    "P0002": 404,  # no_data_found: unknown recommendation
    "55000": 409,  # object_not_in_prerequisite_state: already decided
    "22023": 422,  # invalid_parameter_value
    "22001": 422,  # string_data_right_truncation: note too long
    "PGRST301": 401,  # JWT could not be decoded
    "PGRST303": 401,  # JWT claims invalid (expired)
}


@dataclasses.dataclass(frozen=True)
class SupabaseConfig:
    url: str
    publishable_key: str
    secret_key: str


class SupabaseStore:
    def __init__(self, cfg: SupabaseConfig, timeout_s: float = 10.0) -> None:
        self.cfg = cfg
        self.http = httpx.Client(base_url=f"{cfg.url.rstrip('/')}/rest/v1", timeout=timeout_s)

    def _user(self, token: str) -> dict[str, str]:
        return {"apikey": self.cfg.publishable_key, "Authorization": f"Bearer {token}"}

    def _service(self) -> dict[str, str]:
        return {"apikey": self.cfg.secret_key}

    def _send(self, method: str, path: str, headers: dict, **kw: Any) -> Any:
        try:
            r = self.http.request(method, path, headers=headers, **kw)
        except httpx.HTTPError as e:
            raise StoreError(503, "database unavailable") from e
        if r.is_success:
            return r.json() if r.content else None
        try:
            body = r.json()
        except ValueError:
            body = {}
        code = str(body.get("code", ""))
        status = _SQLSTATE.get(code, 401 if r.status_code == 401 else 502)
        message = body.get("message", "") if status != 502 else "database error"
        raise StoreError(status, message or "request refused")

    def role(self, token: str) -> str | None:
        rows = self._send("GET", "/user_roles", self._user(token), params={"select": "role"})
        return rows[0]["role"] if rows else None

    def publish(self, bundle_id: str, day: dt.date, rows: list[dict], trace: dict) -> int:
        body = {
            "p_bundle_id": bundle_id,
            "p_plan_date": day.isoformat(),
            "p_rows": rows,
            "p_trace": trace,
        }
        return int(self._send("POST", "/rpc/publish_plan", self._service(), json=body))

    def queue(self, token: str, bundle_id: str, day: dt.date) -> list[dict]:
        params = {
            "select": "*",
            "bundle_id": f"eq.{bundle_id}",
            "plan_date": f"eq.{day.isoformat()}",
            "order": "value_tk.desc,id.asc",
        }
        return self._send("GET", "/recommendations", self._user(token), params=params)

    def recommendation(self, token: str, rec_id: int) -> dict | None:
        params = {"select": "*", "id": f"eq.{rec_id}"}
        rows = self._send("GET", "/recommendations", self._user(token), params=params)
        return rows[0] if rows else None

    def decide(self, token: str, rec_id: int, decision: str, note: str | None) -> dict:
        body = {"p_id": rec_id, "p_decision": decision, "p_note": note}
        return self._send("POST", "/rpc/decide_recommendation", self._user(token), json=body)

    def audit(self, token: str, limit: int) -> list[dict]:
        params = {"select": "*", "order": "id.desc", "limit": str(limit)}
        return self._send("GET", "/audit_log", self._user(token), params=params)


# --- Memory ---------------------------------------------------------------------------------


class MemoryStore:
    """The database rules in memory. ``users`` maps a token to ``(user_id, role)``."""

    def __init__(self, users: dict[str, tuple[str, str | None]]) -> None:
        self.users = users
        self.recommendations: list[dict] = []
        self.audit_log: list[dict] = []
        self._ids = itertools.count(1)
        self._audit_ids = itertools.count(1)
        self._lock = threading.Lock()

    def _who(self, token: str) -> tuple[str, str | None]:
        if token not in self.users:
            raise StoreError(401, "invalid token")
        return self.users[token]

    def _log(self, actor: str | None, role: str, action: str, rec_id: int | None, detail: dict):
        self.audit_log.append(
            {
                "id": next(self._audit_ids),
                "at": _now(),
                "actor": actor,
                "actor_role": role,
                "action": action,
                "recommendation_id": rec_id,
                "detail": detail,
            }
        )

    def role(self, token: str) -> str | None:
        return self._who(token)[1]

    def publish(self, bundle_id: str, day: dt.date, rows: list[dict], trace: dict) -> int:
        date = day.isoformat()
        with self._lock:
            if any(
                r["bundle_id"] == bundle_id and r["plan_date"] == date for r in self.recommendations
            ):
                return 0
            for row in rows:
                self.recommendations.append(
                    {
                        "id": next(self._ids),
                        "bundle_id": bundle_id,
                        "plan_date": date,
                        **row,
                        "action": "visit",
                        "trace": trace,
                        "status": "pending",
                        "decided_by": None,
                        "decided_at": None,
                        "decision_note": None,
                        "created_at": _now(),
                    }
                )
            if rows:
                detail = {"bundle_id": bundle_id, "plan_date": date, "recommendations": len(rows)}
                self._log(None, "system", "plan.published", None, detail)
        return len(rows)

    def queue(self, token: str, bundle_id: str, day: dt.date) -> list[dict]:
        _, role = self._who(token)
        if not role:
            return []  # row-level security hides every row from a user without a role
        date = day.isoformat()
        rows = [
            r
            for r in self.recommendations
            if r["bundle_id"] == bundle_id and r["plan_date"] == date
        ]
        return sorted(rows, key=lambda r: (-r["value_tk"], r["id"]))

    def recommendation(self, token: str, rec_id: int) -> dict | None:
        _, role = self._who(token)
        if not role:
            return None
        return next((dict(r) for r in self.recommendations if r["id"] == rec_id), None)

    def decide(self, token: str, rec_id: int, decision: str, note: str | None) -> dict:
        user, role = self._who(token)
        if role != "approver":
            raise StoreError(403, "only an approver can decide")
        if decision not in DECISIONS:
            raise StoreError(422, "decision must be approved or rejected")
        if note is not None and len(note) > NOTE_MAX:
            raise StoreError(422, "note is too long")
        with self._lock:
            rec = next((r for r in self.recommendations if r["id"] == rec_id), None)
            if rec is None:
                raise StoreError(404, f"recommendation {rec_id} not found")
            if rec["status"] != "pending":
                raise StoreError(409, f"recommendation {rec_id} is already decided")
            note = (note or "").strip() or None
            review = bool((rec["evidence"].get("review") or {}).get("flag", False))
            if decision == "approved" and review and note is None:
                raise StoreError(422, REVIEW_NOTE)
            rec.update(status=decision, decided_by=user, decided_at=_now(), decision_note=note)
            detail = {
                "note": note,
                "agent_id": rec["agent_id"],
                "plan_date": rec["plan_date"],
                "bundle_id": rec["bundle_id"],
                "manual_review": review,
            }
            self._log(user, role, f"recommendation.{decision}", rec_id, detail)
            return dict(rec)

    def audit(self, token: str, limit: int) -> list[dict]:
        _, role = self._who(token)
        if not role:
            return []
        return sorted(self.audit_log, key=lambda r: -r["id"])[:limit]


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()
