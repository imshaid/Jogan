# Requirements checklist

Every official requirement and owner decision, as a list we can tick. "Where" points to the file or milestone that meets the requirement.

**Sources:**
- the organizers' AI Hackathon Rulebook, General Rules and Student Guideline (AI Dev Fest 2026, DIU CPC × upay)
- the organizers' announcement of the dates and the video length
- the owner's binding decisions

Docs pack (M11): [`03-architecture`](03-architecture.md), [`04-model-card`](04-model-card.md), [`05-evaluation`](05-evaluation.md), [`06-responsible-ai`](06-responsible-ai.md), [`07-product-readiness`](07-product-readiness.md), [`09-deployment`](09-deployment.md), [`10-demo-script`](10-demo-script.md); report in [`report/report.md`](../report/report.md) and [`report/report.pdf`](../report/report.pdf).

## A. Deadlines and submission

- [x] Initial code pushed before **4 Oct 2026 10:00 BST**, tag `submission-initial` on the last commit before the deadline (D-028, D-030)
- [x] Demo video of **at least 5 minutes** covering the project, its development, how it works, the features and AI components, and its real-world impact (Rulebook §7.2; script: [`10-demo-script.md`](10-demo-script.md); video: <https://drive.google.com/file/d/1uXKkTAHMD9jE1exa-kO9ypYZwW8NukoK/view?usp=drive_link>, D-030)
- [x] Project report on the problem, the idea, the implemented solution, key features, the AI approach, the implementation process and the intended impact (Rulebook §7.3; [`report/report.md`](../report/report.md), exported to [`report/report.pdf`](../report/report.pdf), D-030)
- [ ] Public GitHub link submitted through the organizers' form, with any presentation or file format they specify (Rulebook §7.4; the form also offers a presentation slide, which the owner chose not to add, D-030); check the submission is complete and opens before the deadline (General Rules §6.1)
- [ ] On-site, 7 Oct: new requirements implemented and pushed as small commits, logged in `docs/ONSITE_LOG.md`

## B. GitHub rules (Rulebook §5)

- [x] Public repository
- [x] Clear, continuous, step-by-step commit history in the initial phase (ongoing)
- [ ] Continuous commit history in the on-site phase
- [x] No single final upload
- [x] Source code, prototype files and a complete `README.md` in the repo (M11)

## C. Mandatory README items (Rulebook §6), done in M11

- [x] Project overview: problem, solution, purpose
- [x] Features and how the AI components are used
- [x] Technology stack: languages, frameworks, AI models, APIs, libraries, services
- [x] Requirements: software, dependencies, hardware, prerequisites
- [x] Installation and setup, step by step
- [x] Environment variables: names, purpose, configuration, **placeholders only** (`.env.example` exists)
- [x] Exact run and build commands
- [x] **Live deployment URL**
- [x] Testing instructions
- [x] Other configuration

## D. Development rules

- [x] Everything specific to this challenge is built during the event and visible in the history
- [x] AI tools and models disclosed in [`08-ai-usage.md`](08-ai-usage.md)
- [x] Participants use their own accounts
- [x] Prompt and development history available on request (local brief, Claude Code transcripts)
- [x] Significant external datasets, APIs and services listed (README "Data and external sources"; sources in [`02-data-assumptions.md`](02-data-assumptions.md))
- [ ] Every teammate can explain the design, the implementation and the AI (architecture doc, model card and evaluation written in M11; a walkthrough with both teammates is still due)
- [x] No copying from other teams
- [ ] No external human help during an active contest, nothing shared with other teams (General Rules §4.1–4.2); questions to the organizers only through the official clarification channel (§10.1)

## E. Branding

- [x] No upay logo; an original simple mark; wordmark "Jogan · যোগান" (M7, M9)
- [x] Not presented as upay's product (README disclaimer; UI disclaimer in M9)

## F. Judging criteria and our evidence

| Criterion | Weight | Evidence | Where |
|---|---|---|---|
| Problem relevance | 20% | Official BB figures on MFS scale and Eid peaks; agent stock-outs as a real operational pain | [`01-logic-chain.md`](01-logic-chain.md), [`07-product-readiness.md`](07-product-readiness.md) |
| AI/ML depth | 20% | Peak-drain quantile forecasts, CQR calibration, newsvendor + MILP dispatch, TreeSHAP drivers, ablations | M4–M5, [`04-model-card.md`](04-model-card.md) |
| Business/customer impact | 20% | Failed requests and known cost vs. three baselines (fixed round, threshold, safety stock) over several seeds; break-even value of a lost customer; salary sensitivity; where Jogan does not win | M5, [`05-evaluation.md`](05-evaluation.md) |
| Prototype quality | 15% | Live web app: map, agent detail, queue, approvals, impact page, bilingual | M6–M9 |
| Innovation | 10% | Forecasting the *peak* drain, censoring-aware training (the equity knob in the optimizer was not built, D-027) | [`03-architecture.md`](03-architecture.md), [`04-model-card.md`](04-model-card.md) |
| Scalability & integration | 10% | Documented observed-log table and `Store` protocol as the integration seam (D-027), stateless API, territory decomposition, stress test | M8, M10, [`03-architecture.md`](03-architecture.md) §9–10, [`07-product-readiness.md`](07-product-readiness.md) |
| Responsible AI & security | 5% | RLS roles, append-only audit, human approval, fairness table, grounded LLM, guardrails | M6–M8, [`06-responsible-ai.md`](06-responsible-ai.md) |

## G. Guideline expectations

- [x] One-page logic chain written before heavy coding ([`01-logic-chain.md`](01-logic-chain.md))
- [x] **Data strategy** documented ([`02-data-assumptions.md`](02-data-assumptions.md)):
  - synthetic only
  - known patterns injected (normal, anomalies, seasonality)
  - every assumption documented
  - clean test set never used to train
- [x] **Architecture** ([`03-architecture.md`](03-architecture.md)):
  - data preparation separate from model inference
  - business rules separate from ML predictions
  - traceable, explainable outputs
  - API ready for a real backend
  - no sensitive decision logic inside a free-form LLM prompt
- [x] **Product readiness** ([`07-product-readiness.md`](07-product-readiness.md)):
  - a frequent, economically meaningful problem
  - AI beats simple rules (honest baselines)
  - a clear action after each prediction
  - measurable benefit
  - can be validated with real data
  - privacy, fairness, explainability and security addressed
  - fits a real workflow
- [x] **Responsible AI minimums** ([`06-responsible-ai.md`](06-responsible-ai.md)):
  - privacy: synthetic only
  - explainability: main reasons per important prediction
  - fairness across groups
  - security: adversarial input, prompt injection, data leakage, access control
  - human oversight for high-impact actions
  - predictions, assumptions and generated explanations clearly separated
  - no autonomous approval or denial of consequential financial decisions

## H. Owner decisions (binding)

- [x] Supabase Postgres and Supabase Auth with roles (analyst, approver) and row-level security (M6, M8; D-022, D-024)
- [ ] **Deployment** (all done except the owner's UptimeRobot monitors):
  - Vercel (web)
  - Google Cloud Run (API, Docker, continuous deploy from GitHub)
  - Supabase free tier
  - UptimeRobot on `/health`, plus a keep-alive so Supabase does not pause
  - live until about 15 Oct (M6, M10)
- [x] **Gemini** (Google AI Studio free tier, M7, D-023):
  - model ids in config, overridable by env vars
  - second model on HTTP 429 (and 5xx)
  - template explanations precomputed; Gemini rewordings cached
  - mocked in tests and CI
  - synthetic data only
  - billing off (M7)
- [x] **UI** (M9):
  - full Bangla/English toggle, Noto Sans Bengali, ৳
  - an always-visible "Simulated data" badge
  - outputs labelled prediction, assumption or AI-written explanation
  - a reliable interactive map (MapLibre)
- [x] Brand colours with WCAG AA checks; risk never shown by colour alone ([`DECISIONS.md`](DECISIONS.md) D-007, D-025)
- [x] Small data while developing; the large final dataset generated from a seed (M2, M5, M10)

## I. Quality bar

- [x] `make setup`, `make test`, `make eval` (writes `artifacts/metrics.json`), `make run`; a clean clone works by following the README (M12: fresh clone from GitHub, `make setup`, `make check`, `make run` with local sign-in, approve and audit in headless Chrome)
  - setup and test exist since M0
  - eval: M5
  - run: M12 (API and web app with local sign-in, no accounts)
- [x] CI runs lint and tests; gitleaks secret scanning; Dependabot updates
- [x] **Honest evaluation** (M4–M5, M10; [`05-evaluation.md`](05-evaluation.md)):
  - leakage-free time splits and a held-out test window
  - interval coverage vs. nominal
  - baselines over several seeds with uncertainty
  - losing scenarios reported
  - fairness table
  - drivers per prediction
  - stress check
- [x] **Security and safety** (M7–M8; D-023, D-024):
  - role-based access
  - audit log for approvals
  - rate limiting and input validation
  - structured-input-only LLM
  - low confidence routed to manual review
- [ ] **Docs** (all written except `ONSITE_LOG.md`, which starts on site):
  - README
  - logic chain
  - architecture
  - data assumptions
  - model card
  - evaluation
  - responsible AI
  - product readiness
  - AI usage
  - deployment
  - demo script
  - `STATUS.md`
  - `ONSITE_LOG.md`
- [ ] **Before the deadline** (all done except the last item, the owner's):
  - live URL tested from a clean browser
  - repo public
  - README complete
  - tag `submission-initial`
  - report (Markdown and PDF) and video ready
  - submission form sent, every link opened from a private window
- [ ] **On-site readiness:**
  - config-driven code
  - auto-deploy on push
  - small commits per new requirement
  - own laptop and a backup hotspot (General Rules §2.2); `make run` as a local fallback if the live site is down (map tiles and fonts still come from the internet; not tested offline)
  - every member brings a valid institutional ID card (General Rules §1.2); late entry only up to 1 hour, with no extra time (§3.2)
