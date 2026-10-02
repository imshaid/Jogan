"""API guards (D-024): signed tokens, rate limits, request limits, error bodies, the trace."""

import json
import time

import httpx2 as httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

from jogan.api.app import create_app, from_env
from jogan.api.auth import AuthError, JwksVerifier, StaticVerifier
from jogan.api.bundle import Bundle, save_bundle
from jogan.api.config import Bucket, load_api_config
from jogan.api.guard import Limiter, RateLimited, client_ip
from jogan.api.store import MemoryStore
from jogan.api.trace import decision_trace
from jogan.sim.config import CONFIG_DIR
from tests.test_api import USERS, VERIFIER, auth
from tests.test_ops_costs import _untagged

URL = "https://example-ref.supabase.co"
ISSUER = f"{URL}/auth/v1"
SUB = "6f1c2a8e-0000-4000-8000-000000000001"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def es256_key(kid: str) -> tuple[ec.EllipticCurvePrivateKey, dict]:
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(ECAlgorithm.to_jwk(private.public_key()))
    return private, {**public, "kid": kid, "alg": "ES256", "use": "sig"}


class Jwks:
    """A Supabase JWKS endpoint that counts its calls and can go down."""

    def __init__(self, *keys: dict) -> None:
        self.keys, self.calls, self.down = list(keys), 0, False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{ISSUER}/.well-known/jwks.json"
        self.calls += 1
        if self.down:
            return httpx.Response(503)
        return httpx.Response(200, json={"keys": self.keys})


def claims(**over) -> dict:
    now = int(time.time())
    base = {"iss": ISSUER, "aud": "authenticated", "sub": SUB, "role": "authenticated",
            "iat": now, "exp": now + 3600}  # fmt: skip
    return {k: v for k, v in {**base, **over}.items() if v is not None}


def sign(private, kid: str = "k1", **over) -> str:
    return jwt.encode(claims(**over), private, algorithm="ES256", headers={"kid": kid})


@pytest.fixture
def key() -> tuple:
    return es256_key("k1")


def verifier(jwks: Jwks, clock: Clock) -> JwksVerifier:
    cfg = load_api_config().auth
    return JwksVerifier(URL, cfg, transport=httpx.MockTransport(jwks), clock=clock)


def test_every_api_number_is_tagged() -> None:
    assert _untagged(CONFIG_DIR / "api" / "base.yaml") == []


# --- tokens ---------------------------------------------------------------------------------


def test_a_supabase_token_is_verified_against_the_published_key(key: tuple) -> None:
    private, public = key
    jwks, clock = Jwks(public), Clock()
    v = verifier(jwks, clock)
    token = sign(private)
    assert v.verify(token).user_id == SUB
    assert v.verify(token).token == token
    assert jwks.calls == 1, "the key set is cached"
    clock.t += load_api_config().auth.jwks_ttl_s
    v.verify(token)
    assert jwks.calls == 2, "and refetched once it is older than its lifetime"


def forged(private, public) -> dict[str, str]:
    other, _ = es256_key("k1")
    hs = jwt.encode(claims(), "x" * 32, algorithm="HS256", headers={"kid": "k1"})
    unsigned = jwt.encode(claims(), None, algorithm="none", headers={"kid": "k1"})
    return {
        "another key, same id": sign(other),
        "HS256 (algorithm confusion)": hs,
        "alg none": unsigned,
        "expired": sign(private, exp=int(time.time()) - 3600),
        "other project": sign(private, iss="https://other.supabase.co/auth/v1"),
        "anon audience": sign(private, aud="anon"),
        "anon role": sign(private, role="anon"),
        "service role": sign(private, role="service_role"),
        "no subject": sign(private, sub=None),
        "no expiry": sign(private, exp=None),
        "not a JWT": "abc.def",
        "too long": sign(private) + "A" * 5000,
    }


def test_tokens_failing_any_check_are_refused(key: tuple) -> None:
    private, public = key
    v = verifier(Jwks(public), Clock())
    for name, token in forged(private, public).items():
        with pytest.raises(AuthError) as e:
            v.verify(token)
        assert e.value.status == 401, name
    with pytest.raises(AuthError, match="expired"):
        v.verify(sign(private, exp=int(time.time()) - 3600))


def test_unknown_key_ids_refetch_at_most_once_per_interval(key: tuple) -> None:
    private, public = key
    jwks, clock = Jwks(public), Clock()
    v = verifier(jwks, clock)
    v.verify(sign(private))
    new_private, new_public = es256_key("k2")
    rotated = sign(new_private, kid="k2")
    for _ in range(5):
        with pytest.raises(AuthError):
            v.verify(rotated)
    assert jwks.calls == 1, "made-up key ids cannot make the API hammer Supabase"
    jwks.keys.append(new_public)  # Supabase rotates in a new key
    clock.t += load_api_config().auth.jwks_min_refetch_s
    assert v.verify(rotated).user_id == SUB
    assert jwks.calls == 2


def test_keys_outlive_an_outage_and_none_at_all_is_503(key: tuple) -> None:
    private, public = key
    jwks, clock = Jwks(public), Clock()
    v = verifier(jwks, clock)
    jwks.down = True
    with pytest.raises(AuthError) as e:
        v.verify(sign(private))
    assert e.value.status == 503
    jwks.down = False
    clock.t += load_api_config().auth.jwks_min_refetch_s
    assert v.verify(sign(private)).user_id == SUB
    jwks.down = True
    clock.t += load_api_config().auth.jwks_ttl_s
    assert v.verify(sign(private)).user_id == SUB, "stale keys still verify during an outage"
    assert v.verify(sign(private)).user_id == SUB
    assert jwks.calls == 3, "one failed refetch, then a pause"


def test_the_api_checks_signed_tokens_before_the_store(tiny_bundle: Bundle, key: tuple) -> None:
    private, public = key
    token = sign(private)
    store = MemoryStore({token: (SUB, "analyst")})
    app = create_app(tiny_bundle, store, verifier(Jwks(public), Clock()))
    client = TestClient(app)
    assert client.get("/v1/me", headers=auth(token)).json() == {"user_id": SUB, "role": "analyst"}
    other, _ = es256_key("k1")
    r = client.get("/v1/me", headers=auth(sign(other)))
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid sign-in token", "code": "unauthenticated"}
    assert r.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    r = client.get("/v1/me")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"


def test_the_deployed_app_checks_supabase_tokens(
    tiny_bundle: Bundle, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_bundle(tiny_bundle, tmp_path)
    env = {"JOGAN_BUNDLE_DIR": str(tmp_path), "SUPABASE_URL": URL + "/",
           "SUPABASE_PUBLISHABLE_KEY": "pk", "SUPABASE_SECRET_KEY": "sk",
           "JOGAN_TRUSTED_PROXY_HOPS": "1", "GEMINI_API_KEY": ""}  # fmt: skip
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("JOGAN_STORE", raising=False)
    app = from_env()
    assert isinstance(app.state.verifier, JwksVerifier)
    assert app.state.verifier.jwks_url == f"{ISSUER}/.well-known/jwks.json"
    monkeypatch.setenv("JOGAN_STORE", "memory")
    monkeypatch.setenv("JOGAN_ENV", "development")
    client = TestClient(from_env())
    assert client.get("/v1/me", headers=auth("approver")).json()["role"] == "approver"
    assert client.get("/v1/me", headers=auth("t-approver")).status_code == 401


# --- rate limits ----------------------------------------------------------------------------


def test_a_token_bucket_allows_a_burst_then_its_rate() -> None:
    clock = Clock()
    lim = Limiter({"x": Bucket(per_minute=60, burst=3)}, max_keys=100, clock=clock)
    for _ in range(3):
        lim.hit("x", "a")
    with pytest.raises(RateLimited) as e:
        lim.hit("x", "a")
    assert e.value.retry_after_s == 1
    lim.hit("x", "b")  # another key has its own bucket
    clock.t += 1
    lim.hit("x", "a")
    with pytest.raises(RateLimited):
        lim.hit("x", "a")


def test_the_limiter_keeps_a_bounded_number_of_buckets() -> None:
    clock = Clock()
    lim = Limiter({"x": Bucket(per_minute=60, burst=2)}, max_keys=100, clock=clock)
    for i in range(1000):
        lim.hit("x", str(i))
        assert len(lim._state) <= 100
    lim.hit("x", "999")
    with pytest.raises(RateLimited):
        lim.hit("x", "999")  # a recent bucket was kept


def test_the_client_address_is_read_from_the_right_of_x_forwarded_for() -> None:
    assert client_ip([], "10.0.0.1", 0) == "10.0.0.1"
    assert client_ip(["6.6.6.6"], "10.0.0.1", 0) == "10.0.0.1", "no proxy: the header is forged"
    assert client_ip(["203.0.113.9"], "169.254.1.1", 1) == "203.0.113.9"
    assert client_ip(["6.6.6.6, 7.7.7.7, 203.0.113.9"], None, 1) == "203.0.113.9"
    assert client_ip(["6.6.6.6", "203.0.113.9"], None, 1) == "203.0.113.9"
    assert client_ip(["203.0.113.9, 35.191.0.1"], None, 2) == "203.0.113.9"
    assert client_ip([" "], "10.0.0.1", 1) == "10.0.0.1"
    assert client_ip([], None, 1) == "unknown"


def tight(**buckets: dict) -> tuple:
    cfg = load_api_config({"rate_limit": buckets})
    clock = Clock()
    return cfg, Limiter.from_config(cfg, clock), clock


def test_each_client_address_has_a_limit(tiny_bundle: Bundle) -> None:
    cfg, lim, clock = tight(ip={"per_minute": 60, "burst": 5})
    store = MemoryStore(dict(USERS))
    app = create_app(tiny_bundle, store, VERIFIER, ["http://localhost:3000"],
                     config=cfg, limiter=lim, proxy_hops=1)  # fmt: skip
    client = TestClient(app)
    origin = {"Origin": "http://localhost:3000"}
    for i in range(5):
        spoofed = {"X-Forwarded-For": f"10.9.9.{i}, 203.0.113.9", **origin}
        assert client.get("/health", headers=spoofed).status_code == 200
    r = client.get("/health", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9", **origin})
    assert r.status_code == 429
    assert r.headers["retry-after"] == "1"
    assert r.json() == {"detail": "too many requests; try again in 1 s", "code": "rate_limited",
                        "retry_after_s": 1}  # fmt: skip
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = client.get("/health", headers={"X-Forwarded-For": "198.51.100.7"})
    assert other.status_code == 200
    clock.t += 1
    assert client.get("/health", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 200


def test_each_user_has_a_limit_across_addresses(tiny_bundle: Bundle) -> None:
    cfg, lim, _ = tight(user={"per_minute": 60, "burst": 3})
    app = create_app(tiny_bundle, MemoryStore(dict(USERS)), VERIFIER, config=cfg, limiter=lim,
                     proxy_hops=1)  # fmt: skip
    client = TestClient(app)
    for i in range(3):
        h = {**auth("t-analyst"), "X-Forwarded-For": f"198.51.100.{i}"}
        assert client.get("/v1/me", headers=h).status_code == 200
    h = {**auth("t-analyst"), "X-Forwarded-For": "198.51.100.200"}
    assert client.get("/v1/me", headers=h).status_code == 429
    assert client.get("/v1/me", headers=auth("t-approver")).status_code == 200


def test_deciding_and_ai_rewording_have_their_own_limits(tiny_bundle: Bundle) -> None:
    cfg, lim, _ = tight(decision={"per_minute": 6, "burst": 2},
                        explanation={"per_minute": 6, "burst": 1})  # fmt: skip
    client = TestClient(create_app(tiny_bundle, MemoryStore(dict(USERS)), VERIFIER, config=cfg,
                                   limiter=lim))  # fmt: skip
    day = tiny_bundle.meta["plan_dates"][0]
    rec = client.get(f"/v1/plans/{day}", headers=auth("t-analyst")).json()["items"][0]["id"]
    url = "/v1/recommendations/{}/decision"
    h = auth("t-approver")
    assert client.post(url.format(999998), json={"decision": "rejected"}, headers=h).status_code \
        == 404  # fmt: skip
    assert client.post(url.format(999999), json={"decision": "rejected"}, headers=h).status_code \
        == 404  # fmt: skip
    r = client.post(url.format(rec), json={"decision": "rejected"}, headers=h)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "10"
    assert client.post(url.format(rec), json={"decision": "rejected"},
                       headers=auth("t-analyst")).status_code == 403  # fmt: skip
    why = f"/v1/recommendations/{rec}/explanation"
    assert client.get(why, headers=h).status_code == 200
    assert client.get(why, headers=h).status_code == 429
    assert client.get(why, headers=auth("t-analyst")).status_code == 200


# --- requests, errors and validation --------------------------------------------------------


@pytest.fixture
def client(tiny_bundle: Bundle) -> TestClient:
    return TestClient(create_app(tiny_bundle, MemoryStore(dict(USERS)), VERIFIER))


def test_bodies_must_be_small_and_sized(client: TestClient) -> None:
    url = "/v1/recommendations/1/decision"
    h = auth("t-approver")
    big = client.post(url, json={"decision": "approved", "note": "x" * 9000}, headers=h)
    assert big.status_code == 413
    assert big.json()["code"] == "payload_too_large"
    chunked = client.post(url, content=iter([b'{"decision": "approved"}']),
                          headers={**h, "Content-Type": "application/json"})  # fmt: skip
    assert chunked.status_code == 411


def test_every_refusal_has_the_same_body(client: TestClient) -> None:
    missing = client.get("/v1/nothing")
    assert missing.json() == {"detail": "Not Found", "code": "not_found"}
    wrong = client.get("/v1/recommendations/1/decision", headers=auth("t-approver"))
    assert wrong.status_code == 405
    assert wrong.json()["code"] == "method_not_allowed"
    r = client.post("/v1/recommendations/1/decision", headers=auth("t-approver"),
                    json={"decision": "maybe", "secret": "do not echo"})  # fmt: skip
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid_input"
    assert body["detail"].startswith("body.decision: ")
    assert {e["field"] for e in body["errors"]} == {"body.decision", "body.secret"}
    assert "do not echo" not in r.text, "submitted values are never echoed"
    for res in (missing, wrong, r):
        assert res.headers["cache-control"] == "no-store"
        assert res.headers["x-content-type-options"] == "nosniff"


def test_dates_ids_and_notes_are_validated(client: TestClient, tiny_bundle: Bundle) -> None:
    h = auth("t-analyst")
    day = tiny_bundle.meta["plan_dates"][0]
    assert client.get(f"/v1/plans/{day}", headers=h).status_code == 200
    for bad in ("1717372800", f"{day}T00:00", "2026-02-30", "2026-6-3", "today"):
        assert client.get(f"/v1/plans/{bad}", headers=h).status_code == 422, bad
        assert client.get(f"/v1/anomalies/{bad}", headers=h).status_code == 422, bad
    for bad in ("0", "-1", str(2**63), "1.5", "x"):
        assert client.get(f"/v1/recommendations/{bad}/trace", headers=h).status_code == 422, bad
        assert client.get(f"/v1/audit?recommendation_id={bad}", headers=h).status_code == 422
    url = "/v1/recommendations/1/decision"
    hp = auth("t-approver")
    nul = client.post(url, json={"decision": "rejected", "note": "ok\x00"}, headers=hp)
    assert nul.status_code == 422
    assert nul.json()["errors"] == [
        {"field": "body.note", "message": "the note has control characters"}
    ]
    lines = client.post(url, json={"decision": "rejected", "note": "line 1\nline 2"}, headers=hp)
    assert lines.status_code == 200


def test_an_unexpected_error_is_a_plain_500(tiny_bundle: Bundle) -> None:
    class Broken(MemoryStore):
        def role(self, token: str) -> str | None:
            raise RuntimeError("bug with private detail")

    app = create_app(tiny_bundle, Broken(dict(USERS)), VERIFIER)
    r = TestClient(app, raise_server_exceptions=False).get("/v1/audit", headers=auth("t-analyst"))
    assert r.status_code == 500
    assert r.json() == {"detail": "internal error", "code": "internal_error"}


def test_a_static_verifier_refuses_unknown_tokens() -> None:
    with pytest.raises(AuthError):
        StaticVerifier({"a": "u"}).verify("b")


# --- decision trace -------------------------------------------------------------------------


def test_the_trace_shows_every_layer_and_the_audit_rows(
    client: TestClient, tiny_bundle: Bundle
) -> None:
    day = tiny_bundle.meta["plan_dates"][0]
    items = client.get(f"/v1/plans/{day}", headers=auth("t-analyst")).json()["items"]
    rec, other = items[0], items[-1]
    note = {"decision": "approved", "note": "checked the evidence"}
    url = f"/v1/recommendations/{rec['id']}"
    assert client.post(f"{url}/decision", json=note, headers=auth("t-approver")).status_code == 200
    client.post(f"/v1/recommendations/{other['id']}/decision", json={"decision": "rejected"},
                headers=auth("t-approver"))  # fmt: skip

    t = client.get(f"{url}/trace", headers=auth("t-analyst")).json()
    assert t["served_bundle"] is True
    assert t["status"] == "approved"
    names = [s["step"] for s in t["steps"]]
    assert names == ["forecast", "stock_out_chance", "drivers", "need_and_value", "dispatch",
                     "guardrails", "explanation", "decision"]  # fmt: skip
    by = {s["step"]: s["by"] for s in t["steps"]}
    assert by["decision"] == "human"
    assert "llm" not in {s["by"] for s in t["steps"]}, "the LLM never decides"
    hashes = tiny_bundle.trace(tiny_bundle.plan_dates[0])["config_hashes"]
    for s in t["steps"]:
        if s["config"]:
            assert s["config"]["hash"] == hashes[s["config"]["name"]]
    steps = {s["step"]: s["outputs"] for s in t["steps"]}
    assert steps["dispatch"]["runner_id"] == rec["runner_id"]
    assert steps["drivers"]["drivers"] == rec["evidence"]["drivers"]
    assert steps["decision"]["decision_note"] == "checked the evidence"
    assert t["explanation"] == rec["explanation"]
    assert [a["action"] for a in t["audit"]] == ["recommendation.approved"]
    assert t["audit"][0]["recommendation_id"] == rec["id"]
    flags = {f["agent_id"] for f in tiny_bundle.anomaly_flags(tiny_bundle.plan_dates[0])}
    assert (t["anomaly"] is not None) == (rec["agent_id"] in flags)

    only = client.get(f"/v1/audit?recommendation_id={rec['id']}", headers=auth("t-analyst"))
    assert [a["recommendation_id"] for a in only.json()["items"]] == [rec["id"]]

    assert client.get(f"{url}/trace").status_code == 401
    assert client.get(f"{url}/trace", headers=auth("t-nobody")).status_code == 403
    missing = client.get("/v1/recommendations/999999/trace", headers=auth("t-analyst"))
    assert missing.status_code == 404


def test_a_recommendation_from_another_bundle_has_no_served_evidence(tiny_bundle: Bundle) -> None:
    row = {**tiny_bundle.recommendations(tiny_bundle.plan_dates[0])[0], "id": 7,
           "bundle_id": "older", "plan_date": "2026-05-07", "status": "pending",
           "trace": {}, "decided_by": None, "decided_at": None, "decision_note": None}  # fmt: skip
    t = decision_trace(row, [], tiny_bundle)
    assert t["served_bundle"] is False
    assert t["anomaly"] is None
    assert all(s["config"] is None or s["config"]["hash"] is None for s in t["steps"])
