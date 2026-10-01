# Logic chain

The one-page argument for Jogan, in the format of the Student Guideline §10. External facts carry a source. Everything Jogan itself will show is a target here, not a result; results come only from `make eval` (`artifacts/metrics.json`).

## Problem statement

> **For** upay's liquidity-operations analysts and distributor managers, rebalancing of agents' physical cash and e-float on **fixed rounds and calls**, not on a forecast, **causes** agent stock-outs that turn customers away, costing transactions, agent commission and trust, most of all before Eid.
> **We will build** Jogan, an AI copilot that **uses** agents' transaction and balance histories **to** forecast each agent's liquidity pressure for the next 6–24 hours and recommend human-approved runner dispatches.
> **Success is measured by** failed customer requests, known cost and the break-even value of a lost customer versus fixed-round (status quo), threshold and safety-stock policies in a seeded operations simulation.

## 1. User

| Role | What they need from Jogan |
|---|---|
| **Liquidity-operations analyst** (upay or distributor), the primary user | Which agents will run out of cash or e-float, when, and what to do about it |
| **Approver** (operations or distributor manager) | A short queue of proposed dispatches with reasons, to approve, edit or reject |
| **Runner / DSO** (field staff) | An approved route with the amount to bring or collect at each stop |
| **Agent** | A templated SMS that a runner is coming, and when |
| **Customer** (beneficiary) | Cash-out and cash-in that work when needed |

## 2. Problem and baseline

An agent needs **physical cash** for cash-out and **e-float** for cash-in. A cash-out drains cash and adds e-float; a cash-in does the opposite. When either side runs out, the request fails: the customer leaves, the agent loses the commission, and trust suffers.

**Baseline (status quo).** In Bangladesh, 96% of agents rebalance at their shop through visits by the distributor's runners, "usually at a predetermined time", and some distributors also rebalance on demand. Agents deny a median of zero transactions a day for lack of liquidity, but 34% deny at least one a day ([ANA Bangladesh survey, Helix Institute / MicroSave, 2014](https://www.microsave.net/wp-content/uploads/2014/11/Agent-Network-Accelerator-Bangladesh-Country-Report-2014.pdf)). So today's rebalancing works on a fixed rhythm plus calls, not on a forecast. Refill amounts follow simple rules of thumb (`ASSUMPTION` to validate with upay).

Jogan is compared against three baselines, all simulated on the same customers, all answering agents' calls the same way:
1. **fixed round** (status quo): each runner visits its agents on a fixed cycle
2. **static threshold**: min/max levels per agent
3. **safety stock**: historical mean + kσ of the peak drain

The **oracle** (perfect foresight) is an upper bound for the forecast, not a rival.

## 3. Why now

**Scale.** Bangladesh Bank reports **258,684,285** MFS accounts in July 2026 ([BB, MFS account information](https://www.bb.org.bd/econdata/fin_digitalfstat/tab8.pdf)). In the same month, agents served **308,646,376** cash-out transactions worth **Tk 419,415.1 million** ([BB, MFS transaction statistics](https://www.bb.org.bd/econdata/fin_digitalfstat/tab9.pdf)). The network had **1,856,190** agents in February 2025 ([BB MFS data](https://www.bb.org.bd/en/index.php/financialactivity/mfsdata)).

**Peaks are predictable but large.** Agent cash-out was **Tk 401,864.6 million in April 2026** and **Tk 508,903.2 million in May 2026**, the month of Eid-ul-Azha (28 May 2026). Same Bangladesh Bank table.

Peaks like this come from a few recurring causes:
- **festivals**: Eid-ul-Fitr on 21 March 2026 and Eid-ul-Azha on 28 May 2026
- **paydays**: wages must be paid within seven working days after the wage period, under Labour Act 2006 s.123 ([The Daily Star](https://www.thedailystar.net/law-our-rights/news/the-entitlements-the-workers-relating-wages-1890601))
- **remittance inflows**: Dhaka, Chattogram, Cumilla and Sylhet are the top receiving districts ([The Daily Star, BB data for March 2026](https://online91.thedailystar.net/business/economy/news/dhaka-division-receives-half-march-remittances-4178071))

These are exactly the patterns a model can learn and a fixed rule cannot.

**Hard customer limits.** A customer may cash out up to Tk 30,000 a day at agent points (BB circular of 27 March 2025, as reported by [BSS](https://www.bssnews.net/business/258749)). A single large request can therefore empty a small agent's drawer.

## 4. Solution

Jogan is a copilot for the analyst. Its pipeline:

`forecast → stock-out risk → recommended dispatch → explanation → human approval → audit log`

Interfaces:
- **Web app:** a live network map with a time control, an agent detail view, a recommendation queue and an impact page, in Bangla and English.
- **API:** stateless with respect to simulated time, so it can later sit behind upay's real systems.

## 5. Role of AI

AI is material: without the forecast and the optimizer, Jogan would just be a threshold rule.

| Purpose (guideline wording) | Component | Decides on its own? |
|---|---|---|
| **Prediction** | LightGBM quantile models of the **peak cumulative drain** of cash and e-float over 6/12/24 h, calibrated with conformalized quantile regression (CQR) | No |
| **Recommendation and optimization** | Newsvendor target level from config costs; mixed-integer runner assignment (HiGHS) with a greedy baseline | Proposes only; a human approves |
| **Detection** | Isolation Forest per agent setting plus two rules (advisory anomaly flag, D-023) | Never |
| **Generation** | Bilingual explanations from TreeSHAP drivers via templates, with an optional Gemini narration of the same structured evidence | Never |

Business rules (costs, caps, guardrails) live in config files, separate from the ML. A low-confidence or out-of-distribution case goes to manual review.

## 6. Impact: metric and targets

**Primary metric:** failed customer requests per 1,000 requests (stock-outs).

**Secondary metrics:**
- lost agent commission (simulated ৳, at the sourced Tk 4.10 per 1,000)
- known cost (simulated ৳): lost commission + runner fuel + runner time + idle liquidity, each priced from sourced inputs ([`02-data-assumptions.md`](02-data-assumptions.md) §6)
- break-even value of a lost customer against each baseline: that value is unknown, so it is not priced; instead the value at which Jogan and the baseline cost the same is reported
- runner trips, km and busy hours
- idle cash and e-float
- failure rate by agent group (fairness)

**Targets.** These are hypotheses tested by `make eval`, not results:
- **H1:** Against each of the three baselines, Jogan is cheaper at every lost-customer value (lower known cost and fewer lost requests), or the break-even value is reported with its paired 95% interval across seeds.
- **H2:** Jogan has fewer failed requests than the best of the three baselines, without more runner km.
- **H3:** Prediction intervals are calibrated: empirical coverage within ±5 percentage points of nominal on the held-out window, overall and per agent group.
- **H4:** No agent group is systematically worse served under Jogan than under the best of the three baselines.

Where a hypothesis fails, the evaluation says so. The report has a section on **where Jogan does not win**: every baseline, agent group, period (for example the Eid-ul-Azha test window) or cost setting in which a baseline does as well or better.

## 7. Data

Synthetic only, from a seeded agent-based simulator (see [`02-data-assumptions.md`](02-data-assumptions.md)):
- **Calendar:** the real 2026 Bangladesh calendar.
- **Geography:** district centroids from an MIT-licensed dataset.
- **Injected patterns:** hour of day, weekday, payday, remittance, hat days, Eid, disruptions and anomalous agents.
- **Calibration:** ticket sizes and cash-in/cash-out mix follow Bangladesh Bank aggregates.

No real personal data and no upay production data are used. The final test window is never used for training or tuning.

## 8. Validation

**Offline:**
- pinball loss and coverage vs. nominal for every quantile level
- Brier score and reliability of stock-out probabilities
- time-based backtest against simple statistical forecasts

**Simulated operations:**
- the same customer demand is replayed under every policy (common random numbers)
- several seeds, with paired confidence intervals
- ablations (Jogan forecast with greedy dispatch) and the oracle upper bound

**Business experiment with controlled upay data (proposal):**
1. Shadow mode first: Jogan recommends, people act as usual, and recommendations are compared with outcomes.
2. Then a randomised pilot by distributor territory.
3. Success measures: failed-request complaints, runner trips, agent commission.

## 9. Scale: what changes with real data

- **Data source.** A `DataSource` adapter replaces the simulator. It reads the agent master, hourly ledger aggregates, e-float balances, runner visit logs and runner rosters. Customer-level personal data is never needed.
- **Optimization.** It decomposes by distributor territory, so it grows linearly with the number of territories.
- **Retraining and monitoring.** Retraining is scheduled, and coverage is tracked over time.
- **Physical cash.** Real data only gives an *estimate* of physical cash (e-float is exact), so cash uncertainty becomes part of the forecast.

## "Good project test" (guideline)

- **What happened?** Agent A's cash will probably run out around 14:00 tomorrow, two days before Eid.
- **Why is it important?** An expected ৳X of cash-out requests would fail. The UI shows the computed value with its uncertainty.
- **What should upay do next?** Send runner R with ৳Y by 12:30. One click to approve; the decision is logged.
