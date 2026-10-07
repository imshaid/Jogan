// A runner's day from the plan (D-034, D-039): the order of the approved stops, when the runner
// reaches each shop, and the cash in the bag along the way. The order is a suggestion made here,
// not the dispatch program's road route, which the evidence does not store.

import type { Recommendation, RunnerSettings } from "./api";
import { RISK_BANDS } from "./format";

export type Point = { lat: number; lon: number };

export type StopInput = {
  rec: Recommendation;
  at: Point;
  // the higher of the two stock-out chances, the side the visit is for
  p: number;
};

export type Stop = StopInput & {
  legKm: number; // road km from the previous stop (or the hub)
  arrive: number; // minutes after midnight
  depart: number;
  handOver: number; // cash handed to the agent; negative when the runner collects
  bagAfter: number; // cash in the bag on leaving this shop
};

export type RoutePlan = {
  stops: Stop[];
  hub: Point;
  roadKm: number; // including the return to the hub
  returnKm: number;
  start: number; // shift start, minutes after midnight
  back: number; // back at the hub
  shiftEnd: number;
  load: number; // cash to load at the hub so no hand-over runs short
  peak: number; // most cash in the bag at any point
  capacity: number;
  overShift: boolean;
  overBagAt: number | null; // index of the first stop after which the bag is over its limit
  speedKmh: number;
  roadFactor: number;
  visitMinutes: number;
};

export type Order = "short" | "urgent";

export function haversineKm(a: Point, b: Point) {
  const r = Math.PI / 180;
  const h =
    Math.sin(((b.lat - a.lat) * r) / 2) ** 2 +
    Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

// Nearest next point from `start`, then 2-opt until no swap shortens start → path → end.
function shortestPath(start: Point, pts: Point[], end: Point | null): number[] {
  const left = pts.map((_, i) => i);
  const order: number[] = [];
  let at = start;
  while (left.length) {
    let best = 0;
    for (let k = 1; k < left.length; k++) {
      if (haversineKm(at, pts[left[k]]) < haversineKm(at, pts[left[best]])) best = k;
    }
    const i = left.splice(best, 1)[0];
    order.push(i);
    at = pts[i];
  }
  const node = (k: number) => (k < 0 ? start : k >= order.length ? end : pts[order[k]]);
  const d = (a: Point | null, b: Point | null) => (a && b ? haversineKm(a, b) : 0);
  for (let pass = 0, improved = true; improved && pass < 50; pass++) {
    improved = false;
    for (let i = 0; i < order.length - 1; i++) {
      for (let j = i + 1; j < order.length; j++) {
        // reverse order[i..j]: edges (i-1, i) and (j, j+1) become (i-1, j) and (i, j+1)
        const before = d(node(i - 1), node(i)) + d(node(j), node(j + 1));
        const after = d(node(i - 1), node(j)) + d(node(i), node(j + 1));
        if (after < before - 1e-9) {
          order.splice(i, j - i + 1, ...order.slice(i, j + 1).reverse());
          improved = true;
        }
      }
    }
  }
  return order;
}

// "short": the shortest round from the hub and back. "urgent": every high-risk stop first (in its
// own shortest order), then the rest.
export function orderStops(hub: Point, stops: StopInput[], order: Order): StopInput[] {
  if (order === "short") return shortestPath(hub, stops.map((s) => s.at), hub).map((i) => stops[i]);
  const urgent = stops.filter((s) => s.p >= RISK_BANDS.high);
  const rest = stops.filter((s) => s.p < RISK_BANDS.high);
  const first = shortestPath(hub, urgent.map((s) => s.at), null).map((i) => urgent[i]);
  const from = first.length ? first[first.length - 1].at : hub;
  const then = shortestPath(from, rest.map((s) => s.at), hub).map((i) => rest[i]);
  return [...first, ...then];
}

// Times from the shift start at the territory's speed, and the bag from the hand-overs.
export function planRoute(
  hub: Point,
  ordered: StopInput[],
  rules: RunnerSettings,
  setting: string,
): RoutePlan {
  const geo = rules.settings[setting] ?? Object.values(rules.settings)[0];
  const minutes = (km: number) => (km / geo.speed_kmh) * 60;
  const start = rules.shift[0] * 60;
  const shiftEnd = rules.shift[1] * 60;
  let at = hub;
  let clock = start;
  let km = 0;
  const handOvers = ordered.map((s) => s.rec.target_cash_tk - s.rec.evidence.cash_tk);
  // the least load that keeps the bag at or above zero after every hand-over
  let running = 0;
  let need = 0;
  for (const h of handOvers) {
    running += h;
    need = Math.max(need, running);
  }
  const load = Math.ceil(need / 100) * 100;
  let bag = load;
  let peak = load;
  let overBagAt: number | null = load > rules.bag_capacity_tk ? -1 : null;
  const stops: Stop[] = ordered.map((s, i) => {
    const legKm = haversineKm(at, s.at) * geo.road_factor;
    km += legKm;
    const arrive = clock + minutes(legKm);
    const depart = arrive + rules.visit_minutes;
    bag -= handOvers[i];
    peak = Math.max(peak, bag);
    if (overBagAt === null && bag > rules.bag_capacity_tk) overBagAt = i;
    clock = depart;
    at = s.at;
    return { ...s, legKm, arrive, depart, handOver: handOvers[i], bagAfter: bag };
  });
  const returnKm = ordered.length ? haversineKm(at, hub) * geo.road_factor : 0;
  const back = clock + minutes(returnKm);
  return {
    stops,
    hub,
    roadKm: km + returnKm,
    returnKm,
    start,
    back,
    shiftEnd,
    load,
    peak,
    capacity: rules.bag_capacity_tk,
    overShift: back > shiftEnd,
    overBagAt,
    speedKmh: geo.speed_kmh,
    roadFactor: geo.road_factor,
    visitMinutes: rules.visit_minutes,
  };
}

// Google Maps directions through the next stops. Mobile browsers take up to three waypoints
// (developers.google.com/maps/documentation/urls/get-started, checked 2026-10-07).
export function directionsUrl(stops: Point[]) {
  if (!stops.length) return null;
  const ll = (p: Point) => `${p.lat},${p.lon}`;
  const dest = stops[Math.min(stops.length, 4) - 1];
  const via = stops.slice(0, Math.min(stops.length, 4) - 1);
  const q = new URLSearchParams({ api: "1", destination: ll(dest), travelmode: "driving" });
  if (via.length) q.set("waypoints", via.map(ll).join("|"));
  return `https://www.google.com/maps/dir/?${q.toString()}`;
}
