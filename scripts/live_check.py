"""End-to-end check of the live demo in a real browser, as a judge would use it.

Signs in with the one-click demo accounts on the web app and checks:
- the "Simulated data" badge;
- the analyst sees the queue but no decision buttons, and the API refuses the analyst's decision;
- a visit's "Why?" shows the template explanation in English and Bangla, and "Reword with AI"
  answers (Gemini's rewording, or the template with the reason); the anomaly flags are listed;
- the approver approves one visit and rejects another on the last plan day; a visit flagged for
  manual review is refused without a note and approved with one; every decision appears in the
  append-only audit log;
- the API answers only the production web origin (CORS) and refuses calls without a token.

It changes live data: two or three recommendations get decided, for good, by the demo approver.
Run:

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

        row = page.locator("tbody tr").first
        row.get_by_role("button", name="▸ Why?").click()
        why = page.locator("tbody tr[id^='why-']").first
        expect(why).to_contain_text("Send runner")
        expect(why).to_contain_text("a prediction")
        page.get_by_role("button", name="বাংলা").click()
        expect(why).to_contain_text("পূর্বাভাস")
        why.get_by_role("button", name="Reword with AI").click()
        answer = why.get_by_text(re.compile("Reworded by AI|AI rewording not shown"))
        expect(answer).to_be_visible(timeout=TIMEOUT_MS)
        print(f"why panel ok in both languages; AI: {answer.inner_text()[:90]}")
        page.get_by_role("button", name="English").click()
        flags = page.locator("section", has_text="Advisory anomaly flags")
        expect(flags).to_be_visible()
        print(f"anomaly flags listed: {flags.get_by_role('listitem').count()}")
        sign_out(page)

        sign_in(page, "approver")
        page.get_by_label("Plan date").select_option(day)
        expect(page.get_by_role("button", name="✓ Approve").first).to_be_visible(timeout=TIMEOUT_MS)
        pending = page.locator("tbody tr", has=page.get_by_role("button", name="✓ Approve"))
        plain = pending.filter(has_not_text="Manual review").first
        agent_a = plain.locator("td").first.inner_text().split("\n")[0]
        plain.get_by_role("button", name="✓ Approve").click()
        expect(page.locator("tbody tr", has_text=agent_a)).to_contain_text("approved")
        second = page.locator("tbody tr", has=page.get_by_role("button", name="✕ Reject")).first
        agent_r = second.locator("td").first.inner_text().split("\n")[0]
        second.get_by_role("button", name="✕ Reject").click()
        expect(page.locator("tbody tr", has_text=agent_r)).to_contain_text("rejected")
        decided = [("approved", agent_a), ("rejected", agent_r)]

        flagged = pending.filter(has_text="Manual review")
        if flagged.count():
            row = flagged.first
            agent_f = row.locator("td").first.inner_text().split("\n")[0]
            rec = next(x for x in plan["items"] if x["agent_id"] == agent_f)
            approver = {"Authorization": f"Bearer {access_token(page)}"}
            bare = httpx.post(
                f"{api}/v1/recommendations/{rec['id']}/decision",
                headers=approver,
                json={"decision": "approved"},
            )
            assert bare.status_code == 422, bare.text
            row.get_by_role("button", name="✓ Approve").click()
            row.get_by_label(re.compile("Note")).fill("live check: evidence reviewed")
            row.get_by_role("button", name="✓ Approve with note").click()
            expect(page.locator("tbody tr", has_text=agent_f)).to_contain_text("approved")
            decided.append(("approved", agent_f))
            print(f"flagged {agent_f}: refused without a note (422), approved with one")

        # match by recommendation id: earlier bundles may hold decisions on the same agent and day
        rec_id = {x["agent_id"]: x["id"] for x in plan["items"]}
        audit = page.locator("section", has_text="Audit log")
        entries = audit.get_by_role("listitem")
        for action, agent in decided:
            mine = re.compile(rf"#{rec_id[agent]}(?!\d)")
            entry = entries.filter(has_text=f"recommendation.{action}").filter(has_text=mine)
            expect(entry).to_have_count(1)
            expect(entry).to_contain_text(agent)
            expect(entry).to_contain_text("approver")
        print(f"approver decided {', '.join(a for _, a in decided)} on {day}; all audited")
        browser.close()
    print("live check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
