"""Jogan's round: which agents to visit and which runner goes, as a mixed-integer program.

A generalized-assignment heuristic for vehicle routing (Fisher and Jaikumar 1981, Networks
11(2), 109-124), with optional visits: each runner gets a seed agent, and sending runner ``r``
to agent ``a`` costs the detour of adding ``a`` to the trip to the seed,
``d(start, a) + d(a, seed) - d(start, seed)``. One program per territory:

    maximise    Σ x_ar · (value_a - cost_ar)
    subject to  Σ_r x_ar ≤ 1                       every agent at most once
                Σ_a x_ar ≤ room_r                  visits left after the call reserve
                Σ_a x_ar · seconds_ar ≤ budget_r   shift left after the trip to the seed
                x_ar ∈ {0, 1}

``value_a`` is the expected shortage cost the visit avoids (:mod:`jogan.plan.newsvendor`);
``cost_ar`` is the fuel for the detour and the runner's time for the detour and the stop,
priced like every policy's runs (``configs/ops/costs.yaml``). HiGHS solves it through
``scipy.optimize.milp``.

Seeds: the candidates, sorted by bearing from the hub, are cut into one cone per runner with
equal total value; a cone's seed is its value-weighted medoid (a runner without a cone has the
hub as seed, so a visit costs the round trip). Each runner's agents are then ordered by
nearest neighbour and checked with the fleet's own feasibility code; stops that do not fit
after all are dropped, lowest net value first, because detours only estimate the route; where
routes still have room, unchosen agents are added most valuable first if the visit pays for the
extra fuel and time. A territory whose program fails falls back to the greedy round.
"""

from __future__ import annotations

import contextlib
import ctypes
import dataclasses
import itertools
import os
import sys
import time
from collections.abc import Iterator, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array

from jogan.ops.dispatch import Target, book_visit, nearest_neighbour, plan_rounds
from jogan.ops.fleet import HUB, Fleet, Network, Visit, route_seconds, travel_seconds
from jogan.plan.config import Milp


@dataclasses.dataclass
class SolveLog:
    """What the programs did, for the evaluation's runtime and fallback counts."""

    programs: int = 0
    fallbacks: int = 0
    seconds: float = 0.0
    dropped: int = 0  # stops the route check removed after the program chose them
    filled: int = 0  # stops added afterwards where routes had room (:func:`_fill`)


_LIBC = ctypes.CDLL(None)


@contextlib.contextmanager
def _quiet_stdout() -> Iterator[None]:
    """Silence file descriptor 1 while HiGHS runs: its MIP solver prints debug lines from C++
    (seen with HiGHS 1.12.0 in scipy 1.18.1). The solve status is read from the result."""
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        with open(os.devnull, "w") as null:
            os.dup2(null.fileno(), 1)
            yield
    finally:
        _LIBC.fflush(None)  # C stdio buffers its lines when stdout is not a terminal
        os.dup2(saved, 1)
        os.close(saved)


def _km(net: Network, src: int, dst: int) -> float:
    """Road km between agents or the hub, either way round."""
    if src == dst:
        return 0.0
    if dst == HUB:
        return net.km(HUB, src)
    return net.km(src, dst)


def seeds(net: Network, agents: list[int], value: np.ndarray, k: int) -> list[int]:
    """One seed per runner: value-weighted medoids of ``k`` equal-value cones (``HUB`` if empty)."""
    order = sorted(agents, key=lambda a: net.angle[a])
    v = np.array([value[a] for a in order], dtype=float)
    mid = (np.cumsum(v) - v / 2) / max(v.sum(), 1e-9)
    cone = np.minimum((mid * k).astype(int), k - 1)
    out = []
    for c in range(k):
        members = [a for a, i in zip(order, cone, strict=True) if i == c]
        if not members:
            out.append(HUB)
            continue
        out.append(min(members, key=lambda s: sum(value[a] * _km(net, s, a) for a in members)))
    return out


def milp_rounds(
    agents: Sequence[int],
    value: np.ndarray,
    fleet: Fleet,
    now: int,
    target: Target,
    fuel_tk_per_km: np.ndarray,
    labour_tk_per_min: float,
    reserve: int,
    options: Milp,
    log: SolveLog | None = None,
) -> list[Visit]:
    """Routes for the candidate ``agents`` (any order); ``value`` is indexed by agent."""
    log = log if log is not None else SolveLog()
    net = fleet.network
    by_territory: dict[int, list[int]] = {}
    for a in agents:
        by_territory.setdefault(net.territory[int(a)], []).append(int(a))

    out = []
    for territory, cands in by_territory.items():
        runners = [
            r
            for r in fleet.by_territory.get(territory, ())
            if fleet.on_duty[r] and fleet.max_visits - fleet.visits[r] - reserve > 0
        ]
        if not runners:
            continue
        chosen = _solve(
            cands,
            runners,
            value,
            fleet,
            now,
            fuel_tk_per_km,
            labour_tk_per_min,
            reserve,
            options,
            log,
        )
        if chosen is None:
            log.fallbacks += 1
            ranked = sorted(cands, key=lambda a: -value[a])
            out += plan_rounds(ranked, fleet, now, target, reserve=reserve)
            continue
        routes = {r: [] for r in runners}
        for r, (stops, net_value) in chosen.items():
            route = nearest_neighbour(net, fleet.loc[r], stops)
            while route and not fleet.route_fits(r, route, now):
                stops.remove(min(stops, key=net_value.__getitem__))
                log.dropped += 1
                route = nearest_neighbour(net, fleet.loc[r], stops)
            routes[r] = route
        log.filled += _fill(
            routes, cands, value, fleet, now, fuel_tk_per_km, labour_tk_per_min, reserve
        )
        for r, route in routes.items():
            out += [v for a in route if (v := book_visit(fleet, r, a, now, target, "round"))]
    return out


def _route_km(net: Network, start: int, route: list[int]) -> float:
    stops = [start, *route, HUB]
    return sum(_km(net, a, b) for a, b in itertools.pairwise(stops))


def _fill(
    routes: dict[int, list[int]],
    cands: list[int],
    value: np.ndarray,
    fleet: Fleet,
    now: int,
    fuel_tk_per_km: np.ndarray,
    labour_tk_per_min: float,
    reserve: int,
) -> int:
    """Add unchosen agents, most valuable first, where a route still fits and the visit pays.

    Detours overstate what a stop adds to a nearest-neighbour route, so the program can leave
    room unused; each agent goes to the runner whose route grows the least, if its value beats
    the extra fuel and time.
    """
    net, added = fleet.network, 0
    taken = {a for route in routes.values() for a in route}
    for a in sorted((a for a in cands if a not in taken), key=lambda a: -value[a]):
        best = None
        for r, route in routes.items():
            if len(route) >= fleet.max_visits - fleet.visits[r] - reserve:
                continue
            trial = nearest_neighbour(net, fleet.loc[r], [*route, a])
            if not fleet.route_fits(r, trial, now):
                continue
            km = _route_km(net, fleet.loc[r], trial) - _route_km(net, fleet.loc[r], route)
            seconds = route_seconds(net, fleet.loc[r], trial, fleet.speed[r], fleet.visit_s)
            seconds -= route_seconds(net, fleet.loc[r], route, fleet.speed[r], fleet.visit_s)
            cost = km * fuel_tk_per_km[r] + seconds / 60 * labour_tk_per_min
            if value[a] > cost and (best is None or cost < best[0]):
                best = (cost, r, trial)
        if best is not None:
            routes[best[1]] = best[2]
            added += 1
    return added


def _solve(
    cands: list[int],
    runners: list[int],
    value: np.ndarray,
    fleet: Fleet,
    now: int,
    fuel_tk_per_km: np.ndarray,
    labour_tk_per_min: float,
    reserve: int,
    options: Milp,
    log: SolveLog,
) -> dict[int, tuple[list[int], dict[int, float]]] | None:
    """The program for one territory: ``{runner: (agents, net value per agent)}``."""
    net = fleet.network
    seed = seeds(net, cands, value, len(runners))
    rows: list[tuple[int, int, float, float]] = []  # (agent idx, runner idx, net Tk, seconds)
    budget = []
    for j, r in enumerate(runners):
        start, s, speed = fleet.loc[r], seed[j], fleet.speed[r]
        base_km = _km(net, start, s) + _km(net, s, HUB)
        budget.append(
            fleet.shift_end_s - max(now, fleet.free_at[r]) - travel_seconds(base_km, speed)
        )
        for i, a in enumerate(cands):
            detour = max(_km(net, start, a) + _km(net, a, s) - _km(net, start, s), 0.0)
            seconds = fleet.visit_s + travel_seconds(detour, speed)
            cost = detour * fuel_tk_per_km[r] + seconds / 60 * labour_tk_per_min
            if value[a] - cost > 0 and seconds <= budget[j]:
                rows.append((i, j, value[a] - cost, seconds))
    if not rows:
        return {}
    i_idx, j_idx, gain, secs = (np.array(c) for c in zip(*rows, strict=True))
    n_var, n_a, n_r = len(rows), len(cands), len(runners)
    var = np.arange(n_var)
    # constraint rows: agents, then runner visit counts, then runner seconds
    a_mat = coo_array(
        (
            np.concatenate([np.ones(n_var), np.ones(n_var), secs]),
            (np.concatenate([i_idx, n_a + j_idx, n_a + n_r + j_idx]), np.tile(var, 3)),
        ),
        shape=(n_a + 2 * n_r, n_var),
    ).tocsr()
    room = [fleet.max_visits - fleet.visits[r] - reserve for r in runners]
    upper = np.concatenate([np.ones(n_a), room, budget])
    started = time.perf_counter()
    with _quiet_stdout():
        res = milp(
            c=-gain,
            integrality=np.ones(n_var),
            bounds=Bounds(0, 1),
            constraints=LinearConstraint(a_mat, -np.inf, upper),
            options={"time_limit": options.time_limit_s, "mip_rel_gap": options.mip_rel_gap},
        )
    log.seconds += time.perf_counter() - started
    log.programs += 1
    if res.x is None:
        return None
    out: dict[int, tuple[list[int], dict[int, float]]] = {}
    for k in np.flatnonzero(res.x > 0.5):
        r, a = runners[j_idx[k]], cands[i_idx[k]]
        stops, net_value = out.setdefault(r, ([], {}))
        stops.append(a)
        net_value[a] = float(gain[k])
    return out
