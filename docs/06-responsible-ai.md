# Responsible AI and security

How Jogan meets the organizers' responsible-AI minimums (Student Guideline; [`00-requirements-checklist.md`](00-requirements-checklist.md) §G), what each safeguard is, where it lives in the code and how it is tested. Known gaps are listed at the end, not hidden.

## 1. Summary

| Minimum | What Jogan does | Where | Checked by |
|---|---|---|---|
| Privacy | Simulated data only; agent-level aggregates, no customer data at all; nothing personal sent to an LLM | `jogan/sim`, `jogan/explain/narrator.py` | narrator test: no user text in the prompt |
| Explainability | Drivers, a template explanation and an 8-step decision trace for every recommended visit | `jogan/explain`, `jogan/api/trace.py` | drivers add up to the prediction; trace tests |
| Fairness | Lost requests by territory, setting and agent size, against the best baseline, losses reported | `jogan/eval/report.py` | H4 in `make eval`; [`05-evaluation.md`](05-evaluation.md) §5 |
| Security | Token verification, roles twice (API and RLS), rate limits, validation, append-only audit, secrets in Secret Manager | `jogan/api`, `supabase/migrations` | API security tests, `make test-db`, `live_check.py` |
| Human oversight | Every visit is approved or rejected by a person; flagged visits need a note | `decide_recommendation`, web queue | `make test-db`, API tests, live check |
| Outputs clearly separated | Each output labelled Prediction, Template, AI-written, Assumption or Evaluation | `web/lib/i18n.tsx`, every page | UI review, live check |
| No autonomous financial decisions | Jogan proposes runner visits; it never moves money, blocks an agent or approves anything | the whole design | no code path writes a decision without an approver's token |

## 2. Privacy and data

- **Synthetic only.** Every agent, customer and transaction comes from the seeded simulator. Public facts (Bangladesh Bank aggregates, the 2026 calendar, district coordinates, prices) shape it; no upay data and no personal data are used ([`02-data-assumptions.md`](02-data-assumptions.md)). The interface shows a "Simulated data" badge on every page.
- **Data minimisation by design.** Even with real data, Jogan needs only agent-level hourly aggregates, balances, runner visits and rosters ([`03-architecture.md`](03-architecture.md) §5). It never needs a customer's identity, phone number or transaction detail.
- **What is stored.** The database holds recommendations (agent ids, amounts, evidence), decisions and the audit log, plus the Supabase Auth accounts of the two demo users on a reserved `example.com` domain. Public sign-up is off.
- **LLM data.** Only the template text and the structured evidence of one simulated visit are sent to Gemini, on request. The free tier may use prompts to improve Google's products, which is acceptable only because the data is simulated; a real deployment would need a provider and terms approved by upay, or templates only.
- **Secrets.** Kept in Google Secret Manager and readable only by the API's runtime account; never in git (gitleaks in pre-commit and CI), never in the browser (only the publishable key is public).

## 3. Human oversight and accountability

- **The human decides.** The optimizer proposes visits; an approver approves or rejects each one. An analyst can see everything and decide nothing. There is no "approve all" button.
- **Low confidence goes to manual review.** A visit is flagged when the agent is outside the training range, the forecast interval is wide, data is missing, history is short or the anomaly flag fired ([`04-model-card.md`](04-model-card.md) §3). Approving a flagged visit needs a written note; the rule sits in the database function, so it cannot be skipped by calling the Data API directly.
- **Every decision is audited.** The decision and its audit row are written in one transaction. Triggers make the audit log append-only (no update, delete or truncate) and a recommendation decidable once, even for the table owner and the secret key. The audit row records who, when, the decision, `manual_review` and the note.
- **Every recommendation is traceable.** The trace names, for each of the 8 steps, who produced it (model, model explanation, rule, optimizer, template, human) and the config hash it ran under.
- **The anomaly flag is advisory.** It never acts on an agent; it only asks a person to look. It is weak (see the model card) and must not be read as an accusation.

## 4. Explainability and transparency

- **Drivers:** exact TreeSHAP contributions of the model that set the risk, top 3 with labels in English and Bangla.
- **Explanation of record:** a template filled only from the stored evidence, in English and Bangla (Bangla digits, lakh grouping, ৳).
- **Labels on every output** (D-025): **Prediction** (a model output, such as the stock-out chance), **Template** (the explanation of record), **AI-written** (Gemini's rewording, with the model id), **Assumption** (a configured value such as the risk bands), **Evaluation** (measured by `make eval`).
- **About page** (`/about`, public): how data becomes a decision, where AI is and is not used, every label, data and privacy, access and accountability, limits.
- **Impact page** (`/impact`, public): the evaluation, including the cases where Jogan does not win.

## 5. Fairness

Jogan is evaluated per territory, setting (urban, peri-urban, rural) and agent size (small, medium, large), against the best baseline, and the forecast's coverage is reported per group. The result is mixed and reported as such: Jogan serves most groups better, but it is **worse than the threshold rule for urban agents** and not significantly better for small agents and one territory; H4 ("no group worse served") fails. Details and numbers: [`05-evaluation.md`](05-evaluation.md) §5 and [`04-model-card.md`](04-model-card.md) §1.

The planned equity weight or service floor in the optimizer (D-002 #9) was not built. Before any pilot, a service floor per group and a check of who gets fewer visits under Jogan are required.

## 6. The LLM: what it may and may not do

| Risk | Safeguard |
|---|---|
| The LLM makes or changes a decision | It is not a step of the pipeline. It rewords one finished template on request; the plan, numbers and decision are fixed before it runs |
| Hallucinated numbers | The answer is refused if it contains any number not in the template (Bangla digits normalised first), or drops the stock-out chance |
| Prompt injection through user input | No user text ever enters a prompt: not an approver's note, not a search term. The input is the template plus evidence built from simulated data and config labels |
| Malformed or overlong output | JSON response schema; refused if not JSON, longer than the configured limit, or in the wrong script |
| Misleading wording | The template stays the default; the rewording is labelled "AI-written" with the model id, and the template is one click away |
| Cost and abuse | Requests only on a click, per-user and per-instance rate limits, a cache, a free-tier key with billing off |
| Provider failure | A second model on HTTP 429 or 5xx; otherwise the template, with the reason shown |

Tests mock the HTTP layer and cover the fallback, every refusal, the rate limit, the cache and the absence of user text in the prompt.

## 7. Security

**Access control.** Two roles, analyst (read) and approver (read and decide). They are checked twice: by the API, which verifies every Supabase token itself (signature against the project's JWK set, ES256 or RS256 only, issuer, audience, expiry, subject, role `authenticated`) before any database call, and by row-level security and the SQL functions in Postgres, which verify the token again. Users cannot write to any table directly.

**Threats and mitigations:**

| Threat | Mitigation | Tested |
|---|---|---|
| Forged or tampered token (`none`, HS256, another key, expired, wrong issuer or audience, anon or service-role token) | API token verification; PostgREST re-verifies | twelve kinds of forged token in pytest; a forged token in `live_check.py` |
| The local run's fixed tokens (`analyst`, `approver`) used against the live system | the in-memory store refuses to start unless `JOGAN_ENV=development`; the deployed API verifies every token as a Supabase JWT, so a role name is a 401; the web app offers local sign-in only with `NEXT_PUBLIC_LOCAL_AUTH=1` and an API on `localhost` | pytest (`from_env` in both store modes, forged tokens) |
| Analyst tries to approve | API role check, then `decide_recommendation` refuses (42501 → 403) | pytest, `make test-db`, live check |
| Editing or deleting history | append-only triggers on the audit log; a decided recommendation cannot change | `make test-db` for every role, including the table owner |
| Brute force or flooding | token buckets per address, per user, for decisions and for AI rewording; 429 with `Retry-After` | pytest with a fake clock; live check |
| Dodging the rate limit with forged `X-Forwarded-For` | the client address is read from the right of the header, by the number of trusted proxies | pytest; checked live from two addresses (D-024) |
| Oversized or malformed input | 8 KB body cap, `Content-Length` required, strict dates and ids, note length and control characters, unknown fields refused | pytest |
| Information leakage in errors | one error body; validation errors name the field, never the submitted value; a 500 has no detail | pytest |
| Cross-site use of the API | CORS allows only the production web origin; every data route needs a bearer token anyway | live check |
| Clickjacking and sniffing | `X-Frame-Options: DENY`, `nosniff`, strict referrer and permissions policies on the web app; `no-store` and `nosniff` on the API | API headers in pytest; web headers set in `web/next.config.ts` |
| Leaked secrets | Secret Manager, keyless deploys (Workload Identity Federation for this repo's `main` only), least-privilege deployer, gitleaks | CI secret scan |
| Vulnerable dependencies | lockfiles (`uv.lock`, `package-lock.json`), Dependabot, security fixes merged after CI | Dependabot |
| Adversarial or unusual agent data | guardrails send out-of-range and gappy agents to manual review; the anomaly flag asks a person to look | guardrail tests |

### Access control matrix

Who may do what today, and what enforces it (on-site R7, D-037). Every row is enforced on the server; the web app only hides what the server would refuse anyway.

| Action | Anonymous | Analyst | Approver | API runtime (secret key) | Enforced by |
|---|---|---|---|---|---|
| Read the impact page and "How it works" | yes | yes | yes | – | public pages, simulated aggregates only |
| Read the plan, map, evidence, trace, anomaly flags | no (401) | yes | yes | – | API token check, then row-level security |
| Read the audit log | no | yes | yes | – | API token check, RLS |
| Ask for an AI rewording | no | yes | yes | – | API token check, rate limit per user |
| Approve or reject a visit | no | no (403) | yes, once per visit; a note when flagged | – | API role check, then `decide_recommendation` (approver role, note rule, one transaction with the audit row) |
| Publish a day's plan | no | no | no | yes | `publish_plan` granted to the secret key only |
| Edit or delete a decision or an audit row | no | no | no | no | append-only triggers, even for the table owner |
| Change a model or a config | no | no | no | no | only through a reviewed commit: CI, then a keyless deploy from `main` |

## 8. Accessibility

Risk is never shown by colour alone: every band has a word and a shape (▲ ◆ ●). Text colours meet WCAG AA contrast (measured in D-007, D-025 and D-029); upay yellow is used only as a fill under dark text. Every chart has a table view, and the map's facts are repeated in a territory table and a "highest risk" list for screen readers. The whole interface works in Bangla and English, and at phone width.

## 9. Known gaps

- **Simulated data.** Nothing here proves the safeguards on real agents.
- **Fairness.** H4 fails for urban agents; no equity constraint yet.
- **Rewording checks are about numbers and script, not tone.** A rewording could soften a warning without changing a number; the label and the default template are the defence.
- **Rate limits are per instance** (at most 2), so a client gets at most twice the configured rate.
- **A token stays valid until it expires**, even after sign-out (Supabase and PostgREST behave the same way).
- **No full Content-Security-Policy** on the web app (it would need per-request nonces).
- **The demo password is public by design** so judges can sign in; the accounts see only simulated data and every decision is audited.
- **The anomaly flag is weak on structuring** and must stay advisory.

## 10. Operating a pilot: data protection, monitoring, override and escalation

What a pilot on upay's data adds to the controls above (on-site R7, D-037). Thresholds are ASSUMPTIONS to agree with upay before the pilot; none is tuned.

### 10.1 Agent data protection

| Data | Sensitivity | Who sees it | How it is protected |
|---|---|---|---|
| Customer identity, phone number, single transactions | personal | nobody in Jogan | **never ingested**: Jogan needs agent-hour totals only (§2) |
| Agent id | pseudonymous | analyst, approver | upay's own id, or a key whose mapping table stays inside upay |
| Agent balances and hourly flows | commercially confidential | analyst, approver | TLS in transit; database behind RLS; no export endpoint; the LLM sees one visit's evidence only, and only with a provider approved by upay |
| Agent location | confidential | analyst, approver, the runner of that territory | shown at shop level only where a runner needs it; never sent to the LLM |
| Anomaly flags | sensitive (can stigmatise an agent) | approver and analyst only | advisory, never an accusation; no automatic action |
| Decisions and audit log | accountability record | analyst, approver, auditors | append-only; kept for the pilot and its review |

Retention: hourly aggregates for 13 months, so the forecast sees each Eid once (ASSUMPTION); decisions and the audit log for as long as upay's record rules require. At the end of the pilot, the data is deleted or returned, as in [`09-deployment.md`](09-deployment.md).

### 10.2 Model monitoring

Checked every morning before the plan is published, from data the system already holds. A breach does not stop the queue; it adds a banner for the approver and a ticket for the model owner.

| Signal | How it is measured | Alert when (ASSUMPTION) | What happens |
|---|---|---|---|
| Calibration | realised coverage of the 90% interval over the last 14 days, per setting and size class | below 85% in any group | more visits of that group go to manual review; recalibrate (CQR) on recent days |
| Accuracy | Brier score of the stock-out chance against the `empirical` forecast, last 14 days | worse than `empirical` for 7 days running | model owner reviews; fall back to the safety-stock rule for the affected group |
| Data feed | share of agent-hours missing or late | above 5% in a territory | that territory's visits go to manual review (the data-gap guardrail) |
| Input drift | share of agents outside the training range (guardrail) | twice the training rate | retrain on recent history |
| Human override | share of visits rejected, per approver and territory | above 30% over a week | review the reasons with the approvers; it means the plan does not fit the field |
| Anomaly flag | flags per 1,000 agent-days | twice the evaluation rate | check for a data problem before reading any flag |
| Optimizer | fallbacks to the greedy round, solve time | any fallback; a morning over 60 s | the plan is still valid (greedy); ticket to the model owner |
| Outcome | failed requests per 1,000 against control territories | worse than control for 2 weeks | go/no-go review (`07-product-readiness` §5) |

### 10.3 Override and escalation

1. **Reject.** An approver rejects any visit; the decision and its audit row are written together. A rejection is final for that visit.
2. **Add.** A visit Jogan did not propose is not blocked: the distributor's call path stays open under every policy, and the runner serves it as today.
3. **Escalate.** An approver passes a visit to the operations manager, outside Jogan, when the agent is flagged and the amount is large, when the evidence and the field disagree, or when an approver's rejections pass the monitoring threshold.
4. **Suspected fraud.** Never handled in Jogan: the anomaly flag only asks a person to look, and a concern goes to upay's compliance team through its existing channel.
5. **Kill switch.** Any territory can go back to the status quo (fixed rounds plus calls) at once: the queue simply stops being used and runners keep their rounds. Jogan never moves money, so stopping it is safe at any hour.

Not built yet: the monitoring job and its banner, an "escalate" button with its audit row, and a runner role (§9).

The AI tools used to build Jogan are disclosed in [`08-ai-usage.md`](08-ai-usage.md).
