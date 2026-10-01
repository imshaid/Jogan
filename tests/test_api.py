"""API on the tiny bundle with the in-memory store: roles, publish once, decide, audit."""

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jogan.api.app import create_app
from jogan.api.bundle import Bundle, build_bundle, load_bundle, save_bundle
from jogan.api.store import MemoryStore

FAST = {"lightgbm": {"num_boost_round": 30, "num_threads": 4}}
USERS = {
    "t-analyst": ("u-analyst", "analyst"),
    "t-approver": ("u-approver", "approver"),
    "t-nobody": ("u-nobody", None),
}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle("tiny", 0, FAST)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore(dict(USERS))


@pytest.fixture
def client(bundle: Bundle, store: MemoryStore) -> TestClient:
    return TestClient(create_app(bundle, store))


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
    trace = bundle.trace(bundle.plan_dates[0])
    assert trace["bundle_id"] == bundle.bundle_id
    assert set(trace["config_hashes"]) == {"sim", "ops", "forecast", "plan"}


def test_bundle_round_trips_through_files(bundle: Bundle, tmp_path: Path) -> None:
    save_bundle(bundle, tmp_path)
    loaded = load_bundle(tmp_path)
    assert loaded.meta == bundle.meta
    day = bundle.plan_dates[-1]
    assert loaded.recommendations(day) == bundle.recommendations(day)


def test_health_and_meta_need_no_sign_in(client: TestClient, bundle: Bundle) -> None:
    assert client.get("/health").json()["bundle_id"] == bundle.bundle_id
    meta = client.get("/v1/meta").json()
    assert meta["simulated"] is True
    assert meta["plan_dates"] == bundle.meta["plan_dates"]


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
        bundle, store, ["http://localhost:3000"], r"https://jogan[a-z0-9-]*\.vercel\.app"
    )
    client = TestClient(app)

    def allowed(origin: str) -> str | None:
        r = client.get("/health", headers={"Origin": origin})
        return r.headers.get("access-control-allow-origin")

    assert allowed("http://localhost:3000") == "http://localhost:3000"
    assert allowed("https://jogan-imshaid.vercel.app") == "https://jogan-imshaid.vercel.app"
    assert allowed("https://evil.example") is None
    assert allowed("https://jogan.vercel.app.evil.example") is None
