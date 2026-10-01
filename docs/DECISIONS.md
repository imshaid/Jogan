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

## D-013 · 2026-10-01 · Eid surge calibrated on counts and ticket sizes; both Eids share it

BB table 9 shows agent cash-out amounts rising faster than counts from April to May 2026 (the Eid-ul-Azha month), and the same for cash-in, so tickets grow before Eid as well as volume. The simulator calibrates four quantities by bisection on the expected network: a count surge and a ticket-size surge per side, all with one pre-Eid shape. Eid-ul-Fitr cannot be calibrated separately: table 9 note 5 says Nagad sent no data from March 2025 to February 2026, so March 2026 is not comparable with February 2026. Both Eids therefore use the Azha-calibrated surge. Details: [`02-data-assumptions.md`](02-data-assumptions.md) §5.

## D-014 · 2026-10-01 · World files split into public and truth; one random stream per component

`data/<profile>/seed<n>/` holds public tables (what an operator would know) at the top level and ground truth (every customer attempt, true agent parameters, anomaly labels, disruptions) under `truth/`. Feature code reads only the public level plus the M3 observation log, so labels cannot leak by accident; a test checks the split. Each component draws from its own seeded stream (`numpy` `SeedSequence` keyed by seed and component name), so changing anomalies never shifts demand, and policies compared in M3 replay identical demand.

## D-015 · 2026-10-01 · Simulator profiles

`tiny` moved to 1–28 March (GZP and RNG) so a single month covers payday, hat days, Ramadan, Eid-ul-Fitr and the post-Eid drop for CI tests. `dev` uses DHK, CUM and KUR (urban, remittance, remote rural). `stress` replicates each of the six hubs as 10 distributor areas (60 territories, 10,000 agents), because the optimizer decomposes by territory and one 1,667-agent territory would not reflect real distributor sizes. Runners scale with agents per territory.

## D-016 · 2026-10-01 · Status quo is a fixed runner round plus calls (ANA Bangladesh)

The first environment run used agents' own bank trips as the status quo and lost far more requests than Bangladeshi agents report. A check against the Agent Network Accelerator survey of 2,800 Bangladeshi agents ([Helix Institute / MicroSave, 2014](https://www.microsave.net/wp-content/uploads/2014/11/Agent-Network-Accelerator-Bangladesh-Country-Report-2014.pdf)) showed that this is not how Bangladesh works: 96% of agents rebalance at their shop through distributor runners who visit "usually at a predetermined time", some distributors also rebalance on demand, and the median agent rebalances about 22 times a month.

- The status quo (`fixed_round`) is now a fixed cycle per runner plus calls; the bank trip stays as every agent's fallback under every policy.
- `runners.max_visits` goes from 8 to 20 so the status quo can reach that rebalancing frequency (the count is still an ASSUMPTION).
- `reactive` (calls only) and `none` (no runners) stay as reference policies.
- The survey's "median of zero denials a day" is used as a plausibility test of the status quo, not as a calibration target: it is from 2014 and self-reported.

## D-017 · 2026-10-01 · Operations environment design

- **Event replay, not hourly buckets.** Attempts are replayed one by one in time order, with runner arrivals, bank trips and retries as timed events. A stock-out is decided by the exact balance at the moment of each attempt, which the peak-drain forecast target (D-002 #3) depends on. Policies decide at the start of every hour.
- **Common random numbers.** Retry, bank-trip delay and data-gap draws are keyed by the world seed and the customer or agent, never by the policy, so policy differences are not noise.
- **A visit sets a cash level, not an amount.** The runner swaps cash and e-float until the agent's cash reaches the target, within the agent's balances and the runner's bag. Total liquidity per agent never changes, which a test checks.
- **One dispatch code path.** Planners schedule on a copy of the fleet with the same feasibility code the environment uses, so a plan never fails in execution. Morning rounds are prioritised, split into sectors and ordered by nearest neighbour (the greedy baseline for M5's optimizer); calls go to the runner that arrives first.
- **Costs after the run.** Outcomes and runner km are logged; costs are computed afterwards, so goodwill and commission ranges re-price the same run.
- **The oracle** knows every future attempt and plans the same morning round. It bounds lost requests, not total cost, because it is not cost-aware; the cost-aware comparison comes with the newsvendor in M5.

## D-018 · 2026-10-01 · Observation layer

Jogan sees served transactions only, exact e-float, a cash estimate (exact until the shared drawer exists), runner visits and agents' bank trips as e-float transfers. The hourly feed loses 1% of agent-hour records and delivers 1% of agent-days a day late (ASSUMPTION); every record carries `available_at`, and features must respect it. Live balances at decision time are not affected. The status-quo log under `ops/fixed_round/obs/` is the only training input of M4; `ops/<policy>/truth/` is for evaluation.
