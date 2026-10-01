"""Hourly operations environment: customers meet the agents' cash and e-float.

Every customer attempt in ``truth/demand`` is replayed in time order, so all policies face
exactly the same customers (common random numbers). A cash-out needs physical cash and turns
it into e-float; a cash-in does the opposite. An attempt that finds its side short fails: the
customer leaves (or, as a sensitivity option, retries once within a few hours).

Liquidity moves between the two sides in two ways, and neither changes the agent's total:

- **self-refill** (status quo, under every policy): an agent whose side drops below a share of
  a typical day goes to a bank after a delay, on bank-open days and in bank hours only;
- **runner visits** requested by the policy and checked against the runner's shift.

At the start of each hour the policy sees an :class:`Observation`: what upay would know
(exact e-float, the cash estimate, served transactions only, with data-feed gaps), never the
failed attempts. Everything else is ground truth and stays in the :class:`Episode`.
"""

from __future__ import annotations

import dataclasses
import heapq
import itertools
from typing import Protocol

import numpy as np
import pandas as pd

from jogan.ops.config import OpsConfig, load_ops_config
from jogan.ops.fleet import Fleet, Network, Visit
from jogan.sim.config import TX_TYPES, SimConfig
from jogan.sim.world import World, stream

# Final outcome of a customer attempt.
LOST, SERVED, SERVED_ON_RETRY, _RETRY_PENDING = 0, 1, 2, 3
_VISIT, _REFILL, _RETRY = 0, 1, 2


@dataclasses.dataclass(frozen=True)
class Context:
    """Static public information a policy may use; no ground truth."""

    config: SimConfig
    ops: OpsConfig
    calendar: pd.DataFrame
    agents: pd.DataFrame
    territories: pd.DataFrame
    runners: pd.DataFrame
    network: Network
    opening_cash: np.ndarray
    opening_efloat: np.ndarray
    n_days: int

    @property
    def n_hours(self) -> int:
        return self.n_days * 24


@dataclasses.dataclass
class History:
    """Observed hourly panel (agents by hours), filled as the simulation runs.

    ``co_*`` and ``ci_*`` hold served cash-out and cash-in only: failed attempts never reach
    the ledger. Balances are at the end of each hour; e-float is exact and the cash estimate
    equals true cash until a shared cash drawer is modelled. Some agent-hours never arrive
    (``missing``) and some agent-days arrive only at the end of the next day (``late``).
    """

    co_n: np.ndarray
    co_tk: np.ndarray
    ci_n: np.ndarray
    ci_tk: np.ndarray
    efloat: np.ndarray
    cash_est: np.ndarray
    missing: np.ndarray
    late: np.ndarray

    def arrives_at(self, h0: int, h1: int) -> np.ndarray:
        """Hour index at which each record of hours ``[h0, h1)`` becomes available."""
        hours = np.arange(h0, h1)
        normal = np.broadcast_to(hours + 1, (self.late.shape[0], h1 - h0))
        late = (hours // 24 + 2) * 24
        return np.where(self.late[:, hours // 24], late[None, :], normal)

    def available(self, now: int, h0: int, h1: int) -> np.ndarray:
        """Boolean mask of the records of hours ``[h0, h1)`` a policy can read at hour ``now``."""
        return ~self.missing[:, h0:h1] & (self.arrives_at(h0, h1) <= now)


@dataclasses.dataclass
class Observation:
    """What a policy sees at the start of hour ``hour`` (decisions take effect from then)."""

    hour: int
    cash_est: np.ndarray
    efloat: np.ndarray
    pending: np.ndarray  # agent already has a runner visit scheduled
    fleet: Fleet  # a copy: plan on it freely
    history: History

    @property
    def t(self) -> int:
        return self.hour * 3600

    @property
    def day(self) -> int:
        return self.hour // 24

    @property
    def hour_of_day(self) -> int:
        return self.hour % 24


class Policy(Protocol):
    name: str

    def reset(self, ctx: Context) -> None: ...

    def decide(self, obs: Observation) -> list[Visit]: ...


@dataclasses.dataclass
class Episode:
    """Ground-truth record of one policy on one world."""

    policy: str
    world: World
    ctx: Context
    # replayed attempts in time order; ``row`` points back into ``world.demand``
    row: np.ndarray
    t: np.ndarray
    agent: np.ndarray
    side: np.ndarray
    amount: np.ndarray
    outcome: np.ndarray
    retried: np.ndarray
    # hour-end balances (agents by hours)
    cash: np.ndarray
    efloat: np.ndarray
    history: History
    visits: pd.DataFrame
    refills: pd.DataFrame
    runner_days: pd.DataFrame
    rejected: int

    @property
    def n_hours(self) -> int:
        return self.ctx.n_hours


def _replay_order(world: World) -> tuple[np.ndarray, ...]:
    """Attempts sorted by time (ties keep agent then side order) as int64 arrays."""
    d = world.demand
    ids = world.agents["agent_id"].tolist()
    if list(d["agent_id"].cat.categories) != ids:
        raise ValueError("demand agent categories must follow the agent table")
    if list(d["tx_type"].cat.categories) != list(TX_TYPES):
        raise ValueError(f"tx_type categories must be {TX_TYPES}")
    start = np.datetime64(world.config.start, "s")
    seconds = (d["ts"].to_numpy().astype("datetime64[s]") - start).astype(np.int64)
    row = np.argsort(seconds, kind="stable")
    return (
        row,
        seconds[row],
        d["agent_id"].cat.codes.to_numpy().astype(np.int64)[row],
        d["tx_type"].cat.codes.to_numpy().astype(np.int64)[row],
        d["amount_tk"].to_numpy().astype(np.int64)[row],
    )


def make_context(world: World, ops: OpsConfig) -> Context:
    truth = world.agent_truth
    if truth["agent_id"].tolist() != world.agents["agent_id"].tolist():
        raise ValueError("agent truth must follow the agent table")
    return Context(
        config=world.config,
        ops=ops,
        calendar=world.calendar,
        agents=world.agents,
        territories=world.territories,
        runners=world.runners,
        network=Network(world.agents, world.territories),
        opening_cash=truth["cash0_tk"].to_numpy(dtype=np.int64),
        opening_efloat=truth["efloat0_tk"].to_numpy(dtype=np.int64),
        n_days=world.config.n_days,
    )


def _runner_days(world: World, ctx: Context) -> tuple[np.ndarray, np.ndarray]:
    """On-duty flags and speed factors per (day, runner)."""
    roster = world.roster.pivot(index="date", columns="runner_id", values="on_duty")
    roster = roster.reindex(index=world.calendar["date"], columns=world.runners["runner_id"])
    factor = np.ones((ctx.n_days, len(ctx.territories)))
    day_of = {d: i for i, d in enumerate(world.calendar["date"])}
    code_of = {c: i for i, c in enumerate(ctx.network.territory_codes)}
    for row in world.disruptions.itertuples():
        factor[day_of[row.date], code_of[row.territory]] = row.speed_factor
    terr = world.runners["territory"].map(code_of).to_numpy()
    return roster.to_numpy(dtype=bool), factor[:, terr]


def simulate(world: World, policy: Policy, ops: OpsConfig | None = None) -> Episode:
    """Run ``policy`` over the whole world window. Deterministic for a world, policy and config."""
    ops = ops or load_ops_config()
    ctx = make_context(world, ops)
    env = ops.env
    n, n_days, n_hours = len(world.agents), ctx.n_days, ctx.n_hours
    end_s = n_hours * 3600
    seed = world.seed

    row, t_arr, a_arr, s_arr, x_arr = _replay_order(world)
    m = len(row)
    T, A, S, X = t_arr.tolist(), a_arr.tolist(), s_arr.tolist(), x_arr.tolist()
    bounds = np.searchsorted(t_arr, np.arange(n_hours + 1) * 3600).tolist()

    # Common random numbers: every draw is keyed by the world seed, never by the policy.
    # Retry draws are made per demand row, so a customer's retry does not depend on sorting.
    rng = stream(seed, "ops/retry")
    u, delay = rng.random(m)[row], rng.uniform(0.0, env.retry.within_hours * 3600, m)[row]
    retry_at = np.where(u < env.retry.prob, t_arr + np.ceil(delay).astype(np.int64), -1).tolist()
    sr = env.self_refill
    n_trips = 3 * n_days + 8
    refill_delay = (
        np.round(stream(seed, "ops/self_refill").uniform(*sr.delay_hours, (n, n_trips)) * 3600)
        .astype(np.int64)
        .tolist()
    )
    rng = stream(seed, "ops/observation")
    missing = rng.random((n, n_hours)) < env.observation.missing_hour_prob
    late = rng.random((n, n_days)) < env.observation.late_day_prob

    truth = world.agent_truth
    typ_co = truth["typical_co_tk"].to_numpy(dtype=float)
    typ_ci = truth["typical_ci_tk"].to_numpy(dtype=float)
    cash = ctx.opening_cash.tolist()
    ef = ctx.opening_efloat.tolist()
    total = [c + e for c, e in zip(cash, ef, strict=True)]
    trig_c = (sr.trigger_days * typ_co).tolist()
    trig_e = (sr.trigger_days * typ_ci).tolist()
    split = np.round(np.array(total) * typ_co / (typ_co + typ_ci) / 100) * 100
    refill_target = split.astype(np.int64).tolist()

    bank_open = world.calendar["bank_open"].to_numpy(dtype=bool)
    next_open = np.full(n_days + 1, n_days)
    for d in range(n_days - 1, -1, -1):
        next_open[d] = d if bank_open[d] else next_open[d + 1]
    next_open = next_open.tolist()
    b0, b1 = sr.bank_hours[0] * 3600, sr.bank_hours[1] * 3600

    def bank_time(ts: int) -> int | None:
        """Earliest moment from ``ts`` at which a bank can do the swap."""
        day, sec = divmod(ts, 86400)
        if day < n_days and bank_open[day] and sec < b1:
            return day * 86400 + max(sec, b0)
        nxt = next_open[min(day + 1, n_days)]
        return None if nxt >= n_days else nxt * 86400 + b0

    shape = (n, n_hours)
    cash_h = np.zeros(shape, dtype=np.int64)
    ef_h = np.zeros(shape, dtype=np.int64)
    history = History(
        co_n=np.zeros(shape, dtype=np.int32),
        co_tk=np.zeros(shape, dtype=np.int64),
        ci_n=np.zeros(shape, dtype=np.int32),
        ci_tk=np.zeros(shape, dtype=np.int64),
        efloat=ef_h,
        cash_est=cash_h,  # no shared drawer yet: the estimate is exact
        missing=missing,
        late=late,
    )

    fleet = Fleet(world, ctx.network)
    on_duty, speed_factor = _runner_days(world, ctx)
    heap: list[tuple[int, int, int, int]] = []
    seq = itertools.count()
    outcome = bytearray(m)
    retried = bytearray(m)
    pending = [0] * n
    refill_pending = [False] * n
    trips = [0] * n
    visits: list[dict] = []
    refills: list[dict] = []
    runner_days: list[tuple[int, int, bool, int, float]] = []
    rejected = 0
    co_n = co_tk = ci_n = ci_tk = [0] * n

    def check_refill(a: int, t: int) -> None:
        if refill_pending[a] or (cash[a] >= trig_c[a] and ef[a] >= trig_e[a]):
            return
        refill_pending[a] = True
        done = bank_time(t + refill_delay[a][trips[a] % n_trips])
        trips[a] += 1
        if done is not None and done < end_s:
            heapq.heappush(heap, (done, next(seq), _REFILL, a))

    def attempt(k: int, t: int, retry: bool) -> None:
        a, x = A[k], X[k]
        if S[k] == 0:
            ok = cash[a] >= x
            if ok:
                cash[a] -= x
                ef[a] += x
                co_n[a] += 1
                co_tk[a] += x
        else:
            ok = ef[a] >= x
            if ok:
                ef[a] -= x
                cash[a] += x
                ci_n[a] += 1
                ci_tk[a] += x
        if retry:
            outcome[k] = SERVED_ON_RETRY if ok else LOST
        elif ok:
            outcome[k] = SERVED
        elif 0 <= retry_at[k] < end_s:
            outcome[k] = _RETRY_PENDING
            retried[k] = 1
            heapq.heappush(heap, (retry_at[k], next(seq), _RETRY, k))
        if ok:
            check_refill(a, t)

    def event(t: int, kind: int, ref: int) -> None:
        if kind == _RETRY:
            attempt(ref, t, retry=True)
            return
        if kind == _REFILL:
            a = ref
            refill_pending[a] = False
            if cash[a] >= trig_c[a] and ef[a] >= trig_e[a]:
                return  # a runner came first; the trip is called off
            delta = refill_target[a] - cash[a]
            cash[a] += delta
            ef[a] -= delta
            refills.append({"t": t, "agent": a, "cash_delta": delta})
            return
        v = visits[ref]
        a, r = v["agent"], v["runner"]
        want = v["target_cash"] - cash[a]
        if want > 0:
            delta = min(want, fleet.bag[r], ef[a])
        else:
            delta = -min(-want, cash[a], fleet.capacity - fleet.bag[r])
        delta = int(delta / 100) * 100  # whole Tk 100 notes, rounded towards zero
        cash[a] += delta
        ef[a] -= delta
        fleet.bag[r] -= delta
        pending[a] -= 1
        v["cash_delta"] = delta
        v["bag_after"] = fleet.bag[r]
        check_refill(a, t)

    def close_day(day: int) -> None:
        for r, km in enumerate(fleet.end_day()):
            runner_days.append((r, day, fleet.on_duty[r], fleet.visits[r], km))

    policy.reset(ctx)
    for h in range(n_hours):
        t0 = h * 3600
        if h % 24 == 0:
            day = h // 24
            if day > 0:
                close_day(day - 1)
            fleet.start_day(
                day, on_duty[day].tolist(), speed_factor[day].tolist(), env.runner_bag_start_tk
            )

        obs = Observation(
            hour=h,
            cash_est=np.array(cash, dtype=np.int64),
            efloat=np.array(ef, dtype=np.int64),
            pending=np.array(pending) > 0,
            fleet=fleet.copy(),
            history=history,
        )
        for v in policy.decide(obs):
            scheduled = fleet.commit(v.runner, v.agent, t0)
            if scheduled is None:
                rejected += 1
                continue
            arrive, leg = scheduled
            visits.append(
                {
                    "planned_t": t0,
                    "t": arrive,
                    "runner": v.runner,
                    "agent": v.agent,
                    "reason": v.reason,
                    "target_cash": int(v.target_cash),
                    "km": leg,
                    "cash_delta": None,
                    "bag_after": None,
                }
            )
            pending[v.agent] += 1
            heapq.heappush(heap, (arrive, next(seq), _VISIT, len(visits) - 1))

        co_n, co_tk, ci_n, ci_tk = [0] * n, [0] * n, [0] * n, [0] * n
        for k in range(bounds[h], bounds[h + 1]):
            t = T[k]
            while heap and heap[0][0] <= t:
                te, _, kind, ref = heapq.heappop(heap)
                event(te, kind, ref)
            attempt(k, t, retry=False)
        while heap and heap[0][0] < t0 + 3600:
            te, _, kind, ref = heapq.heappop(heap)
            event(te, kind, ref)

        cash_h[:, h] = cash
        ef_h[:, h] = ef
        history.co_n[:, h] = co_n
        history.co_tk[:, h] = co_tk
        history.ci_n[:, h] = ci_n
        history.ci_tk[:, h] = ci_tk
    close_day(n_days - 1)

    out = np.frombuffer(bytes(outcome), dtype=np.int8).copy()
    out[out == _RETRY_PENDING] = LOST  # retries that would fall after the window
    return Episode(
        policy=policy.name,
        world=world,
        ctx=ctx,
        row=row,
        t=t_arr,
        agent=a_arr,
        side=s_arr,
        amount=x_arr,
        outcome=out,
        retried=np.frombuffer(bytes(retried), dtype=np.int8).astype(bool),
        cash=cash_h,
        efloat=ef_h,
        history=history,
        visits=pd.DataFrame(
            visits,
            columns=[
                "planned_t",
                "t",
                "runner",
                "agent",
                "reason",
                "target_cash",
                "km",
                "cash_delta",
                "bag_after",
            ],
        ),
        refills=pd.DataFrame(refills, columns=["t", "agent", "cash_delta"]),
        runner_days=pd.DataFrame(runner_days, columns=["runner", "day", "on_duty", "visits", "km"]),
        rejected=rejected,
    )
