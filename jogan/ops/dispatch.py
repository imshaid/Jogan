"""Runner dispatch helpers shared by every policy (the greedy baseline for M5's optimizer).

- :func:`send_first_free` answers calls one by one: each agent gets the runner that can be
  there first.
- :func:`plan_rounds` turns a prioritised list of agents into one route per runner: the top
  agents that fit the runners' capacity, split into compact sectors around the hub, each
  ordered by nearest neighbour. Stops that do not fit the shift are dropped, lowest priority
  first.

Both commit on the fleet they are given (a planning copy) and return the visits in the order
the environment must schedule them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from jogan.ops.fleet import Fleet, Network, Visit

Target = Callable[[int, int], float]  # (agent, arrival time) -> cash level after the visit


def book_visit(
    fleet: Fleet, runner: int, agent: int, now: int, target: Target, reason: str
) -> Visit | None:
    """Commit ``runner`` to ``agent`` and return the visit, or ``None`` if it does not fit."""
    scheduled = fleet.commit(runner, agent, now)
    if scheduled is None:
        return None
    return Visit(runner, agent, round(target(agent, scheduled[0]) / 100) * 100, reason)


def send_first_free(
    agents: Sequence[int], fleet: Fleet, now: int, target: Target, reason: str = "call"
) -> list[Visit]:
    """In priority order, send each agent the runner that arrives first; skip the unreachable."""
    out = []
    for a in agents:
        a = int(a)
        best, best_t = -1, None
        for r in fleet.by_territory.get(fleet.network.territory[a], ()):
            t = fleet.arrival(r, a, now)
            if t is not None and (best_t is None or t < best_t):
                best, best_t = r, t
        if best_t is not None and (v := book_visit(fleet, best, a, now, target, reason)):
            out.append(v)
    return out


def nearest_neighbour(net: Network, start: int, agents: Sequence[int]) -> list[int]:
    """Visit order that always drives to the closest remaining agent."""
    left, route, loc = list(agents), [], start
    while left:
        nxt = min(left, key=lambda a: net.km(loc, a))
        left.remove(nxt)
        route.append(nxt)
        loc = nxt
    return route


def plan_rounds(
    agents: Sequence[int],
    fleet: Fleet,
    now: int,
    target: Target,
    reserve: int = 0,
    reason: str = "round",
) -> list[Visit]:
    """Routes for the agents in priority order, keeping ``reserve`` visits per runner free."""
    net = fleet.network
    rank = {int(a): i for i, a in enumerate(agents)}
    by_territory: dict[int, list[int]] = {}
    for a in rank:
        by_territory.setdefault(net.territory[a], []).append(a)

    out = []
    for territory, wanted in by_territory.items():
        runners = [r for r in fleet.by_territory.get(territory, ()) if fleet.on_duty[r]]
        room = {r: max(0, fleet.max_visits - fleet.visits[r] - reserve) for r in runners}
        chosen = sorted(wanted[: sum(room.values())], key=lambda a: net.angle[a])
        for r in runners:
            sector, chosen = chosen[: room[r]], chosen[room[r] :]
            route = nearest_neighbour(net, fleet.loc[r], sector)
            while route and not fleet.route_fits(r, route, now):
                sector.remove(max(sector, key=rank.__getitem__))
                route = nearest_neighbour(net, fleet.loc[r], sector)
            out += [v for a in route if (v := book_visit(fleet, r, a, now, target, reason))]
    return out
