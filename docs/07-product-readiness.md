# Product readiness

Is Jogan more than a demo? This page answers the guideline's product questions ([`00-requirements-checklist.md`](00-requirements-checklist.md) §G): the problem, whether AI beats simple rules, the action after each prediction, the benefit, how to validate with real data, and how it fits a real workflow. Where the answer is "not yet", it says so.

## 1. A frequent, economically meaningful problem

Every MFS cash-out needs physical cash at an agent's shop and every cash-in needs e-float. Agents rebalance through distributor runners on a fixed rhythm plus calls (D-016), demand peaks on paydays, remittance days and before both Eids, and a customer may cash out a large amount in one go. When a side runs dry the customer is turned away, the agent loses commission and the brand loses trust. The scale and the peaks, with sources, are in [`01-logic-chain.md`](01-logic-chain.md) §3. The problem recurs every day at every agent; the cost concentrates on a few days a year that are known in advance.

Agents also refill themselves at a nearby bank, but only in bank transaction hours (10:00 to 15:00) on Sunday to Thursday, leaving the shop while they go. Jogan's environment models that trip for every agent under every policy ([`05-evaluation.md`](05-evaluation.md) §2).

**How big.** Bangladesh Bank publishes what agents served each month, not how many customers were turned away, so the size is a range over turned-away rates. Step 0 below measures the real rate.

<!-- numbers:sizing -->
Agents served 52.0 crore cash-out and cash-in requests worth ৳89,672 crore in July 2026, across all MFS providers, about 280 a month per agent (1,856,190 agents, February 2025). Bangladesh Bank does not publish how many were turned away for lack of cash or e-float, so each row is a rate, not a measurement:

| Share of requests turned away | Customers turned away, July 2026 | Value turned away (৳) | Agent commission lost (৳) | Customers turned away, May 2026 (Eid-ul-Azha) | Value turned away (৳) |
|---|---|---|---|---|---|
| 1% | 52.5 lakh | 906 crore | 3.7 crore | 58.1 lakh | 1,028 crore |
| 2% | 106.1 lakh | 1,830 crore | 7.5 crore | 117.4 lakh | 2,077 crore |
| 5% | 273.7 lakh | 4,720 crore | 19.4 crore | 302.9 lakh | 5,356 crore |

1 lakh = 100,000; 1 crore = 10 million. Commission at ৳4.10 per ৳1,000 (`configs/ops/costs.yaml`). Assumptions: turned-away rates are a sensitivity, not a measurement; a turned-away request has the month's average size; published totals are served requests only (turned away = served * r / (1 - r)); a customer who comes back later is not netted out. Sources: Bangladesh Bank MFS table 9 and agent count (`configs/calibration/bb_mfs_2026.yaml`). Written by `make sizing` to `artifacts/sizing.json`.
<!-- /numbers -->

## 2. AI beats simple rules (on simulated data)

Jogan was compared with the status quo and two stronger rules on the same simulated customers, over seeds never used in development ([`05-evaluation.md`](05-evaluation.md)):

<!-- numbers:hypotheses -->
|  | Hypothesis | Result |
|---|---|---|
| H1 | cheaper at every value, or break-even reported with an interval | at ৳20: Fixed round (status quo): Jogan cheaper at every value of a lost customer; Safety stock: Jogan cheaper at every value of a lost customer; Threshold: Jogan cheaper at every value of a lost customer |
| H2 | fewer failed requests than the best baseline without more runner km | holds: against Threshold, -2.25 (-2.69 to -1.81) lost per 1,000 and -1,654 (-1,883 to -1,425) km |
| H3 | interval coverage within ±5 points of nominal, overall and by group | fails: 45 cells outside ±5 points |
| H4 | no agent group significantly worse served than under the best baseline | fails: worse in `setting=urban`, `territory=DHK` |
<!-- /numbers -->

The win over the best rule is real but modest, and not for every group. The honest claim is: a calibrated forecast plus an optimizer turns away fewer customers than the best simple rule **with less runner driving**, in a world built from public facts; whether the gap holds on upay's agents is what the pilot below must show.

## 3. A clear action after each prediction

The guideline's "good project test", answered by one row of the queue:

| Question | What the approver sees |
|---|---|
| What happened? | The agent's chance of running out of cash or e-float in the next 24 hours (labelled Prediction), the forecast drain against the current balance |
| Why does it matter? | The top drivers, the need on the side at risk, the value of a visit, and any manual-review reason |
| What should upay do next? | Send runner R to this agent this morning, bringing the agent's cash to the target level. One click to approve or reject; the decision is logged |

## 4. Measurable benefit

The same metrics work in simulation and in a pilot:

- **primary:** failed customer requests per 1,000;
- **cost:** runner km and visits, runner time, lost agent commission, idle money;
- **trade-off:** the break-even value of a lost customer, so upay can decide with its own value of a customer instead of ours;
- **fairness:** the same metrics per territory, setting and agent size.

On real data, e-float stock-outs are exact (the balance is in upay's ledger); cash stock-outs are not logged when a customer simply leaves, so the pilot needs a proxy (section 5).

## 5. Validation with real data

**Data needed** (agent-level only; no customer data, [`02-data-assumptions.md`](02-data-assumptions.md) §11):

| Jogan input | Real source |
|---|---|
| Agent master (id, territory, type, location) | upay agent master data |
| Hourly cash-out and cash-in counts and amounts | transaction ledger, aggregated per agent-hour |
| E-float balance | ledger (exact) |
| Physical cash | an estimate from the ledger, runner visits and agent declarations |
| Runner visits and rosters | distributor logs |
| Calendar | public holidays plus upay's campaign calendar |

**Plan:**

0. **Measure the problem first** (two weeks, before any model runs): the pre-evaluation asked for the real frequency and financial impact of liquidity failures, and this step produces them from data upay already holds:
   - **frequency:** agent-hours with cash or e-float below one typical hour of outflow, per agent per month, by territory, setting and size, and on paydays and before Eid;
   - **turned-away requests:** the demand expected in those hours (from the same agent's unconstrained hours) minus what was served, the censoring correction Jogan's forecast already uses (D-020);
   - **financial impact:** turned-away value times the commission rate (agent), the same plus upay's fee share (upay), and runner km and hours per rebalance (distributor);
   - **agents' own bank trips:** e-float bought or sold outside runner visits (how a bank trip shows in the ledger is an ASSUMPTION to confirm with upay), by hour and weekday, and the requests turned away while the bank was closed;
   - **check:** a "could not serve" tally kept by hand for two weeks at a sample of agents, to calibrate the estimate.
1. **Backtest on history.** Run the forecast on at least a year of upay's agent-hour aggregates (so training holds both Eids) with the same time-based splits and the same leakage test; report coverage per group and Brier score, as in the model card. A coverage failure stops here.
2. **Shadow mode** (a few weeks, a few territories). Jogan plans every morning; nobody acts on it; distributors work as usual. Compare Jogan's predicted stock-outs with what happened (e-float exactly, cash through the proxy), and Jogan's proposed visits with the actual rounds.
3. **Randomised pilot by distributor territory.** Pair similar territories; one of each pair uses Jogan's queue with an approver, the other keeps its rounds. Measure the primary and cost metrics per territory, with the agent-group breakdown.
4. **Go or no-go**, on thresholds agreed with upay before the pilot starts (we do not set them), including "no group worse served".

In the guideline's post-hackathon pathway (§13), these steps follow the technical and business reviews: step 1 is the controlled validation, step 2 the POC, step 3 the pilot assessment and step 4 the next decision.

**Proxy for cash stock-outs.** A one-tap "could not serve" button in the agent app, failed cash-out attempts where the system records them, and customer complaints. Each undercounts; using the same proxy in both arms keeps the comparison fair.

## 6. Fits a real workflow

A distributor's morning, with Jogan:

| Time | Who | What |
|---|---|---|
| overnight | system | the previous day's agent-hour aggregates arrive; anomaly flags are scored |
| before the shift | Jogan | forecasts, plans visits per territory, writes the queue (`publish_plan`) |
| before the shift | approver (distributor or upay operations) | reviews the queue, flagged visits first; approves or rejects; notes for flagged ones |
| shift | runners | approved route with the amount at each stop (the runner app is not built) |
| during the day | agents | call as today; calls are served by runners with room left, as under every policy |
| after the day | analyst | impact and audit pages; outcomes feed tomorrow's forecast |

The prototype's screens cover the analyst and the approver; the runner's route view and an SMS to agents (logic chain §1) are not built.

## 7. Privacy, fairness, explainability and security

Covered in [`06-responsible-ai.md`](06-responsible-ai.md): synthetic data only and agent-level aggregates by design, a human decision on every visit with an append-only audit log, drivers and bilingual explanations, labels on every output, fairness by group with its failures reported, and layered security tested in CI and on the live site.

## 8. Integration and operations

- **Integration:** the forecast reads one documented table, storage sits behind the `Store` protocol, and sign-in maps to two roles ([`03-architecture.md`](03-architecture.md) §10). The bundle built at deploy time becomes a morning job.
- **Scale:** planning is one program per territory; the stress check runs a world many times the demo's size within seconds per morning ([`03-architecture.md`](03-architecture.md) §9). Serving a national day on the map would need tiles or clustering.
- **Retraining and monitoring:** retrain on a schedule with the censoring correction; track interval coverage and Brier score per group every week; alert when coverage leaves its band; record the config hash of every plan (already done).
- **Running cost:** the prototype runs on free tiers plus Cloud Run's scale-to-zero; a production run is one batch job a morning plus a small API.

## 9. What is missing before a pilot

| Gap | Why it matters | Next step |
|---|---|---|
| Real data | every result is simulated | measure the problem, then backtest on upay history (section 5, steps 0 and 1) |
| The agent's own bank trip as a planned action | the planner sends a runner or nothing; it never suggests "refill at the bank before it closes" to an agent near a bank | add the bank trip as a cheaper option in the dispatch program, priced by the agent's time away from the shop (D-031) |
| Equity in the optimizer | H4 fails for urban agents | service floor per group (D-002 #9) |
| Runner's bag and arrival time in the program | a visit may not fit what the runner carries, or arrive too late | add both constraints (D-021) |
| Shared cash drawer | cash is less certain than modelled | model cash as uncertain (D-002 #11) |
| Runner app and agent SMS | approved visits must reach the field | a route view and a templated SMS |
| Anomaly flag on structuring | it misses most split cash-outs | transaction-level features and labelled cases |
| LLM provider | the free tier's terms suit simulated data only | an approved provider, or templates only |
