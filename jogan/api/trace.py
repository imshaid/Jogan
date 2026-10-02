"""The decision trace of one recommendation: what each layer produced, and who decided (D-024).

The steps follow the logic chain (docs/01-logic-chain.md): the model forecasts and gives the
stock-out chance, TreeSHAP names the drivers, rules turn the forecast into a need and a value,
the optimizer assigns a runner, the guardrails decide whether a person must write a note, the
template writes the explanation, and an approver decides. Each step names the config whose
hash the stored trace recorded, so a reader can tell which version of the rules produced it.
An LLM appears only as an optional rewording of the explanation; it is never a step that
decides anything.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from jogan.api.bundle import Bundle
from jogan.explain.template import render

DRAINS = [f"drain_{side}_q{q}" for side in ("cash", "efloat") for q in (50, 90, 99)]


def _pick(evidence: dict, keys: list[str]) -> dict[str, Any]:
    return {k: evidence.get(k) for k in keys}


def steps(rec: dict) -> list[dict[str, Any]]:
    ev = rec["evidence"]
    hashes = (rec.get("trace") or {}).get("config_hashes", {})
    plan_hour = (rec.get("trace") or {}).get("plan_hour")

    def step(name: str, by: str, what: str, config: str | None, **outputs: Any) -> dict:
        cfg = {"name": config, "hash": hashes.get(config)} if config else None
        return {"step": name, "by": by, "what": what, "config": cfg, "outputs": outputs}

    side = ev.get("side")
    return [
        step(
            "forecast",
            "model",
            "LightGBM quantile forecast of the next 24 hours' peak drain, calibrated by CQR",
            "forecast",
            inputs=_pick(ev, ["cash_tk", "efloat_tk"]) | {"plan_hour": plan_hour},
            **_pick(ev, DRAINS),
        ),
        step(
            "stock_out_chance",
            "model",
            "chance that the drain exceeds the balance on each side; the higher side is at risk",
            "forecast",
            **_pick(ev, ["p_stockout_cash", "p_stockout_efloat"]),
            side_at_risk=side,
        ),
        step(
            "drivers",
            "model explanation",
            "TreeSHAP contributions on the 24-hour 0.9-quantile model of the side at risk",
            "explain",
            drivers=ev.get("drivers", []),
        ),
        step(
            "need_and_value",
            "rule",
            "newsvendor need on each side, and the value of a visit including the call it saves",
            "plan",
            **_pick(ev, ["need_cash_tk", "need_efloat_tk", "needs_fit"]),
            value_tk=rec.get("value_tk"),
        ),
        step(
            "dispatch",
            "optimizer",
            "runner assignment by a MILP per territory (HiGHS), with route check and fill step",
            "plan",
            runner_id=rec.get("runner_id"),
            target_cash_tk=rec.get("target_cash_tk"),
        ),
        step(
            "guardrails",
            "rule",
            "manual review when the evidence is out of range, wide, gappy, short or flagged",
            "explain",
            review=ev.get("review"),
        ),
        step(
            "explanation",
            "template",
            "written from the evidence above; an LLM may reword it on request, never decide",
            "explain",
        ),
        step(
            "decision",
            "human",
            "an approver approves or rejects; a flagged visit needs a note; every decision is "
            "audited",
            None,
            status=rec.get("status"),
            decided_by=rec.get("decided_by"),
            decided_at=rec.get("decided_at"),
            decision_note=rec.get("decision_note"),
        ),
    ]


def decision_trace(rec: dict, audit: list[dict], bundle: Bundle) -> dict[str, Any]:
    """Everything behind one recommendation; ``audit`` holds its audit rows, newest first."""
    served = rec["bundle_id"] == bundle.bundle_id
    anomaly = None
    if served:
        day = dt.date.fromisoformat(str(rec["plan_date"]))
        anomaly = next(
            (f for f in bundle.anomaly_flags(day) if f["agent_id"] == rec["agent_id"]), None
        )
    return {
        "recommendation_id": rec["id"],
        "bundle_id": rec["bundle_id"],
        "served_bundle": served,
        "plan_date": rec["plan_date"],
        "agent_id": rec["agent_id"],
        "territory": rec["territory"],
        "status": rec["status"],
        "trace": rec.get("trace") or {},
        "steps": steps(rec),
        "explanation": {lang: render(rec, lang) for lang in ("en", "bn")},
        "anomaly": anomaly,
        "audit": sorted(audit, key=lambda a: a["id"]),
    }
