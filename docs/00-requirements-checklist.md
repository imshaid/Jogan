# Requirements checklist

Every official requirement and owner decision, as a list we can tick. "Where" points to the file or milestone that meets the requirement.

**Sources:**
- the organizers' Rulebook and Student Guideline (AI Dev Fest 2026, DIU CPC × upay)
- the owner's binding decisions

Planned docs: `03-architecture`, `04-model-card`, `05-evaluation`, `06-responsible-ai`, `07-product-readiness`, `09-deployment`, `10-demo-script`.

## A. Deadlines and submission

- [ ] Initial code pushed before **4 Oct 2026 10:00 BST**, tag `submission-initial` (M12)
- [ ] Demo video of **at least 5 minutes** covering the project, its development, what it does, how it works and its real-world impact (script in `docs/10-demo-script.md`, M11; recorded by teammates)
- [ ] Project report on the approach, the implementation process and other details (`report/`, M11)
- [ ] Public GitHub link submitted through the organizers' form
- [ ] On-site, 7 Oct: new requirements implemented and pushed as small commits, logged in `docs/ONSITE_LOG.md`

## B. GitHub rules (Rulebook §5)

- [x] Public repository
- [x] Clear, continuous, step-by-step commit history in the initial phase (ongoing)
- [ ] Continuous commit history in the on-site phase
- [x] No single final upload
- [ ] Source code, prototype files and a complete `README.md` in the repo (M11)

## C. Mandatory README items (Rulebook §6), all due in M11

- [ ] Project overview: problem, solution, purpose
- [ ] Features and how the AI components are used
- [ ] Technology stack: languages, frameworks, AI models, APIs, libraries, services
- [ ] Requirements: software, dependencies, hardware, prerequisites
- [ ] Installation and setup, step by step
- [ ] Environment variables: names, purpose, configuration, **placeholders only** (`.env.example` exists)
- [ ] Exact run and build commands
- [ ] **Live deployment URL**
- [ ] Testing instructions
- [ ] Other configuration

## D. Development rules

- [x] Everything specific to this challenge is built during the event and visible in the history
- [x] AI tools and models disclosed in [`08-ai-usage.md`](08-ai-usage.md)
- [x] Participants use their own accounts
- [x] Prompt and development history available on request (local brief, Claude Code transcripts)
- [ ] Significant external datasets, APIs and services listed (partly in [`02-data-assumptions.md`](02-data-assumptions.md); full list in the README, M11)
- [ ] Every teammate can explain the design, the implementation and the AI (architecture doc and model card, plus a walkthrough, M11)
- [x] No copying from other teams

## E. Branding

- [ ] No upay logo; an original simple mark; wordmark "Jogan · যোগান" (M9)
- [x] Not presented as upay's product (README disclaimer; UI disclaimer in M9)

## F. Judging criteria and our evidence

| Criterion | Weight | Evidence | Where |
|---|---|---|---|
| Problem relevance | 20% | Official BB figures on MFS scale and Eid peaks; agent stock-outs as a real operational pain | [`01-logic-chain.md`](01-logic-chain.md) |
| AI/ML depth | 20% | Peak-drain quantile forecasts, CQR calibration, newsvendor + MILP dispatch, TreeSHAP drivers, ablations | M4–M5, `04-model-card` |
| Business/customer impact | 20% | Failed requests and known cost vs. three baselines (fixed round, threshold, safety stock) over several seeds; break-even value of a lost customer; salary sensitivity; where Jogan does not win | M5, `05-evaluation` |
| Prototype quality | 15% | Live web app: map, agent detail, queue, approvals, impact page, bilingual | M6–M9 |
| Innovation | 10% | Forecasting the *peak* drain, censoring-aware training, an equity knob in the optimizer | `03-architecture`, `04-model-card` |
| Scalability & integration | 10% | `DataSource` adapter, stateless API, territory decomposition, stress test | M8, M10, `07-product-readiness` |
| Responsible AI & security | 5% | RLS roles, append-only audit, human approval, fairness table, grounded LLM, guardrails | M6–M8, `06-responsible-ai` |

## G. Guideline expectations

- [x] One-page logic chain written before heavy coding ([`01-logic-chain.md`](01-logic-chain.md))
- [x] **Data strategy** documented ([`02-data-assumptions.md`](02-data-assumptions.md)):
  - synthetic only
  - known patterns injected (normal, anomalies, seasonality)
  - every assumption documented
  - clean test set never used to train
- [ ] **Architecture** (`03-architecture`):
  - data preparation separate from model inference
  - business rules separate from ML predictions
  - traceable, explainable outputs
  - API ready for a real backend
  - no sensitive decision logic inside a free-form LLM prompt
- [ ] **Product readiness** (`07-product-readiness`):
  - a frequent, economically meaningful problem
  - AI beats simple rules (honest baselines)
  - a clear action after each prediction
  - measurable benefit
  - can be validated with real data
  - privacy, fairness, explainability and security addressed
  - fits a real workflow
- [ ] **Responsible AI minimums** (`06-responsible-ai`):
  - privacy: synthetic only
  - explainability: main reasons per important prediction
  - fairness across groups
  - security: adversarial input, prompt injection, data leakage, access control
  - human oversight for high-impact actions
  - predictions, assumptions and generated explanations clearly separated
  - no autonomous approval or denial of consequential financial decisions

## H. Owner decisions (binding)

- [x] Supabase Postgres and Supabase Auth with roles (analyst, approver) and row-level security (M6, M8; D-022, D-024)
- [ ] **Deployment:**
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
- [ ] **UI** (M9):
  - full Bangla/English toggle, Noto Sans Bengali, ৳
  - an always-visible "Simulated data" badge
  - outputs labelled prediction, assumption or AI-written explanation
  - a reliable interactive map (MapLibre)
- [ ] Brand colours with WCAG AA checks; risk never shown by colour alone ([`DECISIONS.md`](DECISIONS.md) D-007, M9)
- [ ] Small data while developing; the large final dataset generated from a seed (M2, M10)

## I. Quality bar

- [ ] `make setup`, `make test`, `make eval` (writes `artifacts/metrics.json`), `make run`; a clean clone works by following the README
  - setup and test exist since M0
  - eval: M5
  - run: M6
- [x] CI runs lint and tests; gitleaks secret scanning; Dependabot updates
- [ ] **Honest evaluation** (M4–M5, M10):
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
- [ ] **Docs:**
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
- [ ] **Before the deadline:**
  - live URL tested from a clean browser
  - repo public
  - README complete
  - tag `submission-initial`
  - report and video script ready
- [ ] **On-site readiness:**
  - config-driven code
  - auto-deploy on push
  - small commits per new requirement
  - own laptop and hotspot
