# Evaluation

Does Jogan turn away fewer customers than simple rules, at what cost, for whom, and where does it lose? Every result on this page is written by `make docs` from `artifacts/metrics.json`, which `make eval` produces; nothing is typed by hand. The forecast's own scores are in [`04-model-card.md`](04-model-card.md).

## 1. Method

**World.** The `full` simulated world (`configs/sim/full.yaml`) on the real 2026 calendar, generated afresh for each evaluation seed. The seeds (`configs/eval/base.yaml`) were never used while building or tuning anything (D-010); every design choice was made on development seeds 0–3 (D-021).

**Same start for every policy.** For each seed the status quo runs from the start of the world (5 January); the forecaster is trained on its observed log; then at the start of the test window every policy takes over from the same balances, runners and history (`Deployed`, D-021). Customers are replayed one by one against the exact balance at that moment (event replay, D-017).

**Common random numbers.** Customer demand, retries, bank-trip delays and data gaps are drawn from the world seed and the customer or agent, never from the policy. Two policies on one seed meet the same customers, so their difference is the policy, not noise.

**Policies compared** (`configs/ops/policies.yaml`, D-016, D-019). Every policy plans one runner round at 08:00 and answers agents' calls with the runners left:

| Policy | Rule |
|---|---|
| Fixed round (status quo) | Each runner visits a fixed cycle of agents, plus calls: how 96% of Bangladeshi agents rebalanced in the Agent Network Accelerator survey (D-016) |
| Threshold | Visit agents whose cover on either side is below a fixed number of typical days |
| Safety stock | Visit agents below mean + k·sd of their recent peak 24-hour drain, k from a 95% service level |
| **Jogan** | Forecast → newsvendor need → value of a visit → one mixed-integer program per territory (D-021) |
| Oracle | Sees every future customer; plans the same round. Not deployable: it marks how much room is left |

**Metrics.** Primary: failed customer requests per 1,000 requests. Secondary: lost requests, runner km and visits, and the **known cost**, built only from sourced inputs (D-019):

- lost agent commission, at the published agent commission per ৳1,000;
- runner fuel, from the 2026 official petrol price and a 100 cc motorcycle's rated mileage;
- runner time while driving or at a stop, from a 2026 distribution-officer job ad (the salary range gives low, middle and high);
- idle liquidity, at Bangladesh Bank's policy rate.

**A lost customer's value is unknown, so it is not priced.** It enters only as an operator setting of Jogan (the newsvendor's underage cost), swept over the values in `configs/eval/base.yaml`. For every pair of policies the evaluation reports the **break-even value**: the value of one lost request at which the two cost the same, with Fieller's interval.

**Statistics.** Each metric is computed over the test window per seed; differences are paired by seed with a t-interval at the level in `configs/eval/base.yaml`. A difference whose interval contains zero is reported as "no significant difference".

**Hypotheses** were written before the evaluation in [`01-logic-chain.md`](01-logic-chain.md) §6 (H1–H4).

## 2. Headline

<!-- numbers:headline -->
| Policy | Lost requests per 1,000 | Lost requests | Runner km | Known cost (৳) |
|---|---|---|---|---|
| Fixed round (status quo) | 118.4 (115.9 to 120.9) | 19,376 (18,935 to 19,818) | 41,861 (41,689 to 42,034) | 713,522 (708,066 to 718,979) |
| Threshold | 111.1 (108.4 to 113.8) | 18,188 (17,707 to 18,668) | 41,848 (41,426 to 42,270) | 699,550 (693,828 to 705,273) |
| Safety stock | 111.5 (108.7 to 114.3) | 18,246 (17,771 to 18,720) | 41,481 (41,123 to 41,839) | 706,256 (699,882 to 712,631) |
| **Jogan** | 108.9 (106.1 to 111.6) | 17,820 (17,338 to 18,300) | 40,194 (39,776 to 40,612) | 693,700 (687,341 to 700,058) |
| Oracle (perfect foresight, not deployable) | 89.0 (86.4 to 91.5) | 14,565 (14,094 to 15,035) | 43,496 (43,126 to 43,867) | 658,728 (652,808 to 664,648) |

Jogan minus each baseline, paired by seed (negative means Jogan is lower):

| Baseline | Lost per 1,000 | Runner km | Known cost (৳) | Break-even |
|---|---|---|---|---|
| Fixed round (status quo) | -9.51 (-10.07 to -8.96) | -1,667 (-2,001 to -1,334) | -19,823 (-22,859 to -16,787) | Jogan cheaper at every value of a lost customer |
| Threshold | -2.25 (-2.69 to -1.81) | -1,654 (-1,883 to -1,425) | -5,851 (-7,463 to -4,238) | Jogan cheaper at every value of a lost customer |
| Safety stock | -2.61 (-3.15 to -2.06) | -1,287 (-1,426 to -1,148) | -12,557 (-14,071 to -11,043) | Jogan cheaper at every value of a lost customer |

In the Eid-ul-Azha window (2026-05-18 to 2026-05-31), Jogan minus the best baseline (Threshold): -1.94 (-2.43 to -1.44) lost requests per 1,000.

Known cost is runner time and fuel, lost commission and idle liquidity at the middle runner salary (`configs/ops/costs.yaml`); Jogan runs at a lost-customer value of ৳20. The oracle sees the future and only marks how much room is left.

_Evaluation on simulated data: profile `full`, 10 seeds (1000 to 1009), test window 2026-05-07 to 2026-06-03 (28 days), mean and 95% interval over seeds. Source: `artifacts/metrics.json`, written by `make eval`._
<!-- /numbers -->

Where the known cost goes, per policy:

<!-- numbers:costs -->
| Policy | Lost commission | Runner time | Runner fuel | Idle liquidity | Known cost | Runner visits |
|---|---|---|---|---|---|---|
| Fixed round (status quo) | 305,496 | 252,330 | 121,796 | 33,900 | 713,522 | 7,028 |
| Threshold | 296,152 | 248,404 | 121,550 | 33,444 | 699,550 | 6,746 |
| Safety stock | 297,183 | 255,233 | 120,432 | 33,409 | 706,256 | 7,446 |
| **Jogan** | 292,346 | 251,617 | 116,757 | 32,980 | 693,700 | 7,541 |

Means over seeds in ৳, middle runner salary, test window.
<!-- /numbers -->

**How often agents run dry, what it is worth, and agents' own bank trips.** The simulator knows every customer turned away and what they asked for, and every time an agent went to a bank to refill. An agent goes when one side falls below a share of a typical day, after a delay, and only in bank hours on bank-open days (`configs/ops/env.yaml`, [`02-data-assumptions.md`](02-data-assumptions.md) §6). The trip happens under every policy; runners come on top of it.

<!-- numbers:problem -->
| Test window | Fixed round (status quo) | Threshold | Safety stock | **Jogan** |
|---|---|---|---|---|
| Requests turned away per 1,000 | 118.4 (115.9 to 120.9) | 111.1 (108.4 to 113.8) | 111.5 (108.7 to 114.3) | 108.9 (106.1 to 111.6) |
| Requests turned away | 19,376 (18,935 to 19,818) | 18,188 (17,707 to 18,668) | 18,246 (17,771 to 18,720) | 17,820 (17,338 to 18,300) |
| Agent-days with a customer turned away | 45.6% | 44.3% | 44.1% | 43.5% |
| Value turned away (৳) | 74,511,295 | 72,232,235 | 72,483,650 | 71,303,785 |
| of it cash-out (৳) | 37,666,940 | 35,760,725 | 36,084,595 | 34,633,215 |
| Agent commission lost (৳) | 305,496 | 296,152 | 297,183 | 292,346 |
| Agents' own bank trips | 1,134 (1,109 to 1,160) | 932 (905 to 959) | 930 (901 to 958) | 922 (894 to 950) |

Agents' own bank trips, Jogan minus each baseline, paired by seed: Fixed round (status quo) -212.6 (-232.1 to -193.1); Threshold -9.9 (-22.2 to 2.4); Safety stock -7.8 (-27.9 to 12.3). An agent goes to a bank only on a bank-open day and in bank hours (`configs/ops/env.yaml`), so a drawer that runs dry on a Friday, a Saturday, a holiday or after the bank closes stays dry until a runner comes.

_Evaluation on simulated data: profile `full`, 10 seeds (1000 to 1009), test window 2026-05-07 to 2026-06-03 (28 days), mean and 95% interval over seeds. Source: `artifacts/metrics.json`, written by `make eval`._
<!-- /numbers -->

**Business KPIs** (D-033). The same runs in the units an MFS business reports, per 1,000 agents a month:

<!-- numbers:business -->
| KPI (Jogan minus baseline; negative is a saving) | vs status quo, 28-day test window | vs status quo, per 1,000 agents a month | vs Threshold, per 1,000 agents a month |
|---|---|---|---|
| Failed transactions | -1,557 (-1,644 to -1,469) | -2,780 (-2,936 to -2,623) | -657 (-789 to -526) |
| Transaction value turned away (৳) | -3,207,510 (-3,523,530 to -2,891,490) | -5,727,696 (-6,292,018 to -5,163,375) | -1,657,946 (-2,049,604 to -1,266,289) |
| of it cash-out (৳) | -3,033,725 (-3,176,928 to -2,890,522) | -5,417,366 (-5,673,087 to -5,161,646) | -2,013,411 (-2,225,843 to -1,800,979) |
| Agent commission lost (৳) | -13,151 (-14,446 to -11,855) | -23,484 (-25,797 to -21,170) | -6,798 (-8,403 to -5,192) |
| Runner km | -1,667 (-2,001 to -1,334) | -2,977 (-3,572 to -2,382) | -2,953 (-3,362 to -2,544) |
| Runner cost, time and fuel (৳) | -5,752 (-7,967 to -3,537) | -10,271 (-14,227 to -6,316) | -2,822 (-5,080 to -564) |
| Agents' own bank trips | -213 (-232 to -193) | -380 (-414 to -345) | -18 (-40 to 4) |
| Known cost (৳) | -19,823 (-22,859 to -16,787) | -35,398 (-40,820 to -29,976) | -10,448 (-13,327 to -7,568) |

**Return on investment.** Against the status quo, Jogan's known cost is lower by ৳35,398 per 1,000 agents a month (95% interval ৳29,976 to ৳40,820), before any value is put on a customer kept. So it pays for itself while running it (cloud, an analyst and an approver's time) costs less than that; every customer kept is extra. The running cost was not measured.

Paired by seed; scaled from the simulated network of 600 agents to 1,000 agents and 30 days. Known cost is runner time and fuel, lost commission and idle liquidity at the middle runner salary. Transaction value turned away is what customers asked for and did not get; upay's own fee on it is not public and is not priced.

_Evaluation on simulated data: profile `full`, 10 seeds (1000 to 1009), test window 2026-05-07 to 2026-06-03 (28 days), mean and 95% interval over seeds. Source: `artifacts/metrics.json`, written by `make eval`._
<!-- /numbers -->

**Bangladesh's calendar** (D-035). Per day type in the test window, how many visits each policy sends and how many requests it turns away. Jogan has no rule for any of these days:

<!-- numbers:events -->
| Day type | Days | Runner visits a day: status quo / Jogan | Jogan minus status quo, visits a day | Turned away per 1,000: status quo / Jogan | Jogan minus status quo, per 1,000 | Jogan minus Threshold, per 1,000 |
|---|---|---|---|---|---|---|
| Eid day and the two after | 3 | 203.1 / 172.5 | -30.5 (-32.7 to -28.4) | 124.1 / 116.5 | -7.6 (-10.1 to -5.1) | -0.5 (-2.7 to 1.8) |
| 10 days before Eid (bonuses, remittances) | 10 | 266.5 / 286.6 | 20.1 (18.0 to 22.3) | 166.4 / 155.7 | -10.7 (-11.3 to -10.1) | -2.2 (-2.8 to -1.6) |
| 1st to 10th of the month (wages, remittances) | 7 | 247.9 / 278.8 | 30.9 (28.5 to 33.3) | 73.1 / 64.0 | -9.1 (-10.1 to -8.0) | -2.0 (-3.0 to -0.9) |
| Other bank holiday | 1 | 188.0 / 267.3 | 79.3 (73.3 to 85.3) | 80.4 / 78.1 | -2.3 (-5.9 to 1.3) | 0.3 (-2.7 to 3.3) |
| Friday or Saturday (banks shut) | 2 | 230.4 / 278.1 | 47.6 (42.9 to 52.4) | 87.3 / 73.9 | -13.4 (-16.1 to -10.8) | -4.7 (-6.5 to -2.9) |
| Ordinary day | 5 | 274.0 / 276.4 | 2.4 (-0.2 to 4.9) | 69.4 / 62.0 | -7.3 (-8.4 to -6.3) | -2.7 (-4.2 to -1.2) |

Each test-window day gets the first type that applies, in the order of the rows. Jogan has no rule for any of these days: the forecast reads calendar features (day of the month, days to Eid, holidays) and recent flows, and the visits follow the forecast and the stock-out chance. Paired by seed; negative means Jogan is lower.

_Evaluation on simulated data: profile `full`, 10 seeds (1000 to 1009), test window 2026-05-07 to 2026-06-03 (28 days), mean and 95% interval over seeds. Source: `artifacts/metrics.json`, written by `make eval`._
<!-- /numbers -->

**Midday check** (D-036). A variant of Jogan that re-forecasts at 14:00 from the live balances and sends the first free runner to agents likely to run dry before close, for surprise rushes:

<!-- numbers:midday -->
| Test window | Midday check minus Jogan | Midday check minus status quo |
|---|---|---|
| Requests turned away per 1,000 | -0.12 (-0.41 to 0.17) | -9.63 (-10.39 to -8.88) |
| Runner visits | 70 (52 to 87) |  |
| Runner km | 514 (403 to 625) | -1,153 (-1,461 to -846) |
| Known cost (৳) | 4,104 (2,966 to 5,244) | -15,718 (-18,570 to -12,867) |

Midday visits sent per seed over the run: 138 (132 to 144). The setting (`configs/plan/midday.yaml`) was not tuned. Paired by seed; negative means the midday check is lower. In the Eid-ul-Azha window, midday check minus Jogan: -0.32 (-0.88 to 0.24) lost requests per 1,000.

_Evaluation on simulated data: profile `full`, 10 seeds (1000 to 1009), test window 2026-05-07 to 2026-06-03 (28 days), mean and 95% interval over seeds. Source: `artifacts/metrics.json`, written by `make eval`._
<!-- /numbers -->

## 3. The lost-customer value and the salary

Jogan at each setting of the lost-customer value, and its total cost against each baseline when lost requests are priced at that same value:

<!-- numbers:by_value -->
| Lost-customer value | Jogan lost per 1,000 | Jogan runner km | Total cost, Jogan minus Fixed round (status quo) (৳) | Total cost, Jogan minus Threshold (৳) | Total cost, Jogan minus Safety stock (৳) |
|---|---|---|---|---|---|
| ৳0 | 109.8 (107.1 to 112.5) | 39,664 | -22,618 (-25,216 to -20,020) | -8,646 (-10,446 to -6,846) | -15,352 (-16,372 to -14,332) |
| ৳5 | 109.0 (106.3 to 111.8) | 39,824 | -30,622 (-33,836 to -27,408) | -10,707 (-11,748 to -9,667) | -17,703 (-19,687 to -15,719) |
| ৳20 | 108.9 (106.1 to 111.6) | 40,194 | -50,955 (-55,085 to -46,824) | -13,213 (-15,931 to -10,494) | -21,077 (-23,632 to -18,521) |
| ৳50 | 108.4 (105.6 to 111.3) | 40,363 | -99,825 (-109,667 to -89,983) | -26,428 (-33,125 to -19,730) | -36,029 (-44,265 to -27,793) |
| ৳100 | 108.4 (105.7 to 111.1) | 40,687 | -179,175 (-191,164 to -167,187) | -46,353 (-59,088 to -33,618) | -58,849 (-73,444 to -44,254) |
| ৳200 | 108.3 (105.6 to 111.0) | 41,182 | -342,883 (-362,730 to -323,036) | -91,210 (-107,439 to -74,982) | -109,497 (-129,635 to -89,358) |

Total cost = known cost + the value times lost requests, middle salary, test window. The same value is used to plan (Jogan's setting) and to price the outcome.
<!-- /numbers -->

Break-even against each baseline:

<!-- numbers:break_even -->
| Jogan's setting | Fixed round (status quo) | Threshold | Safety stock |
|---|---|---|---|
| ৳0 | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer |
| ৳5 | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer |
| ৳20 | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer |
| ৳50 | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer |
| ৳100 | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer | Jogan cheaper at every value of a lost customer |
| ৳200 | Jogan cheaper at every value of a lost customer | Jogan cheaper above ৳3.21 per lost request (0.41 to 6.62) | Jogan cheaper at every value of a lost customer |

Middle runner salary; the low and high salary are named only where their verdict differs.
<!-- /numbers -->

Reading: the higher the setting, the more km Jogan drives to lose fewer customers. "Cheaper above ৳x" means Jogan costs more in known cost but loses fewer customers, so it pays off as soon as one lost request is worth more than ৳x to the operator.

## 4. Hypotheses

<!-- numbers:hypotheses -->
|  | Hypothesis | Result |
|---|---|---|
| H1 | cheaper at every value, or break-even reported with an interval | at ৳20: Fixed round (status quo): Jogan cheaper at every value of a lost customer; Safety stock: Jogan cheaper at every value of a lost customer; Threshold: Jogan cheaper at every value of a lost customer |
| H2 | fewer failed requests than the best baseline without more runner km | holds: against Threshold, -2.25 (-2.69 to -1.81) lost per 1,000 and -1,654 (-1,883 to -1,425) km |
| H3 | interval coverage within ±5 points of nominal, overall and by group | fails: 45 cells outside ±5 points |
| H4 | no agent group significantly worse served than under the best baseline | fails: worse in `setting=urban`, `territory=DHK` |
<!-- /numbers -->

## 5. Fairness

Lost requests per 1,000 by agent group, Jogan against the best baseline over all agents:

<!-- numbers:fairness -->
| Group | Value | Jogan lost per 1,000 | Threshold lost per 1,000 | Jogan minus best | Verdict |
|---|---|---|---|---|---|
| `setting` | `peri_urban` | 75.5 (72.9 to 78.1) | 77.4 (74.9 to 80.0) | -1.95 (-2.27 to -1.63) | lower |
| `setting` | `rural` | 156.9 (151.8 to 162.0) | 161.9 (157.0 to 166.8) | -5.03 (-6.50 to -3.56) | lower |
| `setting` | `urban` | 121.8 (116.5 to 127.1) | 120.8 (115.5 to 126.1) | 1.03 (0.01 to 2.06) | higher |
| `size_class` | `large` | 64.9 (59.4 to 70.4) | 68.6 (62.9 to 74.3) | -3.68 (-4.50 to -2.86) | lower |
| `size_class` | `medium` | 96.6 (93.6 to 99.7) | 98.3 (95.2 to 101.3) | -1.63 (-2.42 to -0.85) | lower |
| `size_class` | `small` | 180.7 (176.5 to 184.9) | 182.0 (177.9 to 186.2) | -1.33 (-2.84 to 0.18) | no significant difference |
| `territory` | `CUM` | 80.7 (74.5 to 86.9) | 83.7 (77.8 to 89.5) | -2.95 (-4.21 to -1.70) | lower |
| `territory` | `DHK` | 121.8 (116.5 to 127.1) | 120.8 (115.5 to 126.1) | 1.03 (0.01 to 2.06) | higher |
| `territory` | `GZP` | 68.7 (63.2 to 74.1) | 68.9 (63.8 to 74.1) | -0.28 (-1.23 to 0.67) | no significant difference |
| `territory` | `KUR` | 156.4 (150.2 to 162.5) | 160.6 (155.2 to 165.9) | -4.20 (-6.04 to -2.36) | lower |
| `territory` | `RNG` | 157.9 (150.8 to 165.1) | 163.8 (155.8 to 171.8) | -5.88 (-7.93 to -3.83) | lower |
| `territory` | `SYL` | 77.9 (73.9 to 81.8) | 80.4 (76.3 to 84.5) | -2.52 (-3.45 to -1.59) | lower |
<!-- /numbers -->

Reading: Jogan helps rural agents, large agents and most territories most. It is **worse than the threshold rule for the urban agents** (in this world all of them are in DHK), and not significantly better for small agents and GZP. A likely reason, not tested: in a dense city a runner reaches many agents in a short ride, so a rule that visits everyone below a cover threshold already does well there, while Jogan's program spends runner time where a visit is worth more. The equity weight or service floor planned in D-002 #9 was not built; it is the first thing to add.

## 6. Eid-ul-Azha

The test window holds Eid-ul-Azha, the hardest days of the year for agent cash (D-013):

<!-- numbers:eid -->
| Policy | Lost per 1,000 | Runner km | Jogan minus this policy, lost per 1,000 |
|---|---|---|---|
| Fixed round (status quo) | 157.7 (153.9 to 161.5) | 20,114 | -9.93 (-10.53 to -9.34) |
| Threshold | 149.7 (145.7 to 153.7) | 20,246 | -1.94 (-2.43 to -1.44) |
| Safety stock | 150.4 (146.7 to 154.1) | 20,109 | -2.65 (-3.37 to -1.93) |
| **Jogan** | 147.8 (143.9 to 151.7) | 19,614 |  |
| Oracle (perfect foresight, not deployable) | 128.8 (125.0 to 132.7) | 20,940 |  |

Eid-ul-Azha window: 2026-05-18 to 2026-05-31 (14 days).
<!-- /numbers -->

Jogan keeps its lead on these days, but every policy, the oracle included, loses far more requests than on other days. On Eid day itself no runner is on duty (roster), so no policy can visit.

## 7. Ablations

Which parts of Jogan matter, on the same seeds:

<!-- numbers:ablations -->
| Jogan minus … | Lost per 1,000 | Runner km | Known cost (৳) |
|---|---|---|---|
| Greedy round instead of the MILP (same forecast and levels) | -0.72 (-1.22 to -0.22) | -1,340 (-1,499 to -1,181) | -7,993 (-9,161 to -6,824) |
| Two-sided newsvendor split instead of the typical split | -2.72 (-3.22 to -2.22) | -105 (-302 to 92) | -6,662 (-8,027 to -5,297) |
<!-- /numbers -->

Reading: the program beats the greedy round with the same forecast, on service and on km. The typical split of liquidity between cash and e-float beats the two-sided newsvendor optimum, which is why Jogan uses it (D-021). The censoring strategies (impute, ignore, drop) were compared on development seed 0 only (D-020).

## 8. Where Jogan does not win

<!-- numbers:limits -->
- **Some groups are served worse than by the best baseline (Threshold).** Lost requests per 1,000, Jogan minus Threshold: `urban` and `DHK` (the same agents) 1.03 (0.01 to 2.06).
- **Forecast intervals are off their nominal coverage by more than 5 points in 45 cells** (by side, horizon, interval and agent group), 4 of them over all agents.
- **The oracle is still ahead:** Jogan minus the oracle, 19.9 (19.1 to 20.7) lost requests per 1,000.
- **The anomaly flag is weak on structuring:** split cash-outs found in 3 of 9 injected windows; precision 4.3% against a base rate of 0.08%.
- **62 group-level comparisons** (across lost-customer values and baselines) show no significant win or a baseline as good or better (`does_not_win` in `artifacts/metrics.json`).
<!-- /numbers -->

Every group-level case at Jogan's setting:

<!-- numbers:does_not_win -->
| Baseline | Agent group | Jogan minus baseline, lost per 1,000 | Why no win |
|---|---|---|---|
| Fixed round (status quo) | `setting` = `urban` | -1.73 (-3.50 to 0.05) | no significant difference |
| Fixed round (status quo) | `territory` = `DHK` | -1.73 (-3.50 to 0.05) | no significant difference |
| Threshold | `setting` = `urban` | 1.03 (0.01 to 2.06) | baseline as good or better |
| Threshold | `size_class` = `small` | -1.33 (-2.84 to 0.18) | no significant difference |
| Threshold | `territory` = `DHK` | 1.03 (0.01 to 2.06) | baseline as good or better |
| Threshold | `territory` = `GZP` | -0.28 (-1.23 to 0.67) | no significant difference |
| Safety stock | `setting` = `urban` | 0.69 (-0.19 to 1.56) | baseline as good or better |
| Safety stock | `size_class` = `small` | 1.17 (-0.23 to 2.57) | baseline as good or better |
| Safety stock | `territory` = `DHK` | 0.69 (-0.19 to 1.56) | baseline as good or better |
| Safety stock | `territory` = `GZP` | -0.80 (-1.78 to 0.18) | no significant difference |

At Jogan's setting of ৳20. Over every setting: 31 no significant difference, 31 baseline as good or better (62 in all).
<!-- /numbers -->

**Costs left unpriced** (no source found, D-019): motorcycle wear and depreciation, the runner's phone, and the agent's own time on bank trips. Each one understates a cost; the first two grow with runner km, which Jogan lowers at its default setting.

**Not modelled in the policy** (D-021): the runner's bag (cash a runner can carry) inside the program, the hours between the 08:00 forecast and the runner's arrival, and a call that rescues an agent who was not visited.

**Simulated world.** The comparison is fair between policies, because they meet the same customers, but the size of every effect depends on the simulator's assumptions ([`02-data-assumptions.md`](02-data-assumptions.md)). The validation plan with real data is in [`07-product-readiness.md`](07-product-readiness.md).

## 9. Reproducing

```bash
make setup
make eval     # the configured seeds → artifacts/metrics.json
make impact   # → web/lib/impact.json
make docs     # → the numbers on this page and in the README
make check    # tests fail if a copy is stale
```

<!-- numbers:runtime -->
`make eval` took 26 min for 10 seeds (`meta.runtime_s`). `make stress` took 101 s at a peak of 1,779 MB on 13th Gen Intel(R) Core(TM) i7-13650HX (20 threads, 15 GB RAM).
<!-- /numbers -->

`artifacts/metrics.json` records the config hashes and library versions it was made with (`meta`); the same commit and configs give the same numbers. Development runs (`make eval ARGS="--seeds 0 1 2 3"`) write `artifacts/eval/metrics_dev.json` instead and never overwrite the final file.
