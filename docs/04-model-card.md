# Model card

The machine-learning parts of Jogan: the **peak-drain forecast** (with its calibration and the stock-out chance read from it), the **drivers** that explain it, and the **anomaly flag**. The newsvendor rule and the dispatch program are business rules and optimization, not learned models; they are described in [`03-architecture.md`](03-architecture.md) §3 and evaluated in [`05-evaluation.md`](05-evaluation.md). Every result below is written by `make docs` from `artifacts/metrics.json`.

## 1. Peak-drain forecast

### Model details

| | |
|---|---|
| What it predicts | Quantiles of an agent's **peak cumulative drain** of cash and of e-float over the next 6, 12 and 24 hours: the money the agent must hold now to serve every customer in the window without a top-up (D-002 #3) |
| Algorithm | LightGBM 4.7.0 quantile regression, one booster per horizon × side × level (levels 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99), trained on `log1p` of the target |
| Calibration | Asymmetric conformalized quantile regression (Romano, Patterson and Candès 2019, Theorem 2): each level gets its own shift from the calibration split, in log space, per setting × size class (pooled for groups under 200 calibration rows); crossed levels are sorted |
| Derived output | P(stock-out within H hours) = P(peak drain > balance now), interpolated from the calibrated quantiles |
| Settings | `configs/forecast/base.yaml`: 150 rounds, learning rate 0.1, 31 leaves, at least 50 rows per leaf, 63 bins, deterministic. Every number is tagged `ASSUMPTION`; none was tuned on an evaluation seed |
| Code | `jogan/forecast/` (`panel`, `features`, `targets`, `model`, `backtest`) |
| Version | the `forecast` config hash in `artifacts/metrics.json` and in every recommendation's trace |
| Owner | Team Jogan (student prototype, AI Dev Fest 2026) |

### Intended use

- **Use:** rank agents by stock-out risk each morning and size the top-up for the side at risk, as input to the newsvendor rule and the dispatch program, with a human approving every visit.
- **Users:** a distributor's or upay's liquidity analyst and an approver (D-001).
- **Not for:** judging an agent's creditworthiness, behaviour or honesty; any automatic action on an agent or customer; any decision without the guardrails and human approval. Not validated on real data (see §5).

### Training and evaluation data

- **Synthetic only** (`jogan/sim`, [`02-data-assumptions.md`](02-data-assumptions.md)): a seeded agent-based world on the real 2026 Bangladesh calendar, calibrated to Bangladesh Bank's agent cash-in/cash-out aggregates, with injected patterns (hour of day, weekday, payday, remittance days, hat days, Ramadan and both Eids, disruptions, anomalous agents).
- **What the model sees:** only the status quo's **observed log** (`obs/hourly.parquet`): served cash-outs and cash-ins, e-float, a cash estimate and `available_at` per agent-hour, with lost and late records. Never the ground truth.
- **Features (41):** agent master data, calendar, recent served flows (3, 24, 168 h), and per horizon the agent's 28-day hour-of-day profile, the same window 1 and 7 days earlier and the median and 90th percentile of the last 28 same-hour windows. Liquidity enters only as the total; the cash/e-float split records when the old policy's runner came, and would tie the model to it (D-020).
- **No leakage:** a record is used only after it arrived; a test perturbs every record that arrives after the origin and checks that no feature changes.
- **Time-based splits** (`full` profile): train 5 Jan → 22 Apr, calibration 23 Apr → 6 May, test 7 May → 3 Jun 2026. The test window holds Eid-ul-Azha, partly out of distribution on purpose. The final evaluation uses seeds 1000–1009, never touched during development (D-010).
- **Censored demand.** During a stock-out the customer leaves and nothing is logged, so served flows understate demand exactly where it matters. Labels are built from **estimated demand**: a censored hour is lifted to served + expected flow (the conditional mean of an exponential tail), with the expected flow learned from clean hours only (D-020). Measured against the simulator's ground truth:

<!-- numbers:censoring -->
| Side (24 h peak drain) | Bias, served flows | Bias, estimated (used) | Bias with lost requests, served | Bias with lost requests, estimated | Stock-out flag precision / recall |
|---|---|---|---|---|---|
| Cash | -26.7% | -3.4% | -46.7% | -14.5% | 31% / 89% |
| E-float | -32.0% | -4.0% | -53.4% | -24.6% | 25% / 87% |

Bias is the mean label minus true demand, relative to true demand, on the test window. Strategy in use: `impute`.
<!-- /numbers -->

### Metrics and results

Scored on the test window of every evaluation seed, against **true** demand, next to two simple forecasts: `empirical` (the agent's quantiles of its last 28 same-hour windows, the idea behind the safety-stock policy) and `naive_cqr` (the same window a week earlier, with additive conformal shifts).

<!-- numbers:forecast -->
| Side | Horizon | Pinball loss, ৳: Empirical / Naive + CQR / LightGBM / LightGBM + CQR | 90% interval: coverage (mean width) | Brier: Empirical / LightGBM + CQR | Stock-out base rate |
|---|---|---|---|---|---|
| Cash | 6 h | 654 / 765 / 585 / 582 | 90.3% (৳5,920) | 0.089 / 0.084 | 14.1% |
| Cash | 12 h | 856 / 959 / 744 / 740 | 89.7% (৳7,291) | 0.105 / 0.097 | 18.0% |
| Cash | 24 h | 1,404 / 1,406 / 1,216 / 1,207 | 87.7% (৳11,400) | 0.157 / 0.147 | 29.2% |
| E-float | 6 h | 654 / 776 / 598 / 595 | 91.0% (৳6,615) | 0.071 / 0.069 | 10.0% |
| E-float | 12 h | 846 / 953 / 749 / 744 | 90.2% (৳8,239) | 0.088 / 0.085 | 13.4% |
| E-float | 24 h | 1,307 / 1,317 / 1,119 / 1,112 | 87.5% (৳12,278) | 0.135 / 0.127 | 21.5% |

Pinball loss is averaged over the eight quantile levels and scored against true demand (lower is better). Coverage is of the calibrated LightGBM interval against true demand (nominal 90%). Brier scores the stock-out chance for the no-top-up event (lower is better).

_Evaluation on simulated data: profile `full`, 10 seeds (1000 to 1009), test window 2026-05-07 to 2026-06-03 (28 days), mean and 95% interval over seeds. Source: `artifacts/metrics.json`, written by `make eval`._
<!-- /numbers -->

### Calibration

H3 of the logic chain asks for coverage within ±5 points of nominal, overall and in every agent group. It **fails**:

<!-- numbers:calibration -->
| 24-hour forecast | Cash 50% | Cash 80% | Cash 90% | E-float 50% | E-float 80% | E-float 90% |
|---|---|---|---|---|---|---|
| All agents, test window | 45.0% | 79.0% | 87.7% | 50.7% | 81.6% | 87.5% |
| Eid-ul-Azha days | 39.3% | 72.3% | 82.7% | 49.4% | 80.4% | 86.6% |
| Other days | 51.2% | 86.3% | 93.2% | 52.1% | 82.8% | 88.5% |
| `setting` = `peri_urban` | 42.9% | 79.4% | 88.5% | 51.0% | 84.2% | 89.2% |
| `setting` = `rural` | 38.1% | 74.2% | 83.7% | 54.5% | 84.2% | 88.7% |
| `setting` = `urban` | 65.1% | 87.6% | 93.4% | 42.2% | 68.4% | 80.2% |
| `size_class` = `large` | 50.5% | 79.7% | 89.5% | 53.6% | 82.8% | 90.1% |
| `size_class` = `medium` | 47.1% | 79.4% | 88.5% | 51.4% | 84.1% | 90.2% |
| `size_class` = `small` | 41.9% | 78.5% | 86.6% | 49.4% | 79.5% | 84.8% |

Cells off nominal by more than 5 points (every side, horizon, interval and group): 45. Over all agents: cash 6 h 80% at 85.2%; e-float 6 h 50% at 66.2%; e-float 6 h 80% at 85.9%; e-float 12 h 50% at 60.9%.
<!-- /numbers -->

Reading: the misses go both ways. Over all agents, the short-horizon intervals are too wide (coverage above nominal): safe, but visits larger than needed. At 24 hours, coverage falls on the Eid-ul-Azha days, which the training window holds only once (Eid-ul-Fitr), and in some groups; one conformal shift per group cannot follow errors that change shape on those days. The planner reads the upper levels (its critical ratios are high), so under-coverage there means visits that come too late or are too small.

### Fairness of the forecast

Coverage by setting and size class is in the table above; the effect on service (lost requests per group under Jogan against the best baseline) is in [`05-evaluation.md`](05-evaluation.md) §5.

## 2. Drivers (explanations)

- **Method:** exact TreeSHAP from LightGBM's built-in `pred_contrib`, on the 24-hour booster at the 0.9 quantile of the side at risk (D-023). Because the model is trained on `log1p`, a feature's effect is shown as `exp(φ) − 1`, relative to the model's average prediction. The conformal shift is one constant per group, so it is not a driver.
- **Shown:** the top 3 effects of at least 5% (`configs/explain/base.yaml`), as diverging bars with English and Bangla labels for every feature (a test checks every feature has both).
- **Checked:** a test checks that the contributions add up to the raw prediction.
- **Limits:** drivers explain the model, not the world. A day-of-month driver raising the forecast means the model learned a payday pattern from the simulated history, not that payday caused this agent's demand.

## 3. Guardrails (manual review)

Rules, not a model, on top of the forecast (`jogan/explain/guardrails.py`, thresholds in `configs/explain/base.yaml`). A visit goes to manual review when:

- **out of range:** one of the agent's own amounts lies outside the training minimum and maximum (trees cannot extrapolate);
- **wide interval:** the 0.9 quantile is more than 4 times the median;
- **data gap:** fewer than 75% of the agent's last 24 hourly records had arrived at the plan hour;
- **short history:** fewer than 7 past same-hour windows behind the features;
- **anomaly:** the advisory anomaly flag fired.

Approving a flagged visit needs a written note, enforced in the database function and audited.

## 4. Anomaly flag

| | |
|---|---|
| What it flags | An agent-day with unusual **excess** activity: transactions outside opening hours, volume against the agent's own hour-of-day profile, mean cash-out size against the agent's own, the busiest hour's cash-outs against their usual count |
| Normalisation | The last three are divided by the territory's median that day, so a payday or an Eid that lifts everyone is not unusual |
| Algorithm | Isolation Forest per setting (scikit-learn 1.9.1, 200 trees, 256 samples), flag above the 99.5% quantile of the setting's training scores; plus two rules: any night transaction, and any feature above its setting's training maximum |
| Data | The observed log only; each morning scores the previous day from the records that have arrived |
| Use | **Advisory.** It never acts: it puts the agent's visit under manual review and lists the agent for a person to look at |
| Not for | Accusing an agent of fraud, blocking an account, or reporting to anyone without a human investigation |

Results on the test window of every evaluation seed, against the injected patterns ([`02-data-assumptions.md`](02-data-assumptions.md) §8):

<!-- numbers:anomaly -->
| Injected pattern | Windows | With a flag |
|---|---|---|
| Night activity | 6 | 6 |
| Unexplained spike | 6 | 3 |
| Split cash-outs | 9 | 1 |

168,000 test agent-days; 1,219 flagged (0.7%), 48 of them on injected anomalies: precision 3.9% against a base rate of 0.08%. Precision at 5 / 10 / 20 per seed, averaged: 0.30 / 0.36 / 0.22. Injected windows with at least one flag: 10 of 21.
<!-- /numbers -->

Reading: night activity is easy, spikes half the time, and **structuring (split cash-outs just under round figures) is mostly missed**: a burst of mid-size cash-outs barely moves day-level features. A real deployment would need transaction-level features (amounts just under round figures, bursts within minutes) and real labelled cases before this flag could be trusted for anything but triage.

## 5. Limitations and risks

- **Simulated data only.** The patterns the model finds are the patterns the simulator put in. Every result here is evidence that the method works on a world built from public facts and assumptions, not that it works on upay's agents.
- **Hourly resolution.** The peak drain is computed from hourly totals, so a dip inside an hour is not seen. upay has the transaction stream; the simulator logs hourly aggregates.
- **Coverage fails H3** on the Eid days and in some groups (above).
- **Cash is assumed observed through an estimate.** A shared cash drawer across MFS brands would make cash much less certain (D-002 #11, not built).
- **Distribution shift.** A new policy changes the data the next model learns from: once Jogan's visits shape the balances, the stock-outs in the log are no longer the status quo's. Retraining should keep the censoring correction and be checked against a held-out period every time.
- **Feedback on the anomaly flag.** A flag that sends an agent to manual review should not lower that agent's service; flagged visits are still recommended, only reviewed.

## 6. How to validate on real data

Shadow mode first (Jogan recommends, nobody acts on it, outcomes are compared), then a randomised pilot by distributor territory. Details in [`07-product-readiness.md`](07-product-readiness.md).
