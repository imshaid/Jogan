# Status

_Last updated: 2026-10-02, end of M10._

Submission deadline: **4 Oct 2026 10:00 BST** (no late submissions). On-site final: **7 Oct 2026**. Keep the live URL up until about 15 Oct.

Working copy: `~/code/Jogan` (ext4). The old NTFS copy under `/run/media/surjo/Code Cache/Jogan` is retired; see D-006 in [`DECISIONS.md`](DECISIONS.md).

## Done

- **M0 · Repo foundation**
  - `.gitignore` / `.gitattributes`, MIT license
  - uv project (Python 3.12.14, flat `jogan/` package), pytest smoke test
  - ruff, pre-commit (ruff + gitleaks), Makefile
  - CI (lint + tests), gitleaks secret scan, Dependabot
  - `.env.example`, Claude Code settings and project guide
  - decision log, AI-usage disclosure, README overview
- **M1 · Logic chain, requirements checklist, data assumptions**
  - [`00-requirements-checklist.md`](00-requirements-checklist.md), [`01-logic-chain.md`](01-logic-chain.md), [`02-data-assumptions.md`](02-data-assumptions.md)
  - decisions D-010 to D-012
  - **Facts verified online**, with sources inside the docs:
    - 2026 Bangladesh holidays and the actual Eid dates (21 Mar, 28 May)
    - Friday–Saturday bank weekend
    - Labour Act s.123 wage timing
    - BB MFS tables (accounts, agent cash-in/out by month to Jul-26)
    - BB agent count (Feb-25)
    - BB customer limits (27 Mar 2025)
    - top remittance districts (Mar-26)
    - upay's launch-time cash-out fee (2021)
    - MIT-licensed district geocodes
- **M2 · World simulator, data profiles, tests**
  - configs:
    - `configs/sim/{base,tiny,dev,full,stress}.yaml`
    - `configs/calendar/bd_2026.yaml`
    - `configs/geo/territories.yaml` (hubs verified against nuhil/bangladesh-geocode)
    - `configs/calibration/bb_mfs_2026.yaml` (BB table 9 re-fetched; Apr, May, Jul 2026)
  - `jogan/sim/`:
    - `config` (pydantic, `extra=forbid`, config hash)
    - `calendar`
    - `demand` (every pattern in data assumptions §5)
    - `calibration` (bisection on the expected network)
    - `world` (agents, roster, demand stream, anomalies)
    - `io`, CLI
  - `make data PROFILE=… SEED=…`; timings on this machine: tiny 0.4 s, dev 0.5 s, full 0.8 s, stress 1.2 s
  - 42 tests, about 1.4 s: determinism, pattern recovery (pooled seeds), calibration, sanity, leakage split
  - decisions D-013 (Eid calibration; Fitr shares Azha's because of the Nagad data gap), D-014 (public/truth split, one RNG stream per component), D-015 (profiles)
- **M3 · Operations environment, baseline policies, status-quo history log**
  - configs: `configs/ops/{costs,env,policies}.yaml` (typed loader `jogan/ops/config.py`)
  - `jogan/ops/`:
    - `env` (event replay of every attempt, hourly policy decisions, retries, agents' bank trips, observation history with gaps)
    - `fleet` (road km, runner shifts, feasibility shared by planners and environment)
    - `dispatch` (first-free runner for calls; prioritised sector rounds in nearest-neighbour order, the greedy baseline for M5)
    - `policies` (`fixed_round` = status quo, `threshold`, `safety_stock`; `oracle` as upper bound), `costs` (derived prices, break-even), `metrics` (costs, groups, windows), `io`, CLI
  - **Verified online:** ANA Bangladesh survey (Helix / MicroSave, 2014): runners rebalance 96% of agents at the shop, usually at a predetermined time, plus on demand; about 22 rebalances a month; median zero denials a day. Status quo and runner visit limit (8 → 20) changed accordingly (D-016)
  - `make history PROFILE=… SEED=…` writes the status-quo log; `make baselines` compares all policies. Full profile: about 1.5 s per policy, 4 s with the log (14 MB)
  - **Cost model from real inputs (owner decision, D-019):** official 2026 petrol prices by date, a 100 cc motorcycle's claimed mileage, a 2026 bKash DSO job ad (Tk 13,000–17,000), the 48-hour legal week, agent commission Tk 4.10 per 1,000 (2022 source), BB policy rate for idle money, 2026 bank transaction hours. A lost customer's value is not priced; `make baselines` prints the break-even value against the status quo. Every number in `configs/ops/*.yaml` carries a SOURCE / DERIVED / ASSUMPTION tag, enforced by a test
  - 89 tests in about 3 s: no negative balances, liquidity conservation, common random numbers, oracle beats each baseline on lost requests, roster and shift limits, bank hours, observation gaps and no leakage, determinism, cost derivation and break-even, cost split by window, tags on every ops number
  - decisions D-016 (status quo per ANA), D-017 (environment design), D-018 (observation layer), D-019 (cost model, break-even, three baselines)

- **M4 · Features (leakage test), quantile forecast, CQR, backtest, censoring**
  - config: `configs/forecast/base.yaml` (typed loader `jogan/forecast/config.py`; origins, horizons, quantile levels, splits per profile, censoring, conformal groups, LightGBM settings; every number tagged, enforced by a test)
  - `jogan/forecast/`:
    - `panel` (observed log as agents × hours arrays with each record's arrival hour; from the parquet log or from a running simulation's `History`, identical by test)
    - `targets` (peak cumulative drain per side, stock-out flags, estimated demand with `impute`/`ignore`/`drop`)
    - `features` (41 features from records usable at each origin; the empirical and naive baselines on the way)
    - `model` (one LightGBM quantile booster per horizon, side and level on `log1p`; asymmetric CQR per setting × size class; P(stock-out) from the grid)
    - `backtest` (time-based splits, fit, scores against estimated labels and true demand), CLI
  - **Verified online:** LightGBM 4.7.0 (PyPI, 18 Jul 2026, MIT; pandas 3 support in its release notes; quantile objective, `deterministic`, `force_row_wise` in the parameter docs); CQR Theorem 2 (Romano, Patterson and Candès, arXiv:1905.03222)
  - `make forecast PROFILE=… SEED=…` (after `make history`) writes `data/<p>/seed<n>/forecast/metrics_<strategy>.json`; `--censoring ignore|drop` for the ablations. Full profile: about 70 s per seed (fit about 60 s)
  - **Censoring:** served flows understate the true 24-hour peak drain by about a quarter to a third on development seeds; estimated-demand labels bring that to a few percent. Thresholds chosen on development seed 0 only. Ablation (full, seed 0): `impute` keeps the 90% interval near nominal against true demand, `ignore` under-covers at 24 h, `drop` is worst (selection bias) (D-020)
  - 106 tests in about 8 s (17 new): leakage by perturbing every record that arrives after the origin, no truth columns, log panel = in-simulation panel, splits, hand-checked peak drain, censoring flags and bias, conformal coverage on synthetic data with group fallback, monotone quantiles, P(stock-out), determinism, CLI
  - decision D-020 (labels from estimated demand, leak-free features, liquidity total only, asymmetric CQR in log space, hourly resolution, runtime)

- **M5 · Newsvendor + MILP dispatch, multi-seed comparison, ablation, fairness, `make eval`**
  - configs: `configs/plan/base.yaml` (policy), `configs/eval/base.yaml` (seeds, value sweep, intervals); every number tagged, enforced by a test
  - `jogan/plan/`:
    - `newsvendor` (quantile function from the grid, expected shortfall, critical ratio, target level)
    - `dispatch` (Fisher–Jaikumar generalized-assignment MILP per territory with optional visits, HiGHS via `scipy.optimize.milp`; route check, fill step, greedy fallback)
    - `policy` (`Jogan`: in-simulation forecast at 08:00, newsvendor needs, value of a visit including the call it saves, decision trace in `Jogan.last`)
  - `Deployed` in `jogan/ops/policies.py`: every policy switched on at the test start from the status quo's state
  - `jogan/eval/`: `run` (one seed: status-quo log → forecaster → every policy), `stats` (paired t-intervals, Fieller break-even), `report`, CLI
  - **`make eval`** writes `artifacts/metrics.json` (`full`, seeds 1000–1009, about 17 min on this laptop with 2 workers). Per-seed records go to `artifacts/eval/` (git-ignored). Development runs (`make eval ARGS="--seeds 0 1 2 3"`) write `artifacts/eval/metrics_dev.json`
  - **Verified:** scipy 1.18.1 bundles HiGHS 1.12.0, read from the installed package; `milp` options from its docstring. scipy is now a direct dependency (already installed through LightGBM). Fisher and Jaikumar (1981, *Networks* 11(2), 109–124); Fieller (1954, *JRSS B* 16(2), 175–185)
  - **Design found on development seeds 0–3 only** (D-021):
    - the two-sided newsvendor split lost more requests than a split by typical outflow;
    - without the saved call in a visit's value, and without the fill step, the MILP used less capacity than the greedy round
  - **Result (`artifacts/metrics.json`, Jogan at Tk 20 per lost customer, test window, 10 evaluation seeds):**
    - Jogan loses fewer requests than every baseline: −9.5 per 1,000 vs `fixed_round`, −2.2 vs `threshold`, −2.6 vs `safety_stock`, all significant
    - it also has lower known cost and fewer runner km, so it is cheaper at every lost-customer value, at all three salaries, in the Eid window too
    - H2 holds
    - ablations: the MILP beats the greedy round (fewer lost requests, fewer km); the typical split beats the two-sided split
    - the oracle still loses about 20 per 1,000 fewer than Jogan
  - **Where Jogan does not win** (`does_not_win`, H3/H4):
    - **H4 fails.** Urban agents (DHK, the only urban territory) are served slightly worse than under `threshold` (+1.0 per 1,000, interval just above zero). Small agents do better under `safety_stock` (not significant)
    - **H3 fails** on 45 coverage cells of the M4 forecast (side × horizon × interval × group), mostly the 50% and 80% intervals, urban the most; 4 of them are overall, not per group
    - no period (test window, Eid) and no cost setting at any swept value is a loss; all 62 cases are agent groups
  - 123 tests in about 18 s (17 new): newsvendor maths exact on a uniform drain, dispatch feasibility and value against greedy, switch-over equals the status quo, Jogan in the environment (trace, candidates only, no rejected visits, deterministic), t- and Fieller intervals, break-even verdicts, the eval CLI on two tiny seeds
  - decision D-021

- **M6 · Walking skeleton live: Cloud Run + Vercel + Supabase schema, RLS, audit**
  - **Live:**
    - web <https://jogan-bd.vercel.app> (one-click demo analyst and approver)
    - API <https://jogan-api-gt7msysppq-as.a.run.app> (`/health`, `/docs`)
    - Supabase, Cloud Run and Artifact Registry all in Singapore
  - `jogan/api/`:
    - `bundle`: the served demo world (`full`, seed 42). Status quo → forecaster → Jogan over the test window, keeping every morning's evidence: 28 plan days, 6,559 visits. Built inside `docker build` in about 75 s; the bundle id comes from the config hashes
    - `store`: Supabase over PostgREST with the user's token, or `MemoryStore` with the same rules
    - `app`: FastAPI with `/health`, `/v1/meta`, `/v1/me`, `/v1/plans/{date}` (publishes a day on first request), `/v1/recommendations/{id}/decision` and `/v1/audit`
  - `supabase/migrations/`:
    - `user_roles`, `recommendations` and `audit_log`, with explicit grants and RLS
    - `publish_plan` (secret key only) and `decide_recommendation` (approvers only, decision and audit row in one transaction)
    - triggers make the audit log append-only and a recommendation decidable once, even for the table owner
  - **Deploy:**
    - `Dockerfile` (python 3.12-slim-trixie, uv 0.12.21, non-root)
    - `scripts/gcp-setup.sh`, run once by the owner: Secret Manager, keyless Workload Identity Federation for this repo's `main` only, a least-privilege deployer, the first deploy
    - `.github/workflows/deploy-api.yml` builds, pushes and deploys after CI passes, and pins CORS to `https://jogan-bd.vercel.app`
    - Vercel deploys `web/` on push
  - `web/` (Next.js 16.3.8, Tailwind 4, supabase-js 2.117.2): sign-in, the day's queue with P(stock-out) labelled as a prediction (word + symbol, not colour alone), approve/reject for approvers, the audit log, an always-visible "Simulated data" badge
  - **Checks:**
    - 132 Python tests (9 new, API on the tiny bundle)
    - `make test-db`: the migration on Postgres 17 with RLS, grants and append-only rules checked for every role
    - CI jobs for Python, database and web
    - `scripts/live_check.py` passed on the live site in Chrome: analyst sees 254 visits and is refused a decision (403); approver approves and rejects on 3 Jun, both audited; CORS and the missing-token 401
    - probed as anonymous on live Supabase: sign-up disabled, every table and function refused (42501)
  - decision D-022

- **M7 · Explanations, guardrails, Gemini narrator, anomaly flag**
  - configs: `configs/explain/base.yaml` (every number tagged, enforced by a test) and `configs/explain/labels.yaml` (English and Bangla words; teammate 1 reviews the Bangla)
  - `jogan/explain/`:
    - `drivers`: TreeSHAP from LightGBM's `pred_contrib`, on the 24-hour 0.9-quantile booster of the side at risk; top 3 effects of at least 5%
    - `guardrails`: manual review on out of training range (the agent's own amounts only), wide interval, data gap, short history or an anomaly flag
    - `template`: the explanation of record, in English and Bangla, from the stored evidence only (Bangla digits, lakh grouping)
    - `narrator`: Gemini rewords one template on request; `gemini-3.5-flash-lite`, falling back to `gemini-3.1-flash-lite` on 429/5xx (the owner's choice) (both verified stable and free-tier on 2026-10-02); refused, and the template shown, if any number is new, the stock-out chance is lost, the script is wrong or the text is too long; 8 calls a minute per instance, cached
  - `jogan/detect/anomaly.py`: advisory flag from the observed log (night transactions, volume, cash-out size, busiest hour, against the agent's own history and the territory's day). An Isolation Forest per setting (scikit-learn 1.9.1, new dependency) plus two rules: night transactions, and a value beyond the setting's training maximum
  - bundle: every planned visit's evidence now holds `side`, `drivers` and `review`, and each morning's anomaly flags (on the previous day) are kept. Demo bundle (`full`, seed 42, about 80 s): 6,559 visits, 772 for manual review, 104 anomaly flags over 28 days
  - API:
    - every queue row carries `explanation.en` and `explanation.bn`
    - `GET /v1/recommendations/{id}/explanation?lang=en|bn` returns Gemini's rewording or the template, with the reason
    - `GET /v1/anomalies/{day}` lists the advisory flags
  - database: migration `20261002020000_review_note.sql`. Approving a flagged visit needs a note (422 otherwise), and the audit row records `manual_review`
  - web:
    - "Why?" panel per visit with an English/Bangla switch and "Reword with AI" (labelled with the model id; the template stays the default)
    - "⚑ Manual review" tag (word and symbol, not colour alone) and a note form when approving a flagged visit
    - anomaly flag list
    - the owner's logo: favicon, Apple icon and header mark from `docs/brand/jogan-light.png` (`scripts/brand_icons.py`); the text wordmark stays
  - `make eval` also scores the anomaly flag on every evaluation seed's test window (`anomaly` in `artifacts/metrics.json`); every other section is unchanged:
    - 168,000 test agent-days over 10 seeds; 1,219 flags (0.7%), 48 of them on injected anomalies, a precision of 3.9% against a base rate of 0.08%
    - precision at 5 / 10 / 20 (per seed, averaged): 0.30 / 0.36 / 0.22
    - injected windows with at least one flag: night 6 of 6, spike 3 of 6, split (structuring) 1 of 9
    - **the flag is weak on structuring**, which goes into the report's "where Jogan does not win"
  - **Checks:** 160 Python tests (28 new: drivers add up to the raw prediction, every feature has both labels, lakh grouping and Bangla digits, guardrail reasons, the narrator with a mocked Gemini (fallback, refusals, rate limit, cache, no user text in the prompt), the anomaly flag on a synthetic log (patterns found, a territory-wide payday ignored, no leak from late or future records), API explanation, anomaly and review-note endpoints); `make test-db` checks the note rule; `scripts/live_check.py` now covers "Why?", Bangla, the AI rewording and a flagged approval. Passed on the live site after the owner applied the migration and mounted the Gemini key: the Bangla rewording came from `gemini-3.5-flash-lite`, and a flagged visit was refused without a note (422) and approved with one
  - decision D-023

- **M8 · Full API: auth, roles, queue, approve/reject, audit, rate limit, decision trace**
  - config: `configs/api/base.yaml` (typed loader `jogan/api/config.py`; every number tagged, enforced by a test)
  - `jogan/api/`:
    - `auth`: the API checks every Supabase token itself before any database call. It verifies the signature against the project's JWK set (ES256; RS256 allowed), the issuer, the audience, the expiry, the subject and the role `authenticated`. The key set is cached for 10 min, and an unknown key id refetches it at most every 30 s. Stale keys keep working through an outage; no keys at all gives 503. PostgREST still checks the token again
    - `guard`: token-bucket rate limits in memory, per client address (every request) and per user (signed-in requests), plus separate buckets for deciding and for AI rewording. A refusal is a 429 with `Retry-After`. The guard also caps bodies at 8 KB with a `Content-Length` and adds `Cache-Control: no-store` and `nosniff` to every response. The client address is read from the right of `X-Forwarded-For` (`JOGAN_TRUSTED_PROXY_HOPS=1` in the image)
    - `errors`: every refusal is `{detail, code}`. Validation errors add `errors` (field and message, never the submitted value); a 429 adds `retry_after_s`; an unexpected error is a plain 500
    - `trace`: `GET /v1/recommendations/{id}/trace` returns the layers in order (forecast and stock-out chance → drivers → need and value → runner → guardrails → template → human decision). Each layer names the config hash it ran under. The response also holds the stored trace, both explanations, that morning's anomaly flag and the audit rows. An LLM is never a step
    - input validation: dates only as `YYYY-MM-DD` (pydantic also took a Unix time or a datetime), ids within `bigint`, a note of at most 500 characters with no control characters, no unknown body fields; `/v1/audit?recommendation_id=` filters the log; `/v1/me` returns `user_id`
  - new dependency: PyJWT 2.15.1 with `crypto` (cryptography 50.0.2), verified on PyPI
  - web: `web/lib/api.ts` has `api.trace`, the `DecisionTrace` type, and `ApiError.code` / `retryAfterS` for M9
  - **Checks:**
    - 180 Python tests (20 new): real ES256 tokens signed in the tests and twelve kinds of forged or wrong tokens refused (another key, HS256, `none`, expired, other issuer, anon, service role, no subject …); key rotation and the refetch cap; an outage; bucket refill and the bound on stored buckets; the client address under forged headers; the per-address, per-user, decision and rewording limits; 411/413; one error body for 404/405/422/500; date, id and note validation; the trace's layers, config hashes and audit rows; `from_env` in both store modes
    - `scripts/live_check.py` also checks a forged token (401 from the API), a Unix time as a date (422), the trace of an approved visit, and that forged `X-Forwarded-For` values still hit the rate limit. It passed on the live site
    - The client-address rule was also checked live from a second address (D-024). The owner's ISP uses carrier-grade NAT with 3 public addresses
  - decision D-024

- **M9 · Web UI: map, agent detail, queue, impact, audit, about; Bangla/English**
  - six routes (`web/app/`): `/` network map, `/queue`, `/agents/[id]`, `/audit` (signed in); `/impact`, `/about` (public). The plan day lives in the URL (`?day=`)
  - **network:** MapLibre GL JS 6.11.2 on OpenFreeMap `positron` (no key, so the MapTiler key is no longer needed); every agent as a shape by risk band (▲ ◆ ●) with a ring for a planned visit; risk for the higher side, cash or e-float; filter to visits or high risk; KPI strip; a 28-day timeline of planned visits with play; territory table and "highest risk" list (the map's facts in readable form)
  - **queue:** filters (agent or runner, territory, status, manual review only), 50 rows a page, "Why?" row with the explanation (template or AI-written, labelled), drivers as diverging bars and guardrail reasons; approve, reject, approve with a note; 429 counts down `Retry-After`
  - **agent:** stock-out chance over the test window (cash and e-float, visit days marked, click a day), forecast drain (median, 90%, 99%) against the balance, the recommendation with its decision controls, drivers, guardrails, anomaly flags, and the decision trace (8 steps, who produced each, config hash, audit rows); every chart has a table view
  - **impact:** every number from `web/lib/impact.json`, a copy of `artifacts/metrics.json` made by `make impact` (`jogan/eval/web.py`) and checked by a test: Jogan vs the status quo and the best baseline with 95% intervals, lost requests by policy, Jogan minus each baseline (lost, km, cost), hypotheses H1–H4, "where Jogan does not win", fairness by group, forecast coverage and Brier, the anomaly flag, ablations; test or Eid window
  - **audit** (filter by action, 50/100/200 rows) and **about** (data to decision, where AI is and is not used, every label explained, data and privacy, access and accountability, limits)
  - **Bangla/English:** all copy in `web/lib/i18n.tsx`; a cookie read by the server layout, so the first paint is in the chosen language; Bangla digits, lakh grouping, ৳, dates in Bangla; ids never translated. Teammate 1 reviews the Bangla
  - labels on every output: Prediction, Template, AI-written, Assumption, Evaluation
  - look: upay yellow and blue in our own layout (white sidebar, yellow active marker and top strip, blue actions); derived text colours checked for contrast; lucide-react 1.49.0 icons; security headers on the web app
  - API (`jogan/api/views.py`): `GET /v1/network/{day}`, `GET /v1/agents/{id}`, `days` in `/v1/meta`, bilingual display text for drivers and review reasons, gzip (a day's network: 172 KB → 16 KB)
  - **Checks:** 186 Python tests (6 new: meta day counts, the network's agents and visits, display text, one agent's days and flags, the impact copy matches `metrics.json`); web lint, types and build. Checked locally in headless Chrome against the in-memory API on the demo bundle: analyst without buttons, approve, reject, approve with a note, "Why?", AI rewording, the trace after a decision, audit, pagination, Bangla and a 390 px phone width. `scripts/live_check.py` rewritten for the new pages and passed on the live site after the deploy: public impact page, the map, the analyst refused (403), the whole interface in Bangla with Gemini's rewording (`gemini-3.5-flash-lite`), an approval and a rejection on 3 Jun audited, the 8-step trace, the rate limit. No flagged visit was pending on the first page of 3 Jun this run, so the note step was skipped (it passed in M7–M8)
  - decision D-025

- **M10 · Final eval check, stress test, monitoring, keep-alive**
  - **`make eval` not re-run:** the six config hashes and the library versions recomputed now equal `artifacts/metrics.json`'s `meta`; the only code change behind it since then is `jogan/eval/web.py`; `make impact` changes nothing
  - **`make stress`** (`jogan/eval/stress.py`, `configs/eval/stress.yaml`) → `artifacts/stress.json` (committed, timing only): 10,000 agents, 260 runners, 60 territories; status quo 7 days, then 7 Jogan mornings (25–31 May, Eid-ul-Azha inside) through the whole served pipeline with the demo bundle's models (`full`, seed 42); the forecaster sees each distributor area as its hub (D-026)
    - on this laptop (i7-13650HX, 20 threads): a morning takes 3.1 s on average, 4.3 s at most (plan 2.4 s of which HiGHS 1.7 s; drivers, guardrails and flags 0.7 s); 360 programs, 0 fallbacks, 23,836 visits; the 14-day status quo for 10,000 agents 2.3 s; peak memory 1.8 GB (fitting on `full` included); whole run 101 s
    - 28 May has no programs: no runner is on duty on Eid (roster)
    - not scored (13 days of history at most), and not covered: publishing and serving a 10,000-agent day
  - `jogan.api.bundle.fit_models` shared by the bundle and the stress check (tiny bundle identical before and after)
  - **monitoring:** `GET /health/db` runs one PostgREST query with the secret key (`select=id`, `limit=1`), answer reused 60 s under a lock, 503 if the database fails; `scripts/live_check.py` checks it
  - **keep-alive:** a Free Supabase project pauses after a week without database activity (verified); UptimeRobot's free plan cannot send the `apikey` header (verified), hence `/health/db`. `.github/workflows/keepalive.yml` calls it every 6 hours as a backup; UptimeRobot (every 5 min) is the owner's checklist item
  - **Checks:** 192 Python tests (6 new: stress config and tags, hub mapping, a stress run on a replicated tiny world with a different agent count, refusal of unseen hubs, `/health/db` caching and 503, the Supabase ping request)
  - decision D-026

## Next

**M11 · Full README, docs pack, report draft, video script** (budget 3 h)

- README with the live URLs, demo accounts, `make` targets and the headline numbers from `artifacts/metrics.json` (and timings from `artifacts/stress.json`).
- Docs pack named in the requirements checklist: `03-architecture`, `04-model-card`, `05-evaluation`, `06-responsible-ai`, `07-product-readiness`.
- Report draft (with teammate 1's skeleton in `report/`) and the video script (teammate 2's storyboard).

**Carried into M11:**
- The report gets a section on **where Jogan does not win**: H4 (DHK/urban vs `threshold`), H3 (group coverage of the forecast), the oracle gap, the anomaly flag's weakness on structuring (split cash-outs, 1 of 9 windows), and the costs left unpriced (motorcycle wear, phone, agents' own time).
- Not modelled in the policy: the runner's bag in the program, the hours between the forecast and the runner's arrival, and a call rescuing an agent who was not visited (D-021).
- Every number in README, report, UI and video comes from `artifacts/metrics.json`. Re-run `make eval` after any change to sim, ops, forecast or plan code or configs; its `meta.config_hashes` records the versions.
- Timings (stress check) come from `artifacts/stress.json` (`make stress`), never typed by hand (D-026).

## Milestone plan

| # | Milestone | Budget | Target (BST) | State |
|---|---|---|---|---|
| M0 | Repo foundation | 1.5 h | Thu 1 Oct 18:30 | done |
| M1 | Logic chain, requirements checklist, data assumptions | 1.5 h | Thu 20:30 | done |
| M2 | World simulator, data profiles, tests | 3.5 h | Fri 2 Oct 00:30 | done |
| M3 | Operations environment, baseline policies, status-quo history log | 3.5 h | Fri 11:30 | done |
| M4 | Features (leakage test), quantile forecast, CQR, backtest, censoring | 4 h | Fri 16:00 | done |
| M5 | Newsvendor + MILP dispatch, multi-seed comparison, ablation, fairness, `make eval` | 3.5 h | Fri 19:30 | done |
| M6 | Walking skeleton live: Cloud Run + Vercel + Supabase schema, RLS, audit | 3 h | Fri 22:30 | done |
| M7 | Explanations, guardrails, Gemini narrator, anomaly flag | 2.5 h | Sat 3 Oct 09:30 | done |
| M8 | Full API: auth, roles, queue, approve/reject, audit, rate limit, decision trace | 2.5 h | Sat 12:00 | done |
| M9 | Web UI: map, agent detail, queue, impact, audit, about; Bangla/English | 6.5 h | Sat 19:00 | done |
| M10 | Final eval and stress test, monitoring, keep-alive | 1.5 h | Sat 20:30 | done |
| M11 | Full README, docs pack, report draft, video script | 3 h | Sat 23:30 | next |
| M12 | Clean-clone test, live check, fixes, tag `submission-initial` | 3 h | Sun 4 Oct 08:00 | |
| – | Buffer and submission form (submit by about 09:00) | 2 h | Sun 10:00 | |

**Cut-line if behind schedule** (drop in this order; the anomaly flag and Gemini narration are done in M7):

1. ~~10k-agent stress test~~ (done in M10)
2. partially observed cash

Never cut the end-to-end flow: simulator → environment → forecast → dispatch → approval → impact page → deploy → docs.

## Open decisions and questions

- **Organizers:** are fix pushes and redeploys allowed between 4 Oct 10:00 and the on-site start? The owner will ask. Until answered, only critical fixes in that window.
- Dependabot: during the competition merge only security fixes after CI passes. Python stays on 3.12, and major web bumps are skipped (TypeScript 7 breaks typescript-eslint). PR #3 (React 19.3.0) is green but not a security fix, so leave it open.

## Owner checklist

- [x] uv updated to 0.12.21
- [x] `gh` logged in as `imshaid`; push works
- [x] Working copy moved to `~/code/Jogan`
- [ ] `claude update`, check `/model` and `/usage`
- [x] Supabase project (Singapore, D-022), migration pushed, demo users seeded, public sign-up off
- [x] Google AI Studio API key (do not enable billing)
- [x] ~~MapTiler key~~ not needed: the map uses OpenFreeMap (D-025)
- [x] GCP project with billing and a budget alert; `scripts/gcp-setup.sh` run
- [x] Vercel project `jogan-bd` (root `web/`)
- [ ] UptimeRobot (free, no card; D-026), sign up at <https://uptimerobot.com> and add two monitors, both HTTP(s), every 5 minutes, alerts to your email:
  - `Jogan API + DB`: `https://jogan-api-gt7msysppq-as.a.run.app/health/db` (also the Supabase keep-alive)
  - `Jogan web`: `https://jogan-bd.vercel.app/about`
  - Keep them until about 15 Oct, then delete them and `.github/workflows/keepalive.yml`
- [ ] Teammates added as collaborators
- [ ] Repo secret scanning and push protection enabled
- [ ] Commit email verified on the GitHub account
- [ ] Organizers asked the question above

## Teammate tasks

- **Teammate 1**
  - Report skeleton in `report/`.
  - Collect official public sources on upay and MFS agents (links only, no guessing).
  - Later, review the Bangla UI strings.
- **Teammate 2**
  - Storyboard the video (5 minutes or more) and set up OBS.
  - Saturday afternoon: manual QA on the live URL.
  - Saturday night: clean-clone test following the README.

## How to run

```bash
make setup   # install deps and git hooks
make check   # lint + tests (same as CI)
make data PROFILE=dev SEED=0   # simulated world → data/dev/seed0/
make history PROFILE=dev SEED=0   # status-quo log → data/dev/seed0/ops/fixed_round/
make baselines PROFILE=dev SEED=0 # three baselines + oracle, break-even vs status quo
make forecast PROFILE=dev SEED=0  # drain forecast backtest → data/dev/seed0/forecast/
make eval    # final comparison, seeds 1000–1009 → artifacts/metrics.json (about 17 min)
make eval ARGS="--seeds 0 1 2 3"  # development run → artifacts/eval/metrics_dev.json
make impact  # copy the impact page's numbers from artifacts/metrics.json → web/lib/impact.json
make stress  # time Jogan's mornings for 10,000 agents → artifacts/stress.json (about 2 min)
make bundle PROFILE=tiny SEED=0  # served demo bundle → bundle/ (deployed: PROFILE=full SEED=42)
make api     # API on :8000 with the in-memory store (tokens "analyst", "approver")
make test-db # migration + RLS/audit checks on a throwaway Postgres 17 (Docker)
cd web && npm ci && npm run dev  # web app on :3000 (NEXT_PUBLIC_* in web/.env.local)
uv run --with playwright python scripts/live_check.py  # live end-to-end check (decides 2 visits)
make help    # list all targets
```
