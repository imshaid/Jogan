# Data assumptions

Jogan runs on **synthetic data only**. This page lists every assumption behind the simulated world, so judges and teammates can see what is grounded in an outside source and what is our choice.

**Labels used on this page:**
- **SOURCE**: a verified outside fact, with a link
- **DERIVED**: computed from sources; the formula is shown, and the simulator code recomputes it
- **ASSUMPTION**: our choice, made for realism; not verified, and covered by sensitivity analysis where it matters

The parameter values live in `configs/`: `sim/base.yaml` (shared), `sim/<profile>.yaml`, `calendar/`, `geo/` and `calibration/`. This page explains them. The generator is `jogan/sim/`.

## 1. Principles

- **No personal or production data.** No real personal data and no upay production data, ever.
- **Seeded.** The same config and seed always produce identical data, and a test checks this.
- **Clearly synthetic.**
  - Agents have generated IDs such as `DHK-017`.
  - Locations are random points around district centroids.
  - No real shop names are used.
- **Known patterns are injected on purpose.** Ground-truth labels (anomalies, true demand) are kept away from model inputs.
- **Development and final-evaluation seeds never overlap.** Development uses seeds 0–9 and the final evaluation uses seeds 1000–1009, so the method cannot be tuned to the worlds it is scored on.
- **The test window is untouched.** It is never used for training, calibration or tuning.

## 2. Calendar

The simulator uses the real 2026 Bangladesh calendar (**SOURCE**):
- Official 2026 holiday list: [The Daily Star](https://tds-images.thedailystar.net/news/bangladesh/news/govt-announces-official-list-public-holidays-2026-4031596)
- Eid-ul-Fitr date: [BSS](https://www.bssnews.net/news/370394)
- Eid-ul-Azha date: [Ittefaq](https://en.ittefaq.com.bd/16594/bangladesh-to-celebrate-eid-ul-azha-on-may-28)

| Date (2026) | Event |
|---|---|
| 4 Feb | Shab-e-Barat |
| 19 Feb – 20 Mar | Ramadan (**DERIVED**: Eid-ul-Fitr on 21 Mar after a full 30-day Ramadan) |
| 21 Feb | Shaheed Day |
| 17 Mar | Shab-e-Qadr |
| 19–23 Mar | Eid-ul-Fitr holidays; Eid on Sat 21 Mar |
| 26 Mar | Independence Day |
| 14 Apr | Pahela Baishakh |
| 1 May | May Day and Buddha Purnima |
| 25–31 May | Eid-ul-Azha holidays; Eid on Thu 28 May |
| 26 Jun | Ashura |
| 5 Aug, 26 Aug, 4 Sep | Mass Uprising Day, Eid-e-Miladunnabi, Janmashtami |
| 20–21 Oct | Durga Puja |
| 16 Dec, 25 Dec | Victory Day, Christmas |

**Weekly holidays.** Banks close on Friday and Saturday (**SOURCE**: [The Financial Express](https://thefinancialexpress.com.bd/views/opinions/banking-on-holidays)). Agent shops open every day (**ASSUMPTION**).

**Profiles** (`configs/sim/`). `make data PROFILE=<name> SEED=<n>` writes one world to `data/<name>/seed<n>/`.

| Profile | Agents | Territories | Window | Days | Purpose |
|---|---|---|---|---|---|
| `tiny` | 40 | 2 (GZP, RNG) | 1 Mar → 28 Mar | 28 | CI tests, seconds; payday, hat days, Ramadan and Eid-ul-Fitr in one month |
| `dev` | 150 | 3 (DHK, CUM, KUR) | 20 Feb → 20 Apr | 60 | development |
| `full` | 600 | 6 | 5 Jan → 3 Jun | 150 | final evaluation and demo |
| `stress` | 10,000 | 6 hubs × 10 distributor areas | 18 May → 31 May | 14 | inference and optimizer timing only |

**Splits for `full`** (time-based):

| Split | Dates | Days | Contains |
|---|---|---|---|
| Train | 5 Jan → 22 Apr | 108 | Eid-ul-Fitr |
| Calibration | 23 Apr → 6 May | 14 | |
| Test | 7 May → 3 Jun | 28 | Eid-ul-Azha |

The model sees one Eid in training and is tested on the other. This is an honest check of whether festival effects generalise. Eid-ul-Azha also brings extra cash needs from cattle markets (**ASSUMPTION**), so part of the test is out of distribution by design, and the results report it as such.

## 3. Geography and network

There are six distributor territories. Each hub sits at a district centroid (**SOURCE**: [nuhil/bangladesh-geocode](https://github.com/nuhil/bangladesh-geocode), MIT license, which also gives the Bangla names).

| Code | District | Area type | Why this place |
|---|---|---|---|
| DHK | Dhaka (ঢাকা) | urban core | Capital and top remittance-receiving district (**SOURCE**, BB data for March 2026 via [The Daily Star](https://online91.thedailystar.net/business/economy/news/dhaka-division-receives-half-march-remittances-4178071)) |
| GZP | Gazipur (গাজীপুর) | peri-urban industrial | Garment-factory cluster (**ASSUMPTION**); payday cash-out peaks |
| CUM | Cumilla (কুমিল্লা) | remittance, semi-urban | Top-4 remittance district (**SOURCE**, same as above) |
| SYL | Sylhet (সিলেট) | remittance, mixed | Top-4 remittance district (**SOURCE**, same as above) |
| RNG | Rangpur (রংপুর) | rural agriculture | Weekly market (hat) economy (**ASSUMPTION**) |
| KUR | Kurigram (কুড়িগ্রাম) | remote rural, flood-prone | Long runner trips and flood disruptions (**ASSUMPTION**) |

**Placement and travel** (all **ASSUMPTION**):
- **Agent locations:** uniform in a disc around the hub. Radius is 6 km for urban, 12 km for peri-urban and 20 km for rural territories.
- **Road distance:** straight-line (haversine) distance × 1.3 (urban and peri-urban) or 1.4 (rural).
- **Market clusters:** in hat territories, agents are split into 4 angular sectors around the hub; each sector has 1–2 fixed market weekdays.
- **Runner speed:** 12 km/h in Dhaka traffic, 18 km/h peri-urban, 22 km/h rural. Halved on disruption days.

## 4. Agents

**Volume.** Expected daily cash-in + cash-out transactions per agent follow a log-normal distribution (**ASSUMPTION**). It is anchored on the national average of about **9 per agent per day** (**DERIVED**):
- 520,025,003 agent cash-in + cash-out transactions in July 2026 ([BB table 9](https://www.bb.org.bd/econdata/fin_digitalfstat/tab9.pdf))
- ÷ 31 days
- ÷ 1,856,190 agents in February 2025 ([BB MFS data](https://www.bb.org.bd/en/index.php/financialactivity/mfsdata))
- The two figures come from different months, so this is an order of magnitude only.

The overall level is **calibrated**: the expected reference network (every territory, equal agent counts) averages the DERIVED volume per agent-day in July 2026. Agent spread: log-normal with σ = 0.6; urban ×1.3, peri-urban ×1.0, rural ×0.8 (**ASSUMPTION**).

Size classes by quantile (**ASSUMPTION**): small is the bottom 50%, medium the next 35%, large the top 15%.

**Opening hours** (**ASSUMPTION**):
- urban 09:00–22:00, peri-urban 08:00–21:00, rural 08:00–20:00
- Eid day 14:00–20:00

**Liquidity holdings** (**ASSUMPTION**). Starting cash and e-float are about 1–1.5 days of each agent's expected gross outflow on that side.

**Shared cash drawer** (**ASSUMPTION**, optional feature). Many shops serve several MFS brands from one drawer. Physical cash then moves for reasons upay cannot see. upay knows e-float exactly but physical cash only approximately.

## 5. Demand model

Each agent has two hourly arrival processes, **cash-out (CO)** and **cash-in (CI)**. Counts are Poisson. Gamma multipliers at day and hour level make them over-dispersed, close to negative binomial. The hourly rate is:

```
rate(agent, hour) = base(agent) × area_mix(type) × hour_profile(area, hour) × weekday(area)
                  × payday(area, day_of_month) × remittance(area, date) × hat(cluster, weekday)
                  × festival(event, days_to_event) × disruption(territory, date) × noise
```

| Pattern | Applies to | Shape | Default | Basis |
|---|---|---|---|---|
| Hour of day | all | late-morning (11:30) and evening (17:30–19:00 by setting) peaks over a floor; zero when closed | each day sums to 1 | ASSUMPTION |
| Ramadan | all | activity shifts towards the evening | evening peak 1.5 h later and ×1.4, morning ×0.6 | ASSUMPTION |
| Weekday | all | Friday quieter in the morning (×0.8 before 12:00, ×0.4 at prayer time 12:00–14:00); banks shut Fri–Sat, so agents cannot self-refill from banks | Thu ×1.05, Fri ×0.90 | weekend SOURCE; size ASSUMPTION |
| Payday | GZP, DHK | CO uplift on days 1–10 of the month, peak around day 5–7 | ×1.6 at peak | timing SOURCE (wages due within 7 working days after the wage period, [Labour Act s.123](https://www.thedailystar.net/law-our-rights/news/the-entitlements-the-workers-relating-wages-1890601)); size ASSUMPTION |
| Remittance | CUM, SYL | CO uplift before each Eid (linear ramp over 14 days) and a mild uplift on days 1–7 of the month | ×1.3 before Eid, ×1.1 at month start | concentration SOURCE; size ASSUMPTION |
| Hat days | RNG, KUR | each agent cluster has 1–2 fixed market weekdays | ×1.5 | ASSUMPTION |
| Pre-Eid surge | all | counts and ticket sizes ramp up over the 10 days before Eid, peaking 2 days before; CO weight urban 0.7, peri-urban 1.0, rural 1.2; CI weight urban 1.0, peri-urban 0.6, rural 0.2, as city workers send money home | calibrated, see below | DERIVED target, ASSUMPTION shape |
| Eid days | all | volume drops on Eid day and the next 2 days; shops open 14:00–20:00 on Eid day | ×0.3, ×0.4, ×0.6 | ASSUMPTION |
| Cattle markets | RNG, KUR, GZP | extra CO in the 7 days before Eid-ul-Azha only | ×1.3 extra | ASSUMPTION (the out-of-distribution test) |
| Disruptions | random territory-days | demand ×0.6, runner speed ×0.5; probability 2% per territory-day, 5% for KUR in June | — | ASSUMPTION |
| Noise | all | gamma multipliers: CV 0.15 per day, 0.30 per hour | — | ASSUMPTION |

**Eid calibration targets (DERIVED).** Bangladesh Bank's agent figures for April and May 2026 (the Eid-ul-Azha month, [BB table 9](https://www.bb.org.bd/econdata/fin_digitalfstat/tab9.pdf)) give four May ÷ April ratios: cash-out count and amount, cash-in count and amount. Amounts grow faster than counts, so people also withdraw and deposit **larger tickets** before Eid. The simulator therefore calibrates, per side, a count surge and a ticket-size surge with the same pre-Eid shape. The ratios are computed in code (`jogan/sim/calibration.py`) and every world's `meta.json` records targets and achieved values.

**Eid-ul-Fitr uses the same surge.** Table 9 note 5: Nagad sent no data from March 2025 to February 2026, so March 2026 is not comparable with February 2026 and the Fitr month cannot be calibrated on its own. Both Eids share the Azha-calibrated surge; cattle markets add extra cash-out before Azha only.

**Ticket sizes.**
- **Distribution:** log-normal per transaction type (**ASSUMPTION**).
- **Calibration:** network-wide means are tuned to BB's July 2026 agent averages, i.e. amount ÷ count for CO (Tk 419,415.1 million ÷ 308,646,376) and for CI (Tk 477,301.5 million ÷ 211,378,627) (**DERIVED** in code).
- **CO/CI count ratio:** taken from the same table. Each agent's cash-out share is a log-odds tilt by setting (urban −0.8, peri-urban 0, rural +0.5, remittance territories +0.4 more, agent noise σ = 0.25; **ASSUMPTION**) around a centre calibrated to the July 2026 ratio.
- **Rounding:** to Tk 50 below Tk 1,000, Tk 100 below Tk 10,000, Tk 500 above; at least Tk 50 (**ASSUMPTION**).
- **Spread:** log-normal σ = 0.9 on both sides (**ASSUMPTION**); the location is calibrated so the capped mean equals the July 2026 mean.
- **Caps:** cash-out at most Tk 30,000 and cash-in at most Tk 50,000 per customer per day (**SOURCE**: BB circular of 27 March 2025, via [BSS](https://www.bssnews.net/business/258749)). The simulator simplifies these to per-transaction caps.

**Area mix** (**ASSUMPTION**). Urban agents lean towards cash-in; rural and remittance agents lean towards cash-out. Cash therefore piles up in cities and drains in villages, which is exactly why rebalancing is needed.

## 6. Operations, money and costs

The operations environment (`jogan/ops/`, parameters in `configs/ops/` and the `runners` block of `configs/sim/base.yaml`) replays every customer attempt of a world in time order against each agent's cash and e-float. Every policy faces exactly the same customers.

**How agents rebalance in Bangladesh (SOURCE).** The Agent Network Accelerator survey of 2,800 agents ([Helix Institute / MicroSave, Bangladesh country report, November 2014](https://www.microsave.net/wp-content/uploads/2014/11/Agent-Network-Accelerator-Bangladesh-Country-Report-2014.pdf)) found that:
- 96% of agents rebalance at their shop, through visits by the provider or the aggregator (distributor);
- runners, the distributor's staff, visit "usually at a predetermined time", and some aggregators also rebalance on demand;
- the median agent makes 12 cash deposits and 10 cash withdrawals a month to manage liquidity;
- agents deny a median of zero transactions a day for lack of liquidity, while 34% report denying at least one a day.

The survey is from 2014 and self-reported. It sets the form of the status quo and serves as a plausibility check, not as a calibration target (D-016).

| Item | Default | Basis |
|---|---|---|
| Runners per territory | 3 urban/peri-urban, 2 rural per 100 agents (at least 1) | ASSUMPTION |
| Runner roster | Off on Eid day; 2% random absence per runner-day | ASSUMPTION |
| Runner shift | 09:00–18:00: 8 working hours plus a 1-hour break; at most 20 visits of 10 min; cash bag up to Tk 300,000 with Tk 150,000 loaded each morning | 8-hour day SOURCE (Bangladesh Labour Act 2006 s.100, [text](https://www.lawyersnjurists.com/article/the-bangladesh-labour-act-2006-chapter-ix/)); visit count sized to the ANA rebalancing frequency (SOURCE above); the rest ASSUMPTION |
| Travel | road km between agents (§3) at the runner's speed, halved on disruption days; the runner must be back at the hub when the shift ends | ASSUMPTION |
| What a visit does | Brings the agent's cash to a target level by swapping cash and e-float with the distributor; the agent's total liquidity is unchanged. The swap is limited by the agent's balances and the runner's bag, in Tk 100 steps | Problem framing |
| Status quo (`fixed_round`) | Each runner serves a compact sector of agents. Its route is cut into daily groups of at most 16 stops that fit a shift, visited in turn. At each stop the agent asks for a balanced split. 4 visits per runner stay free for calls | form SOURCE (ANA); sizes ASSUMPTION |
| Agent call | When cash or e-float drops below 0.25 of the agent's typical day, the runner who can arrive first goes | ASSUMPTION |
| Agent self-refill (fallback under every policy) | Below 15% of a typical day, the agent goes to a bank after 2–6 h, only on bank-open days between 10:00 and 15:00; called off if a runner fixed it first | bank transaction hours 10:00–15:00 from 5 Apr 2026 SOURCE ([Dhaka Tribune](https://www.dhakatribune.com/business/banks/406921/bb-reschedules-bank-transaction-hours)), applied to the whole run ASSUMPTION; Fri/Sat bank weekend SOURCE; the rest ASSUMPTION |
| Agent commission | Tk 4.10 per Tk 1,000 of cash-out and of cash-in | SOURCE: the same at bKash, Nagad, Rocket and upay ([Prothom Alo, 10 Aug 2022](https://www.prothomalo.com/business/7cxvrytmp6)); unchanged in 2026 ASSUMPTION |
| Idle-liquidity cost | 10% a year on cash or e-float above one typical day of outflow on that side | rate SOURCE: Bangladesh Bank policy rate until the cut to 9.5% from 2 Aug 2026 ([The Financial Express](https://thefinancialexpress.com.bd/economy/bb-cuts-repo-rate-by-50-bps-to-950pc-to-spur-investment-economic-recovery)); using it as the cost of idle money and the one-day need ASSUMPTION |
| Failed request | Lost, no retry; sensitivity: 30% retry within 2 h, with the same retry draws under every policy | ASSUMPTION |

**Runner cost** is built from real inputs (`configs/ops/costs.yaml`; D-019), not typed per km or per visit:

| Input | Value | Basis |
|---|---|---|
| Petrol, official consumer price | Tk 118 a litre from 1 Jan 2026, 116 from 1 Feb, 135 from 19 Apr, 140 from 1 Jun | SOURCE: Energy and Mineral Resources Division notifications as reported by [The Financial Express](https://thefinancialexpress.com.bd/trade/fuel-prices-cut-by-tk-2-a-litre-at-start-of-2026), [Dhaka Tribune](https://www.dhakatribune.com/bangladesh/power-energy/420367/fuel-prices-rise-up-to-nearly-36%25-between-january), [TBS](https://www.tbsnews.net/node/1426246) and [UNB](https://unb.com.bd/category/Bangladesh/fuel-prices-raised-again-octane-petrol-up-by-tk-5-per-litre/187098) |
| Motorcycle mileage | 45 km a litre in town (urban, peri-urban), 50 on open roads (rural) | SOURCE: Bajaj's claim for the 100 cc Platina 100 ([BikeBD](https://bikebd.com/price/bajaj-platina-100-2015)); that runners ride such a bike ASSUMPTION. Claimed mileage beats real riding, so fuel cost is understated |
| Runner salary | Tk 13,000–17,000 a month; the midpoint is used, the range is the sensitivity | SOURCE: bKash distribution sales officer at a distributor, Dhaka, job ad of 21 May 2026 ([EZ Jobs](https://ezjobsbangla.com/jobs/bkash-distribution-sales-officer--j_wE-oIwkZQKe2FRlqJ-UF6A); a second ad gives Tk 13,500–17,000, [Niyog](https://niyog.co/jobs/bkash-distribution-sales-officer-883a8e53)) |
| Working week | 48 hours | SOURCE: Bangladesh Labour Act 2006 s.102 |
| Fuel, Tk per km | petrol price on the day ÷ mileage of the setting | DERIVED in `jogan/ops/costs.py` |
| Runner time, Tk per minute | salary ÷ (48 h × 60 × 365.25 ÷ 12 ÷ 7 weeks a month) | DERIVED |
| Which runner minutes cost money | only minutes spent driving or at a stop, including the ride back to the hub | ASSUMPTION: the roster and salaries are the same under every policy, so only the time a policy uses differs |

Motorcycle wear, depreciation and the runner's phone are not priced (no source found); this understates runner cost.

**Known cost** = lost commission (each lost amount × the commission rate) + runner fuel + runner time + idle liquidity. Costs are counted after a run from the logged outcomes, so a run can be re-priced.

**A lost customer's value is not priced.** It is unknown. For any two policies, the break-even value per lost request is the value at which they cost the same: `(known cost A − known cost B) ÷ (lost requests B − lost requests A)`. The policy with fewer lost requests is cheaper for every value above it. A policy with both a lower known cost and fewer lost requests is cheaper at every value. This replaces the earlier Tk 50 "goodwill" assumption (D-019).

**Policies compared** (`configs/ops/policies.yaml`, all **ASSUMPTION**). Jogan is compared with three baselines; the oracle is an upper bound, not a rival (D-019). Every policy uses the same runners, the same call handling and the same agents' self-refill; they differ only in the 08:00 morning round.

| Policy | Morning round | Calls |
|---|---|---|
| `fixed_round` (status quo) | the runner's next fixed group | yes |
| `threshold` | agents below 0.75 typical days of cover on either side | yes |
| `safety_stock` | agents below mean + k·sd of their observed peak 24-hour drain on either side; k is the standard normal quantile of a 95% service level (DERIVED) | yes |
| `oracle` (upper bound) | agents whose true balance would fail within 26 h, most lost requests first; target in the middle of the cash band that serves every attempt | yes |
| Jogan (M5) | agents whose visit avoids more expected shortage and call cost than a stop's runner time, from the 24-hour drain forecast; newsvendor target (§14); runners assigned by a mixed-integer program | yes |

- **Typical day** (policy side): mean served outflow per side over the last 28 complete observed days, or the opening balance ÷ 1.25 before 3 such days exist. Served flows are censored by stock-outs, as in reality.
- **Rounds:** the top-priority agents that fit the runners' remaining capacity, split into sectors around the hub, each in nearest-neighbour order. Stops that do not fit the shift are dropped, lowest priority first.
- **Oracle:** never deployable; an upper bound for the forecast. It is not cost-aware, so it bounds lost requests, not cost.

Results are reported with the break-even value against each baseline and across the salary range. Where Jogan does not win (a baseline, an agent group, a period or a cost setting), the evaluation and the report say so (D-019).

## 7. Ground truth vs what Jogan sees

| Field | Ground truth in the simulator | What Jogan sees (like real upay) |
|---|---|---|
| Customer demand | every attempt | only served transactions; failed attempts are invisible, so demand is **censored** |
| E-float balance | exact | exact; live at decision time and hourly in the log |
| Physical cash | exact | an estimate from the opening balance and logged flows; it equals true cash until the optional shared drawer is built (cut-line item 4) |
| Runner visits | exact | logged (time, runner, amount) |
| Agents' own bank trips | exact | seen as e-float transfers |
| Anomaly labels | known | hidden; used only to evaluate the detector |
| Data gaps | none | 1% of agent-hour records never arrive, and 1% of agent-days arrive only at the end of the next day (**ASSUMPTION**). Each record carries `available_at`; features may only use records available at the forecast time |

The gaps affect the history only: live balances at decision time come from the ledger.

**Status-quo history log.** `make history PROFILE=<p> SEED=<n>` runs the status quo and writes `data/<p>/seed<n>/ops/fixed_round/`: `obs/` (hourly served flows and balances, visits, bank trips, runner days) is what M4 trains on; `truth/hourly.parquet` (every request and lost request, true balances) is for evaluation only.

## 8. Injected anomalous agents

About 2% of agents (at least one) get one injected pattern inside a random window (**ASSUMPTION**):
1. **Split cash-outs:** for 3–7 days, 1–3 bursts a day of 3–6 cash-outs within 40 minutes, at amounts just under round figures (Tk 9,950 … 29,950), a structuring-like pattern.
2. **Unexplained spike:** for 1–3 days, the agent's volume is ×2.5–4 with no calendar reason.
3. **Night activity:** for 7–14 days, on about 60% of days, 1–4 transactions between 00:00 and 05:00, outside opening hours.

These flags are **advisory** and always go to human review. Precision@k is reported.

## 9. Simulator tests (M2)

Run with `make test`; they use the `tiny` profile (the ticket check uses `dev` for a larger sample).

- **Determinism:** the same seed gives byte-identical files; a different seed gives different demand.
- **Pattern recovery:** payday, hat-day, pre-Eid (counts and tickets), Eid-day drop, Ramadan evening shift and the rural cash-out tilt all show up in the generated attempts. These tests pool four seeds, so a pattern must be clearly present, not luckily drawn.
- **Calibration:**
  - The solver reproduces every DERIVED target exactly in the expected network.
  - Realized attempts match the expected intensity, and realized mean tickets on days without the Eid surge match the July 2026 means.
  - The targets are stored with their sources in `configs/calibration/`.
- **Sanity:**
  - opening hours respected (except injected night activity)
  - amounts on the rounding grid and within the caps
  - agents inside their territory's radius; size classes follow the quantiles
  - runners off on Eid day
  - each anomaly pattern present and visible
- **Leakage guard:** public tables (`calendar`, `territories`, `agents`, `runners`, `roster`) and truth tables (`truth/demand`, `truth/agents`, `truth/anomalies`, `truth/disruptions`) are written to separate folders. A test checks that no truth column appears in a public table, and the reader returns truth tables only on request.

## 10. Operations tests (M3)

Run with `make test`, on the `tiny` profile with the three baselines and the oracle:

- **Balances:** cash and e-float never go negative, and their sum per agent never changes (customers, visits and bank trips only move money between the two sides).
- **Common random numbers:** every policy replays the same attempts, and the hourly requests are identical.
- **Ledger:** served flows in the observation log equal the served attempts; requests = served + lost.
- **Runners:** on-duty only, inside the shift, at most the daily visit limit, inside their own territory; plans made on the fleet copy are never rejected.
- **Self-refill:** only on bank-open days in bank hours.
- **Observation:** no failed attempts or truth columns; about 1% of agent-hours missing; some late days; a policy never sees a record before its `available_at` or any ground truth.
- **Oracle** loses fewer requests than each of the three baselines (two seeds).
- **Costs:** prices are derived from the configured inputs (commission per 1,000, petrol by date, mileage, salary, legal week); break-even values are exact; known cost adds up and splits across date windows; **every number in `configs/ops/*.yaml` carries a SOURCE, DERIVED or ASSUMPTION tag** (a test fails otherwise).
- **Status quo plausibility:** the median agent-day has zero lost requests, the shape of the ANA finding.
- **Determinism:** the same run gives identical outcomes and byte-identical logs.

## 11. Mapping to real upay data (future)

| Simulated table | Expected real source |
|---|---|
| agents (ID, territory, type, location) | Agent master data |
| hourly cash-in/cash-out counts and amounts | Transaction ledger aggregated per agent-hour |
| e-float balance | Ledger (exact) |
| physical cash | Agent declarations and runner visit counts (an estimate) |
| runner visits and roster | Distributor and runner visit logs |
| calendar | Public holiday list plus the internal campaign calendar |

Only agent-level aggregates are needed. No customer personal data is required.

## 12. Drain forecast (M4)

The forecast lives in `jogan/forecast/`; its parameters are in `configs/forecast/base.yaml`, and every number there carries a tag, checked by a test. `make forecast PROFILE=<p> SEED=<n>` runs the backtest on the status-quo log written by `make history` (D-020).

**Target** (D-002 #3). From a forecast origin `t` (the start of hour `t`), the cash drain after `k` hours is the sum of cash-outs minus cash-ins over hours `t … t+k−1`.
- The **peak cash drain** over `H` hours is the largest such sum (at least 0). It is the cash the agent must hold at `t` to serve every customer in the window without a top-up.
- The **peak e-float drain** is the same for the opposite direction.
- P(stock-out within `H` h) = P(peak drain > balance at `t`).
- Horizons: 6, 12 and 24 h. Origins: 08:00 (the round's plan hour) and every two hours to 20:00 (**ASSUMPTION**).
- The target is built from hourly totals, so a dip inside an hour is not seen. It understates the exact intra-hour peak; this is a limitation, the same for every method.

**Splits** (time-based). An origin belongs to a split only when its whole 24-hour window lies inside it. Training origins also need 7 days of history first.

| Profile | Train | Calibration | Test |
|---|---|---|---|
| `tiny` | 1 → 17 Mar | 18 → 22 Mar | 23 → 28 Mar |
| `dev` | 20 Feb → 31 Mar | 1 → 9 Apr | 10 → 20 Apr |
| `full` | 5 Jan → 22 Apr | 23 Apr → 6 May | 7 May → 3 Jun (§2) |

**Inputs.** Only `ops/fixed_round/obs/hourly.parquet` (served flows, e-float, cash estimate, `available_at`) and the public tables (calendar, agents). A record is usable at origin `t` only if it arrived by `t`:
- window sums use every received record, minus the delayed records still on their way at `t`;
- a past window counts only if every one of its hours had arrived;
- a test perturbs every record that arrives after `t` and checks that no feature at `t` changes.

**Features** (41 per row):
- **Agent master data:** territory, setting, size class, road km to the hub, opening hours.
- **Calendar:** hour, weekday, day of month (payday), Ramadan, days to and since Eid, bank open and holiday today and tomorrow, the agent's hat day today and tomorrow.
- **Recent served flows:** per side over the last 3, 24 and 168 hours; the last day against the last week; mean liquidity over the week.
- **Per horizon:**
  - open hours in the window;
  - the agent's 28-day hour-of-day profile summed over the window, and its peak drain;
  - the peak drain of the same window 1 and 7 days earlier;
  - the median and 90th percentile of the last 28 same-hour windows.

Liquidity enters only as the total. The current cash/e-float split is left out, because it mostly records when the status quo's runner came (D-020).

**Censoring** (D-002 #8). A stock-out hides demand: the customer leaves and nothing is logged. Labels are therefore built from **estimated demand**, not from served flows:

| Step | Rule | Basis |
|---|---|---|
| Censored hour | the side's balance at the start or end of the hour is below 3 of the agent's mean served tickets on that side | ASSUMPTION |
| Clean hour | the side started the hour with at least 5 mean tickets. Even hours that never run dry lose the large tickets, so only clean hours set the profile | ASSUMPTION |
| Expected flow | the agent's hour-of-day profile over the training split (clean hours), times the territory's level that day (clean hours, clipped to 0.25–4) | ASSUMPTION |
| Lost record (data feed) | filled with the expected flow | ASSUMPTION |
| Censored hour, `impute` (default) | served + expected: the conditional mean of an exponential tail, `E[D │ D > s] = s + μ` | ASSUMPTION |

- `ignore` (served flows only) and `drop` (no censored windows in training and calibration) are kept as ablations: `--censoring ignore|drop`.
- The bias is measured against true demand in `truth/hourly.parquet`, on windows with and without lost requests. The stock-out flags are scored by precision and recall over the hours in which customers asked for that side.
- The thresholds were chosen on development seed 0 (`tiny`, `full`) by the label bias against true demand, never on the evaluation seeds 1000–1009.

**Models.**
- LightGBM 4.7.0 ([PyPI](https://pypi.org/project/lightgbm/4.7.0/), MIT), one quantile booster per horizon, side and level (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99). That is 48 boosters, trained on `log1p` of the peak drain; quantiles survive the monotone transform.
- Settings: 150 rounds, learning rate 0.1, 31 leaves, at least 50 rows per leaf, 63 bins, deterministic (**ASSUMPTION**; sized for about a minute per `full` seed, not tuned on evaluation seeds).
- **Calibration:** asymmetric conformalized quantile regression ([Romano, Patterson and Candès 2019](https://arxiv.org/abs/1905.03222), Theorem 2). Each level is shifted by the conformal quantile of its own residuals on the calibration split: for `τ ≥ 0.5`, `P(y ≤ q'_τ) ≥ τ`; below the median, `P(y ≥ q'_τ) ≥ 1 − τ`, if the windows are exchangeable. Shifts are in log space, per setting by size class, with the pooled shift for groups under 200 calibration rows. Crossed levels are sorted afterwards.
- **P(stock-out)** is read from the calibrated grid by linear interpolation. Above the 0.99 quantile, the remaining 1% of tail mass is halved (**ASSUMPTION**).

**Baselines** (scored on the same rows):
- `empirical`: the agent's quantiles of its last 28 same-hour windows, the idea behind `safety_stock`;
- `naive_cqr`: the same window a week earlier (a day earlier when missing), plus additive conformal shifts in Tk from the calibration split.

**Backtest output.** `data/<p>/seed<n>/forecast/metrics_<strategy>.json`, all on the test split:
- pinball loss and coverage per level and method, against estimated labels and against true demand;
- coverage and width of the 50%, 80% and 90% intervals, overall, per setting and per size class;
- the Eid window (10 days before to 3 days after) against other days;
- Brier score and a reliability table of P(stock-out) for the no-top-up event (true peak drain above the live balance at the origin);
- stock-out flag quality and label bias.

## 13. Forecast tests (M4)

Run with `make test` on the `tiny` profile:

- **Leakage:** features, the empirical quantiles and the naive forecast at every origin up to a cut are unchanged when every record arriving after the cut gets other values and a later arrival. The cut falls while late records are still on their way. No feature column is a truth column or `agent_id`, and the panel refuses a frame with any column outside the observation log.
- **One code path:** the panel read from the log equals the panel a policy sees inside the simulation (`History`), so M5's in-simulation forecast uses the same features as training.
- **Target:** a hand-computed peak drain; the NaN-aware quantiles match numpy.
- **Splits:** every window lies inside its split, after the warm-up; train, calibration and test rows never overlap.
- **Censoring:** the flags find most hours with lost requests; served labels understate true demand, and estimated labels cut that bias substantially.
- **Calibration:** on synthetic, miscalibrated predictions, the conformal shifts reach nominal coverage per group, and small groups fall back to the pooled shift. On the calibration split, the upper levels are covered at least nominally.
- **Outputs:** quantiles are non-negative and monotone; P(stock-out) reads the grid exactly and falls as the balance rises; every method, interval and group is scored.
- **Determinism:** training twice gives identical predictions; the CLI writes the metrics file.

## 14. Jogan's policy and the evaluation (M5)

Configs: `configs/plan/base.yaml` (policy) and `configs/eval/base.yaml` (evaluation); every number is tagged, enforced by a test. Decision: D-021.

**At 08:00 each day** Jogan builds the forecast features from the observed history (the same code as training), predicts calibrated quantiles of the 24-hour peak drain per side, and plans the round. Calls are answered as under every policy.

| Quantity | Rule | Tag |
|---|---|---|
| Underage cost per Tk short | agent commission per Tk + lost-customer value ÷ the agent's mean served ticket on that side | commission SOURCE; one lost request per mean ticket ASSUMPTION |
| Lost-customer value | operator setting, Tk 20 per lost request in the demo; the evaluation sweeps 0, 5, 20, 50, 100, 200 | ASSUMPTION (unknown, D-019) |
| Overage cost per Tk held | policy rate × 24 h ÷ hours in a year | DERIVED |
| Need per side | forecast quantile at the critical ratio cu ÷ (cu + co), linear between grid levels, extended linearly above 0.99 | DERIVED; tail extension ASSUMPTION |
| Target cash level | middle of the band that meets both needs; when the liquidity cannot (most agent-mornings), the split in proportion to typical served outflow | ASSUMPTION, chosen on development seeds (D-021) |
| Value of a visit | expected shortage cost at today's balances minus at the target, plus the call trip it saves: change in P(falling below the call level) × the known cost of a round trip from the hub | DERIVED |
| Candidate | value above the runner time of one stop | DERIVED |
| Runner assignment | Fisher–Jaikumar generalized assignment with optional visits, one program per territory (HiGHS); then a route check and a fill step | D-021 |

**Not modelled:** the runner's bag in the program (the environment still limits each swap by it); the time between the 08:00 forecast and the runner's arrival; that a call can rescue an agent who was not visited.

**Evaluation.** The `full` profile, evaluation seeds 1000–1009 (D-010). The status quo runs over the whole period and its log trains the forecaster; every other policy is switched on at the start of the test window from the same state. Each policy is scored on the test window and on the Eid-ul-Azha days in it (ten days before to three after), with the known cost at the low, middle and high runner salary. Differences are paired over seeds with 95% t-intervals; the break-even value per lost request gets Fieller's interval. `make eval` writes `artifacts/metrics.json`; a run with other seeds or settings writes `artifacts/eval/metrics_dev.json` instead.

## 15. Policy and evaluation tests (M5)

Run with `make test` on the `tiny` profile:

- **Newsvendor:** for a uniform drain, the interpolated quantiles, exceedance probabilities and expected shortfalls are exact; the need is the critical quantile, the target the middle of the band, the two-sided split equalises the stock-out probabilities at equal costs, and the typical split is clipped to the liquidity.
- **Dispatch program:** every agent at most once, within the territory, the call reserve and the shift, every visit committed on the fleet; no visits when nothing has value; with near-zero costs it collects at least the greedy round's value.
- **Switch-over:** the status quo switched to itself equals the status quo; a switched baseline equals it before the switch.
- **Jogan in the environment:** a decision trace per agent, targets within the liquidity, probabilities in [0, 1], round visits only to candidates, no fallbacks and no rejected visits; deterministic; a horizon without a forecast is refused.
- **Evaluation:** the t-interval matches scipy; Fieller's interval covers a known ratio and is unbounded when the denominator is not away from zero; break-even verdicts; the CLI writes every section on two tiny seeds.
