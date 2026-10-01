"""Baseline runner-dispatch policies and the perfect-foresight oracle.

Jogan is compared with three baselines (D-019); the oracle is an upper bound, not a rival.
Every policy works with the same runners, the same agents' own bank trips, the same call
handling and the same dispatch helpers; they differ only in the morning round:

- ``fixed_round`` (the status quo): each runner visits its own agents on a fixed cycle at a
  predetermined time, as the ANA Bangladesh survey describes (D-016).
- ``threshold``: a round to agents below ``min_days`` of cover on either side.
- ``safety_stock``: a round to agents whose balance is below the mean + k·sd of their past
  peak 24-hour drain.
- ``oracle``: a round planned with perfect knowledge of every customer attempt. Never
  deployable.

Calls: an agent whose cover falls below ``call_days`` of its typical day calls, and the runner
that can arrive first goes. Morning rounds keep ``call_reserve_visits`` per runner free for them.

Policies read only the :class:`~jogan.ops.env.Observation` (served transactions, balances,
runner state). The oracle alone is handed the true demand, on purpose.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np

from jogan.ops.dispatch import nearest_neighbour, plan_rounds, send_first_free
from jogan.ops.env import Context, Observation
from jogan.ops.fleet import HUB, Visit, route_seconds
from jogan.sim.world import World

BASELINES = ("fixed_round", "threshold", "safety_stock")
STATUS_QUO = "fixed_round"
UPPER_BOUND = "oracle"
POLICIES = (*BASELINES, UPPER_BOUND)


def _by_priority(mask: np.ndarray, score: np.ndarray) -> np.ndarray:
    """Indices where ``mask`` holds, lowest ``score`` first (ties by agent order)."""
    idx = np.flatnonzero(mask)
    return idx[np.argsort(score[idx], kind="stable")]


class Typical:
    """An agent's typical day of served outflow per side, estimated from observed history.

    Mean of the last ``history_days`` complete calendar days that the policy can see. Served
    flows are censored by stock-outs, so this underestimates busy agents, as a real rule would.
    Before ``min_days`` such days exist it falls back to the opening balance.
    """

    def __init__(self, ctx: Context) -> None:
        self.params = ctx.ops.policies.typical
        p = self.params
        self.cold = (
            ctx.opening_cash / p.cold_start_balance_days,
            ctx.opening_efloat / p.cold_start_balance_days,
        )
        self._day = -1
        self._value: tuple[np.ndarray, np.ndarray] = self.cold

    def __call__(self, obs: Observation) -> tuple[np.ndarray, np.ndarray]:
        if obs.day != self._day:
            self._day = obs.day
            self._value = self._estimate(obs)
        return self._value

    def _estimate(self, obs: Observation) -> tuple[np.ndarray, np.ndarray]:
        w = min(self.params.history_days, obs.day)
        if w == 0:
            return self.cold
        n = len(obs.cash_est)
        h0, h1 = (obs.day - w) * 24, obs.day * 24
        hist = obs.history
        complete = hist.available(obs.hour, h0, h1).reshape(n, w, 24).all(axis=2)
        days = complete.sum(axis=1)
        out = []
        for flows, cold in ((hist.co_tk, self.cold[0]), (hist.ci_tk, self.cold[1])):
            daily = flows[:, h0:h1].reshape(n, w, 24).sum(axis=2)
            mean = (daily * complete).sum(axis=1) / np.maximum(days, 1)
            out.append(np.maximum(np.where(days >= self.params.min_days, mean, cold), 1.0))
        return out[0], out[1]


def balanced_target(obs: Observation, typ_co: np.ndarray, typ_ci: np.ndarray) -> np.ndarray:
    """Cash level that splits the agent's liquidity in proportion to its typical outflows."""
    total = obs.cash_est + obs.efloat
    return total * typ_co / (typ_co + typ_ci)


class Planned:
    """A morning round at ``plan_hour`` (:meth:`plan`), then calls answered with what is left."""

    name = "planned"

    def reset(self, ctx: Context) -> None:
        self.ctx = ctx
        self.params = ctx.ops.policies
        self.typical = Typical(ctx)

    def decide(self, obs: Observation) -> list[Visit]:
        visits = self.plan(obs) if obs.hour_of_day == self.params.plan_hour else []
        return visits + self.calls(obs, {v.agent for v in visits})

    def plan(self, obs: Observation) -> list[Visit]:
        return []

    def calls(self, obs: Observation, booked: set[int]) -> list[Visit]:
        if not self.params.plan_hour <= obs.hour_of_day < obs.fleet.shift[1]:
            return []
        typ_co, typ_ci = self.typical(obs)
        cover = np.minimum(obs.cash_est / typ_co, obs.efloat / typ_ci)
        low = cover < self.params.calls.call_days
        due = [a for a in _by_priority(low & ~obs.pending, cover) if a not in booked]
        target = balanced_target(obs, typ_co, typ_ci)
        return send_first_free(due, obs.fleet, obs.t, lambda a, _: target[a])

    def rounds(self, obs: Observation, agents, target) -> list[Visit]:
        reserve = self.params.call_reserve_visits
        return plan_rounds(agents, obs.fleet, obs.t, target, reserve=reserve)


class FixedRound(Planned):
    """Status quo: every runner serves its own sector and visits a fixed group each day.

    A territory's agents are split into one compact sector per runner; each sector's nearest-
    neighbour route is cut into groups of at most ``max_visits - call_reserve_visits`` stops
    that fit a normal shift, visited in turn, one group a day. At each stop the agent asks for
    a balanced split. An absent runner's group waits for the next cycle.
    """

    name = "fixed_round"

    def reset(self, ctx: Context) -> None:
        super().reset(ctx)
        net = ctx.network
        runners_cfg = ctx.config.runners
        size = runners_cfg.max_visits - self.params.call_reserve_visits
        shift_s = (runners_cfg.shift[1] - runners_cfg.shift[0]) * 3600
        visit_s = runners_cfg.visit_minutes * 60
        speed = ctx.runners["speed_kmh"].to_numpy(dtype=float)
        runner_terr = ctx.runners["territory"].map(
            {c: i for i, c in enumerate(net.territory_codes)}
        )
        self.groups: dict[int, list[list[int]]] = {}
        for t in range(len(net.territory_codes)):
            runners = np.flatnonzero(runner_terr.to_numpy() == t).tolist()
            mine = sorted(
                (a for a in range(len(ctx.agents)) if net.territory[a] == t),
                key=lambda a: net.angle[a],
            )
            for r, sector in zip(
                runners, np.array_split(np.array(mine, dtype=int), len(runners)), strict=True
            ):
                groups: list[list[int]] = [[]]
                for a in nearest_neighbour(net, HUB, sector.tolist()):
                    trial = [*groups[-1], a]
                    fits = route_seconds(net, HUB, trial, speed[r], visit_s) <= shift_s
                    if len(trial) <= size and fits:
                        groups[-1] = trial
                    else:
                        groups.append([a])
                self.groups[r] = groups

    def plan(self, obs: Observation) -> list[Visit]:
        typ_co, typ_ci = self.typical(obs)
        target = balanced_target(obs, typ_co, typ_ci)
        fleet, visits = obs.fleet, []
        for r, groups in self.groups.items():
            route = list(groups[obs.day % len(groups)])
            while route and not fleet.route_fits(r, route, obs.t):
                route.pop()
            for a in route:
                if fleet.commit(r, a, obs.t) is not None:
                    visits.append(Visit(r, a, round(target[a] / 100) * 100, "round"))
        return visits


class Threshold(Planned):
    """Static min/max: visit agents with less than ``min_days`` of cover on either side."""

    name = "threshold"

    def plan(self, obs: Observation) -> list[Visit]:
        typ_co, typ_ci = self.typical(obs)
        cover = np.minimum(obs.cash_est / typ_co, obs.efloat / typ_ci)
        due = _by_priority((cover < self.params.threshold.min_days) & ~obs.pending, cover)
        target = balanced_target(obs, typ_co, typ_ci)
        return self.rounds(obs, due, lambda a, _: target[a])


class SafetyStock(Planned):
    """Mean + k·sd of each agent's past peak 24-hour drain, per side, as the level to hold.

    The peak drain of a 24-hour window is the largest cumulative net outflow of a side inside
    it, from observed hourly served flows. Agents with fewer than ``min_days`` complete windows
    fall back to the threshold rule.
    """

    name = "safety_stock"

    def plan(self, obs: Observation) -> list[Visit]:
        p = self.params.safety_stock
        n = len(obs.cash_est)
        cash, ef = obs.cash_est.astype(float), obs.efloat.astype(float)
        total = cash + ef
        need_c, need_e, enough = np.zeros(n), np.zeros(n), np.zeros(n, dtype=bool)
        w = min(p.history_days, obs.hour // 24)
        if w > 0:
            h0, h1 = obs.hour - 24 * w, obs.hour
            hist = obs.history
            complete = hist.available(obs.hour, h0, h1).reshape(n, w, 24).all(axis=2)
            net = (hist.co_tk[:, h0:h1] - hist.ci_tk[:, h0:h1]).reshape(n, w, 24).cumsum(axis=2)
            days = complete.sum(axis=1)
            enough = days >= p.min_days
            for peak, need in ((net.max(axis=2), need_c), ((-net).max(axis=2), need_e)):
                peak = np.maximum(peak, 0).astype(float)
                k = np.maximum(days, 1)
                mean = (peak * complete).sum(axis=1) / k
                var = (((peak - mean[:, None]) ** 2) * complete).sum(axis=1) / np.maximum(k - 1, 1)
                need[:] = mean + NormalDist().inv_cdf(p.service_level) * np.sqrt(var)

        typ_co, typ_ci = self.typical(obs)
        cover = np.minimum(cash / typ_co, ef / typ_ci)
        min_days = self.params.threshold.min_days
        short = np.maximum(
            (need_c - cash) / np.maximum(need_c, 1), (need_e - ef) / np.maximum(need_e, 1)
        )
        due = np.where(enough, (cash < need_c) | (ef < need_e), cover < min_days) & ~obs.pending
        urgency = np.where(enough, short, (min_days - cover) / min_days)

        band_ok = need_c + need_e <= total
        stocked = np.where(
            band_ok,
            (need_c + total - need_e) / 2,
            total * need_c / np.maximum(need_c + need_e, 1),
        )
        target = np.where(enough, stocked, balanced_target(obs, typ_co, typ_ci))
        return self.rounds(obs, _by_priority(due, -urgency), lambda a, _: target[a])


class Oracle(Planned):
    """Perfect foresight of every customer attempt over ``horizon_hours``.

    An agent is visited when its true balance would fail some attempt in the horizon, most lost
    requests first (then most Tk). The visit aims for the middle of the band of cash levels that
    serve every attempt from the runner's arrival onwards (or the best split when none can).
    """

    name = "oracle"

    def __init__(self, world: World) -> None:
        d = world.demand  # sorted by agent, then time
        start = np.datetime64(world.config.start, "s")
        self._t = (d["ts"].to_numpy().astype("datetime64[s]") - start).astype(np.int64)
        self._x = d["amount_tk"].to_numpy().astype(np.int64)
        self._co = d["tx_type"].cat.codes.to_numpy() == 0
        codes = d["agent_id"].cat.codes.to_numpy()
        agents = np.arange(len(world.agents))
        self._lo = np.searchsorted(codes, agents, "left")
        self._hi = np.searchsorted(codes, agents, "right")
        # prefix sums of the cash drain: a cash-out drains cash, a cash-in refills it
        self._p = np.concatenate([[0], np.cumsum(np.where(self._co, self._x, -self._x))])

    def _span(self, a: int, t0: int, t1: int) -> tuple[int, int]:
        lo, hi = self._lo[a], self._hi[a]
        times = self._t[lo:hi]
        return lo + int(np.searchsorted(times, t0)), lo + int(np.searchsorted(times, t1))

    def _peaks(self, a: int, t0: int, t1: int) -> tuple[int, int]:
        """Cash and e-float an agent needs at ``t0`` to serve every attempt until ``t1``."""
        i0, i1 = self._span(a, t0, t1)
        if i1 <= i0:
            return 0, 0
        drain = self._p[i0 + 1 : i1 + 1] - self._p[i0]
        return max(0, int(drain.max())), max(0, -int(drain.min()))

    def _loss(self, a: int, cash: int, ef: int, t0: int, t1: int) -> tuple[int, int]:
        """Requests and Tk lost between ``t0`` and ``t1`` if no runner comes."""
        lost, lost_tk = 0, 0
        i0, i1 = self._span(a, t0, t1)
        for x, co in zip(self._x[i0:i1].tolist(), self._co[i0:i1].tolist(), strict=True):
            if co and cash >= x:
                cash, ef = cash - x, ef + x
            elif not co and ef >= x:
                cash, ef = cash + x, ef - x
            else:
                lost, lost_tk = lost + 1, lost_tk + x
        return lost, lost_tk

    def plan(self, obs: Observation) -> list[Visit]:
        horizon = self.params.oracle.horizon_hours * 3600
        t0 = obs.t
        total = obs.cash_est + obs.efloat
        scored = []
        for a in np.flatnonzero(~obs.pending).tolist():
            cash, ef = int(obs.cash_est[a]), int(obs.efloat[a])
            need_c, need_e = self._peaks(a, t0, t0 + horizon)
            if cash < need_c or ef < need_e:
                lost, lost_tk = self._loss(a, cash, ef, t0, t0 + horizon)
                scored.append((-lost, -lost_tk, a))
        scored.sort()

        def target(a: int, arrive: int) -> float:
            need_c, need_e = self._peaks(a, arrive, arrive + horizon)
            liquidity = float(total[a])
            if need_c + need_e <= liquidity:
                return (need_c + liquidity - need_e) / 2
            return liquidity * need_c / (need_c + need_e)

        return self.rounds(obs, [a for *_, a in scored], target)


def make_policy(name: str, world: World) -> Planned:
    """A fresh policy by name (see ``POLICIES``)."""
    policies = {"fixed_round": FixedRound, "threshold": Threshold, "safety_stock": SafetyStock}
    if name in policies:
        return policies[name]()
    if name == UPPER_BOUND:
        return Oracle(world)
    raise ValueError(f"unknown policy {name!r}; choose from {POLICIES}")
