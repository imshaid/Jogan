# Status

_Last updated: 2026-10-01, end of M5._

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

## Next

**M6 · Walking skeleton live: Cloud Run + Vercel + Supabase schema, RLS, audit** (budget 3 h)

- The service accounts in the owner checklist must exist first (Supabase, GCP with a budget alert, Vercel).
- Minimal end-to-end path: the API serves one day's recommendations, the UI shows them, an approver approves or rejects, and every action writes an append-only audit row (RLS by role).
- **Inputs from M5:**
  - `Jogan.last` (one row per agent at each plan): balances, P(stock-out) per side, drain quantiles q50/q90/q99, needs, target cash, value in Tk, candidate flag, assigned runner. It is the evidence for the queue and, in M7, for explanations.
  - `artifacts/metrics.json` for the impact page.
  - The live demo needs a trained forecaster per demo world: train it once on the status-quo log and ship it with the API (to decide in M6).

**Carried into M7 and M11:**
- The report gets a section on **where Jogan does not win**: H4 (DHK/urban vs `threshold`), H3 (group coverage of the forecast), the oracle gap, and the costs left unpriced (motorcycle wear, phone, agents' own time).
- Not modelled in the policy: the runner's bag in the program, the hours between the forecast and the runner's arrival, and a call rescuing an agent who was not visited (D-021).
- Every number in README, report, UI and video comes from `artifacts/metrics.json`. Re-run `make eval` after any change to sim, ops, forecast or plan code or configs; its `meta.config_hashes` records the versions.

## Milestone plan

| # | Milestone | Budget | Target (BST) | State |
|---|---|---|---|---|
| M0 | Repo foundation | 1.5 h | Thu 1 Oct 18:30 | done |
| M1 | Logic chain, requirements checklist, data assumptions | 1.5 h | Thu 20:30 | done |
| M2 | World simulator, data profiles, tests | 3.5 h | Fri 2 Oct 00:30 | done |
| M3 | Operations environment, baseline policies, status-quo history log | 3.5 h | Fri 11:30 | done |
| M4 | Features (leakage test), quantile forecast, CQR, backtest, censoring | 4 h | Fri 16:00 | done |
| M5 | Newsvendor + MILP dispatch, multi-seed comparison, ablation, fairness, `make eval` | 3.5 h | Fri 19:30 | done |
| M6 | Walking skeleton live: Cloud Run + Vercel + Supabase schema, RLS, audit | 3 h | Fri 22:30 | next |
| M7 | Explanations, guardrails, Gemini narrator, anomaly flag | 2.5 h | Sat 3 Oct 09:30 | |
| M8 | Full API: auth, roles, queue, approve/reject, audit, rate limit, decision trace | 2.5 h | Sat 12:00 | |
| M9 | Web UI: map, agent detail, queue, impact, audit, about; Bangla/English | 6.5 h | Sat 19:00 | |
| M10 | Final eval and stress test, monitoring, keep-alive | 1.5 h | Sat 20:30 | |
| M11 | Full README, docs pack, report draft, video script | 3 h | Sat 23:30 | |
| M12 | Clean-clone test, live check, fixes, tag `submission-initial` | 3 h | Sun 4 Oct 08:00 | |
| – | Buffer and submission form (submit by about 09:00) | 2 h | Sun 10:00 | |

**Cut-line if behind schedule** (drop in this order):

1. anomaly flag
2. 10k-agent stress test
3. Gemini narration (templates stay)
4. partially observed cash

Never cut the end-to-end flow: simulator → environment → forecast → dispatch → approval → impact page → deploy → docs.

## Open decisions and questions

- **Organizers:** are fix pushes and redeploys allowed between 4 Oct 10:00 and the on-site start? The owner will ask. Until answered, only critical fixes in that window.
- All service accounts below must exist before M6 (Friday evening).

## Owner checklist

- [x] uv updated to 0.12.21
- [x] `gh` logged in as `imshaid`; push works
- [x] Working copy moved to `~/code/Jogan`
- [ ] `claude update`, check `/model` and `/usage`
- [ ] Supabase project (Mumbai, `ap-south-1`). Keep the DB password. Put the `sb_publishable_…` and `sb_secret_…` keys only in the local `.env`
- [ ] Google AI Studio API key (do not enable billing)
- [ ] MapTiler key
- [ ] GCP project with billing and a budget alert
- [ ] Vercel (log in with GitHub) and UptimeRobot accounts
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
make help    # list all targets
```
