# Jogan · যোগান

**Agent liquidity copilot for mobile financial services (MFS) agents.** A student hackathon prototype for AI Dev Fest 2026 (DIU CPC × upay), Track 05: Merchant & Agent Intelligence.

> **All data in this project is simulated.** Jogan is an independent student prototype. It is not an upay product and uses no upay production data.

## Problem

An MFS agent's shop needs two kinds of money: **physical cash** and **e-float** (digital balance). A cash-out drains cash and fills e-float; a cash-in does the reverse. When either runs out, the agent has a **stock-out**: the customer is turned away, the agent loses commission and trust suffers. Our working hypothesis, to be validated with upay, is that refills today are mostly reactive.

## What Jogan does (being built)

- Forecasts each agent's cash and e-float pressure for the next 6, 12 and 24 hours, with calibrated uncertainty.
- Estimates the risk of a stock-out and recommends rebalancing or runner visits under an explicit cost trade-off.
- Explains each recommendation with its main drivers, in English and Bangla.
- Keeps a human approver in the loop, with an audit log.
- Measures its impact in a simulated operations environment against simple baseline policies.

## Live demo

- Web app: <https://jogan-bd.vercel.app>. Use the one-click demo analyst or approver account on the sign-in page.
- API: <https://jogan-api-gt7msysppq-as.a.run.app> (`/health`, interactive docs at `/docs`)

The demo serves one simulated world (600 agents, 6 territories). Each day of its test window has Jogan's planned runner visits; an approver approves or rejects them, and every decision goes into an append-only audit log.

## Status

Work in progress; see [`docs/STATUS.md`](docs/STATUS.md). The full README (features, stack, setup, environment variables, live URL, testing) is completed before submission.

## Quick start (developers)

Requirements: Linux or macOS, `git`, [`uv`](https://docs.astral.sh/uv/), GNU `make`.

```bash
git clone https://github.com/imshaid/Jogan.git
cd Jogan
make setup   # Python deps (uv) and git hooks
make check   # lint and tests, same as CI
```

## License

[MIT](LICENSE)
