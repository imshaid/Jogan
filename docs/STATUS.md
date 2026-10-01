# Status

_Last updated: 2026-10-01, end of M4._

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


## Next

**M5 · Newsvendor + MILP dispatch, multi-seed comparison, ablation, fairness, `make eval`** (budget 3.5 h)

- **Jogan policy** (subclass of `Planned` in `jogan/ops/policies.py`): at the plan hour, build features with `build_features(panel_from_history(obs.history), ctx.calendar, ctx.agents, cfg, np.array([obs.hour]))`, predict calibrated quantiles with `Forecaster.models[h, side].predict(x, groups)`, pick the newsvendor level from the critical ratio, and plan the round.
- **Newsvendor:** the underage cost includes the lost-customer value as an operator setting (D-019); the quantile grid is 0.05–0.99, so interpolate between levels for the critical ratio.
- **Training per seed:** fit on the status-quo log's training split, calibrate on its calibration split, compare policies on the test split only (D-010). Evaluation seeds 1000–1009 are never used for tuning.
- **Dispatch:** MILP runner assignment (HiGHS; verify the current release and API first) against the greedy `plan_rounds` baseline; ablation: Jogan forecast + greedy dispatch.
- **`make eval`** writes `artifacts/metrics.json`: the forecast metrics (from `jogan.forecast.backtest.evaluate`) and the policy comparison, with paired intervals across seeds, the break-even value against each baseline and the salary range, a fairness table, and the list of cases where Jogan does not win.

**Carried into M5 and M11 (D-019):**
- Jogan is compared with `fixed_round`, `threshold` and `safety_stock` only; the oracle is the upper bound.
- Jogan's newsvendor takes the lost-customer value as an operator setting; the evaluation sweeps it and reports the break-even value against each baseline with paired intervals across seeds, plus the salary range.
- `make eval` lists where Jogan does not win (baseline, agent group, period, cost setting); the report gets a section on it, plus the costs left unpriced (motorcycle wear, phone, agents' own time).

**Inputs from M4:** `jogan.forecast.backtest.build_dataset` / `fit_forecaster` / `evaluate`; `jogan.forecast.model.stockout_probability`; the forecast is hourly-resolution and of demand, with live balances entering only in P(stock-out) and the newsvendor (D-020). The Eid-ul-Azha test window is scored separately (`periods.eid`).

## Milestone plan

| # | Milestone | Budget | Target (BST) | State |
|---|---|---|---|---|
| M0 | Repo foundation | 1.5 h | Thu 1 Oct 18:30 | done |
| M1 | Logic chain, requirements checklist, data assumptions | 1.5 h | Thu 20:30 | done |
| M2 | World simulator, data profiles, tests | 3.5 h | Fri 2 Oct 00:30 | done |
| M3 | Operations environment, baseline policies, status-quo history log | 3.5 h | Fri 11:30 | done |
| M4 | Features (leakage test), quantile forecast, CQR, backtest, censoring | 4 h | Fri 16:00 | done |
| M5 | Newsvendor + MILP dispatch, multi-seed comparison, ablation, fairness, `make eval` | 3.5 h | Fri 19:30 | next |
| M6 | Walking skeleton live: Cloud Run + Vercel + Supabase schema, RLS, audit | 3 h | Fri 22:30 | |
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
make help    # list all targets
```
