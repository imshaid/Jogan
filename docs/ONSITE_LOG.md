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
