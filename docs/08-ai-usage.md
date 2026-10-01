# AI usage disclosure

The competition allows AI tools. Participants must use their own accounts, are responsible for everything they submit, and must disclose the AI tools and models used and show prompt and development history if judges ask. This page is that disclosure; it is updated as the project grows.

## AI used to build Jogan (development time)

| Tool | Model | What it is used for | Account |
|---|---|---|---|
| Claude Code (VS Code extension) | Claude Opus 5.5 (`claude-opus-5-5`) | Planning, code, tests, docs and commits, under the owner's review | Owner's own account |

Commits made with Claude Code carry a `Co-Authored-By: Claude …` trailer, so its involvement is visible in the git history.

## AI inside the product (run time)

Updated as each component lands. All model inputs are simulated data.

| Component | Technique | Role | Decides on its own? |
|---|---|---|---|
| Demand forecast | LightGBM quantile regression, trained in this repo | Predicts cash and e-float pressure per agent | No: feeds the decision rules |
| Calibration | Conformalized quantile regression (CQR) | Makes the prediction intervals honest | No |
| Dispatch optimizer | Mixed-integer program (SciPy `milp`, HiGHS) | Proposes runner visits and amounts | No: a human approver decides |
| Explanations | TreeSHAP drivers (LightGBM `pred_contrib`) + bilingual templates; on request, Gemini rewords a template: `gemini-3.8-flash`, falling back to `gemini-3.5-flash-lite` (Google AI Studio free tier, ids verified 2026-10-02). A rewording with any number not in the evidence is discarded | Explains structured evidence in English and Bangla | Never |
| Guardrails | Rules on the evidence (out of training range, wide interval, data gap, short history, anomaly flag) | Sends a visit to manual review; approving it needs a note | Never |
| Anomaly flag | Isolation Forest per agent setting (scikit-learn) plus two rules | Advisory flag for human review | Never |

## How AI-written content is marked

The UI labels every output as a **prediction**, an **assumption**, or an **AI-written explanation**. LLM text is never the source of a number or a decision: the template explanation is shown by default, and a Gemini rewording is marked "Reworded by AI" with the model id. Free-tier prompts may be used by Google to improve its products, so only simulated data is ever sent.

## Prompt and development history

- The owner's original brief is kept locally (`.claude/master-prompt.local.md`, git-ignored) and can be shown to judges on request.
- Claude Code session transcripts are stored locally by Claude Code and can be exported with secrets redacted.
- Decisions and their reasons are logged in [`DECISIONS.md`](DECISIONS.md).

## Human responsibility

The team reviews, runs and must be able to explain every part of the system. The docs in this folder are written so every teammate can explain the design, the implementation and the AI components.
