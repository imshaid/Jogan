"""Read-only views of the served bundle for the web app: the network map, one agent, day counts.

The queue (``/v1/plans``) holds only the visits Jogan planned. The map needs every agent of a
plan day, and the agent page needs one agent's evidence over the whole test window. Both come
straight from the bundle (the replay does not react to decisions), and both carry the same
display text the template uses, so the web app never re-implements feature labels (D-025).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from jogan.api.bundle import EVIDENCE_COLUMNS, Bundle, _plain
from jogan.explain.template import anomaly_items, feature_text, reason_text
from jogan.ops.config import load_ops_config
from jogan.sim.config import load_config

LANGS = ("en", "bn")


def annotate(evidence: dict[str, Any]) -> dict[str, Any]:
    """Evidence with each driver's label and value, and each review reason, as display text."""
    out = dict(evidence)
    drivers = []
    for d in evidence.get("drivers") or []:
        shown = {lang: feature_text(d["feature"], d["value"], lang) for lang in LANGS}
        drivers.append(
            {
                **d,
                "label": {lang: shown[lang][0] for lang in LANGS},
                "value_text": {lang: shown[lang][1] for lang in LANGS},
            }
        )
    out["drivers"] = drivers
    review = evidence.get("review")
    if review is not None:
        reasons = [
            {**r, "text": {lang: reason_text(r, lang) for lang in LANGS}} for r in review["reasons"]
        ]
        out["review"] = {**review, "reasons": reasons}
    return out


def _flagged(bundle: Bundle, day: dt.date) -> set[str]:
    return {f["agent_id"] for f in bundle.anomaly_flags(day)}


def day_counts(bundle: Bundle) -> list[dict[str, Any]]:
    """Per plan day: planned visits, visits for manual review and advisory anomaly flags."""
    plans = bundle.plans
    sent = plans[plans["runner_id"].notna()]
    visits = sent.groupby("plan_date").size()
    review = sent["review"].map(lambda r: bool(json.loads(r)["flag"])).groupby(sent["plan_date"])
    reviewed = review.sum()
    flags = bundle.anomalies.groupby("plan_date").size()
    return [
        {
            "date": d.isoformat(),
            "visits": int(visits.get(d, 0)),
            "manual_review": int(reviewed.get(d, 0)),
            "anomaly_flags": int(flags.get(d, 0)),
        }
        for d in bundle.plan_dates
    ]


def runner_settings(bundle: Bundle) -> dict[str, Any] | None:
    """The runner rules the bundle's world ran under, for the runner screen's times and bag.

    Read from the same sim and ops configs the bundle was built with, so the screen never shows
    a shift, speed or bag the plan did not use; ``None`` if the configs changed since the build.
    """
    sim = load_config(bundle.meta["profile"])
    ops = load_ops_config()
    built = bundle.meta["config_hashes"]
    if built.get("sim") != sim.config_hash() or built.get("ops") != ops.config_hash():
        return None
    r = sim.runners
    return {
        "shift": list(r.shift),
        "visit_minutes": r.visit_minutes,
        "max_visits": r.max_visits,
        "bag_capacity_tk": r.bag_capacity_tk,
        "bag_start_tk": ops.env.runner_bag_start_tk,
        "settings": {
            name: {"speed_kmh": g.runner_speed_kmh, "road_factor": g.road_factor}
            for name, g in sim.geo.settings.items()
        },
        "hubs": {t.code: {"lat": t.lat, "lon": t.lon} for t in sim.geo.territories},
    }


def network(bundle: Bundle, day: dt.date) -> list[dict[str, Any]]:
    """Every agent on the morning of ``day``: place, balances, stock-out chance, planned visit."""
    rows = bundle.plan(day).merge(bundle.agents, on="agent_id", how="left")
    flagged = _flagged(bundle, day)
    out = []
    for r in rows.itertuples(index=False):
        visit = r.runner_id is not None
        review = json.loads(r.review) if visit and isinstance(r.review, str) else None
        out.append(
            {
                "agent_id": r.agent_id,
                "territory": r.territory,
                "setting": r.setting,
                "size_class": r.size_class,
                "lat": round(float(r.lat), 5),
                "lon": round(float(r.lon), 5),
                "cash_tk": _plain(r.cash_tk),
                "efloat_tk": _plain(r.efloat_tk),
                "p_stockout_cash": _plain(r.p_stockout_cash),
                "p_stockout_efloat": _plain(r.p_stockout_efloat),
                "runner_id": r.runner_id,
                "value_tk": round(float(r.value_tk), 2) if visit else None,
                "side": r.side if visit else None,
                "manual_review": bool(review["flag"]) if review else False,
                "anomaly": r.agent_id in flagged,
            }
        )
    return out


def agent(bundle: Bundle, agent_id: str) -> dict[str, Any] | None:
    """One agent's evidence on every plan day and its advisory anomaly flags."""
    known = bundle.agents[bundle.agents["agent_id"] == agent_id]
    if known.empty:
        return None
    info = {k: _plain(v) for k, v in known.iloc[0].to_dict().items()}
    place = bundle.territories.set_index("territory").loc[info["territory"]]
    info |= {"district_en": place["district_en"], "district_bn": place["district_bn"]}
    rows = bundle.plans[bundle.plans["agent_id"] == agent_id].sort_values("plan_date")
    days = []
    for r in rows.itertuples(index=False):
        visit = r.runner_id is not None
        ev: dict[str, Any] = {c: _plain(getattr(r, c)) for c in EVIDENCE_COLUMNS}
        if visit:
            ev |= {"side": r.side, "drivers": json.loads(r.drivers), "review": json.loads(r.review)}
            ev = annotate(ev)
        days.append(
            {
                "plan_date": r.plan_date.isoformat(),
                "runner_id": r.runner_id,
                "candidate": bool(r.candidate),
                "target_cash_tk": round(float(r.target_cash_tk), 2),
                "value_tk": round(float(r.value_tk), 2),
                "evidence": ev,
            }
        )
    flags = bundle.anomalies[bundle.anomalies["agent_id"] == agent_id].sort_values("plan_date")
    anomalies = []
    for f in flags.itertuples(index=False):
        items = json.loads(f.items)
        anomalies.append(
            {
                "plan_date": f.plan_date.isoformat(),
                "date": f.date,
                "score": round(float(f.score), 4),
                "items": items,
                "text": {lang: anomaly_items(items, lang) for lang in LANGS},
            }
        )
    return {"agent": info, "days": days, "anomalies": anomalies}
