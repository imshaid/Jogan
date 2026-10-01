# Status

_Last updated: 2026-10-01, end of M3._

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
  - configs: `configs/ops/{costs,env,policies}.yaml` (typed loader `jogan/ops/config.py`, sensitivity ranges for commission and goodwill)
  - `jogan/ops/`:
    - `env` (event replay of every attempt, hourly policy decisions, retries, agents' bank trips, observation history with gaps)
    - `fleet` (road km, runner shifts, feasibility shared by planners and environment)
    - `dispatch` (first-free runner for calls; prioritised sector rounds in nearest-neighbour order, the greedy baseline for M5)
    - `policies` (`none`, `reactive`, `fixed_round` = status quo, `threshold`, `safety_stock`, `oracle`), `metrics` (costs, groups, windows), `io`, CLI
  - **Verified online:** ANA Bangladesh survey (Helix / MicroSave, 2014): runners rebalance 96% of agents at the shop, usually at a predetermined time, plus on demand; about 22 rebalances a month; median zero denials a day. Status quo and runner visit limit (8 → 20) changed accordingly (D-016)
  - `make history PROFILE=… SEED=…` writes the status-quo log; `make baselines` compares all policies. Full profile: about 1.5 s per policy, 4 s with the log (14 MB)
  - 88 tests in about 3 s (46 new): no negative balances, liquidity conservation, common random numbers, oracle beats every baseline on lost requests, roster and shift limits, bank hours, observation gaps and no leakage, determinism, cost split by window
  - decisions D-016 (status quo per ANA), D-017 (environment design), D-018 (observation layer)


## Next

**M4 · Features (leakage test), quantile forecast, CQR, backtest, censoring** (budget 4 h)

- **Features** from `ops/fixed_round/obs/` only, respecting `available_at`: recent served flows per side, balances, calendar (weekday, payday, days to Eid, bank-open, Ramadan), agent master data, hat days. A leakage test (no feature uses a record after the forecast origin, no truth column).
- **Target:** peak cumulative drain of cash and of e-float over 6/12/24 h from the forecast origin (D-002 #3), from served flows.
- **Censoring:** hours with a stock-out under-report demand; mark them (balance near zero, failed side) and handle them explicitly; measure the bias against `truth/hourly.parquet`.
- **Models:** LightGBM quantile regression (check the current version and API before pinning), conformalized quantile regression on the calibration split, pinball loss and coverage per quantile and agent group; simple statistical baselines; time-based backtest (splits in data assumptions §2).
- Add `lightgbm` to the dependencies (verify the release first).

**Inputs from M3:** `simulate(world, make_policy("fixed_round", world))` or the files of `make history`. `Observation`/`History` (`jogan/ops/env.py`) is the in-simulation view a Jogan policy will get in M5; a Jogan policy subclasses `Planned` in `jogan/ops/policies.py` and plans its round with `plan_rounds`.

## Milestone plan

| # | Milestone | Budget | Target (BST) | State |
|---|---|---|---|---|
| M0 | Repo foundation | 1.5 h | Thu 1 Oct 18:30 | done |
| M1 | Logic chain, requirements checklist, data assumptions | 1.5 h | Thu 20:30 | done |
| M2 | World simulator, data profiles, tests | 3.5 h | Fri 2 Oct 00:30 | done |
| M3 | Operations environment, baseline policies, status-quo history log | 3.5 h | Fri 11:30 | done |
| M4 | Features (leakage test), quantile forecast, CQR, backtest, censoring | 4 h | Fri 16:00 | next |
| M5 | Newsvendor + MILP dispatch, multi-seed comparison, ablation, fairness, `make eval` | 3.5 h | Fri 19:30 | |
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
- **Owner: cost balance.** With the default costs (runner Tk 10/km + Tk 100/visit, goodwill Tk 50 per lost request), a runner visit usually costs more than the goodwill and commission it saves, so `none` has the lowest total cost in development runs. Not tuned on purpose. Options: keep the costs (Jogan's cost-aware newsvendor must then earn every visit, and the report says so), or revisit the runner cost or goodwill with a source. Decide before M5.

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
make baselines PROFILE=dev SEED=0 # compare every baseline policy
make help    # list all targets
```
