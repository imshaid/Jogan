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

| Item | Default | Basis |
|---|---|---|
| Runners per territory | 3 urban/peri-urban, 2 rural per 100 agents (at least 1) | ASSUMPTION |
| Runner roster | Off on Eid day; 2% random absence per runner-day | ASSUMPTION |
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
| Data gaps | none | about 1% of hourly records missing, and occasional late days (**ASSUMPTION**; applied by the observation layer in M3) |

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
  - no negative balances (checked in the operations environment, M3)
- **Leakage guard:** public tables (`calendar`, `territories`, `agents`, `runners`, `roster`) and truth tables (`truth/demand`, `truth/agents`, `truth/anomalies`, `truth/disruptions`) are written to separate folders. A test checks that no truth column appears in a public table, and the reader returns truth tables only on request.

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
