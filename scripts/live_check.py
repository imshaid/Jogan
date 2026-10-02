"""End-to-end check of the live demo in a real browser, as a judge would use it.

Signs in with the one-click demo accounts on the web app and checks:
- the "Simulated data" badge, and the network map with its day's counts;
- the analyst sees the queue but no decision buttons, and the API refuses the analyst's decision;
- a visit's "Why?" shows the template explanation, the whole interface switches to Bangla, and
  "Reword with AI" answers (Gemini's rewording, or the template with the reason);
- the approver approves one visit and rejects another on the last plan day; a visit flagged for
  manual review is refused without a note and approved with one; every decision appears in the
  append-only audit log, and the agent page shows the approved visit's decision trace;
- the impact page shows the evaluation's numbers without signing in;
- the API answers only the production web origin (CORS) and refuses calls without a token;
- the API checks the token's signature itself (a forged token is a 401), refuses a date that is
  not YYYY-MM-DD, and returns the decision trace of an approved visit with its audit row;
- many requests with forged X-Forwarded-For values still hit this machine's rate limit (429
  with Retry-After), so the client address is read from the right of the header.

It changes live data: two or three recommendations get decided, for good, by the demo approver.
The last step uses up this address's request budget for about half a minute.
Run:

    uv run --with playwright python scripts/live_check.py

Uses the installed Google Chrome (Playwright's ``channel="chrome"``), so no browser download.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx2 as httpx
from playwright.sync_api import Page, expect, sync_playwright

WEB = "https://jogan-bd.vercel.app"
TIMEOUT_MS = 60_000  # a cold Cloud Run start plus the first publish of a day


def api_base(page: Page) -> str:
    """The API URL baked into the web app's JavaScript."""
    for src in page.eval_on_selector_all("script[src]", "els => els.map(e => e.src)"):
        m = re.search(r"https://[a-z0-9.-]+\.run\.app", httpx.get(src).text)
        if m:
            return m.group(0)
    raise RuntimeError("no Cloud Run URL in the web bundle")


def access_token(page: Page) -> str:
    """The signed-in user's Supabase access token, from the browser's storage."""
    raw = page.evaluate(
        "() => Object.entries(localStorage).find(([k]) => k.endsWith('-auth-token'))?.[1]"
    )
    return json.loads(raw)["access_token"]


def sign_in(page: Page, role: str) -> None:
    page.goto(WEB)
    page.get_by_role("button", name=re.compile(rf"^{role.title()}")).click()
    expect(page.get_by_role("heading", name="Network")).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.locator("header").get_by_text(role.title(), exact=True)).to_be_visible(
        timeout=TIMEOUT_MS
    )


def open_queue(page: Page, day: str) -> None:
    page.goto(f"{WEB}/queue?day={day}")
    expect(page.get_by_role("heading", name="Visit queue")).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.locator("tbody tr a").first).to_be_visible(timeout=TIMEOUT_MS)


def button(scope, name: str):
    return scope.get_by_role("button", name=name, exact=True)


def sign_out(page: Page) -> None:
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("heading", name="Sign in to Jogan")).to_be_visible()


def rate_limit(api: str, attempts: int = 4000, batch: int = 64) -> httpx.Response:
    """Health checks with a different forged X-Forwarded-For each; the first 429 answer.

    Each instance keeps its own buckets, and a carrier-grade NAT may send this machine's
    requests from several public addresses, so it can take a few hundred requests.
    """

    def one(i: int) -> httpx.Response:
        forged = f"10.{i // 65536 % 256}.{i // 256 % 256}.{i % 256}"
        return http.get(f"{api}/health", headers={"X-Forwarded-For": forged})

    with httpx.Client(timeout=30) as http, ThreadPoolExecutor(32) as pool:
        for start in range(0, attempts, batch):
            for r in pool.map(one, range(start, start + batch)):
                if r.status_code == 429:
                    return r
    raise AssertionError(f"no 429 in {attempts} requests with forged X-Forwarded-For")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto(WEB)
        expect(page.get_by_text("Simulated data").first).to_be_visible()
        api = api_base(page)
        print(f"web {WEB} → api {api}")

        r = httpx.get(f"{api}/health", headers={"Origin": WEB}, timeout=30)
        assert r.json()["status"] == "ok", r.text
        assert r.headers.get("access-control-allow-origin") == WEB, "CORS for the web app"
        other = httpx.get(f"{api}/health", headers={"Origin": "https://jogan-x.vercel.app"})
        assert "access-control-allow-origin" not in other.headers, "CORS for other origins"
        db = httpx.get(f"{api}/health/db", timeout=30)
        assert db.status_code == 200, db.text
        assert db.json()["database"] == "ok", db.text
        meta = httpx.get(f"{api}/v1/meta").json()
        day = meta["plan_dates"][-1]
        assert httpx.get(f"{api}/v1/plans/{day}").status_code == 401, "no token, no plan"
        assert httpx.get(f"{api}/v1/network/{day}").status_code == 401, "no token, no network"
        print(f"health, database, CORS and 401 ok; bundle {meta['bundle_id']}, checking {day}")

        page.goto(f"{WEB}/impact")
        expect(page.get_by_text("lost requests per 1,000").first).to_be_visible()
        expect(page.get_by_role("heading", name="Where Jogan does not win")).to_be_visible()
        print("impact page public, with the evaluation's numbers")

        sign_in(page, "analyst")
        expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=TIMEOUT_MS)
        first = meta["days"][0]
        expect(page.get_by_text("Planned visits", exact=True).first).to_be_visible()
        print(f"network map shown; {first['visits']} planned visits on {first['date']}")
        open_queue(page, meta["plan_dates"][0])
        rows = page.locator("tbody tr")
        print(f"analyst sees {rows.count()} visits on the first page of {meta['plan_dates'][0]}")
        assert rows.count() > 0
        assert button(page, "Approve").count() == 0, "analyst cannot approve"
        token = access_token(page)
        analyst = {"Authorization": f"Bearer {token}"}
        me = httpx.get(f"{api}/v1/me", headers=analyst).json()
        assert me["role"] == "analyst", me
        assert me["user_id"], me
        head, payload, sig = token.split(".")
        forged = {"Authorization": f"Bearer {head}.{payload}.{sig[::-1]}"}
        r = httpx.get(f"{api}/v1/me", headers=forged)
        assert r.status_code == 401, r.text
        assert r.json()["code"] == "unauthenticated", r.text
        r = httpx.get(f"{api}/v1/plans/1717372800", headers=analyst)
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "invalid_input", r.text
        print("forged token refused by the API (401); a Unix time as a date refused (422)")
        plan = httpx.get(
            f"{api}/v1/plans/{day}", headers={"Authorization": f"Bearer {token}"}, timeout=60
        ).json()
        rec = next(x for x in plan["items"] if x["status"] == "pending")
        refused = httpx.post(
            f"{api}/v1/recommendations/{rec['id']}/decision",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision": "approved"},
        )
        assert refused.status_code == 403, refused.text
        print("analyst decision refused with 403")

        page.locator("tbody tr").first.get_by_role("button", name="Why?").click()
        why = page.locator("tbody tr[id^='why-']").first
        expect(why).to_contain_text("Send runner")
        expect(why).to_contain_text("a prediction")
        button(page, "বাংলা").click()
        expect(page.get_by_role("heading", name="ভিজিটের তালিকা")).to_be_visible()
        expect(why).to_contain_text("পূর্বাভাস")
        button(why, "AI দিয়ে নতুন করে লিখুন").click()
        answer = why.get_by_text(re.compile("নতুন করে লিখেছে|AI-এর লেখা দেখানো হয়নি"))
        expect(answer).to_be_visible(timeout=TIMEOUT_MS)
        print(f"why panel ok; Bangla interface; AI: {answer.inner_text()[:90]}")
        button(page, "EN").click()
        expect(page.get_by_role("heading", name="Visit queue")).to_be_visible()
        sign_out(page)

        sign_in(page, "approver")
        open_queue(page, day)
        expect(button(page, "Approve").first).to_be_visible(timeout=TIMEOUT_MS)
        pending = page.locator("tbody tr", has=button(page, "Approve"))
        plain = pending.filter(has_not_text="Manual review").first
        agent_a = plain.locator("td").first.inner_text().split("\n")[0]
        button(plain, "Approve").click()
        expect(page.locator("tbody tr", has_text=agent_a)).to_contain_text("Approved")
        second = page.locator("tbody tr", has=button(page, "Reject")).first
        agent_r = second.locator("td").first.inner_text().split("\n")[0]
        button(second, "Reject").click()
        expect(page.locator("tbody tr", has_text=agent_r)).to_contain_text("Rejected")
        decided = [("Approved", agent_a), ("Rejected", agent_r)]

        flagged = pending.filter(has_text="Manual review")
        if flagged.count():
            agent_f = flagged.first.locator("td").first.inner_text().split("\n")[0]
            rec = next(x for x in plan["items"] if x["agent_id"] == agent_f)
            approver = {"Authorization": f"Bearer {access_token(page)}"}
            bare = httpx.post(
                f"{api}/v1/recommendations/{rec['id']}/decision",
                headers=approver,
                json={"decision": "approved"},
            )
            assert bare.status_code == 422, bare.text
            button(flagged.first, "Approve").click()
            row = page.locator("tbody tr", has_text=agent_f)
            row.get_by_label(re.compile("Note")).fill("live check: evidence reviewed")
            button(row, "Approve with note").click()
            expect(row).to_contain_text("Approved")
            decided.append(("Approved", agent_f))
            print(f"flagged {agent_f}: refused without a note (422), approved with one")

        # match by recommendation id: earlier bundles may hold decisions on the same agent and day
        rec_id = {x["agent_id"]: x["id"] for x in plan["items"]}
        page.goto(f"{WEB}/audit")
        entries = page.locator("tbody tr")
        expect(entries.first).to_be_visible(timeout=TIMEOUT_MS)
        for action, agent in decided:
            mine = re.compile(rf"#{rec_id[agent]}(?!\d)")
            entry = entries.filter(has_text=mine).filter(has_text=action)
            expect(entry).to_have_count(1)
            expect(entry).to_contain_text(agent)
            expect(entry).to_contain_text("Approver")
        print(f"approver decided {', '.join(a for _, a in decided)} on {day}; all audited")

        page.goto(f"{WEB}/agents/{agent_a}?day={day}")
        steps = page.locator("ol > li")
        expect(steps).to_have_count(8, timeout=TIMEOUT_MS)
        expect(steps.last).to_contain_text("Approved")
        approver = {"Authorization": f"Bearer {access_token(page)}"}
        trace = httpx.get(
            f"{api}/v1/recommendations/{rec_id[agent_a]}/trace", headers=approver, timeout=30
        ).json()
        assert trace["status"] == "approved", trace
        assert trace["served_bundle"], trace
        assert trace["steps"][-1]["by"] == "human", trace["steps"][-1]
        assert [a["action"] for a in trace["audit"]] == ["recommendation.approved"], trace
        print(f"decision trace of {agent_a}: {' → '.join(s['by'] for s in trace['steps'])}")
        browser.close()

    r = rate_limit(api)
    assert r.json()["code"] == "rate_limited", r.text
    retry = r.headers["retry-after"]
    assert int(retry) >= 1, retry
    print(f"forged X-Forwarded-For values still rate-limited: 429, Retry-After {retry} s")
    print("live check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
