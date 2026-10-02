"""One error body for every refusal: ``{"detail": <message>, "code": <slug>}`` (D-024).

``detail`` stays a plain string, so a client can always show it; validation errors add
``errors`` (field and message, never the submitted value) and rate limits add
``retry_after_s`` next to the ``Retry-After`` header.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi.responses import JSONResponse

CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    411: "length_required",
    413: "payload_too_large",
    422: "invalid_input",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
    503: "unavailable",
}


def problem(
    status: int, detail: str, headers: Mapping[str, str] | None = None, **extra: Any
) -> JSONResponse:
    body = {"detail": detail, "code": CODES.get(status, "error"), **extra}
    return JSONResponse(body, status_code=status, headers=dict(headers or {}))


def validation_errors(errors: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    """A one-line summary and the list of ``{field, message}``, from pydantic's errors."""
    items = [
        {
            "field": ".".join(str(p) for p in e.get("loc", ())),
            "message": str(e.get("msg", "")).removeprefix("Value error, "),
        }
        for e in errors
    ]
    first = items[0] if items else {"field": "request", "message": "invalid input"}
    return f"{first['field']}: {first['message']}", items
