# On-site log · 7 October 2026

New requirements from the pre-evaluation, in the order we worked on them. Each entry gives the feedback, what changed, the commits and the checks. Numbers live in the generated blocks of the linked docs, not here.

## R1 · Problem relevance

**Feedback (three judges):**

1. Define the problem and the proposed solution more clearly.
2. Quantify the real frequency and financial impact of liquidity-related transaction failures with operational data.
3. Look at how shopkeepers get money from nearby banks on their own.

**What changed:**

- **Clearer problem and solution:** the README overview now leads with the problem in one line, who loses what (customer, agent, distributor and upay), the two ways agents refill today, and the solution in three steps (predict, plan, approve). Report §1.1 and §1.3 follow the same structure.
- **National size of the problem from official data:** `make sizing` (`jogan/eval/sizing.py`, `configs/sizing/base.yaml`) writes `artifacts/sizing.json`. It takes Bangladesh Bank's monthly agent cash-out and cash-in totals, the agent count and the agent commission rate, and gives the requests, taka and commission turned away for each turned-away rate. Bangladesh Bank does not publish that rate, so the rates are labelled ASSUMPTION and shown as a range. The new `sizing` block is in the README, `07-product-readiness` §1 and report §1.1.
- **Frequency and value in the simulated network:** `make eval` now also aggregates what each seed already recorded: the value of the requests turned away (all and cash-out), the share of agent-days with a customer turned away, and agents' own bank trips, plus Jogan minus each baseline in bank trips. The simulation, its configs and every earlier number are unchanged. The new `problem` block is in the README, `05-evaluation` §2 and report §5.1.
- **Agents' own bank trips:** described as the second refill channel (bank hours 10:00 to 15:00, closed Friday, Saturday and holidays, with a source) in the README and report §1.3, and counted per policy in the `problem` block.
- **Real operational data:** step 0 of the validation plan (`07-product-readiness` §5, report §8.2) measures the real frequency, turned-away value and bank trips on upay's own logs before any model runs, with a manual tally to check the estimate. We hold no upay data, so this is a plan, not a result.

**Commits:** see `git log` for 7 Oct.

## R2 · AI/ML depth

**Feedback (three judges):**

1. Use a deeper AI/ML model in the next version, and explain clearly how the model works, how it is trained and how well it is expected to perform.
2. Improve urban agents, forecast calibration and anomaly detection; benchmark against existing operations with real data.
3. The split cash-out (structuring) detector did not work well and needs fixing.

**What changed:**

- **Split cash-outs:** a new anomaly feature, `hour_tk`: the busiest hour's cash-out taka against the usual taka in that hour. Splitting a large cash-out adds a few requests to an hour but many times its usual taka, which the old count-only `burst` feature missed. Designed and checked on development seeds 0–3 only. A second idea, a rule for the pattern repeating on two of three days, raised false alarms and was dropped.
- **Why most splits stay invisible:** `make eval` now counts the injected split cash-outs that were served. Most were turned away because the drawer was short, and a turned-away request is never logged, so no detector on the served log can see it. The model card says so, and the next version moves the detector to upay's transaction-level ledger.
- **How the model works:** a new README section covers what the forecast predicts, the six training steps (data, censoring-corrected labels, 41 leak-free features, 48 LightGBM quantile boosters, CQR calibration, a test on unseen seeds), and the generated performance table against two simple forecasts.
- **Next version:** model card §7 plans a global deep probabilistic forecaster (DeepAR or TFT) with CQR on top, adaptive conformal calibration for Eid and the weak groups, urban features and a service floor, decision-focused training, and a transaction-level split detector. Each must beat the current model on the same splits and seeds.

## R3 · Business and customer impact

**Feedback (three judges):**

1. The business impact is moderate without a proper AI/ML model.
2. Translate the simulation into business KPIs: fewer failed transactions, extra transaction value and revenue, lower runner cost, and ROI.
3. The 1,600 km saved is real fuel and money, but in busy city areas the basic rules still did slightly better.

**What changed:**

- **Business KPIs** (`jogan/eval/business.py`, written by `make eval` into `artifacts/metrics.json`): Jogan minus the status quo and minus the best baseline, paired by seed, for failed transactions, transaction value turned away, agent commission, runner km, runner cost, agents' own bank trips and known cost. Each is also scaled to 1,000 agents and 30 days.
- **ROI:** the known-cost saving per 1,000 agents a month against the status quo is the most Jogan's running cost can be and still pay for itself, before any value is put on a customer kept. We did not measure the running cost, and upay's own fee is not public, so neither is priced.
- **Where it shows:** a `business` block in the README (Results), `05-evaluation` §2 and report §8.1, and a "Business KPIs" panel on the impact page, with both windows.
- **Urban agents:** still the one place a simple rule does better. It stays in "where Jogan does not win", and the fix (urban features and a service floor per group) is in model card §7 and `07-product-readiness` §9.

## R4 · Prototype quality

**Feedback (three judges):**

1. There is no proper functional prototype; build a more complete one.
2. Every result is simulated; next, run a controlled pilot on real agent transaction, liquidity and runner-route data.
3. The map, buttons and review screens work well together; build a simple phone screen for the motorcycle riders on the road.

**What changed:**

- **Runner route** (`/runner`, a new page in the web app, English and Bangla): the phone screen for a runner on the road. Pick a runner and a day to see that runner's approved visits in a suggested order (nearest next stop from the territory centre), with "hand over ৳X cash" or "collect ৳X cash" at each shop, the cash level to leave, the stock-out chance, the distance from the last stop, and a directions button. Totals at the top: stops, cash to load at the hub, cash to collect, distance. Visits still waiting for an approver are counted, not shown. It reads the existing API only, so nothing new can change a decision. The page is in the sidebar and the phone tab bar.
- **The prototype is easy to find and try:** the README now opens with a two-minute walkthrough of the live app (demo approver → network → queue → runner route → agent page → audit and impact), and `make run` does the same locally.
- **Pilot on real data:** the validation plan (`07-product-readiness` §5) already runs measure → backtest → shadow mode → randomised pilot by territory. Step 0, added in R1, measures the problem first; runner-route data (distributor logs) is in its data list.

## R5 · Innovation

**Feedback (three judges):**

1. Training a dedicated AI/ML model would be a significant innovation.
2. Show how the solution responds to Bangladesh-specific events: salary dates, remittances, holidays and Eid.
3. Checking the peak drain instead of the end-of-day balance is clever; add a way for neighbouring shops to share extra cash directly.

**What changed:**

- **A dedicated model, made visible:** Jogan trains its own models: 48 LightGBM quantile boosters on 41 leak-free features, calibrated with CQR. The README section from R2 now explains them step by step.
- **Response to Bangladesh's calendar** (`make eval` → `events` in `artifacts/metrics.json`): every test-window day is typed as Eid, the 10 days before Eid, the 1st to 10th of the month (wages and remittances), another bank holiday, a Friday or Saturday, or an ordinary day. Per type, it reports runner visits a day and requests turned away per 1,000 for the status quo and Jogan, with paired differences. Jogan has no rule for any of these days; the forecast reads the calendar and the visits follow. The new `events` block is in the README and `05-evaluation`.
- **Peer swap idea** (agent page, English and Bangla): for an agent at risk on one side, it lists agents within 3 km in the same territory who are at risk on the other side. Such an agent holds what this one lacks, so the two could swap cash for e-float without a runner. The panel is labelled an idea and is not used in the plan or the evaluation; whether agent-to-agent swaps are allowed is for upay to confirm.

## R6 · Scalability and integration

**Feedback (three judges):**

1. Demonstrate the model's accuracy and reliability before large-scale work.
2. Show the architecture, data requirements, optimization time and operational feasibility at large-network scale, with integration into the transaction, balance, distributor and runner systems.
3. 10,000 shops in under two minutes is fast; now handle surprise cash rushes in the middle of the day.

**What changed:**

- **Midday check** (`JoganMidday` in `jogan/plan/policy.py`, `configs/plan/midday.yaml`): at 14:00 the forecaster runs again from the live balances. It is trained at every origin from 08:00 to 20:00, so this is in range. Agents whose stock-out chance within 6 hours reaches the threshold get the first free runner. `make eval` runs it as its own variant, `jogan_midday@20`, next to Jogan; the main plan, its config hash and the served demo are unchanged. Its setting was not tuned. **Result:** no significant change in requests turned away, with more runner km and a higher known cost, so the main plan keeps calls for midday rushes; the numbers are in the `midday` block of the README and `05-evaluation`.
- **Scale and integration in the README:** a table of the systems Jogan reads from and writes to, how often, and the seam in the code for each; the morning as a job; and links to the 10,000-agent stress result, the data requirements and the architecture.
- **Accuracy before scale:** the forecast's scores on unseen seeds against true demand, and its calibration, are in the README (R2) and the model card.

## R7 · Responsible AI and security

**Feedback (three judges):**

1. There is no clear mention of data security or how user data is protected; address security, privacy and responsible AI.
2. Human approval, bilingual explanations and the append-only audit log are strong; define access control, sensitive agent-data protection, model monitoring and override and escalation procedures.
3. Approval of every trip and the unchangeable audit log are top-tier practice; being honest about weaknesses shows integrity.

**What changed:**

- **README:** the responsible-AI section now has four clear parts: data security and privacy (no personal data by design, HTTPS, RLS, Secret Manager, keyless deploys, what the LLM may see), access control, human oversight with override and escalation, and monitoring and transparency.
- **`06-responsible-ai`:** an access-control matrix (every action against anonymous, analyst, approver and the server, and what enforces it); a new §10 for operating a pilot: agent-data classification and protection with retention; eight model-monitoring signals with thresholds and actions; and five override and escalation steps ending in a kill switch back to fixed rounds. Report §7 summarises it.
- **Honest scope:** what is enforced today is named with its component; the monitoring job, an escalate button and a runner role are listed as not built.

## Polish and follow-up (after R7)

- **Web app motion and charts** (D-038): page transitions, bars that grow from the baseline, an animated route sketch on the runner screen, the calendar-response charts on the impact page (with a table view), a business-KPI table that fits a phone, and a human-oversight panel on the audit log (decisions, approvals, rejections, notes, approvers and the override rate against its review threshold).
- **Urban agents** (R2, R3): a per-setting value factor was tried on development seeds and did not move urban losses, so it was reverted and recorded (D-038).
