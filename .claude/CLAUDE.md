# Jogan · যোগান: Claude Code project guide

Read `docs/STATUS.md` first in every session: it says what is done, what is next, open decisions and how to run things. Decisions and their reasons live in `docs/DECISIONS.md`. The original brief is kept local only (git-ignored): `.claude/master-prompt.local.md`.

Deadline: **4 Oct 2026 10:00 BST** (no late submissions). On-site final: 7 Oct 2026.

## Language
- Talk to the owner (Md. Shaid Hasan, GitHub `imshaid`) in Bangla, informal "তুমি".
- Code, comments, commits, README and docs are English. The Bangla UI copy is product content.
- Commands for the owner must work in **fish** (`set -x X Y`, no heredocs). Repo scripts and the Makefile are bash/POSIX with a shebang.

## Git rules
- Work on `main`. One finished task = one small commit = one push.
- Message: one line, imperative, about 60 chars max, Conventional Commits (`feat(sim): ...`, `fix(api): ...`, `docs: ...`, `chore: ...`), plus the AI co-author trailer.
- Stage specific files (never `git add -A`), review `git status` and `git diff --staged`, run the relevant checks, and make sure no secret, `.env`, data or scratch file is staged.
- Never force-push, rewrite history, backdate, use `--no-verify` or fake activity. If a push fails on auth, stop and tell the owner what to run.
- Throw-away experiments only in `scratch/` (git-ignored).

## Make targets
`make setup` · `make lint` · `make format` · `make test` · `make check` (same as CI) · `make clean`. New targets are added per milestone; `make help` lists them.

## Rules that never bend
- Never read `.env*` files (except `.env.example`) or `data/`.
- Verified data only: check official docs or registries before pinning a version or calling an API; label anything unverifiable `ASSUMPTION`.
- Every number in README, report, UI or video comes from `make eval` (`artifacts/metrics.json`), never typed by hand.
- Synthetic data only. The LLM only explains structured evidence and never decides. High-impact actions need a human approver and an audit-log entry.
- Save tokens: targeted reads, small data profiles while developing, never print big files or DataFrames.

## Brand tokens
Measured from the official guideline PDF, not from an official brand guide:
`--upay-yellow #FBD603` (fill only, ink text on it) · `--upay-blue #0C55A4` (primary) · `--upay-red #EB1D27` (critical only; 4.43:1 on white, so small text uses a darker derived red) · `--upay-ink #050608`.
Never encode risk by colour alone. Never copy the upay logo; use the wordmark "Jogan · যোগান".

## End of every milestone
Checks pass → update `docs/STATUS.md` → commit and push → tell the owner in Bangla what is finished and that `/clear` is safe now.
