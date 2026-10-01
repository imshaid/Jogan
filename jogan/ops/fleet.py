"""Road distances and runners inside distributor territories.

A runner works one shift a day out of the territory hub. Scheduling a visit commits the
runner: it leaves when free, travels at today's speed (lower on disruption days), spends a
fixed time at the agent and must still reach the hub before the shift ends. Planners schedule
on a copy of the fleet and the environment schedules on the real one with the same code, so a
plan that fits on paper also fits in the simulation.
"""

from __future__ import annotations

import copy
import dataclasses
import math

import numpy as np
import pandas as pd

from jogan.sim.world import EARTH_RADIUS_KM, World

HUB = -1  # location code of a runner standing at its territory hub


@dataclasses.dataclass(frozen=True)
class Visit:
    """A runner visit as a policy requests it: bring the agent's cash to ``target_cash``.

    The runner brings cash and takes e-float back, or the reverse, so the agent's total
    liquidity never changes. The amount actually swapped is limited by the agent's balances
    and the runner's bag.
    """

    runner: int
    agent: int
    target_cash: int
    reason: str  # "round" (planned stop) or "call" (the agent ran low and called)


class Network:
    """Road distances between agents and hubs (public: locations are agent master data)."""

    def __init__(self, agents: pd.DataFrame, territories: pd.DataFrame) -> None:
        codes = territories["territory"].tolist()
        road = dict(zip(codes, territories["road_factor"], strict=True))
        self.territory_codes = codes
        self.territory = agents["territory"].map({c: i for i, c in enumerate(codes)}).tolist()
        self._lat = np.radians(agents["lat"].to_numpy()).tolist()
        self._lon = np.radians(agents["lon"].to_numpy()).tolist()
        self._road = agents["territory"].map(road).tolist()
        self.hub_km = agents["hub_road_km"].astype(float).tolist()
        hub = territories.set_index("territory").loc[agents["territory"], ["lat", "lon"]]
        north = agents["lat"].to_numpy() - hub["lat"].to_numpy()
        east = (agents["lon"].to_numpy() - hub["lon"].to_numpy()) * np.cos(np.radians(hub["lat"]))
        self.angle = np.arctan2(north, east).tolist()  # bearing from the hub, for sectors

    def km(self, src: int, dst: int) -> float:
        """Road km from an agent (or ``HUB``) to an agent of the same territory."""
        if src == HUB:
            return self.hub_km[dst]
        if src == dst:
            return 0.0
        p1, p2 = self._lat[src], self._lat[dst]
        a = (
            math.sin((p2 - p1) / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin((self._lon[dst] - self._lon[src]) / 2) ** 2
        )
        return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a)) * self._road[dst]


def travel_seconds(km: float, speed_kmh: float) -> int:
    return math.ceil(km / speed_kmh * 3600)


def route_seconds(
    net: Network, start: int, route: list[int], speed_kmh: float, visit_s: int
) -> int:
    """Time to drive from ``start`` through ``route`` (visiting each agent) back to the hub."""
    t, loc = 0, start
    for agent in route:
        t += travel_seconds(net.km(loc, agent), speed_kmh) + visit_s
        loc = agent
    return t + (travel_seconds(net.km(HUB, loc), speed_kmh) if loc != HUB else 0)


class Fleet:
    """Runner state for one day: who is on duty, where each runner is and when it is free."""

    def __init__(self, world: World, network: Network) -> None:
        r = world.runners
        cfg = world.config.runners
        self.network = network
        self.runner_ids = r["runner_id"].tolist()
        codes = {c: i for i, c in enumerate(network.territory_codes)}
        self.territory = r["territory"].map(codes).tolist()
        self.base_speed = r["speed_kmh"].astype(float).tolist()
        self.by_territory: dict[int, list[int]] = {}
        for i, t in enumerate(self.territory):
            self.by_territory.setdefault(t, []).append(i)
        self.shift = cfg.shift
        self.max_visits = cfg.max_visits
        self.visit_s = cfg.visit_minutes * 60
        self.capacity = cfg.bag_capacity_tk
        n = len(self.runner_ids)
        self.day = -1
        self.shift_end_s = 0
        self.on_duty = [False] * n
        self.visits = [0] * n
        self.free_at = [0] * n
        self.loc = [HUB] * n
        self.speed = list(self.base_speed)
        self.km = [0.0] * n
        self.busy_s = [0] * n
        self.bag = [0] * n

    def start_day(
        self, day: int, on_duty: list[bool], speed_factor: list[float], bag_tk: int
    ) -> None:
        n = len(self.runner_ids)
        self.day = day
        start = day * 86400 + self.shift[0] * 3600
        self.shift_end_s = day * 86400 + self.shift[1] * 3600
        self.on_duty = list(on_duty)
        self.visits = [0] * n
        self.free_at = [start] * n
        self.loc = [HUB] * n
        self.speed = [s * f for s, f in zip(self.base_speed, speed_factor, strict=True)]
        self.km = [0.0] * n
        self.busy_s = [0] * n
        self.bag = [min(bag_tk, self.capacity) if on else 0 for on in on_duty]

    def end_day(self) -> list[tuple[float, int]]:
        """Km and busy seconds (driving or at a stop) per runner today, with the trip home."""
        out = []
        for r, loc in enumerate(self.loc):
            home = self.network.km(HUB, loc) if loc != HUB else 0.0
            out.append((self.km[r] + home, self.busy_s[r] + travel_seconds(home, self.speed[r])))
        return out

    def arrival(self, runner: int, agent: int, now: int) -> int | None:
        """When ``runner`` would reach ``agent`` if sent now; ``None`` if it cannot go."""
        if not self.on_duty[runner] or self.visits[runner] >= self.max_visits:
            return None
        if self.territory[runner] != self.network.territory[agent]:
            return None
        speed = self.speed[runner]
        depart = max(now, self.free_at[runner])
        arrive = depart + travel_seconds(self.network.km(self.loc[runner], agent), speed)
        back = arrive + self.visit_s + travel_seconds(self.network.km(HUB, agent), speed)
        return arrive if back <= self.shift_end_s else None

    def route_fits(self, runner: int, route: list[int], now: int) -> bool:
        """Whether ``runner`` could still visit every agent of ``route`` in order today."""
        if not self.on_duty[runner] or self.visits[runner] + len(route) > self.max_visits:
            return False
        duration = route_seconds(
            self.network, self.loc[runner], route, self.speed[runner], self.visit_s
        )
        return max(now, self.free_at[runner]) + duration <= self.shift_end_s

    def commit(self, runner: int, agent: int, now: int) -> tuple[int, float] | None:
        """Schedule the visit; returns arrival time and km driven, or ``None`` if infeasible."""
        arrive = self.arrival(runner, agent, now)
        if arrive is None:
            return None
        leg = self.network.km(self.loc[runner], agent)
        self.busy_s[runner] += travel_seconds(leg, self.speed[runner]) + self.visit_s
        self.free_at[runner] = arrive + self.visit_s
        self.loc[runner] = agent
        self.visits[runner] += 1
        self.km[runner] += leg
        return arrive, leg

    def copy(self) -> Fleet:
        """An independent copy for planning; the network is shared."""
        out = copy.copy(self)
        for name in ("on_duty", "visits", "free_at", "loc", "speed", "km", "busy_s", "bag"):
            setattr(out, name, list(getattr(self, name)))
        return out
