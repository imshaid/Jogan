# AI usage disclosure

The competition allows AI tools. Participants must use their own accounts, are responsible for everything they submit, and must disclose the AI tools and models used and show prompt and development history if judges ask. This page is that disclosure; it is updated as the project grows.

## AI used to build Jogan (development time)

| Tool | Model | What it is used for | Account |
|---|---|---|---|
| Claude Code (VS Code extension) | Claude Opus 5.5 (`claude-opus-5-5`) | Planning, code, tests, docs and commits, under the owner's review | Owner's own account |

Commits made with Claude Code carry a `Co-Authored-By: Claude …` trailer, so its involvement is visible in the git history.

## AI inside the product (run time)

Everything here is planned and will be updated as each component lands. All model inputs are simulated data.

| Component | Technique | Role | Decides on its own? |
|---|---|---|---|
| Demand forecast | LightGBM quantile regression, trained in this repo | Predicts cash and e-float pressure per agent | No: feeds the decision rules |
| Calibration | Conformalized quantile regression (CQR) | Makes the prediction intervals honest | No |
| Dispatch optimizer | Mixed-integer program (SciPy `milp`, HiGHS) | Proposes runner visits and amounts | No: a human approver decides |
| Explanations | TreeSHAP drivers + bilingual templates; optional Gemini Flash-Lite narration (Google AI Studio free tier, model ids verified before use) | Explains structured evidence in English and Bangla | Never |
| Anomaly flag | Isolation Forest per peer group | Advisory flag for human review | Never |

## How AI-written content is marked

The UI labels every output as a **prediction**, an **assumption**, or an **AI-written explanation**. LLM text is never the source of a number or a decision.

## Prompt and development history

- The owner's original brief is kept locally (`.claude/master-prompt.local.md`, git-ignored) and can be shown to judges on request.
- Claude Code session transcripts are stored locally by Claude Code and can be exported with secrets redacted.
- Decisions and their reasons are logged in [`DECISIONS.md`](DECISIONS.md).

## Human responsibility

The team reviews, runs and must be able to explain every part of the system. The docs in this folder are written so every teammate can explain the design, the implementation and the AI components.
