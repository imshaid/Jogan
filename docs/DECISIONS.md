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
- `reactive` (calls only) and `none` (no runners) were kept as reference policies; D-019 drops them.
- The survey's "median of zero denials a day" is used as a plausibility test of the status quo, not as a calibration target: it is from 2014 and self-reported.

## D-017 · 2026-10-01 · Operations environment design

- **Event replay, not hourly buckets.** Attempts are replayed one by one in time order, with runner arrivals, bank trips and retries as timed events. A stock-out is decided by the exact balance at the moment of each attempt, which the peak-drain forecast target (D-002 #3) depends on. Policies decide at the start of every hour.
- **Common random numbers.** Retry, bank-trip delay and data-gap draws are keyed by the world seed and the customer or agent, never by the policy, so policy differences are not noise.
- **A visit sets a cash level, not an amount.** The runner swaps cash and e-float until the agent's cash reaches the target, within the agent's balances and the runner's bag. Total liquidity per agent never changes, which a test checks.
- **One dispatch code path.** Planners schedule on a copy of the fleet with the same feasibility code the environment uses, so a plan never fails in execution. Morning rounds are prioritised, split into sectors and ordered by nearest neighbour (the greedy baseline for M5's optimizer); calls go to the runner that arrives first.
- **Costs after the run.** Outcomes, runner km and busy minutes are logged; costs are computed afterwards, so another cost setting re-prices the same run (cost model: D-019).
- **The oracle** knows every future attempt and plans the same morning round. It bounds lost requests, not total cost, because it is not cost-aware; the cost-aware comparison comes with the newsvendor in M5.

## D-018 · 2026-10-01 · Observation layer

Jogan sees served transactions only, exact e-float, a cash estimate (exact until the shared drawer exists), runner visits and agents' bank trips as e-float transfers. The hourly feed loses 1% of agent-hour records and delivers 1% of agent-days a day late (ASSUMPTION); every record carries `available_at`, and features must respect it. Live balances at decision time are not affected. The status-quo log under `ops/fixed_round/obs/` is the only training input of M4; `ops/<policy>/truth/` is for evaluation.

## D-019 · 2026-10-01 · Costs from real inputs, break-even for lost customers, three baselines (owner decision)

The owner decided: no made-up or round cost numbers.

- **Runner cost is built from real inputs:**
  - the official petrol price by date in 2026 (Energy and Mineral Resources Division, as reported in the press);
  - the manufacturer's mileage of a 100 cc commuter motorcycle;
  - a 2026 job ad for a bKash distribution sales officer (Tk 13,000–17,000 a month);
  - the 48-hour legal week (Labour Act s.102).

  Fuel per km and runner time per minute are DERIVED in `jogan/ops/costs.py`. A runner's time is priced only while driving or at a stop, because the roster and salaries are the same under every policy. The earlier Tk 10 per km and Tk 100 per visit are gone.
- **Lost commission** = each lost amount × Tk 4.10 per 1,000 (the agent commission, the same at bKash, Nagad, Rocket and upay, Prothom Alo 2022), replacing the 0.40% / 0.30% guesses.
- **A lost customer's value is unknown and not priced.** The Tk 50 "goodwill" is gone. For any two policies the evaluation reports the break-even value per lost request at which they cost the same (`break_even` in `jogan/ops/costs.py`). Consequence for M5: Jogan's newsvendor needs an underage cost, so the lost-customer value enters it as an operator setting (a policy knob, not a fact), and the evaluation shows results across that setting next to the break-even values.
- **Idle money** is priced at Bangladesh Bank's policy rate (10% until 2 Aug 2026); using it as the cost of idle money is an ASSUMPTION.
- **Bank hours** for agents' own bank trips are the 2026 transaction hours, 10:00–15:00 from 5 April (Dhaka Tribune), applied to the whole run.
- **Every number in `configs/ops/*.yaml` is tagged** SOURCE, DERIVED or ASSUMPTION, and a test fails if one is not. The safety-stock factor is derived from a 95% service level instead of a typed 1.65.
- **Comparison set:** Jogan is compared with `fixed_round` (status quo), `threshold` and `safety_stock`. The oracle stays as an upper bound for the forecast, not a rival. `reactive` and `none` are removed.
- **Where Jogan does not win** goes into the evaluation output and gets its own report section: every baseline, agent group, period or cost setting in which a baseline does as well or better.

Not priced, for lack of a source: motorcycle wear and depreciation, the runner's phone, the agent's own time on bank trips. Each one understates a cost, and the report lists them.

## D-020 · 2026-10-01 · Drain forecast: estimated-demand labels, leak-free features, asymmetric CQR

- **Labels come from estimated demand, not served flows.** The status-quo log loses many requests, so served flows understate demand most in the windows that matter. A side counts as censored in an hour when its balance at the start or end is below 3 mean tickets. Such an hour is lifted to served + expected flow: the conditional mean of an exponential tail. The expected flow comes from *clean* hours only (at least 5 mean tickets at the start), because large tickets fail long before a side is empty. The thresholds are ASSUMPTIONs chosen on development seed 0 by the label bias against true demand, never on the evaluation seeds. `ignore` and `drop` stay as ablations, and every backtest reports the label bias and the stock-out flags' precision and recall against `truth/hourly.parquet`.
- **Ablation on development seed 0 (`full`)** (`python -m jogan.forecast --profile full --seed 0 --censoring <strategy>`; reported numbers come from `make eval`):
  - with `impute`, the calibrated 90% interval covers true demand in about 88–91% of test windows at every horizon;
  - with `ignore` (served flows), about 80–83% at 24 h;
  - with `drop`, about two-thirds at 24 h, worse than the empirical baseline. Dropping censored windows keeps the quiet ones: selection bias.
- **Features are leak-free by construction and by test.** Records are used only once they arrived (`available_at`), with an exact correction for late records. A perturbation test changes every record that arrives after the origin and checks that nothing moves. The log panel equals the in-simulation `History` panel, so M5's policy computes the same features.
- **Liquidity enters as the total, not the cash/e-float split.** The split mostly reflects when the status quo's runner came; learning from it would tie the forecast to the old policy. The forecast is of demand, and the live balances enter only later, in P(stock-out) and in the newsvendor (M5).
- **One booster per horizon, side and level, on `log1p`, then asymmetric CQR.** Romano, Patterson and Candès (2019, Theorem 2): each level gets its own one-sided guarantee, which the newsvendor's high critical ratios need, rather than only a two-sided interval. Shifts are applied in log space (relative), per setting by size class, with the pooled shift for small groups. The naive baseline gets additive Tk shifts instead, because a zero last week would make relative shifts explode. Crossed levels are sorted.
- **Hourly resolution.** The peak drain is computed from hourly totals, which understates dips inside an hour for every method alike. Exact peaks would need the transaction stream, which upay has; the simulator logs only hourly aggregates.
- **Runtime.** 48 boosters, 150 rounds at a learning rate of 0.1, 63 bins: about a minute per `full` seed on a 20-thread laptop, so M5 can retrain per evaluation seed. LightGBM 4.7.0 (MIT) runs with `deterministic` and `force_row_wise`, and training twice gives identical predictions (tested).
- **Scored where it may not win.** The test window holds Eid-ul-Azha, partly out of distribution (D-010). The metrics split the Eid window from other days, and report coverage per setting and size class, so a failure shows.

## D-021 · 2026-10-01 · Jogan's policy (newsvendor + MILP dispatch) and the final evaluation

- **Forecast in the loop.** At 08:00 Jogan builds features from the in-simulation history with the training code (the panel equals the log, D-020), predicts the 24-hour peak drain per side, and plans one round. Calls are handled as under every policy.
- **Newsvendor need per side** at the critical ratio cu ÷ (cu + co): underage = commission per Tk + the operator's lost-customer value ÷ the agent's mean ticket; overage = the policy rate over 24 hours. The quantile grid is interpolated linearly, and extended linearly above 0.99 (ASSUMPTION). The lost-customer value is an operator setting (D-019), Tk 20 in the demo (ASSUMPTION).
- **Target level.** A visit only moves liquidity between the sides (D-017). When the liquidity meets both needs, the target is the middle of that band. On development seeds this was rare (about 2% of agent-mornings), so the split for the other case decides most visits. The two-sided newsvendor optimum (equal marginal cost on both sides) lost more requests than the baselines' split in proportion to typical served outflow. The likely reason is that the hourly peak drain misses dips inside an hour (D-020), and the gross-outflow split keeps a buffer on both sides. Jogan uses the typical split; the two-sided split stays as an ablation (`newsvendor.split`).
- **Value of a visit** = expected shortage cost avoided + the call trip it saves (change in the probability of falling below the call level × the known cost of a round trip from the hub). An agent is a candidate when the value exceeds the runner time of one stop. Without the call term, the program skipped visits that later came back as calls. On development seeds that cost more km and more lost requests than the greedy round.
- **Dispatch program.** A generalized-assignment heuristic for vehicle routing (Fisher and Jaikumar 1981, *Networks* 11(2), 109–124), with optional visits. Each runner gets a seed (the value-weighted medoid of an equal-value cone), and a visit costs the detour to that seed. One program per territory maximises value minus fuel and runner time, under visit and shift-time limits. HiGHS 1.12.0 solves it through `scipy.optimize.milp` (scipy 1.18.1, read from the installed package; scipy is now a direct dependency, and it was already installed through LightGBM). Detours overestimate a nearest-neighbour route, so a route check drops stops that do not fit, and a fill step adds unchosen agents where a route has room and the visit pays. A territory whose program fails falls back to the greedy round. The greedy round with the same forecast and levels is the dispatch ablation. HiGHS prints debug lines from C++, which are silenced around the solve.
- **Same starting state.** Every policy is switched on at the start of the test window (`Deployed`), so all of them start from the status quo's balances, runners and history.
- **Final evaluation** (`make eval`). The `full` profile, seeds 1000–1009, never used during development (D-010), with the lost-customer value swept over 0, 5, 20, 50, 100 and 200 Tk. Policies are compared on the test window and its Eid-ul-Azha days, with the known cost at the low, middle and high salary. Results are paired over seeds with 95% t-intervals. The break-even value has Fieller's interval (Fieller 1954, *JRSS B* 16(2), 175–185), which is reported as unbounded when Jogan and a baseline lose about as many requests. Further outputs: a fairness table against the best baseline, H1–H4 of the logic chain, and the list of cases where Jogan does not win. Only the configured run writes `artifacts/metrics.json`; development runs write `artifacts/eval/metrics_dev.json`. All design choices above were made on development seeds 0–3.
- **Not modelled:** the runner's bag in the program, the hours between the forecast and the runner's arrival, and a call rescuing an agent who was not visited.

## D-022 · 2026-10-02 · Walking skeleton: served bundle, Supabase queue and audit, Cloud Run and Vercel

- **Regions.** Supabase runs in Singapore (the owner created the project there instead of the Mumbai region in the old checklist), and Cloud Run and Artifact Registry run in `asia-southeast1` (Singapore). The API and the database sit in the same region.
- **The served bundle.** The API never simulates or trains. `jogan.api.bundle` builds the demo world (`full`, seed 42, outside the development seeds 0–9 and the evaluation seeds 1000–1009), runs the status quo, trains the forecaster on its log as `make eval` does, and switches Jogan on at the start of the test window. Every morning's evidence (`Jogan.last`) is kept: 28 plan days and 6,559 planned visits on this laptop's build. The build takes about 75 s and peaks at 1.8 GB of memory. It runs inside `docker build`, so no model or data file is committed (D-002 #7); the bundle id is derived from the config hashes, so the same commit gives the same id. The bundle is a replay: approving a visit records the decision but does not change the simulated world. On Eid-ul-Azha day (28 May) the roster has no runners, so the plan is empty.
- **Database.** One migration (`supabase/migrations/`) creates `user_roles`, `recommendations` and `audit_log`. The project does not expose new tables to the Data API by default (Supabase changelog 45329), so every grant is explicit, and RLS is enabled on each table. Users only read: analysts and approvers see the queue and the audit log, anyone else sees nothing. Every write goes through a function:
  - `publish_plan` (only the secret key) inserts a day's plan once, under an advisory lock, and logs `plan.published`.
  - `decide_recommendation` (only approvers) updates a pending row and appends the audit row in the same transaction.

  Triggers refuse any other change to a recommendation and any update, delete or truncate of the audit log, even with the secret key or as the table owner. `make test-db` applies the migration to Postgres 17 with a stub `auth` schema and checks all of this for each role; CI runs it.
- **API.** FastAPI on Cloud Run, sync endpoints, talking to PostgREST over HTTPS (D-002 #6). It sends the user's token with the publishable key, so RLS applies to reads and decisions. The secret key is used only to publish a day's plan, and only after the caller has shown a role. Database errors map to HTTP by SQLSTATE (403 role, 404 unknown, 409 already decided, 422 bad input). `httpx2` replaces `httpx` because Starlette 1.7's test client asks for it. The tests use `MemoryStore`, which enforces the same rules. API-level JWT verification and rate limiting come in M8.
- **Secrets and deploys.** Supabase and Gemini values live in Secret Manager. Only the runtime service account `jogan-api` can read them, and the owner loads them from `.env` with `scripts/gcp-setup.sh`. GitHub Actions deploys without keys: Workload Identity Federation trusts only this repository (matched by its numeric id) on `main`, and the deployer account can only push images, deploy revisions and act as `jogan-api`. The workflow runs after CI passes and reuses the image layers in the GitHub Actions cache. Cloud Run is capped at 2 instances (1 vCPU, 1 GiB), and Artifact Registry keeps the 3 newest images.
- **CORS.** The API answers one browser origin, the production web app `https://jogan-bd.vercel.app` (the owner's final domain). The deploy workflow sets it as `JOGAN_CORS_ORIGINS` on every deploy, so it lives in git. Vercel preview deployments and look-alike `jogan-*.vercel.app` projects are refused. `JOGAN_CORS_ORIGIN_REGEX` remains as an option for previews and is unset in production. CORS is not the security boundary: every data endpoint needs a bearer token.
- **Demo accounts.** `jogan.analyst@example.com` and `jogan.approver@example.com` (a reserved domain, so no email is sent) are created through the admin API by `scripts/seed_demo_users.py`. Public sign-up is turned off in Supabase Auth. Their shared password is public by design when `NEXT_PUBLIC_DEMO_PASSWORD` is set, so judges can sign in with one click. The data is simulated, and every decision is in the audit log.
- **Web.** Next.js 16.3.8 as `create-next-app` scaffolds it (React 19.2, TypeScript 5, Tailwind 4) with `@supabase/supabase-js` 2.117.2. In M6 it is one client page: sign in, the day's queue with P(stock-out) labelled as a prediction, approve or reject for approvers, and the audit log. Risk is shown with a word and a symbol, never by colour alone. The display bands (≥ 50% high, ≥ 20% medium) are an ASSUMPTION of the UI, not a decision rule. The derived small-text red `#B5121B` has 6.85:1 contrast on white.

Verified on 2026-10-01/02: FastAPI 0.142.2, Uvicorn 0.54.0, httpx2 2.13.1 (PyPI), Next.js 16.3.8, supabase-js 2.117.2, Supabase CLI 2.119.0 (npm), the action tags `google-github-actions/auth@v3`, `setup-gcloud@v3`, `docker/build-push-action@v7`, `setup-buildx-action@v4`, `actions/setup-node@v7`, the `ghcr.io/astral-sh/uv:0.12.21` and `python:3.12-slim-trixie` images. The publishable and secret keys go in the `apikey` header, never as a bearer token (<https://supabase.com/docs/guides/api/api-keys>). Explicit grants for new tables: <https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically>.
