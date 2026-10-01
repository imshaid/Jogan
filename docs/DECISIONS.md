# Decision log

Significant choices and the reasons behind them, newest at the bottom. Facts marked `ASSUMPTION` are not verified yet.

## D-001 · 2026-10-01 · Product direction (owner decision, binding)

Agent Liquidity Copilot **Jogan (যোগান)** for upay's operations and distributor analysts. Python package `jogan`, repo `imshaid/Jogan`. Not re-debated.

## D-002 · 2026-10-01 · Deviations from the owner's non-binding architecture sketch

Approved by the owner on 2026-10-01.

1. **Operations environment and baseline policies come before ML.** The training history is itself the log produced by today's (status-quo) policy, stock-outs included; baselines also set the bar to beat early, and the hardest component gets done first.
2. **A walking skeleton is deployed early** (API on Cloud Run, web on Vercel, Supabase schema) instead of at the end, so deployment problems surface while there is time to fix them.
3. **Forecast target is the peak cumulative drain** over the next 6/12/24 h, for cash and for e-float, plus the net drain. A stock-out happens when the balance hits zero at any point inside the window, not only at its end, so P(stock-out) = P(peak drain > current balance), read directly from calibrated quantiles.
4. **Newsvendor rule.** Cost parameters in config (lost commission and goodwill vs. runner trip and idle-cash cost) give a critical ratio, which selects the quantile used as the top-up target. ML predicts; this business rule decides. The two stay separate and explainable.
5. **Drivers come from LightGBM's built-in TreeSHAP** (`pred_contrib=True`) instead of the `shap` package: the values are the same exact TreeSHAP, without the numba/llvmlite dependency, so the Docker image is smaller and cold starts are faster.
6. **The API talks to Supabase over HTTPS (PostgREST and SQL functions) with the user's JWT** instead of SQLAlchemy/psycopg. Roles are enforced by row-level security in the database, approve-and-audit happens atomically in one SQL function, and the audit log is append-only via triggers. Cloud Run needs no DB connection pool, and the direct Postgres connection's IPv6-only path is avoided (`ASSUMPTION`, checked in the deploy milestone). Tests use an in-memory store.
7. **No model binaries in git.** The served bundle (simulated world and trained models) is rebuilt deterministically from a seed during the Docker build.
8. **Training accounts for censored demand.** During a stock-out the true demand is not observed; censored windows are handled explicitly and the bias is measured against the simulator's ground truth.
9. **Equity in the optimizer.** A configurable equity weight or service floor stops small and rural agents from being deprioritised just because their ৳ value is small. A fairness table is reported.
10. **LLM guardrails.** Input and output are structured JSON. Every number in a generated explanation must appear in the evidence, otherwise the template explanation is used. Free text from users never enters a prompt.
11. **Partially observed physical cash** (only if time allows). upay sees e-float exactly, but a shop's cash drawer may be shared with other MFS brands (`ASSUMPTION`), so cash is modelled with uncertainty.

## D-003 · 2026-10-01 · Python 3.12 with uv and a flat package layout

Python is pinned with `.python-version` (`3.12`) and `requires-python = "==3.12.*"`. uv manages the interpreter (CPython 3.12.14 installed on 2026-10-01). Reason: well-supported by the planned scientific stack and matches a `python:3.12-slim` image. The flat `jogan/` layout (uv build backend `module-root = ""`) is easier for teammates to navigate than `src/`.

## D-004 · 2026-10-01 · MIT license

## D-005 · 2026-10-01 · Master brief kept local

The owner's original brief is stored at `.claude/master-prompt.local.md` (git-ignored) and shown to judges on request. Reason: in a public repo it would expose the full plan to other teams during the 72-hour window. The binding rules are reflected in committed docs.

## D-006 · 2026-10-01 · Working copy moves from NTFS to ext4

The first clone lived on an NTFS partition mounted through FUSE (`fuseblk`) with a space in the path. Measured on this machine: small-file writes about 3× slower and reads about 6× slower than the ext4 home partition, and `chmod` has no effect. Working copy moves to `~/code/Jogan` (ext4) after M0.

## D-007 · 2026-10-01 · Brand colours and contrast

These are the owner's measured values; no official upay brand guide has been found yet. WCAG contrast ratios, computed locally:

| Pair | Ratio | Use |
|---|---|---|
| blue `#0C55A4` on white | 7.37:1 | primary text and fills |
| ink `#050608` on yellow `#FBD603` | 14.21:1 | text on yellow fills |
| yellow on white | 1.43:1 | never as text |
| red `#EB1D27` on white | 4.43:1 | fails AA for normal text; small text uses a darker derived red |

## D-008 · 2026-10-01 · CI, secret scanning and dependency updates

- GitHub Actions runs `make lint` and `make test` through uv.
- gitleaks-action v3 runs on every push; per its README no license is needed for personal accounts.
- `astral-sh/setup-uv` publishes no floating major tag (only `v10.0.0` … `v10.2.0` exist), so it is pinned to `v10.2.0`.
- Dependabot covers `uv` and `github-actions` weekly (supported ecosystems per GitHub docs). `npm` and `docker` are added once the web app and Dockerfile exist.
- A pre-commit gitleaks hook also scans locally before every commit. Pre-commit bootstraps Go itself.

Sources: <https://github.com/gitleaks/gitleaks-action>, <https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories>.

## D-009 · 2026-10-01 · Supabase key types

Use the new `sb_publishable_…` key (browser, RLS applies) and `sb_secret_…` key (server only, bypasses RLS). Supabase documents the legacy `anon` and `service_role` keys as deprecated by the end of 2026.
Source: <https://supabase.com/docs/guides/api/api-keys>.

## D-010 · 2026-10-01 · Simulation calendar, splits and seeds

The simulator runs on the real 2026 Bangladesh calendar. In the `full` profile (5 Jan → 3 Jun 2026), training includes Eid-ul-Fitr and the held-out test window includes Eid-ul-Azha. This is an honest test of whether festival effects generalise, and it is partly out of distribution by design (cattle markets). Development uses seeds 0–9 and the final evaluation uses seeds 1000–1009, so the method is never tuned to the worlds it is scored on. Details: [`02-data-assumptions.md`](02-data-assumptions.md) §2.

## D-011 · 2026-10-01 · Calibrate the simulator to official aggregates

Mean ticket sizes, the cash-out/cash-in count ratio and the Eid-month uplift are tuned to Bangladesh Bank's MFS transaction table (`tab9`, monthly, "Amount in million Tk"). The targets are stored with their source in `configs/calibration/` and recomputed in code, not typed by hand. Hub coordinates and Bangla district names come from `nuhil/bangladesh-geocode` (MIT).

## D-012 · 2026-10-01 · Six territories

The territories are Dhaka (urban), Gazipur (industrial payday), Cumilla and Sylhet (top remittance districts per BB data for March 2026), Rangpur (rural hat economy) and Kurigram (remote, flood-prone). Together they cover the demand patterns that make rebalancing hard. Reasons per territory: [`02-data-assumptions.md`](02-data-assumptions.md) §3.
