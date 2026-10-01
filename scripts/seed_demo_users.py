"""Create the demo analyst and approver in Supabase Auth and give them their Jogan roles.

Run by the owner after the migrations, with the secret key from ``.env`` (never printed):

    uv run --env-file .env python scripts/seed_demo_users.py

Needs ``SUPABASE_URL``, ``SUPABASE_SECRET_KEY`` and ``JOGAN_DEMO_PASSWORD`` (at least 12
characters; the same password for both demo accounts). Safe to re-run: an existing user keeps
its id and gets the current password, and the role is upserted. The addresses use the reserved
``example.com`` domain, and the accounts are confirmed by the admin API, so no email is sent.
"""

from __future__ import annotations

import os
import sys

import httpx2 as httpx

DEMO_USERS = {
    "jogan.analyst@example.com": "analyst",
    "jogan.approver@example.com": "approver",
}


def main() -> int:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    secret = os.environ["SUPABASE_SECRET_KEY"]
    password = os.environ.get("JOGAN_DEMO_PASSWORD", "")
    if len(password) < 12:
        print("set JOGAN_DEMO_PASSWORD (12+ characters) in .env", file=sys.stderr)
        return 1
    http = httpx.Client(base_url=url, headers={"apikey": secret}, timeout=15)

    listed = http.get("/auth/v1/admin/users", params={"page": 1, "per_page": 1000})
    listed.raise_for_status()
    existing = {u["email"]: u["id"] for u in listed.json()["users"]}

    for email, role in DEMO_USERS.items():
        if email in existing:
            user_id = existing[email]
            r = http.put(f"/auth/v1/admin/users/{user_id}", json={"password": password})
            r.raise_for_status()
            state = "updated"
        else:
            body = {"email": email, "password": password, "email_confirm": True}
            r = http.post("/auth/v1/admin/users", json=body)
            r.raise_for_status()
            user_id, state = r.json()["id"], "created"
        r = http.post(
            "/rest/v1/user_roles",
            json={"user_id": user_id, "role": role},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        r.raise_for_status()
        print(f"{email}: {state}, role {role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
