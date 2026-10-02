# Demo video script

The script for the submission video. The rules ask for **at least 5 minutes** covering the project, its development, what it does, how it works and its real-world impact ([`00-requirements-checklist.md`](00-requirements-checklist.md) §A). This script runs about 7 minutes at a calm speaking pace, so there is room to slow down.

- **Recorded by:** Md. Afsahul Arefin Talukder (screen and OBS), narrated by the team.
- **Narration:** written in English below; it may be spoken in Bangla, keeping the meaning and the numbers.
- **Numbers:** never typed into this script. Every number the narrator says is read from the [numbers sheet](#numbers-sheet) at the end, which `make docs` writes from `artifacts/metrics.json` and `artifacts/stress.json`, or from the impact page on screen, which comes from the same file. A line like *(sheet A: Jogan, lost per 1,000)* means "read that cell".

## Before recording

1. **Warm the API**: open <https://jogan-api-gt7msysppq-as.a.run.app/health> a minute before; the first request after idle starts an instance.
2. **Browser**: a clean Chrome profile, 1920×1080, zoom 100%, bookmarks bar hidden, notifications off, English interface to start. Sign out of the app.
3. **Pick the plan day**: on the Network page, choose a day in the Eid-ul-Azha week where the KPI strip shows visits **Awaiting decision** and some **For manual review**. Avoid 3 Jun (the live check decides visits there).
4. **Decisions are permanent.** The audit log is append-only and a visit can be decided once, so every take uses up visits. Rehearse on one day and record on another; note the agent ids you will approve and reject.
5. **AI rewording** is limited per minute: click "Reword with AI" once per take.
6. **OBS**: 1080p, 30 fps, a single display capture, microphone checked for noise; record scenes separately if easier and join them.

## Scenes

### 1. The problem (0:00–0:50)

**Screen:** a still or slow pan of the README's overview, then the sign-in page with the wordmark "Jogan · যোগান" and the "Simulated data" badge.

**Say:**
> A customer walks into an MFS agent's shop to cash out money sent from abroad, two days before Eid. The agent has no cash left. The customer walks away, the agent loses the commission, and trust in the service takes a hit.
>
> An agent holds two kinds of money: physical cash for cash-outs and e-float for cash-ins. Today, distributors' runners refill agents on a fixed round, plus calls when an agent is already running dry. But demand is not fixed: it jumps on paydays, remittance days and before Eid.
>
> We are Team Jogan from Daffodil International University, and this is Jogan, যোগান: a copilot that tells a distributor, every morning, which agents will run out, and which runner should go where. Everything you will see runs on simulated data; this is a student prototype, not an upay product.

### 2. What Jogan does, in one picture (0:50–1:20)

**Screen:** the README's architecture diagram on GitHub (or the About page, "From data to a decision").

**Say:**
> Every morning Jogan does four things. It forecasts each agent's peak cash and e-float drain for the next day, with honest uncertainty. A business rule turns that into a need, and an optimizer assigns runners within their shifts. Guardrails send weak evidence to manual review. And then a person, the approver, decides every visit, and every decision is written to an audit log that nobody can edit.

### 3. Live: the network (1:20–2:10)

**Screen:** click **Analyst** under "Demo accounts". The **Network** page opens. Point at the KPI strip, then the map: shapes ▲ ◆ ● and the blue rings. Switch **Show** to "Planned visits", then "High risk". Click **Play through the days** and let the timeline run into the Eid week, then pause on the chosen day. Scroll to **Territories** and **Highest risk this morning**.

**Say:**
> I'm signed in as an analyst. This is the network on one morning: every agent, shaped by its stock-out risk for the next 24 hours. Triangle is high, diamond medium, circle low, never colour alone. A ring means Jogan planned a runner visit.
>
> If I play through the days, you can see the planned visits climb as Eid-ul-Azha gets close. The same facts are in the tables beside the map: risk by territory, and the agents at highest risk this morning.

### 4. Live: the queue and "Why?" (2:10–3:10)

**Screen:** open **Visit queue**. Show the columns (Cash · e-float now, Stock-out chance, Target cash, Value of visit). Tick **Manual review only**, then untick. Open **Why?** on a high-value row: the **Prediction** label, the explanation with its **Template** label, **What drives the forecast**, **Guardrails**. Switch the language to **বাংলা** in the header, show the same row, click **Reword with AI**, wait, point at the **AI-written** label and the model id. Switch back to English.

**Say:**
> This is the visit queue: runner visits Jogan recommends today, highest value first. Each one waits for an approver.
>
> Why this agent? The stock-out chance is labelled as a prediction, because it can be wrong. The explanation is written by a fixed template from the stored evidence, and below it are the drivers: the model's own reasons, computed with TreeSHAP.
>
> Field staff in Bangladesh work in Bangla, so the whole interface is bilingual, down to Bangla digits and lakh grouping. On request, a language model can reword the explanation. It is labelled AI-written, with the model name, and if it adds a single number that is not in the evidence, we throw it away and show the template. The language model never decides anything.
>
> As an analyst I have no approve button. Only an approver can decide.

### 5. Live: the approver decides (3:10–4:00)

**Screen:** **Sign out**, click **Approver**. Back on the same day's queue: **Approve** one visit. Open a row tagged **⚑ Manual review**, click **Approve with note**, point at the note field marked as required, type a short note ("Checked the agent's last week; demand looks real."), submit. **Reject** another visit. Open **Audit log** and show the three new rows (action, by, note, manual review).

**Say:**
> Now I'm the approver. I approve this visit. This one is flagged for manual review: the evidence was weak or an anomaly model raised a flag. Approving it needs a written note, and the database itself enforces that rule. I reject this one.
>
> Every decision lands in the audit log, which is append-only: not even the server can edit or delete an entry.

### 6. Live: one agent, end to end (4:00–4:45)

**Screen:** on a decided row, open **Why?** and click **Agent detail and decision trace**. Show **Stock-out chance over the test window** (both sides, dots on visit days), **Forecast peak drain against the balance**, then scroll to **Decision trace** and walk down the steps, pointing at the "by" column and the config hash. Toggle **Show as table** on one chart.

**Say:**
> Every recommendation can be traced. Here is this agent's risk over the whole test window, and the forecast drain against the balance this morning.
>
> The decision trace shows each step in order: the forecast and the stock-out chance from the model, the drivers, the need and value from a business rule, the runner from the optimizer, the guardrails, the template, and finally the human decision. Each step records the configuration version it ran under. A language model is never a step.

### 7. How it works, under the hood (4:45–5:35)

**Screen:** the About page sections **Where AI is used, and where it is not** and **Labels you will see**; optionally a quick scroll of `docs/03-architecture.md` on GitHub.

**Say:**
> Under the hood: we had no real agent data, so we built a simulator of agents, customers and runners on the real 2026 Bangladesh calendar, with paydays, remittances and both Eids, calibrated to Bangladesh Bank's public MFS statistics.
>
> Jogan forecasts the peak drain, not just the end-of-day balance, because an agent runs out the moment the balance touches zero. The forecast is a LightGBM quantile model, calibrated with conformal prediction so its intervals mean what they say, and trained on labels corrected for demand that stock-outs hid.
>
> Then a newsvendor rule weighs a lost customer against the cost of idle money, and a mixed-integer program, one per territory, assigns the runners. The model predicts; rules and the optimizer propose; a person decides.
>
> The API checks every login token itself, roles are enforced again by the database, and requests are rate-limited and validated.

### 8. Impact, and where Jogan does not win (5:35–6:35)

**Screen:** open **Impact** (public). The hero number, **Lost requests per 1,000, by policy**, **Jogan minus each baseline**, the test/Eid window switch, **Hypotheses**, **Who is served better, and who is not**, **Where Jogan does not win**.

**Say:**
> Does it work? We compared Jogan with three policies on the same simulated customers: today's fixed round, a threshold rule and a safety-stock rule, over *(sheet A, note under the tables: number of seeds)* simulated worlds we never touched while building it.
>
> Jogan turns away *(sheet A: Jogan, lost per 1,000)* requests per thousand, against *(sheet A: Fixed round, lost per 1,000)* for today's fixed round and *(sheet A: Threshold, lost per 1,000)* for the best rule, while its runners drive *(sheet B: Threshold row, runner km, said as a positive number)* fewer kilometres than under the best rule. In the Eid window the gap holds *(sheet C: Threshold row, last column)*.
>
> But we report where it does not win. Urban agents in Dhaka are served slightly worse than by the simple threshold rule. Our forecast intervals miss their target coverage in some groups and on Eid days. And our anomaly flag catches split cash-outs, a structuring pattern, in only *(sheet D: split cash-outs line)* of the injected cases. These are on the impact page, from the same evaluation file as the wins.

### 9. How we built it (6:35–7:15)

**Screen:** the GitHub repo: commit history, `docs/DECISIONS.md`, the Actions tab, `artifacts/metrics.json`.

**Say:**
> We built Jogan during the event in small, tested steps, and logged every design decision with its reason. Some ideas failed and changed the design: our first status quo was wrong until a survey of Bangladeshi agents showed how runners really work, and the textbook newsvendor split lost to a simpler one, so we kept the simpler one.
>
> Every number on the impact page, in the README and in this video is written by one command from the evaluation file; tests fail if any copy is stale. The API runs on Google Cloud Run, the web app on Vercel, the database on Supabase, and each push is tested and deployed automatically. We used Claude Code as a coding assistant and disclose it in the repo.

### 10. Real-world path and close (7:15–7:45)

**Screen:** `docs/07-product-readiness.md` section 5, then the sign-in page with the team names as a lower third.

**Say:**
> With upay's data, the next step is not a bigger model but a careful test: a backtest on history, then a shadow run where Jogan plans and nobody acts, then a randomised pilot by distributor territory. Jogan needs only agent-level aggregates, never a customer's personal data.
>
> Jogan, যোগান: fewer customers turned away, with a person in charge of every visit. Thank you.

**Credits (on screen):** Md. Shaid Hasan (team leader) · Md. Fazle Rabbi · Md. Afsahul Arefin Talukder · Department of CSE, Daffodil International University · AI Dev Fest 2026 (DIU CPC × upay) · <https://jogan-bd.vercel.app> · <https://github.com/imshaid/Jogan>

## After recording

- Watch it once end to end: at least 5 minutes, every scene audible, no private tab or notification visible, no password on screen.
- Check each spoken number against the sheet below.
- Upload where the organizers ask and add the link to the submission form and the README.

## Numbers sheet

Written by `make docs`; do not edit by hand.

**A. Test window, by policy** (with the differences against each baseline as table **B** below it):

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

**C. Eid-ul-Azha window:**

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

**D. Where Jogan does not win:**

<!-- numbers:limits -->
- **Some groups are served worse than by the best baseline (Threshold).** Lost requests per 1,000, Jogan minus Threshold: `urban` and `DHK` (the same agents) 1.03 (0.01 to 2.06).
- **Forecast intervals are off their nominal coverage by more than 5 points in 45 cells** (by side, horizon, interval and agent group), 4 of them over all agents.
- **The oracle is still ahead:** Jogan minus the oracle, 19.9 (19.1 to 20.7) lost requests per 1,000.
- **The anomaly flag is weak on structuring:** split cash-outs found in 1 of 9 injected windows; precision 3.9% against a base rate of 0.08%.
- **62 group-level comparisons** (across lost-customer values and baselines) show no significant win or a baseline as good or better (`does_not_win` in `artifacts/metrics.json`).
<!-- /numbers -->

**E. Scale** (if asked):

<!-- numbers:stress -->
| Measure | Mean | Max |
|---|---|---|
| One morning, end to end (s) | 3.1 | 4.3 |
| Plan (s) | 2.4 | 3.5 |
| of which MILP solver (s) | 1.7 | 2.8 |
| Drivers, guardrails, flags (s) | 0.7 | 0.8 |

10,000 agents, 260 runners, 60 territories; 7 Jogan mornings after 7 days of status quo. 360 programs, 0 fallbacks, 23,836 visits; peak memory 1,779 MB; whole run 101 s.

_Timing only, on 13th Gen Intel(R) Core(TM) i7-13650HX (20 threads). Source: `artifacts/stress.json`, written by `make stress`._
<!-- /numbers -->
