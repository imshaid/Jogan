"""End-to-end check of the live demo in a real browser, as a judge would use it.

Signs in with the one-click demo accounts on the web app and checks:
- the "Simulated data" badge;
- the analyst sees the queue but no decision buttons, and the API refuses the analyst's decision;
- the approver approves one visit and rejects another on the last plan day, and both decisions
  appear in the append-only audit log;
- the API answers only the production web origin (CORS) and refuses calls without a token.

It changes live data: two recommendations get decided, for good, by the demo approver. Run:

    uv run --with playwright python scripts/live_check.py

Uses the installed Google Chrome (Playwright's ``channel="chrome"``), so no browser download.
"""

from __future__ import annotations

import json
import re
import sys

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
    page.get_by_role("button", name=f"Sign in as {role}").click()
    expect(page.get_by_text("Runner visit queue")).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.locator("strong", has_text=role)).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.locator("tbody tr").first).not_to_contain_text("Loading", timeout=TIMEOUT_MS)


def sign_out(page: Page) -> None:
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto(WEB)
        expect(page.locator("header").get_by_text("Simulated data")).to_be_visible()
        api = api_base(page)
        print(f"web {WEB} → api {api}")

        r = httpx.get(f"{api}/health", headers={"Origin": WEB}, timeout=30)
        assert r.json()["status"] == "ok", r.text
        assert r.headers.get("access-control-allow-origin") == WEB, "CORS for the web app"
        other = httpx.get(f"{api}/health", headers={"Origin": "https://jogan-x.vercel.app"})
        assert "access-control-allow-origin" not in other.headers, "CORS for other origins"
        meta = httpx.get(f"{api}/v1/meta").json()
        day = meta["plan_dates"][-1]
        assert httpx.get(f"{api}/v1/plans/{day}").status_code == 401, "no token, no plan"
        print(f"health, CORS and 401 ok; bundle {meta['bundle_id']}, checking {day}")

        sign_in(page, "analyst")
        rows = page.locator("tbody tr")
        print(f"analyst sees {rows.count()} visits on {meta['plan_dates'][0]}")
        assert rows.count() > 0
        assert page.get_by_role("button", name="✓ Approve").count() == 0, "analyst cannot approve"
        token = access_token(page)
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
        sign_out(page)

        sign_in(page, "approver")
        page.get_by_label("Plan date").select_option(day)
        expect(page.get_by_role("button", name="✓ Approve").first).to_be_visible(timeout=TIMEOUT_MS)
        first = page.locator("tbody tr", has=page.get_by_role("button", name="✓ Approve")).first
        agent_a = first.locator("td").first.inner_text().split("\n")[0]
        first.get_by_role("button", name="✓ Approve").click()
        expect(page.locator("tbody tr", has_text=agent_a)).to_contain_text("approved")
        second = page.locator("tbody tr", has=page.get_by_role("button", name="✕ Reject")).first
        agent_r = second.locator("td").first.inner_text().split("\n")[0]
        second.get_by_role("button", name="✕ Reject").click()
        expect(page.locator("tbody tr", has_text=agent_r)).to_contain_text("rejected")
        audit = page.locator("section", has_text="Audit log")
        entries = audit.get_by_role("listitem")
        for action, agent in (("approved", agent_a), ("rejected", agent_r)):
            entry = entries.filter(has_text=f"recommendation.{action}").filter(has_text=agent)
            expect(entry).to_have_count(1)
            expect(entry).to_contain_text("approver")
        print(f"approver approved {agent_a} and rejected {agent_r} on {day}; both audited")
        browser.close()
    print("live check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
