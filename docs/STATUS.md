# Status

_Last updated: 2026-10-01, end of M2._

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

## Next

**M3 · Operations environment, baseline policies, status-quo history log** (hard part: maximum thinking)

- **Costs config:** `configs/ops/costs.yaml` with commission, goodwill, runner and idle-cash costs and their sensitivity ranges (data assumptions §6).
- **Environment** (`jogan/ops/`), hourly over `truth/demand`:
  - cash and e-float balances; failed attempts when a side runs dry (censoring), optional 30% retry within 2 h
  - status-quo self-refill: below 15% of a typical day, 2–6 h delay, no bank refill on Fri/Sat/holidays
  - runner visits (shift, bag capacity, max visits, travel time with disruption speed factor)
  - costs: lost commission, goodwill, runner km and visits, idle liquidity
- **Observation layer:** what Jogan sees (data assumptions §7):
  - served transactions only
  - exact e-float, estimated cash
  - about 1% missing hours and late days (moved here from M2)
- **Policies:** reactive, static threshold, safety stock (mean + kσ), oracle, plus a policy interface for Jogan (M5).
- **Status-quo history log** for M4 training.
- **Tests:**
  - no negative balances
  - liquidity conservation (a visit swaps cash and e-float)
  - identical demand under every policy (common random numbers)
  - oracle at least as good as every baseline

**Inputs from M2:** `build_world(load_config(profile), seed)` or `read_world(path, truth=True)`. `agents.parquet` is master data; starting balances and typical-day amounts are in `truth/agents`. Runner speeds are in `runners`, on-duty days in `roster`, and disruption days and speed factors in `truth/disruptions`.

## Milestone plan

| # | Milestone | Budget | Target (BST) | State |
|---|---|---|---|---|
| M0 | Repo foundation | 1.5 h | Thu 1 Oct 18:30 | done |
| M1 | Logic chain, requirements checklist, data assumptions | 1.5 h | Thu 20:30 | done |
| M2 | World simulator, data profiles, tests | 3.5 h | Fri 2 Oct 00:30 | done |
| M3 | Operations environment, baseline policies, status-quo history log | 3.5 h | Fri 11:30 | next |
| M4 | Features (leakage test), quantile forecast, CQR, backtest, censoring | 4 h | Fri 16:00 | |
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
make help    # list all targets
```
