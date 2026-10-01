# Data assumptions

Jogan runs on **synthetic data only**. This page lists every assumption behind the simulated world, so judges and teammates can see what is grounded in an outside source and what is our choice.

**Labels used on this page:**
- **SOURCE**: a verified outside fact, with a link
- **DERIVED**: computed from sources; the formula is shown, and the simulator code recomputes it
- **ASSUMPTION**: our choice, made for realism; not verified, and covered by sensitivity analysis where it matters

The parameter values live in `configs/` (added in M2). This page explains them.

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

**Profiles.** The plan is below; exact values go in `configs/sim/` in M2.

| Profile | Agents | Territories | Window | Days | Purpose |
|---|---|---|---|---|---|
| `tiny` | 40 | 2 | 7 Mar → 3 Apr | 28 | CI tests, seconds |
| `dev` | 150 | 3 | 20 Feb → 20 Apr | 60 | development |
| `full` | 600 | 6 | 5 Jan → 3 Jun | 150 | final evaluation and demo |
| `stress` | 10,000 | 6 hubs, replicated | 14-day slice | 14 | inference and optimizer timing only |

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
- **Road distance:** straight-line (haversine) distance × 1.3 (urban) or 1.4 (rural).
- **Runner speed:** 12 km/h in Dhaka traffic, 18 km/h peri-urban, 22 km/h rural. Halved on disruption days.

## 4. Agents

**Volume.** Expected daily cash-in + cash-out transactions per agent follow a log-normal distribution (**ASSUMPTION**). It is anchored on the national average of about **9 per agent per day** (**DERIVED**):
- 520,025,003 agent cash-in + cash-out transactions in July 2026 ([BB table 9](https://www.bb.org.bd/econdata/fin_digitalfstat/tab9.pdf))
- ÷ 31 days
- ÷ 1,856,190 agents in February 2025 ([BB MFS data](https://www.bb.org.bd/en/index.php/financialactivity/mfsdata))
- The two figures come from different months, so this is an order of magnitude only.

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
| Hour of day | all | late-morning and evening peaks; zero when closed | — | ASSUMPTION |
| Ramadan | all | activity shifts towards the evening | profile shift | ASSUMPTION |
| Weekday | all | Friday quieter in the morning; banks shut Fri–Sat, so agents cannot self-refill from banks | ±10% | weekend SOURCE; size ASSUMPTION |
| Payday | GZP, DHK | CO uplift on days 1–10 of the month, peak around day 5–7 | ×1.6 at peak | timing SOURCE (wages due within 7 working days after the wage period, [Labour Act s.123](https://www.thedailystar.net/law-our-rights/news/the-entitlements-the-workers-relating-wages-1890601)); size ASSUMPTION |
| Remittance | CUM, SYL | CO uplift before each Eid and a mild uplift at month start | ×1.3 | concentration SOURCE; size ASSUMPTION |
| Hat days | RNG, KUR | each agent cluster has 1–2 fixed market weekdays | ×1.5 | ASSUMPTION |
| Pre-Eid surge | all | CO ramps up over the 10 days before Eid, peaking 1–3 days before; urban CI rises as people send money home | calibrated, see below | DERIVED target, ASSUMPTION shape |
| Eid days | all | volume drops on Eid day and the next 1–2 days | ×0.3 | ASSUMPTION |
| Cattle markets | RNG, KUR, GZP | extra CO in the 7 days before Eid-ul-Azha only | ×1.3 extra | ASSUMPTION (the out-of-distribution test) |
| Disruptions | random territory-days | demand ×0.6, runner speed ×0.5; probability 2% per territory-day, 5% for KUR in June | — | ASSUMPTION |
| Noise | all | gamma multipliers: CV 0.15 per day, 0.30 per hour | — | ASSUMPTION |

**Eid calibration target (DERIVED).** Bangladesh Bank reports agent cash-out of Tk 508,903.2 million in May 2026 (the Eid-ul-Azha month) against Tk 401,864.6 million in April 2026 ([BB table 9](https://www.bb.org.bd/econdata/fin_digitalfstat/tab9.pdf)). The simulated Eid-month uplift is tuned to the same ratio. The ratio is computed in code in M2, not typed here.

**Ticket sizes.**
- **Distribution:** log-normal per transaction type (**ASSUMPTION**).
- **Calibration:** network-wide means are tuned to BB's July 2026 agent averages, i.e. amount ÷ count for CO (Tk 419,415.1 million ÷ 308,646,376) and for CI (Tk 477,301.5 million ÷ 211,378,627) (**DERIVED** in code).
- **CO/CI count ratio:** taken from the same table.
- **Rounding:** amounts round to Tk 50, 100 or 500 (**ASSUMPTION**).
- **Caps:** cash-out at most Tk 30,000 and cash-in at most Tk 50,000 per customer per day (**SOURCE**: BB circular of 27 March 2025, via [BSS](https://www.bssnews.net/business/258749)). The simulator simplifies these to per-transaction caps.

**Area mix** (**ASSUMPTION**). Urban agents lean towards cash-in; rural and remittance agents lean towards cash-out. Cash therefore piles up in cities and drains in villages, which is exactly why rebalancing is needed.

## 6. Operations, money and costs

| Item | Default | Basis |
|---|---|---|
| Runners per territory | 3 urban/peri-urban, 2 rural | ASSUMPTION |
| Runner shift | 09:00–18:00, at most 8 visits, cash bag up to Tk 300,000, 10 min per visit | ASSUMPTION |
| What a visit does | Swaps cash for e-float with the distributor; the agent's total liquidity is unchanged | Problem framing |
| Status-quo self-refill | When cash or e-float falls below 15% of a typical day, the agent goes to the distributor or bank after a 2–6 h delay; no bank refills on Fri/Sat | ASSUMPTION; weekend SOURCE |
| Customer cash-out fee | 1.4% (Tk 14 per 1,000) at agent points | Reported at upay's 2021 launch ([TBS](https://www.tbsnews.net/node/234661)); the 2026 value is an ASSUMPTION |
| Agent commission | CO 0.40%, CI 0.30% of amount; sensitivity CO 0.3–0.5%, CI 0.2–0.4% | ASSUMPTION |
| Goodwill cost per failed request | Tk 50; sensitivity Tk 0–200 (stands for the value lost if a customer switches provider) | ASSUMPTION |
| Runner cost | Tk 10 per km + Tk 100 per visit | ASSUMPTION |
| Idle-liquidity cost | 10% per year on cash and e-float held above need | ASSUMPTION |
| Failed request | Lost, no retry; sensitivity: 30% retry within 2 h | ASSUMPTION |

The results are reported across the goodwill and commission ranges. Jogan's advantage, or the lack of it, depends on these values and is shown honestly.

## 7. Ground truth vs what Jogan sees

| Field | Ground truth in the simulator | What Jogan sees (like real upay) |
|---|---|---|
| Customer demand | every attempt | only served transactions; failed attempts are invisible, so demand is **censored** |
| E-float balance | exact | exact, hourly |
| Physical cash | exact | estimated from the start value and net flows, plus noise when the shared drawer is on |
| Runner visits | exact | logged |
| Anomaly labels | known | hidden; used only to evaluate the detector |
| Data gaps | none | about 1% of hourly records missing, and occasional late days (**ASSUMPTION**) |

## 8. Injected anomalous agents

About 2% of agents get one injected pattern (**ASSUMPTION**):
1. **Split cash-outs:** many cash-outs just under round amounts, a structuring-like pattern.
2. **Unexplained spike:** a sudden volume jump vs. peers with no calendar reason.
3. **Night activity:** transactions outside opening hours.

These flags are **advisory** and always go to human review. Precision@k is reported.

## 9. Simulator tests (M2)

- **Determinism:** the same seed gives byte-identical data.
- **Pattern recovery:** the payday, hat-day and Eid uplifts show up in the generated data.
- **Calibration:**
  - Mean tickets, the CO/CI count ratio and the Eid-month uplift land close to their DERIVED targets.
  - The targets are stored with their sources in `configs/calibration/`.
- **Sanity:**
  - no negative balances
  - opening hours respected
  - caps respected
  - anomaly labels never leak into model inputs

## 10. Mapping to real upay data (future)

| Simulated table | Expected real source |
|---|---|
| agents (ID, territory, type, location) | Agent master data |
| hourly cash-in/cash-out counts and amounts | Transaction ledger aggregated per agent-hour |
| e-float balance | Ledger (exact) |
| physical cash | Agent declarations and runner visit counts (an estimate) |
| runner visits and roster | Distributor and runner visit logs |
| calendar | Public holiday list plus the internal campaign calendar |

Only agent-level aggregates are needed. No customer personal data is required.
