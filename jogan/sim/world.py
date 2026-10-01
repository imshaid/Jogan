"""Generate a seeded synthetic world: territories, agents, runners, demand and ground truth.

Every random draw comes from a named stream derived from the seed, so changing one component
(say, anomalies) never shifts the draws of another (say, customer demand).

Public tables hold what a real operator would know (calendar, territories, agent master data,
runner roster). Truth tables hold what Jogan must never read directly: every customer attempt
(demand is censored once agents run dry), agents' true parameters, anomaly labels and
disruption days. ``jogan.sim.io`` writes the two groups to separate folders.
"""

from __future__ import annotations

import dataclasses
import math
import zlib
from typing import Any

import numpy as np
import pandas as pd

import jogan
from jogan.sim import demand
from jogan.sim.calendar import build_calendar
from jogan.sim.calibration import (
    Calibrated,
    achieved,
    calibrate,
    capped_lognormal_mean,
    caps,
    targets_flat,
)
from jogan.sim.config import SETTINGS, TX_TYPES, WEEKDAYS, SimConfig, Territory, Tickets

ANOMALY_PATTERNS = ("split", "spike", "night")
SIZE_CLASSES = ("small", "medium", "large")
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQUATOR = 111.320
EARTH_RADIUS_KM = 6371.0


def stream(seed: int, name: str) -> np.random.Generator:
    """Independent random stream for one component of the world."""
    return np.random.default_rng([seed, zlib.crc32(name.encode())])


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km; arguments broadcast like numpy arrays."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat, dlon = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def offset_latlon(lat: float, lon: float, east_km: np.ndarray, north_km: np.ndarray):
    new_lat = lat + north_km / KM_PER_DEG_LAT
    new_lon = lon + east_km / (KM_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat)))
    return new_lat, new_lon


def round_amounts(x: np.ndarray, tickets: Tickets, cap: int) -> np.ndarray:
    """Round to the configured grid (Tk 50 / 100 / 500 by size), floor and cap."""
    step = np.full_like(x, float(tickets.rounding[-1][1]))
    for bound, unit in reversed(tickets.rounding[:-1]):
        step = np.where(x < bound, float(unit), step)
    rounded = np.maximum(np.round(x / step) * step, tickets.min_tk)
    return np.minimum(rounded, cap).astype(np.int32)


def hat_day_names(mask: int) -> list[str]:
    return [name for i, name in enumerate(WEEKDAYS) if mask >> i & 1]


@dataclasses.dataclass
class World:
    config: SimConfig
    seed: int
    calibrated: Calibrated
    # public
    calendar: pd.DataFrame
    territories: pd.DataFrame
    agents: pd.DataFrame
    runners: pd.DataFrame
    roster: pd.DataFrame
    # truth
    demand: pd.DataFrame
    agent_truth: pd.DataFrame
    anomalies: pd.DataFrame
    disruptions: pd.DataFrame
    # in memory only: expected attempts per (agent, day, side) before hourly noise
    expected: np.ndarray

    def meta(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "profile": cfg.name,
            "seed": self.seed,
            "start": cfg.start.isoformat(),
            "end": cfg.end.isoformat(),
            "n_days": cfg.n_days,
            "timezone": cfg.calendar.timezone,
            "timestamps": "local time, naive",
            "config_hash": cfg.config_hash(),
            "jogan_version": jogan.__version__,
            "counts": {
                "territories": len(self.territories),
                "agents": len(self.agents),
                "runners": len(self.runners),
                "attempts": len(self.demand),
                "anomalous_agents": len(self.anomalies),
                "disruption_days": len(self.disruptions),
            },
            "calibration": {
                "params": self.calibrated.as_dict(),
                "targets": targets_flat(cfg.calibration),
                "achieved_expected": achieved(cfg, self.calibrated),
            },
        }


@dataclasses.dataclass(frozen=True)
class _Area:
    """One distributor territory in this world (a replica of a configured territory)."""

    code: str
    spec: Territory
    lat: float
    lon: float
    n_agents: int
    n_runners: int


def _areas(cfg: SimConfig) -> list[_Area]:
    specs = [cfg.geo.territory(code) for code in cfg.territories]
    n_areas = len(specs) * cfg.replicas
    sizes = [cfg.n_agents // n_areas + (i < cfg.n_agents % n_areas) for i in range(n_areas)]
    areas = []
    for k, spec in enumerate(specs):
        radius = cfg.geo.settings[spec.setting].radius_km
        for j in range(cfg.replicas):
            n = sizes[k * cfg.replicas + j]
            lat, lon = spec.lat, spec.lon
            if j > 0:  # replicas sit on a ring around the real hub; geometry only, no randomness
                angle = 2 * math.pi * (j - 1) / (cfg.replicas - 1)
                lat, lon = offset_latlon(
                    lat,
                    lon,
                    np.array(2.5 * radius * math.cos(angle)),
                    np.array(2.5 * radius * math.sin(angle)),
                )
                lat, lon = float(lat), float(lon)
            code = spec.code if cfg.replicas == 1 else f"{spec.code}{j + 1:02d}"
            runners = max(1, round(spec.runners * n / 100))
            areas.append(_Area(code, spec, round(lat, 6), round(lon, 6), n, runners))
    return areas


def _agents(cfg: SimConfig, seed: int, calib: Calibrated, areas: list[_Area]) -> pd.DataFrame:
    rng = stream(seed, "agents")
    hat_rng = stream(seed, "hat")
    a = cfg.agents
    frames = []
    for area_idx, area in enumerate(areas):
        n, spec = area.n_agents, area.spec
        geo = cfg.geo.settings[spec.setting]
        r = geo.radius_km * np.sqrt(rng.random(n))
        theta = 2 * math.pi * rng.random(n)
        lat, lon = offset_latlon(area.lat, area.lon, r * np.cos(theta), r * np.sin(theta))
        hub_km = haversine_km(lat, lon, area.lat, area.lon) * geo.road_factor
        volume = (
            calib.level
            * a.volume_scale[spec.setting]
            * rng.lognormal(-(a.volume_sigma**2) / 2, a.volume_sigma, n)
        )
        logit = (
            calib.mix_centre
            + demand.mix_tilt(cfg, spec)
            + cfg.mix.agent_sigma * rng.standard_normal(n)
        )
        co_share = demand.sigmoid(logit)

        cluster = np.minimum(
            (theta / (2 * math.pi) * a.hat_clusters).astype(int), a.hat_clusters - 1
        )
        masks = np.zeros(a.hat_clusters, dtype=np.int8)
        if "hat" in spec.patterns:
            lo, hi = a.hat_days_per_cluster
            for c in range(a.hat_clusters):
                days = hat_rng.choice(7, size=int(hat_rng.integers(lo, hi + 1)), replace=False)
                masks[c] = sum(1 << int(d) for d in days)
        open_h, close_h = a.hours[spec.setting]
        frames.append(
            pd.DataFrame(
                {
                    "area_idx": area_idx,
                    "agent_id": [f"{area.code}-{i + 1:03d}" for i in range(n)],
                    "territory": area.code,
                    "setting": spec.setting,
                    "lat": np.round(lat, 5),
                    "lon": np.round(lon, 5),
                    "hub_road_km": np.round(hub_km, 2),
                    "open_hour": np.int8(open_h),
                    "close_hour": np.int8(close_h),
                    "hat_mask": masks[cluster] if "hat" in spec.patterns else np.int8(0),
                    "hat_cluster": np.where("hat" in spec.patterns, cluster, -1).astype(np.int8),
                    "base_volume": volume,
                    "co_share": co_share,
                }
            )
        )
    agents = pd.concat(frames, ignore_index=True)

    lo_q, hi_q = a.size_quantiles
    rank = agents["base_volume"].rank(method="first").to_numpy() / len(agents)
    size = np.select([rank <= lo_q, rank <= hi_q], [0, 1], default=2)
    agents["size_class"] = pd.Categorical.from_codes(size, categories=list(SIZE_CLASSES))

    ticket = {
        s: float(capped_lognormal_mean(calib.ticket_mu[s], cfg.tickets.sigma[s], caps(cfg)[s]))
        for s in TX_TYPES
    }
    agents["typical_co_tk"] = agents["base_volume"] * agents["co_share"] * ticket["CO"]
    agents["typical_ci_tk"] = agents["base_volume"] * (1 - agents["co_share"]) * ticket["CI"]
    lo_d, hi_d = a.start_balance_days
    for col, typical in (("cash0_tk", "typical_co_tk"), ("efloat0_tk", "typical_ci_tk")):
        days = rng.uniform(lo_d, hi_d, len(agents))
        start = np.round(days * agents[typical].to_numpy() / 100) * 100
        agents[col] = np.maximum(start, a.min_start_balance_tk).astype(np.int64)
    return agents


def _anomaly_plan(cfg: SimConfig, seed: int, agents: pd.DataFrame) -> pd.DataFrame:
    rng = stream(seed, "anomalies")
    an = cfg.anomalies
    n = round(an.share * len(agents))
    if an.share > 0:
        n = max(n, 1)
    chosen = rng.choice(len(agents), size=n, replace=False)
    rows = []
    for k, agent in enumerate(chosen):
        pattern = ANOMALY_PATTERNS[k % len(ANOMALY_PATTERNS)]
        lo, hi = getattr(an, pattern).days
        length = int(rng.integers(lo, hi + 1))
        latest = max(0, cfg.n_days - length)
        first = int(rng.integers(min(an.start_after_days, latest), latest + 1))
        last = min(first + length, cfg.n_days) - 1
        factor = float(rng.uniform(*an.spike.factor)) if pattern == "spike" else float("nan")
        rows.append(
            {
                "agent_idx": int(agent),
                "pattern": pattern,
                "first_day": first,
                "last_day": last,
                "factor": factor,
            }
        )
    return pd.DataFrame(rows, columns=["agent_idx", "pattern", "first_day", "last_day", "factor"])


def _anomaly_attempts(
    cfg: SimConfig,
    seed: int,
    plan: pd.DataFrame,
    agents: pd.DataFrame,
    cal: pd.DataFrame,
    calib: Calibrated,
) -> tuple[pd.DataFrame, list[int]]:
    """Extra attempts injected by the split and night patterns."""
    rng = stream(seed, "anomaly_attempts")
    an = cfg.anomalies
    is_eid = cal["eid"].notna().to_numpy()
    rows: list[tuple[int, int, int, int, int]] = []  # agent, day, second of day, side, amount
    extra = []
    for p in plan.itertuples():
        before = len(rows)
        for day in range(p.first_day, p.last_day + 1):
            if p.pattern == "split":
                open_h, close_h = (
                    cfg.agents.eid_day_hours
                    if is_eid[day]
                    else (
                        int(agents.at[p.agent_idx, "open_hour"]),
                        int(agents.at[p.agent_idx, "close_hour"]),
                    )
                )
                for _ in range(
                    int(rng.integers(an.split.bursts_per_day[0], an.split.bursts_per_day[1] + 1))
                ):
                    size = int(rng.integers(an.split.burst_size[0], an.split.burst_size[1] + 1))
                    start = int(
                        rng.integers(open_h * 3600, close_h * 3600 - an.split.burst_minutes * 60)
                    )
                    offsets = np.sort(rng.integers(0, an.split.burst_minutes * 60, size))
                    amounts = rng.choice(an.split.amounts, size)
                    rows += [
                        (p.agent_idx, day, start + int(o), 0, int(v))
                        for o, v in zip(offsets, amounts, strict=True)
                    ]
            elif p.pattern == "night" and rng.random() < an.night.day_prob:
                k = int(rng.integers(an.night.per_day[0], an.night.per_day[1] + 1))
                seconds = rng.integers(an.night.hours[0] * 3600, an.night.hours[1] * 3600, k)
                sides = rng.integers(0, 2, k)
                for sec, side in zip(seconds, sides, strict=True):
                    tx = TX_TYPES[side]
                    raw = rng.lognormal(calib.ticket_mu[tx], cfg.tickets.sigma[tx], 1)
                    amount = int(round_amounts(raw, cfg.tickets, caps(cfg)[tx])[0])
                    rows.append((p.agent_idx, day, int(sec), int(side), amount))
        extra.append(len(rows) - before)
    frame = pd.DataFrame(rows, columns=["agent_idx", "day", "second", "side", "amount"])
    return frame, extra


def _runners(
    cfg: SimConfig, seed: int, areas: list[_Area], cal: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = cfg.runners
    runners = pd.DataFrame(
        [
            {
                "runner_id": f"{area.code}-R{j + 1}",
                "territory": area.code,
                "shift_start": np.int8(r.shift[0]),
                "shift_end": np.int8(r.shift[1]),
                "max_visits": np.int16(r.max_visits),
                "bag_capacity_tk": np.int64(r.bag_capacity_tk),
                "visit_minutes": np.int16(r.visit_minutes),
                "speed_kmh": cfg.geo.settings[area.spec.setting].runner_speed_kmh,
            }
            for area in areas
            for j in range(area.n_runners)
        ]
    )
    rng = stream(seed, "roster")
    present = rng.random((len(cal), len(runners))) >= r.absence_prob
    if r.off_on_eid_day:
        present &= ~cal["eid"].notna().to_numpy()[:, None]
    roster = pd.DataFrame(
        {
            "date": np.repeat(cal["date"].to_numpy(), len(runners)),
            "runner_id": np.tile(runners["runner_id"].to_numpy(), len(cal)),
            "on_duty": present.ravel(),
        }
    )
    return runners, roster


def build_world(cfg: SimConfig, seed: int) -> World:
    """Generate the world for a config and seed. Same inputs give identical outputs."""
    calib = calibrate(cfg)
    cal = build_calendar(cfg.calendar, cfg.start, cfg.end)
    n_days = len(cal)
    areas = _areas(cfg)
    agents = _agents(cfg, seed, calib, areas)
    n_agents = len(agents)
    area_idx = agents["area_idx"].to_numpy()

    # Territory-day factors and disruptions.
    rng = stream(seed, "disruptions")
    terr = {
        s: np.stack(
            [demand.territory_day_factors(cal, cfg, a.spec, calib.surge_count)[s] for a in areas]
        )
        for s in TX_TYPES
    }
    p_dis = np.stack([demand.disruption_prob(cal, cfg, a.spec) for a in areas])
    disrupted = rng.random(p_dis.shape) < p_dis
    dis_factor = np.where(disrupted, cfg.disruption.demand_factor, 1.0)

    # Agent-day multipliers: hat days, anomaly spikes, day noise.
    weekday_bit = 1 << cal["weekday"].to_numpy().astype(np.int64)
    on_hat = (agents["hat_mask"].to_numpy().astype(np.int64)[:, None] & weekday_bit[None, :]) > 0
    agent_day = np.where(on_hat, cfg.hat.factor, 1.0) * dis_factor[area_idx]
    plan = _anomaly_plan(cfg, seed, agents)
    for p in plan[plan["pattern"] == "spike"].itertuples():
        agent_day[p.agent_idx, p.first_day : p.last_day + 1] *= p.factor
    cv = cfg.noise.day_cv
    agent_day *= (
        stream(seed, "day_noise").gamma(1 / cv**2, cv**2, (n_agents, n_days)) if cv > 0 else 1.0
    )

    base = agents["base_volume"].to_numpy()
    share = {"CO": agents["co_share"].to_numpy(), "CI": 1 - agents["co_share"].to_numpy()}
    expected = np.stack(
        [(base * share[s])[:, None] * terr[s][area_idx] * agent_day for s in TX_TYPES], axis=-1
    )

    # Hourly rates and Poisson attempts: (agents, days, 24, sides).
    setting_idx = agents["setting"].map({s: i for i, s in enumerate(SETTINGS)}).to_numpy()
    hours = np.stack([demand.hour_weights(cal, cfg, s) for s in SETTINGS])
    rate = expected[:, :, None, :] * hours[setting_idx][:, :, :, None]
    cv = cfg.noise.hour_cv
    if cv > 0:
        rate *= stream(seed, "hour_noise").gamma(1 / cv**2, cv**2, rate.shape)
    counts = stream(seed, "counts").poisson(rate)

    flat = np.repeat(np.arange(counts.size), counts.ravel())
    agent_i, day_i, hour_i, side_i = np.unravel_index(flat, counts.shape)
    second = hour_i * 3600 + stream(seed, "timing").integers(0, 3600, flat.size)

    scale = demand.ticket_scale(cal, cfg, calib.surge_ticket)
    amount_rng = stream(seed, "amounts")
    amount = np.empty(flat.size, dtype=np.int32)
    for s, tx in enumerate(TX_TYPES):
        pick = side_i == s
        mu = calib.ticket_mu[tx] + np.log(scale[tx][day_i[pick]])
        raw = amount_rng.lognormal(mu, cfg.tickets.sigma[tx])
        amount[pick] = round_amounts(raw, cfg.tickets, caps(cfg)[tx])

    extra, extra_counts = _anomaly_attempts(cfg, seed, plan, agents, cal, calib)
    agent_i = np.concatenate([agent_i, extra["agent_idx"].to_numpy()])
    day_i = np.concatenate([day_i, extra["day"].to_numpy()])
    second = np.concatenate([second, extra["second"].to_numpy()])
    side_i = np.concatenate([side_i, extra["side"].to_numpy()])
    amount = np.concatenate([amount, extra["amount"].to_numpy(dtype=np.int32)])

    start = np.datetime64(cfg.start, "s")
    ts = start + (day_i.astype(np.int64) * 86400 + second.astype(np.int64)).astype("timedelta64[s]")
    order = np.lexsort((side_i, ts, agent_i))
    ids = agents["agent_id"].tolist()
    demand_df = pd.DataFrame(
        {
            "agent_id": pd.Categorical.from_codes(agent_i[order], categories=ids),
            "ts": ts[order],
            "tx_type": pd.Categorical.from_codes(side_i[order], categories=list(TX_TYPES)),
            "amount_tk": amount[order],
        }
    )

    territories = pd.DataFrame(
        {
            "territory": [a.code for a in areas],
            "base_code": [a.spec.code for a in areas],
            "district_en": [a.spec.district_en for a in areas],
            "district_bn": [a.spec.district_bn for a in areas],
            "setting": [a.spec.setting for a in areas],
            "lat": [a.lat for a in areas],
            "lon": [a.lon for a in areas],
            "radius_km": [cfg.geo.settings[a.spec.setting].radius_km for a in areas],
            "road_factor": [cfg.geo.settings[a.spec.setting].road_factor for a in areas],
            "patterns": [",".join(a.spec.patterns) for a in areas],
            "n_agents": [a.n_agents for a in areas],
            "n_runners": [a.n_runners for a in areas],
        }
    )
    runners, roster = _runners(cfg, seed, areas, cal)

    dis_area, dis_day = np.nonzero(disrupted)
    disruptions = pd.DataFrame(
        {
            "date": cal["date"].to_numpy()[dis_day],
            "territory": [areas[i].code for i in dis_area],
            "demand_factor": cfg.disruption.demand_factor,
            "speed_factor": cfg.disruption.speed_factor,
        }
    ).sort_values(["date", "territory"], ignore_index=True)

    dates = cal["date"].to_numpy()
    anomalies = pd.DataFrame(
        {
            "agent_id": [ids[i] for i in plan["agent_idx"]],
            "pattern": plan["pattern"].to_numpy(),
            "first_date": dates[plan["first_day"].to_numpy(dtype=int)],
            "last_date": dates[plan["last_day"].to_numpy(dtype=int)],
            "factor": plan["factor"].to_numpy(),
            "extra_attempts": np.array(extra_counts, dtype=np.int64),
        }
    )

    public_cols = [
        "agent_id",
        "territory",
        "setting",
        "lat",
        "lon",
        "hub_road_km",
        "size_class",
        "open_hour",
        "close_hour",
        "hat_mask",
    ]
    truth_cols = [
        "agent_id",
        "base_volume",
        "co_share",
        "hat_cluster",
        "typical_co_tk",
        "typical_ci_tk",
        "cash0_tk",
        "efloat0_tk",
    ]
    return World(
        config=cfg,
        seed=seed,
        calibrated=calib,
        calendar=cal,
        territories=territories,
        agents=agents[public_cols].copy(),
        runners=runners,
        roster=roster,
        demand=demand_df,
        agent_truth=agents[truth_cols].copy(),
        anomalies=anomalies,
        disruptions=disruptions,
        expected=expected,
    )
