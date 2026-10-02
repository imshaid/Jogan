"""API on the tiny bundle with the in-memory store: roles, publish once, decide, audit.

Tokens are opaque here (:class:`StaticVerifier`); ``test_api_guard.py`` checks real signed
tokens, rate limits, error bodies, input validation and the decision trace.
"""

import dataclasses
import datetime as dt
import json
from pathlib import Path

import httpx2 as httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from jogan.api.app import create_app
from jogan.api.auth import StaticVerifier
from jogan.api.bundle import Bundle, load_bundle, save_bundle
from jogan.api.config import load_api_config
from jogan.api.store import REVIEW_NOTE, MemoryStore, StoreError, SupabaseConfig, SupabaseStore
from jogan.explain.config import load_explain_config
from jogan.explain.narrator import Narrator

USERS = {
    "t-analyst": ("u-analyst", "analyst"),
    "t-approver": ("u-approver", "approver"),
    "t-nobody": ("u-nobody", None),
}
VERIFIER = StaticVerifier({token: user for token, (user, _) in USERS.items()})


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def bundle(tiny_bundle: Bundle) -> Bundle:
    return tiny_bundle


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore(dict(USERS))


@pytest.fixture
def client(bundle: Bundle, store: MemoryStore) -> TestClient:
    return TestClient(create_app(bundle, store, VERIFIER))


def first_day(bundle: Bundle) -> str:
    return bundle.meta["plan_dates"][0]


def test_bundle_covers_the_test_window(bundle: Bundle) -> None:
    start, end = (dt.date.fromisoformat(d) for d in bundle.meta["test_window"])
    assert bundle.plan_dates == [start + dt.timedelta(d) for d in range((end - start).days + 1)]
    n_agents = bundle.meta["counts"]["agents"]
    assert (bundle.plans.groupby("plan_date").size() == n_agents).all()
    recs = bundle.recommendations(bundle.plan_dates[0])
    assert recs, "the tiny world should get at least one visit on its first test day"
    assert [r["value_tk"] for r in recs] == sorted((r["value_tk"] for r in recs), reverse=True)
    assert {"p_stockout_cash", "drain_cash_q90", "need_efloat_tk"} <= recs[0]["evidence"].keys()
    for r in recs:
        ev = r["evidence"]
        assert ev["side"] in ("cash", "efloat")
        assert ev[f"p_stockout_{ev['side']}"] == max(ev["p_stockout_cash"], ev["p_stockout_efloat"])
        assert 0 < len(ev["drivers"]) <= 3
        assert set(ev["review"]) == {"flag", "reasons"}
        assert ev["review"]["flag"] == bool(ev["review"]["reasons"])
    counts = bundle.meta["counts"]
    reviewed = sum(r["evidence"]["review"]["flag"] for d in bundle.plan_dates
                   for r in bundle.recommendations(d))  # fmt: skip
    assert counts["manual_review"] == reviewed
    assert counts["anomaly_flags"] == len(bundle.anomalies)
    trace = bundle.trace(bundle.plan_dates[0])
    assert trace["bundle_id"] == bundle.bundle_id
    assert set(trace["config_hashes"]) == {"sim", "ops", "forecast", "plan", "explain"}


def test_bundle_round_trips_through_files(bundle: Bundle, tmp_path: Path) -> None:
    save_bundle(bundle, tmp_path)
    loaded = load_bundle(tmp_path)
    assert loaded.meta == bundle.meta
    day = bundle.plan_dates[-1]
    assert loaded.recommendations(day) == bundle.recommendations(day)
    assert loaded.anomalies.equals(bundle.anomalies)


def test_health_and_meta_need_no_sign_in(client: TestClient, bundle: Bundle) -> None:
    assert client.get("/health").json()["bundle_id"] == bundle.bundle_id
    meta = client.get("/v1/meta").json()
    assert meta["simulated"] is True
    assert meta["plan_dates"] == bundle.meta["plan_dates"]


def test_health_db_asks_the_store_at_most_once_per_cache_window(bundle: Bundle) -> None:
    class Counted(MemoryStore):
        pings, down = 0, False

        def ping(self) -> None:
            self.pings += 1
            if self.down:
                raise StoreError(503, "database unavailable")

    store = Counted(dict(USERS))
    cached = TestClient(create_app(bundle, store, VERIFIER))
    ok = {"status": "ok", "database": "ok", "bundle_id": bundle.bundle_id}
    assert cached.get("/health/db").json() == ok
    store.down = True
    assert cached.get("/health/db").json() == ok  # the answer is reused within db_cache_s
    assert store.pings == 1
    cfg = load_api_config({"health": {"db_cache_s": 0}})
    r = TestClient(create_app(bundle, store, VERIFIER, config=cfg)).get("/health/db")
    assert r.status_code == 503
    assert r.json() == {"detail": "database unavailable", "code": "unavailable"}
    assert store.pings == 2


def test_uptime_monitors_may_send_head_and_still_reach_the_database(bundle: Bundle) -> None:
    class Counted(MemoryStore):
        pings = 0

        def ping(self) -> None:
            self.pings += 1

    store = Counted(dict(USERS))
    c = TestClient(create_app(bundle, store, VERIFIER))
    for path in ("/health", "/health/db"):
        r = c.head(path)
        assert r.status_code == 200, path
        assert r.content == b""
    assert store.pings == 1  # HEAD runs the check, so it keeps the database awake
    assert c.post("/health/db", headers={"Content-Length": "0"}).status_code == 405


def test_supabase_ping_reads_one_id_with_the_secret_key() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"id": 1}])

    store = SupabaseStore(SupabaseConfig("https://x.supabase.co", "pub-key", "secret-key"))
    store.http = httpx.Client(
        base_url="https://x.supabase.co/rest/v1", transport=httpx.MockTransport(answer)
    )
    store.ping()
    (request,) = seen
    assert request.method == "GET"
    assert request.url.path == "/rest/v1/recommendations"
    assert dict(request.url.params) == {"select": "id", "limit": "1"}
    assert request.headers["apikey"] == "secret-key"

    store.http = httpx.Client(
        base_url="https://x.supabase.co/rest/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(503, text="paused")),
    )
    with pytest.raises(StoreError):
        store.ping()


def test_plans_need_a_signed_in_user_with_a_role(client: TestClient, bundle: Bundle) -> None:
    day = first_day(bundle)
    assert client.get(f"/v1/plans/{day}").status_code == 401
    assert client.get(f"/v1/plans/{day}", headers=auth("forged")).status_code == 401
    assert client.get(f"/v1/plans/{day}", headers=auth("t-nobody")).status_code == 403
    assert client.get("/v1/plans/1999-01-01", headers=auth("t-analyst")).status_code == 404


def test_a_day_is_published_once(client: TestClient, store: MemoryStore, bundle: Bundle) -> None:
    day = first_day(bundle)
    first = client.get(f"/v1/plans/{day}", headers=auth("t-analyst")).json()["items"]
    again = client.get(f"/v1/plans/{day}", headers=auth("t-approver")).json()["items"]
    assert len(first) == len(bundle.recommendations(bundle.plan_dates[0]))
    assert [r["id"] for r in first] == [r["id"] for r in again]
    assert all(r["status"] == "pending" for r in first)
    published = [a for a in store.audit_log if a["action"] == "plan.published"]
    assert len(published) == 1
    assert published[0]["actor"] is None
    assert published[0]["actor_role"] == "system"


def test_only_an_approver_decides_and_every_decision_is_audited(
    client: TestClient, store: MemoryStore, bundle: Bundle
) -> None:
    day = first_day(bundle)
    items = client.get(f"/v1/plans/{day}", headers=auth("t-analyst")).json()["items"]
    rec = items[0]["id"]
    url = f"/v1/recommendations/{rec}/decision"
    assert client.post(url, json={"decision": "approved"}).status_code == 401
    analyst = client.post(url, json={"decision": "approved"}, headers=auth("t-analyst"))
    assert analyst.status_code == 403
    assert store.recommendations[0]["status"] == "pending"

    r = client.post(url, json={"decision": "approved", "note": " ok "}, headers=auth("t-approver"))
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["decided_by"] == "u-approver"
    assert r.json()["decision_note"] == "ok"
    again = client.post(url, json={"decision": "rejected"}, headers=auth("t-approver"))
    assert again.status_code == 409

    audit = client.get("/v1/audit", headers=auth("t-analyst")).json()["items"]
    assert audit[0]["action"] == "recommendation.approved"
    assert audit[0]["actor"] == "u-approver"
    assert audit[0]["recommendation_id"] == rec
    assert sum(a["action"].startswith("recommendation.") for a in audit) == 1


def test_bad_decisions_are_refused(client: TestClient, bundle: Bundle) -> None:
    client.get(f"/v1/plans/{first_day(bundle)}", headers=auth("t-analyst"))
    h = auth("t-approver")
    url = "/v1/recommendations/{}/decision"
    assert client.post(url.format(1), json={"decision": "maybe"}, headers=h).status_code == 422
    long_note = {"decision": "rejected", "note": "x" * 501}
    assert client.post(url.format(1), json=long_note, headers=h).status_code == 422
    missing = client.post(url.format(999999), json={"decision": "rejected"}, headers=h)
    assert missing.status_code == 404


def test_audit_needs_a_role(client: TestClient) -> None:
    assert client.get("/v1/audit").status_code == 401
    assert client.get("/v1/audit", headers=auth("t-nobody")).status_code == 403
    assert client.get("/v1/audit?limit=0", headers=auth("t-analyst")).status_code == 422


def test_cors_allows_only_configured_origins(bundle: Bundle, store: MemoryStore) -> None:
    app = create_app(
        bundle,
        store,
        VERIFIER,
        ["http://localhost:3000"],
        r"https://jogan[a-z0-9-]*\.vercel\.app",
    )
    client = TestClient(app)

    def allowed(origin: str) -> str | None:
        r = client.get("/health", headers={"Origin": origin})
        return r.headers.get("access-control-allow-origin")

    assert allowed("http://localhost:3000") == "http://localhost:3000"
    assert allowed("https://jogan-imshaid.vercel.app") == "https://jogan-imshaid.vercel.app"
    assert allowed("https://evil.example") is None
    assert allowed("https://jogan.vercel.app.evil.example") is None


def test_queue_rows_carry_bilingual_template_explanations(
    client: TestClient, bundle: Bundle
) -> None:
    items = client.get(f"/v1/plans/{first_day(bundle)}", headers=auth("t-analyst")).json()["items"]
    for r in items:
        assert r["explanation"]["en"].startswith(f"Send runner {r['runner_id']} to agent")
        assert "পূর্বাভাস" in r["explanation"]["bn"]


def gemini(text: str, status: int = 200) -> Narrator:
    def answer(request: httpx.Request) -> httpx.Response:
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"text": text})}]}}]}
        return httpx.Response(status, json=body)

    cfg = load_explain_config().narrator
    return Narrator(cfg, "test-key", transport=httpx.MockTransport(answer))


def test_explanation_is_reworded_only_when_it_keeps_the_evidence(
    bundle: Bundle, store: MemoryStore
) -> None:
    day = first_day(bundle)
    plain = TestClient(create_app(bundle, store, VERIFIER))
    items = plain.get(f"/v1/plans/{day}", headers=auth("t-analyst")).json()["items"]
    rec = items[0]
    url = f"/v1/recommendations/{rec['id']}/explanation"
    off = plain.get(url, headers=auth("t-analyst")).json()
    assert off["source"] == "template"
    assert off["text"] == off["template"] == rec["explanation"]["en"]

    side = rec["evidence"]["side"]
    p = round(rec["evidence"][f"p_stockout_{side}"] * 100)
    good = f"Runner {rec['runner_id']} should visit {rec['agent_id']}: a predicted {p}% chance."
    on = TestClient(create_app(bundle, store, VERIFIER, narrator=gemini(good))).get(
        url, headers=auth("t-analyst")
    )
    assert on.json()["source"] == "gemini"
    assert on.json()["text"] == good

    bad_narrator = gemini(good + " Saves 123457 taka.")
    bad = TestClient(create_app(bundle, store, VERIFIER, narrator=bad_narrator))
    refused = bad.get(url + "?lang=bn", headers=auth("t-approver")).json()
    assert refused["source"] == "template"
    assert refused["text"] == rec["explanation"]["bn"]

    assert plain.get(url).status_code == 401
    assert plain.get(url, headers=auth("t-nobody")).status_code == 403
    assert plain.get(url + "?lang=fr", headers=auth("t-analyst")).status_code == 422
    missing = "/v1/recommendations/999999/explanation"
    assert plain.get(missing, headers=auth("t-analyst")).status_code == 404


def test_anomaly_flags_are_advisory_and_need_a_role(client: TestClient, bundle: Bundle) -> None:
    day = first_day(bundle)
    r = client.get(f"/v1/anomalies/{day}", headers=auth("t-analyst"))
    assert r.status_code == 200
    assert r.json()["advisory"] is True
    assert len(r.json()["items"]) == len(bundle.anomaly_flags(bundle.plan_dates[0]))
    assert client.get(f"/v1/anomalies/{day}").status_code == 401
    assert client.get(f"/v1/anomalies/{day}", headers=auth("t-nobody")).status_code == 403
    assert client.get("/v1/anomalies/1999-01-01", headers=auth("t-analyst")).status_code == 404


def test_a_flagged_recommendation_needs_a_note_to_approve(
    client: TestClient, store: MemoryStore
) -> None:
    review = {"flag": True, "reasons": [{"code": "data_gap", "arrived": 6, "hours": 24}]}
    row = {"agent_id": "X-001", "territory": "X", "runner_id": "X-R1", "target_cash_tk": 1.0,
           "value_tk": 1.0, "evidence": {"review": review}}  # fmt: skip
    store.publish("other", dt.date(2026, 5, 7), [row, {**row, "agent_id": "X-002"}], {})
    first, second = (r["id"] for r in store.recommendations[-2:])
    url = "/v1/recommendations/{}/decision"
    h = auth("t-approver")
    refused = client.post(url.format(first), json={"decision": "approved"}, headers=h)
    assert refused.status_code == 422
    assert refused.json()["detail"] == REVIEW_NOTE
    blank = client.post(url.format(first), json={"decision": "approved", "note": " "}, headers=h)
    assert blank.status_code == 422
    note = {"decision": "approved", "note": "data arrived late; called the agent"}
    assert client.post(url.format(first), json=note, headers=h).status_code == 200
    assert (
        client.post(url.format(second), json={"decision": "rejected"}, headers=h).status_code == 200
    )
    audit = client.get("/v1/audit", headers=h).json()["items"]
    assert [a["detail"]["manual_review"] for a in audit[:2]] == [True, True]


def test_meta_counts_every_plan_day(client: TestClient, bundle: Bundle) -> None:
    days = client.get("/v1/meta").json()["days"]
    assert [d["date"] for d in days] == bundle.meta["plan_dates"]
    counts = bundle.meta["counts"]
    assert sum(d["visits"] for d in days) == counts["recommendations"]
    assert sum(d["manual_review"] for d in days) == counts["manual_review"]
    assert sum(d["anomaly_flags"] for d in days) == counts["anomaly_flags"]


def test_the_network_shows_every_agent_and_the_planned_visits(
    client: TestClient, bundle: Bundle
) -> None:
    day = first_day(bundle)
    url = f"/v1/network/{day}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth("t-nobody")).status_code == 403
    assert client.get("/v1/network/1999-01-01", headers=auth("t-analyst")).status_code == 404
    r = client.get(url, headers={**auth("t-analyst"), "Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"
    agents = r.json()["agents"]
    assert len(agents) == bundle.meta["counts"]["agents"]
    recs = {x["agent_id"]: x for x in bundle.recommendations(bundle.plan_dates[0])}
    assert {a["agent_id"] for a in agents if a["runner_id"]} == set(recs)
    for a in agents:
        assert all(0 <= a[f"p_stockout_{s}"] <= 1 for s in ("cash", "efloat"))
        assert abs(a["lat"]) <= 90
        assert abs(a["lon"]) <= 180
        if a["runner_id"]:
            rec = recs[a["agent_id"]]
            assert a["side"] == rec["evidence"]["side"]
            assert a["manual_review"] == rec["evidence"]["review"]["flag"]
        else:
            assert (a["side"], a["value_tk"], a["manual_review"]) == (None, None, False)


def test_queue_and_trace_carry_display_text_for_drivers_and_reasons(
    client: TestClient, bundle: Bundle
) -> None:
    items = client.get(f"/v1/plans/{first_day(bundle)}", headers=auth("t-analyst")).json()["items"]
    for r in items:
        for d in r["evidence"]["drivers"]:
            assert all(d["label"][lang] for lang in ("en", "bn"))
            assert all(d["value_text"][lang] for lang in ("en", "bn"))
        for reason in r["evidence"]["review"]["reasons"]:
            assert all(reason["text"][lang] for lang in ("en", "bn"))
    trace = client.get(f"/v1/recommendations/{items[0]['id']}/trace", headers=auth("t-analyst"))
    drivers = next(s for s in trace.json()["steps"] if s["step"] == "drivers")["outputs"]
    assert drivers["drivers"] == items[0]["evidence"]["drivers"]


def test_an_agent_has_its_evidence_on_every_plan_day(client: TestClient, bundle: Bundle) -> None:
    rec = bundle.recommendations(bundle.plan_dates[0])[0]
    flag = {"plan_date": bundle.plan_dates[1], "agent_id": rec["agent_id"],
            "date": bundle.meta["plan_dates"][0], "score": 0.5,
            "items": json.dumps([{"feature": "night_n", "value": 4}])}  # fmt: skip
    flagged = dataclasses.replace(bundle, anomalies=pd.DataFrame([flag]))
    c = TestClient(create_app(flagged, MemoryStore(dict(USERS)), VERIFIER))
    url = f"/v1/agents/{rec['agent_id']}"
    assert c.get(url).status_code == 401
    assert c.get(url, headers=auth("t-nobody")).status_code == 403
    assert c.get("/v1/agents/ZZZ-999", headers=auth("t-analyst")).status_code == 404
    assert c.get("/v1/agents/drop%20table", headers=auth("t-analyst")).status_code == 422
    body = c.get(url, headers=auth("t-analyst")).json()
    assert body["agent"]["agent_id"] == rec["agent_id"]
    assert body["agent"]["district_bn"]
    assert [d["plan_date"] for d in body["days"]] == bundle.meta["plan_dates"]
    first = body["days"][0]
    assert first["runner_id"] == rec["runner_id"]
    assert first["evidence"]["p_stockout_cash"] == rec["evidence"]["p_stockout_cash"]
    assert [d["feature"] for d in first["evidence"]["drivers"]] == [
        d["feature"] for d in rec["evidence"]["drivers"]
    ]
    assert all(d["label"]["bn"] for d in first["evidence"]["drivers"])
    assert all("drivers" not in d["evidence"] for d in body["days"] if d["runner_id"] is None)
    [anomaly] = body["anomalies"]
    assert anomaly["plan_date"] == bundle.meta["plan_dates"][1]
    assert anomaly["text"]["en"].startswith("transactions outside opening hours")
