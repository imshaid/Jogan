# Status

_Last updated: 2026-10-01, end of M0._

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

## Next

**M1 · Logic chain, requirements checklist, data assumptions**

- Write `docs/00-requirements-checklist.md` (rulebook, guideline and owner decisions as a tickable list).
- Write `docs/01-logic-chain.md` (guideline §10 format) and `docs/02-data-assumptions.md`.
- Verify online before using:
  - Bangladesh 2026 public holidays (Eid, Durga Puja, …) and weekend days
  - garment wage payment rule (Labour Act)
  - public upay facts, official sources only
  - a geography dataset and its license

## Milestone plan

| # | Milestone | Budget | Target (BST) | State |
|---|---|---|---|---|
| M0 | Repo foundation | 1.5 h | Thu 1 Oct 18:30 | done |
| M1 | Logic chain, requirements checklist, data assumptions | 1.5 h | Thu 20:30 | next |
| M2 | World simulator, data profiles, tests | 3.5 h | Fri 2 Oct 00:30 | |
| M3 | Operations environment, baseline policies, status-quo history log | 3.5 h | Fri 11:30 | |
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
make help    # list all targets
```
