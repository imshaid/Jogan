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

## D-023 · 2026-10-02 · Explanations, guardrails, Gemini narrator and the anomaly flag

- **Drivers.** LightGBM's built-in TreeSHAP (`pred_contrib`, D-002 #5) on the 24-hour booster at the 0.9 quantile of the side at risk (the side with the higher P(stock-out)). They are computed once, when the bundle is built, for every planned visit and stored in its evidence, so the API never loads a model. The boosters are trained on `log1p`, so a feature's effect is `exp(φ) - 1`, relative to the model's average prediction. The conformal shift is one constant per agent group, so it is not a driver. The top 3 with an effect of at least 5% are kept. A test checks that the contributions add up to the raw prediction.
- **Template explanation.** English and Bangla, written only from the stored evidence by `jogan/explain/template.py`; the words live in `configs/explain/labels.yaml` (Bangla digits, lakh grouping). The template is the explanation of record. An approver's note, or any other user text, never enters an explanation or a prompt.
- **Gemini narrator.** `gemini-3.5-flash-lite`, with `gemini-3.1-flash-lite` as the fallback on HTTP 429 or 5xx. Both are stable and on the free tier (models and pricing pages, checked 2026-10-02). The owner chose Flash-Lite models; the first deploy used `gemini-3.8-flash`, and there is no 3.8 Flash-Lite text model. The ids live in `configs/explain/base.yaml`, which is what Cloud Run uses. `GEMINI_MODEL_PRIMARY` and `GEMINI_MODEL_FALLBACK` only override them where they are set (locally from `.env`; they are not set on Cloud Run).
  - The API calls REST `models.generateContent` with `responseMimeType: application/json` and a `responseSchema`. The key goes in the `x-goog-api-key` header, never in the URL.
  - Input: the template and the same evidence as display text.
  - The answer is accepted only if it is JSON, at most 1,200 characters, in the requested script, keeps the stock-out chance, and uses no number that is not already in the template (Bangla digits and grouping are normalised first). Otherwise the template is shown, with the reason.
  - Calls happen on request only (one visit, one language), at most 8 a minute per instance, and results are cached. A whole day (about 230 visits) cannot be narrated within free-tier limits, so nothing is precomputed.
  - Free-tier prompts may be used by Google to improve its products; only simulated data is sent.
  - Tests mock the HTTP layer.
  - The key is the `gemini-api-key` secret. The CI deployer has `roles/run.developer`, and the Cloud Run docs list `roles/run.admin` for configuring secrets, so the owner mounts it once by hand (`gcloud run services update … --update-secrets`) instead of widening the deployer's role. Later image deploys keep it. `scripts/gcp-setup.sh` mounts it on a fresh setup.
- **Guardrails and manual review.** A visit goes to manual review when one of these fires:
  - **out of range:** one of the agent's own amounts lies outside the training min/max. Calendar features are left out: a test window later in the year is always outside the training calendar (days since Eid, for one).
  - **wide interval:** the 90% quantile is more than 4× the median.
  - **data gap:** fewer than 75% of the last 24 hourly records had arrived at the plan hour.
  - **short history:** fewer than 7 past same-hour windows behind the features.
  - **anomaly:** the advisory anomaly flag fired.

  "Cash plus e-float cannot cover both needs" was dropped: on development seed 0 it fired on 728 of 732 planned visits. For a visited agent that is the normal case, not a warning. On the demo bundle 772 of 6,559 visits (12%) go to manual review.

  Approving a flagged visit needs a note. The rule is in `decide_recommendation` (a new migration), because an approver can call that function through the Data API directly, and in `MemoryStore`. The audit row records `manual_review`. Rejecting needs no note.
- **Anomaly flag.** Agent-day features from the observed log only:
  - transactions outside opening hours;
  - volume against the agent's own hour-of-day profile;
  - mean cash-out against the agent's own mean;
  - the busiest hour's cash-outs against their usual count.

  The last three are divided by the territory's median that day, so a payday or an Eid that lifts everyone is not unusual. Only excess counts (`log(max(x, 1))`): on development seeds the strangest days were quiet ones, agents that had run dry, which the liquidity forecast already covers. An Isolation Forest (scikit-learn 1.9.1, BSD-3-Clause) per setting scores the three continuous features, and an agent-day is flagged above the 99.5% quantile of its setting's training scores. Two rules cover what a forest misses:
  - transactions outside opening hours are zero on nearly every training day, so the forest's sub-samples almost never hold a value to split on;
  - a forest scores a point past the edge of its training sample like the edge itself, so a feature above its setting's training maximum is flagged directly. A synthetic test with a 7× cash-out size showed this.

  Flags never act. They put the agent's visit under manual review and list the agent for a person to look at. Each morning the bundle scores the previous day from the records that have arrived by then. `make eval` reports precision at 5, 10 and 20 and how many injected windows got a flag, on the test window of every evaluation seed.
- **Bundle id.** The bundle hashes now include the explain config (narrator settings excluded, since they act only at request time). The new evidence is therefore published under a new bundle id, and live decisions made on the old one stay with it.

## D-024 · 2026-10-02 · API guards: token checks, rate limits, one error body, decision trace

- **Token checks in the API.** Until M7 the API passed the bearer token on to PostgREST and let the database refuse it. Now `jogan/api/auth.py` checks it first, so a bad token never costs a database call, and PostgREST still checks it again (row-level security unchanged).
  - The project signs access tokens with an asymmetric key. The public keys are at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, and on 2026-10-02 the live set held one ES256 key (<https://supabase.com/docs/guides/auth/signing-keys>).
  - Checked: the signature, an allowed algorithm (ES256 or RS256, the two Supabase offers; `none` and HS256 are refused), the issuer `<SUPABASE_URL>/auth/v1`, the audience `authenticated`, the expiry (30 s leeway), a subject, and the role `authenticated` (claims: <https://supabase.com/docs/guides/auth/jwt-fields>).
  - PyJWT 2.15.1 (PyPI, 28 Sep 2026, MIT) with its `crypto` extra, which adds cryptography 50.0.2 (Apache-2.0 or BSD-3-Clause). Both are new dependencies.
  - The key set is kept for 10 minutes, the time Supabase's edge caches it (same page). A token naming an unknown key refetches the set at most once every 30 s, so made-up key ids cannot make the API flood Supabase. PyJWT's own `PyJWKClient` refetches on every unknown key id, which is why the cache is our own (about 40 lines, tested with a mocked HTTP layer and a fake clock).
  - If Supabase cannot be reached, the keys already held keep working. With no keys at all the answer is 503.
  - A token stays valid until it expires, even after sign-out; PostgREST behaves the same way.
- **Rate limits.** Token buckets in memory (`jogan/api/guard.py`): one per client address for every request, one per user for every signed-in request, and separate ones for deciding and for AI rewording. The narrator keeps its own 8-a-minute cap on top (D-023). A refusal is a 429 with `Retry-After`.
  - Each Cloud Run instance counts on its own. At most 2 instances run (D-022), so a client gets at most twice the configured rate. A shared store (Redis) is not worth it at this size.
  - The sizes are ASSUMPTIONS in `configs/api/base.yaml`. Every judge signs in with the same demo account, so the per-user buckets fit several people on one account. At the on-site final many people may share one address, so the per-address bucket is generous.
  - slowapi 0.1.10 (PyPI, June 2026) was the brief's suggestion. Its limits are decorators keyed by a function of the request, so a per-user key would need the token decoded a second time. Its previous release was in February 2024. Our own buckets are about 60 lines and tested with a fake clock.
- **Client address.** Uvicorn runs with `--forwarded-allow-ips '*'` (D-022), which makes the leftmost `X-Forwarded-For` entry the client. The client writes that entry itself, so a limit keyed on it could be dodged with a new made-up address on every request. The guard reads the raw header instead, `JOGAN_TRUSTED_PROXY_HOPS` entries from the right (1 in the Docker image, 0 locally, where the socket peer is used). Google's docs do not say what Cloud Run puts in the header, so this was checked on the live service on 2026-10-02:
  - For 75 s, 16 threads on this laptop sent `/health` requests, each with a different forged `X-Forwarded-For`. From the tenth second on, about 7 of every 8 got a 429. The forged values did not open new buckets.
  - Meanwhile the same URL, fetched from another server (a public page-reader service), got 200 three times out of three. So the key is the caller's own address, not a Google address that every client shares.
  - Successful requests settled at 16 a second, four times one bucket's rate. The laptop's ISP uses carrier-grade NAT and sent its requests from 3 public addresses within one minute, and 2 instances were counting. Many people in Bangladesh share one public address this way, which is another reason the per-address bucket is generous.

  `scripts/live_check.py` repeats the forged-header part on every run.
- **One error body.** Every refusal is `{"detail": <message>, "code": <slug>}`; `detail` stays a string, so the web app can always show it.
  - Validation errors add `errors` (field and message, never the submitted value).
  - A 429 adds `retry_after_s`.
  - A 401 from a bad token carries `WWW-Authenticate: Bearer error="invalid_token"`.
  - An unexpected error is a plain 500 with no detail.
  - Every response has `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
- **Input validation.**
  - Dates must be `YYYY-MM-DD`: pydantic also took a Unix time (`/v1/plans/1717372800` was 3 Jun 2024) and a datetime.
  - Ids must lie between 1 and 2^63 − 1 (Postgres `bigint`).
  - A note may hold at most 500 characters and no control characters except newline, carriage return and tab (Postgres text cannot hold NUL).
  - A decision body with unknown fields is refused.
  - A body must have a `Content-Length` (411 otherwise) and be at most 8 KB (413).
- **Decision trace.** `GET /v1/recommendations/{id}/trace` (`jogan/api/trace.py`) returns what each layer produced, in the order of the logic chain:
  1. the forecast and the stock-out chance (model);
  2. the drivers (TreeSHAP);
  3. the need and value (rule);
  4. the runner (optimizer);
  5. the guardrails (rule);
  6. the explanation (template);
  7. the decision (human).

  Each step names the config whose hash the stored trace recorded. The response also holds the stored trace, both template explanations, the agent's anomaly flag that morning, and the recommendation's audit rows; `/v1/audit` takes `recommendation_id` for the same filter. An LLM is never a step. It can only reword the explanation on request. A recommendation from an older bundle still gets its trace, but without the served anomaly flag, since the bundle that made it is gone.

## D-025 · 2026-10-02 · Web UI: pages, map, Bangla, impact numbers

- **Pages.** The single M6 page becomes six routes in the App Router: `/` network map, `/queue` visit queue, `/agents/[id]` agent detail with the decision trace, `/audit` audit log, `/impact` evaluation results and `/about` how it works. The first four need a signed-in user with a role; impact and about are public, so a judge can read the results before signing in. Every page renders on the client behind the Supabase session, as in M6. The plan day lives in the URL (`?day=`), so links and reloads keep it.
- **Map.** MapLibre GL JS 6.11.2 (npm, BSD-3-Clause, 2026-09-24) on OpenFreeMap's `positron` style. OpenFreeMap needs no key, account or cookie, sets no request limit and allows commercial use; attribution is required and MapLibre shows the style's own (<https://openfreemap.org>, checked 2026-10-02). The MapTiler key on the owner checklist is therefore not needed; `NEXT_PUBLIC_MAP_STYLE_URL` can point at any other style. MapLibre 6 loads its worker from a URL next to its own module, which the bundler does not keep, so `npm run dev` and `npm run build` copy the worker into `public/maplibre/<version>/` and the map calls `setWorkerUrl`.
- **Risk on the map.** Each agent is a shape by risk band (▲ high, ◆ medium, ● low), coloured as well, and a planned visit adds a blue ring. The legend names every shape. The bands (≥ 50%, ≥ 20%) stay a display ASSUMPTION (D-022). The map cannot be read by a screen reader, so the same facts are in the territory table and the "highest risk" list next to it.
- **API views for the web** (`jogan/api/views.py`). The queue only holds planned visits; the map needs every agent:
  - `GET /v1/network/{day}`: every agent's position, balances, both stock-out chances, planned runner, manual review and anomaly flag on that morning.
  - `GET /v1/agents/{id}`: one agent's evidence on every plan day and its anomaly flags. Ids must match `^[A-Z]{3}-\d{3,5}$`.
  - `/v1/meta` gains `days`: planned visits, manual reviews and anomaly flags per plan day, for the timeline.
  - Queue rows, agent days and traces carry each driver's label and value, and each review reason, as English and Bangla display text from `configs/explain/labels.yaml`, so the web app never re-implements feature labels.
  - Both views read the bundle only and need a role, like the queue. Responses over 1 KB are gzip-compressed (Cloud Run does not compress): a day's network for the demo bundle is 172 KB of JSON, 16 KB compressed.
- **Impact numbers.** `make impact` (`jogan/eval/web.py`) copies the sections the impact page shows from `artifacts/metrics.json` into `web/lib/impact.json`. Nothing is estimated on the way; the only arithmetic is counting list entries. A test regenerates the file and compares it with the committed one, so a stale copy fails CI. The page reads nothing else, so every number on it comes from `make eval`.
- **Bangla and English.** All interface copy is in `web/lib/i18n.tsx` (English and Bangla dictionaries of the same shape, checked by TypeScript); explanations and labels still come from the API. The language is a cookie that the server layout reads, so the first paint is in the chosen language and `<html lang>` is right; this makes every route render on demand. Numbers use `Intl` with `en-IN` or `bn-BD`: lakh grouping, Bangla digits in Bangla, the ৳ sign, a true minus sign. Plan days are formatted in UTC so no time zone moves them; timestamps in Asia/Dhaka. Ids (agents, runners, recommendations) are never grouped or translated. Noto Sans Bengali stays the Bangla face; teammate 1 reviews the Bangla copy.
- **Labels.** Each output says what it is: Prediction (model output), Template (the explanation of record), AI-written (Gemini's rewording, with the model id), Assumption, Evaluation (measured by `make eval`). The decision trace shows who produced each step: model, model explanation, rule, optimizer, template or human.
- **Charts.** Hand-written SVG, no chart library: 2 px lines, 8 px markers with a surface ring, solid hairline grids, a hover or keyboard readout, a legend for two or more series, and a table view for every chart. Cash is upay blue and e-float `#D9730D`; the pair passes the categorical palette checks (worst colour-blind ΔE 27.7, normal-vision ΔE 36.1). Status colours (red, amber, green) only ever mean status and always come with a word and an icon.
- **Look.** upay's yellow and blue (D-007) in a layout of our own: a white sidebar with a yellow active marker, a thin yellow strip across the top, blue for primary actions, yellow only as a fill under ink text. Derived text colours were checked for contrast on white: amber `#7A4B00` 7.4:1, green `#13663A` 7.0:1, secondary grey `#4A5361` 7.8:1, tertiary `#636B78` 5.4:1. Icons from lucide-react 1.49.0 (npm, ISC).
- **Queue.** Filters (agent or runner, territory, status, manual review only), 50 rows a page, and a "Why?" row with the explanation, drivers and guardrails. A 429 shows "try again in N s" and counts down `Retry-After` before offering a retry.
- **Headers.** The web app sends `X-Frame-Options: DENY`, `nosniff`, a strict referrer policy and a `Permissions-Policy`, and hides `X-Powered-By`. A full Content-Security-Policy would need per-request nonces; it is left out.
- **Checks.** Besides lint, types and the build, the UI was checked locally against the API's in-memory store (the demo bundle `full`, seed 42) in headless Chrome: analyst without decision buttons, approve, reject, approve with a note, "Why?" and AI rewording, the trace after a decision, the audit log, pagination, Bangla, and a 390 px phone width. `scripts/live_check.py` now walks the new pages on the live site.

## D-026 · 2026-10-02 · Final eval check, stress check, monitoring and keep-alive

- **`make eval` not re-run.** Since `artifacts/metrics.json` was written (commit `c9bad60`), the only change to the code behind it is `jogan/eval/web.py` (M9, the impact copy). Recomputed on 2026-10-02, the six config hashes equal `meta.config_hashes` and the library versions equal `meta.versions`, and `make impact` leaves `web/lib/impact.json` unchanged. M10 moves the bundle's model fitting into `jogan.api.bundle.fit_models` with the same steps; a tiny bundle built by the old and the new code has identical plans, flags and meta. No sim, ops, forecast or plan code changed.
- **Stress check** (`make stress` → `artifacts/stress.json`; `jogan/eval/stress.py`, `configs/eval/stress.yaml`). The `stress` profile (10,000 agents, 6 hubs × 10 distributor areas, 18 to 31 May, D-015) times the served morning at scale:
  - Fourteen days are too few to train on, so the models are the demo bundle's, fitted on `full` seed 42 by `fit_models` (as `make bundle` does).
  - The forecaster takes the territory as a feature and as a conformal group, so it sees each distributor area as its hub, whose demand pattern the area copies. Runners, routes and the programs keep the 60 areas. The anomaly detector keeps its forest per setting; its list of agents is the stress world's.
  - The status quo runs 7 days; then Jogan runs the 7 mornings 25 to 31 May (Eid-ul-Azha on 28 May, when no runner works, so that morning has no programs). Each morning runs the whole served pipeline (`Recorder`): features, forecast, newsvendor levels, values, one program per territory, TreeSHAP drivers, guardrails and anomaly flags. The file records the time of each part, the programs, fallbacks, visits, peak memory and the machine.
  - **Timing only.** With at most 13 days of history behind the features, the forecasts, reviews and flags are not scored. Most early visits go to manual review because of the short history, which is the guardrail working as intended.
  - Not covered: publishing a 10,000-agent day to Supabase and serving its map from the API.
  - Timing numbers depend on the machine, so they are kept out of `metrics.json`. They follow the same rule: every timing in README, report or video comes from `artifacts/stress.json`, never typed by hand.
- **Monitoring and keep-alive.**
  - A Free plan Supabase project is paused when it "does not receive sufficient user database activity over the past week"; "typically a few user requests to the database each day" are enough (<https://supabase.com/docs/guides/platform/free-project-pausing>, checked 2026-10-02). Judges may not open the demo for days after 4 Oct, and it must stay up until about 15 Oct.
  - UptimeRobot's free plan: 50 monitors, a 5-minute interval, HTTP and keyword monitors, email alerts, "good for hobby and non-profit projects"; custom HTTP headers are a paid feature (<https://uptimerobot.com/pricing/>, checked 2026-10-02). Supabase's Data API needs an `apikey` header, so a free monitor cannot query the database directly.
  - So the API has `GET /health/db`: one PostgREST query with the secret key (`recommendations`, `select=id`, `limit=1`), answered `{"status": "ok", "database": "ok", "bundle_id": …}` or a 503. Nothing from the database is returned. The answer is reused for 60 s (`configs/api/base.yaml`, ASSUMPTION) under a lock, so callers cannot turn the public endpoint into a stream of database queries, and the per-address rate limit applies as to every request.
  - UptimeRobot's HTTP monitor sends `HEAD`, which FastAPI's `@app.get` routes refuse with 405 (seen live on 2026-10-02). `/health` and `/health/db` take `GET` and `HEAD`; a `HEAD` runs the same check, so it still reaches the database, and the server sends no body.
  - The owner adds two UptimeRobot monitors (owner checklist): the API's `/health/db` and the web app's `/about`, both every 5 minutes with email alerts.
  - Backup that needs no outside account: `.github/workflows/keepalive.yml` calls `/health/db` every 6 hours (with retries) and by hand; it needs no secrets or permissions. It is removed after the live period.
  - `scripts/live_check.py` checks `/health/db` too.

## D-027 · 2026-10-02 · Docs pack: numbers written from the artifacts, report and video script

- **Numbers in Markdown are generated.** `make docs` (`jogan/eval/docs.py`) rewrites every `<!-- numbers:NAME -->` … `<!-- /numbers -->` block in `README.md`, `docs/*.md` and `report/*.md` from `artifacts/metrics.json` and `artifacts/stress.json`, the same way `make impact` feeds the web app (D-025). Values are copied and rounded, never estimated; the only arithmetic is counting, a share of two counts and the days in a window. Prose outside the blocks carries no result numbers. Tests regenerate every file and fail on a stale copy, an unknown block name or a renderer no file uses.
- **Docs pack** (M11): `03-architecture`, `04-model-card`, `05-evaluation`, `06-responsible-ai`, `07-product-readiness`, `09-deployment`, `10-demo-script`, and the README rewritten for the Rulebook's §6 items.
- **Integration seam, as built.** The requirements checklist promised a `DataSource` adapter; none exists. What exists is the observed-log table the forecast reads (`OBS_COLUMNS`, refused if other columns appear) and the `Store` protocol for storage. The checklist and the architecture doc (§10) describe those; the logic chain's `DataSource` stays a description of the real-data step.
- **`scripts/gcp-setup.sh` has prerequisites** it does not perform: enabling the Google Cloud APIs, creating the Artifact Registry repository and both service accounts, and pushing a first `bootstrap` image. `09-deployment` lists them.
- **Report** is a Markdown draft in `report/report.md` (teammate 1's skeleton was not in the repo). The team's names and student IDs are on its cover and in the README; their university emails are kept out of the public repository unless the owner asks. The roles on the cover are the planned split and are confirmed before submission.
- **Video script** (`docs/10-demo-script.md`): the narration never contains a number. It points to cells of a numbers sheet at the end of the script, which `make docs` writes. Live decisions in a take are permanent (append-only audit), so the script asks for rehearsal and recording on different plan days and keeps away from 3 Jun, the live check's day.

## D-028 · 2026-10-02 · Clean-clone test, `make run` with local sign-in

- **What the clean clone found.** A fresh clone from GitHub, following only the README: `make setup` and `make check` passed (198 tests), `make bundle PROFILE=tiny SEED=0` and `make api` worked. But the web app could only sign in through Supabase, so without a Supabase project a judge saw the public pages and nothing else. The README's `cp .env.example .env` suggested that something reads `.env`; only `scripts/gcp-setup.sh` and `uv run --env-file .env` do. The API's bare URL, linked from the README, answered 404.
- **`make run`** (`scripts/run-local.sh`) starts the API with the in-memory store and the web app together, builds `bundle/` first if it is missing (the deployed world, `full`, seed 42, about 80 s once), installs the web packages if needed, waits for `/health`, and stops both on Ctrl+C. It serves whatever `bundle/` holds, so `make bundle PROFILE=tiny SEED=0` beforehand gives a small, fast world.
- **Local sign-in.** With `NEXT_PUBLIC_LOCAL_AUTH=1` (set only by `make run`) and an API on `localhost`, the sign-in card offers "Local run" as analyst or approver instead of the password form; the token is the role name, which only the in-memory store accepts. It cannot open the live system: the in-memory store refuses to start unless `JOGAN_ENV=development`, the deployed API verifies every token as a Supabase JWT (a role name is a 401, now tested), and the production web build does not set the variable (the live check still signs in with the demo accounts). The choice is kept per tab in `sessionStorage`.
- **API root.** `GET /` answers with the docs and health paths instead of a 404; it is not in the OpenAPI schema.
- **Next.js agent files.** `next dev` 16.3 writes `web/AGENTS.md` and `web/CLAUDE.md` when it detects an AI coding agent (`agentRules`, documented in `node_modules/next/dist/docs/01-app/02-guides/ai-agents.md`). They point agents to the bundled Next.js docs, which helps on site, so they are git-ignored rather than switched off.
- **Links.** Every relative link and anchor in the README, `web/README.md`, `docs/` and `report/` resolves. Of 41 external links, one failed: the Daily Star holiday list on its image host (402); the docs now use `www.thedailystar.net` (same article, 200). `configs/calendar/bd_2026.yaml` keeps the original URL, because its `sources` are part of the simulator config hash behind `artifacts/metrics.json`.
- **Rulebooks re-read** (AI Hackathon Rulebook, General Rules, Student Guideline). The checklist gained the video's "features and AI components" (Rulebook §7.2), the report's items (§7.3), any presentation the organizers specify (§7.4), no outside human help during the contest and the official clarification channel (General Rules §4.1, §10.1), and the ID card, backup internet and late-entry rules for the final (§1.2, §2.2, §3.2). `07-product-readiness` maps the validation plan to the guideline's post-hackathon pathway.

## D-029 · 2026-10-02 · Web UI redesign: trays, KPI cards, rail sidebar, phone layout

The owner asked for a more professional interface, shown by three references: a two-level sidebar with a command search and counts, a phone app with soft cards and a pill tab bar, and an analytics dashboard with small caps labels, KPI cards with bar sparklines, grey trays around white cards and block charts. The redesign keeps every feature, label, route and number source of M9 (D-025); only the presentation changed.

- **Look.** Warm greys on white: the sidebar and the trays sit one step below the white canvas, and white cards sit inside the trays. Section labels and table heads are small caps in Geist Mono (Google Fonts through `next/font`, checked in Next 16.3's font list); in Bangla they drop the capitals and the letter spacing, which breaks Bangla conjuncts. upay's colours keep their roles (D-007): blue for primary actions, links, focus and the cash series; yellow only as a fill under ink (Simulated data, Manual review, pending count, the human step in the trace); red for critical text only. The 3 px yellow strip and the yellow active marker of D-025 are gone; the active page is a raised white item with a blue icon.
- **Numbers and ids.** Quantities use Inter's tabular figures. Ids, codes and hashes use Geist Mono, whose zero is slashed: that tells `0` from `O` in ids like `DHK-001`, but it read as "Ø" in counts, and the Google build of Geist Mono has no plain-zero alternate (its subset carries no `zero` feature), so quantities stay in Inter.
- **Contrast** (on white / on the tray `#F6F6F4`): text `#111113` 18.9:1, secondary `#4B4C52` 8.6 / 7.9, tertiary `#66676D` 5.6 / 5.2 (never below 11 px). Unselected data marks (timeline blocks) `#86857F` 3.7:1 on white and 3.2:1 on their empty cells, above the 3:1 for graphics (WCAG 1.4.11). The D-025 derived colours (amber, green, red text) are unchanged.
- **Shell.** The sidebar collapses to an icon rail; the choice is a cookie the server layout reads, like the language, so the first paint has the right width. The sidebar's queue item shows the pending count only if a page already loaded that day's plan: reading a plan publishes the day (D-022), so side views never fetch one. The top bar has a breadcrumb; on phones a floating tab bar replaces the sidebar.
- **Command menu** (`/` or Ctrl/⌘ K): jump to a page, open an agent by id, switch the language or the sidebar. Agent ids come from the network or plan already loaded for the day in view; an id typed in full opens even if nothing is loaded.
- **Pages.** KPI cards with the last ten plan days of planned visits, manual reviews and anomaly flags as bars (from `/v1/meta`'s `days`), and the change in planned visits against the previous plan day. The planned-visits timeline is drawn as columns of blocks. The impact hero adds two bars from zero (Jogan and the status quo), so the gap is not drawn bigger than it is. The queue becomes a card list below 768 px, sharing state with the table; on a phone the agent page puts the recommendation and the decision before the charts and the trace.
- **Kept for the checks and the video.** Every heading, button name and label that `scripts/live_check.py` and the demo script use is unchanged, and the decision trace is still the agent page's only ordered list. The live check's browser steps were replayed against `make run` and passed.
- **Focus.** The global focus outline moved into the base layer so a control can draw its own focus state; every control that removes the outline has a ring instead.

## D-030 · 2026-10-04 · Submission: team name, video, report PDF, tag

- **Team name.** The team is registered as **Team Adrenaline** (the owner, 4 Oct); the docs said "Team Jogan". The README, the report's cover, the model card and the demo script now use the registered name. The product stays Jogan · যোগান.
- **Video.** Recorded by the team from [`10-demo-script.md`](10-demo-script.md) and shared on Google Drive to anyone with the link: <https://drive.google.com/file/d/1uXKkTAHMD9jE1exa-kO9ypYZwW8NukoK/view?usp=drive_link>. Checked without signing in: the page opens, and `ffprobe` reads 610 s at 1920×1200 with sound, above the 5-minute minimum. Linked from the README, the report and the script.
- **Report.** Final, no longer a draft. Rulebook §7.3 names the key features and the intended real-life impact, which the draft covered only in passing, so it gained §4.1 (key features), §8.1 (intended impact) and the problem statement in the Student Guideline's format (§10). No result number was typed; the numbers blocks are unchanged.
- **Report PDF.** `report/report.pdf` is an export of `report/report.md`: Python-Markdown to HTML, then headless Chrome 154 to A4, with Inter as TrueType from Google Fonts (the locally installed Inter OTF was embedded as Type 3 glyphs, which some viewers render badly), Noto Sans Bengali, page numbers in CSS margin boxes, and relative links rewritten to GitHub `main`. The export script is not committed, so the repository's structure does not change at submission; it is kept locally in `scratch/report-pdf/` (git-ignored). The PDF is committed (521 KB, under the 800 KB pre-commit limit) because judges may read the repository rather than the form upload. After any change to `report/report.md`, export it again.
- **No slide deck.** The submission form also offers a presentation slide; the owner chose not to add one.
- **Tag.** `submission-initial` marks the commit that records this decision, pushed before the deadline (D-028).

## D-031 · 2026-10-07 · On-site R1: problem relevance (size, frequency, agents' bank trips)

Pre-evaluation feedback on problem relevance asked for a clearer problem and solution, the real frequency and financial impact of liquidity failures, and a look at how shopkeepers refill from nearby banks themselves ([`ONSITE_LOG.md`](ONSITE_LOG.md) R1).

- **No upay data, so two honest substitutes.** (1) A national sizing from Bangladesh Bank's published agent totals (`make sizing` → `artifacts/sizing.json`). BB does not publish a turned-away rate, so the sizing is a sensitivity over rates tagged ASSUMPTION, never a claim. (2) Frequency and value measured in the simulated network, where every turned-away customer is known. The real rate is measured in a new step 0 of the validation plan, on upay's own logs with the censoring correction of D-020, before any model runs.
- **Turned away = served × r / (1 − r).** BB's totals are served requests, so a rate r of all attempts adds served × r / (1 − r) on top; each turned-away request is priced at the month's average size, and a customer who comes back later is not netted out. All three assumptions are written into the artifact and the docs block.
- **Agents' own bank trips were already simulated** (D-016, D-017) but never reported. `make eval` now aggregates them, with the turned-away value and the share of agent-days with a loss, from what each seed already recorded. The simulator, every config and every earlier number are unchanged; `make eval` was re-run to write them.
- **The bank trip stays a fallback, not a planned action.** Letting the planner recommend "go to the bank before 15:00" instead of a runner visit would answer the feedback more fully, but it changes the environment, the plan and the evaluation; it is listed as a gap, not built on site.
