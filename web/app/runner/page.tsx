"use client";

import { ArrowDownToLine, ArrowUpFromLine, Bike, ExternalLink, Info } from "lucide-react";
import Link from "next/link";
import { Suspense, useMemo, useState } from "react";

import { DayControl } from "@/components/day";
import { Staff } from "@/components/shell";
import { Empty, ErrorNotice, PageHeader, Provenance, RiskBadge, Select, Skeleton } from "@/components/ui";
import type { NetworkAgent, Recommendation } from "@/lib/api";
import { useDay, useMeta, useNetwork, usePlan } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";

// The runner's phone screen (on-site R4, D-034): the approved visits of one runner on one day,
// in a suggested order, with what to hand over or collect at each shop. Read-only; nothing here
// changes a decision. Locations are simulated.

export default function Page() {
  return (
    <Staff>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <RunnerView />
      </Suspense>
    </Staff>
  );
}

type Stop = { rec: Recommendation; agent: NetworkAgent; km: number; handOver: number };
type Point = { lat: number; lon: number };

// Great-circle distance in km; the order is a suggestion, not the optimizer's road route.
function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const r = Math.PI / 180;
  const h =
    Math.sin(((b.lat - a.lat) * r) / 2) ** 2 +
    Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

// Nearest next stop, starting from the middle of the runner's territory.
// A to-scale sketch of the order: the territory centre (square), then each stop, numbered.
function RouteSketch({ start, stops, label }: { start: Point; stops: Stop[]; label: string }) {
  const W = 560;
  const H = 220;
  const pad = 22;
  const pts = [start, ...stops.map((s) => s.agent)];
  const kx = Math.cos((start.lat * Math.PI) / 180);
  const xs = pts.map((p) => p.lon * kx);
  const ys = pts.map((p) => p.lat);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const k = Math.min((W - 2 * pad) / Math.max(x1 - x0, 1e-6), (H - 2 * pad) / Math.max(y1 - y0, 1e-6));
  const ox = (W - (x1 - x0) * k) / 2;
  const oy = (H - (y1 - y0) * k) / 2;
  const xy = pts.map((p, i) => [ox + (xs[i] - x0) * k, H - (oy + (ys[i] - y0) * k)] as const);
  const len = xy.slice(1).reduce((a, [x, y], i) => a + Math.hypot(x - xy[i][0], y - xy[i][1]), 0);
  return (
    <figure className="rounded-2xl border border-line bg-tray p-1">
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full rounded-xl border border-line bg-surface" role="img" aria-label={label}>
        <polyline
          points={xy.map(([x, y]) => `${x},${y}`).join(" ")}
          fill="none"
          stroke="#0c55a4"
          strokeWidth={2}
          strokeLinejoin="round"
          className="anim-draw"
          style={{ ["--jg-len" as string]: Math.ceil(len) + 1 }}
        />
        <rect x={xy[0][0] - 6} y={xy[0][1] - 6} width={12} height={12} rx={2} fill="#111113" />
        {xy.slice(1).map(([x, y], i) => (
          <g key={i} className="anim-pop" style={{ ["--i" as string]: i }}>
            <circle cx={x} cy={y} r={10} fill="#ffffff" stroke="#0c55a4" strokeWidth={2} />
            <text x={x} y={y} dy="0.34em" textAnchor="middle" fontSize={10} fontWeight={700} fill="#111113">
              {i + 1}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="px-3 pt-1.5 pb-1 text-xs text-fg-3">{label}</figcaption>
    </figure>
  );
}

function route(recs: Recommendation[], agents: Map<string, NetworkAgent>): Stop[] {
  const left = recs.filter((r) => agents.has(r.agent_id));
  if (!left.length) return [];
  const area = [...agents.values()].filter((a) => a.territory === left[0].territory);
  let at = {
    lat: area.reduce((s, a) => s + a.lat, 0) / area.length,
    lon: area.reduce((s, a) => s + a.lon, 0) / area.length,
  };
  const out: Stop[] = [];
  while (left.length) {
    let best = 0;
    left.forEach((r, i) => {
      if (km(at, agents.get(r.agent_id)!) < km(at, agents.get(left[best].agent_id)!)) best = i;
    });
    const rec = left.splice(best, 1)[0];
    const agent = agents.get(rec.agent_id)!;
    out.push({ rec, agent, km: km(at, agent), handOver: rec.target_cash_tk - rec.evidence.cash_tk });
    at = agent;
  }
  return out;
}

function RunnerView() {
  const { t, f } = useLang();
  const r = t.runner;
  const meta = useMeta();
  const [day, setDay] = useDay(meta.data);
  const plan = usePlan(day);
  const network = useNetwork(day);
  const [picked, setPicked] = useState<string | null>(null);

  const items = useMemo(() => (plan.data?.plan_date === day ? plan.data.items : undefined), [plan.data, day]);
  const agents = useMemo(
    () => new Map((network.data?.plan_date === day ? network.data.agents : []).map((a) => [a.agent_id, a])),
    [network.data, day],
  );
  // runners with an approved visit, most stops first
  const runners = useMemo(() => {
    const n = new Map<string, number>();
    for (const x of items ?? []) if (x.status === "approved") n.set(x.runner_id, (n.get(x.runner_id) ?? 0) + 1);
    return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [items]);
  const runner = picked && runners.some(([id]) => id === picked) ? picked : (runners[0]?.[0] ?? null);
  const mine = (items ?? []).filter((x) => x.runner_id === runner);
  const stops = useMemo(
    () => route(mine.filter((x) => x.status === "approved"), agents),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [runner, items, agents],
  );
  const waiting = mine.filter((x) => x.status === "pending").length;
  const load = stops.reduce((s, x) => s + Math.max(x.handOver, 0), 0);
  const collect = stops.reduce((s, x) => s + Math.max(-x.handOver, 0), 0);
  const total = stops.reduce((s, x) => s + x.km, 0);
  const centre = useMemo(() => {
    const area = [...agents.values()].filter((a) => a.territory === stops[0]?.rec.territory);
    if (!area.length) return null;
    return {
      lat: area.reduce((s, a) => s + a.lat, 0) / area.length,
      lon: area.reduce((s, a) => s + a.lon, 0) / area.length,
    };
  }, [agents, stops]);

  if (meta.error) return <ErrorNotice error={meta.error} onRetry={meta.reload} />;
  if (!meta.data || !day) return <Skeleton className="h-96 w-full" />;
  const error = plan.error ?? network.error;

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <PageHeader
        title={r.title}
        subtitle={r.subtitle}
        actions={<DayControl meta={meta.data} day={day} onChange={setDay} />}
      />

      {error ? (
        <ErrorNotice error={error} onRetry={() => (plan.error ? plan.reload() : network.reload())} />
      ) : !items || !network.data ? (
        <Skeleton className="h-72 w-full" />
      ) : !runner ? (
        <div className="rounded-2xl border border-line bg-surface shadow-card">
          <Empty>
            <p>{r.none}</p>
            <Link href={`/queue?day=${day}`} className="font-medium text-brand hover:underline">
              {r.toQueue}
            </Link>
          </Empty>
        </div>
      ) : (
        <>
          <label className="block text-sm">
            <span className="eyebrow mb-1.5 block text-fg-3">{r.runner}</span>
            <Select value={runner} onChange={(e) => setPicked(e.target.value)} className="w-full">
              {runners.map(([id, n]) => (
                <option key={id} value={id}>
                  {r.option(id, f.num(n))}
                </option>
              ))}
            </Select>
          </label>

          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              [r.stops, f.num(stops.length)],
              [r.load, f.tk(load)],
              [r.collect, f.tk(collect)],
              [r.distance, `${f.num(total, 1)} km`],
            ].map(([k, v], i) => (
              <div key={k} className="anim-rise rounded-xl border border-line bg-surface px-3 py-2.5 shadow-card" style={{ ["--i" as string]: i }}>
                <dt className="eyebrow text-fg-3">{k}</dt>
                <dd className="num mt-1 text-lg font-semibold">{v}</dd>
              </div>
            ))}
          </dl>

          {waiting > 0 && (
            <p className="flex items-center gap-2 rounded-xl border border-brand/20 bg-brand-tint px-3.5 py-2.5 text-sm text-brand">
              <Info aria-hidden className="size-4 shrink-0" />
              {r.waiting(f.num(waiting))}
            </p>
          )}

          {centre && stops.length > 0 && <RouteSketch start={centre} stops={stops} label={r.sketch} />}

          <ol className="space-y-3">
            {stops.map((s, i) => {
              const give = s.handOver >= 0;
              const amount = f.tk(Math.abs(s.handOver));
              const p = s.rec.evidence.side === "cash" ? s.rec.evidence.p_stockout_cash : s.rec.evidence.p_stockout_efloat;
              const Icon = give ? ArrowUpFromLine : ArrowDownToLine;
              return (
                <li key={s.rec.id} className="anim-rise rounded-2xl border border-line bg-tray p-1" style={{ ["--i" as string]: i + 4 }}>
                  <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
                    <div className="flex items-center gap-3">
                      <span className="mono flex size-8 shrink-0 items-center justify-center rounded-lg bg-ink text-sm font-semibold text-white">
                        {i + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <Link href={`/agents/${s.rec.agent_id}?day=${day}`} className="mono font-semibold hover:underline">
                          {s.rec.agent_id}
                        </Link>
                        <div className="text-xs text-fg-3">{r.from(f.num(s.km, 1), i === 0)}</div>
                      </div>
                      <RiskBadge p={p} side={s.rec.evidence.side} compact />
                    </div>
                    <div className="mt-3 flex items-start gap-2.5">
                      <Icon aria-hidden className="mt-1 size-5 shrink-0 text-brand" />
                      <div>
                        <div className="num text-xl font-semibold">{give ? r.give(amount) : r.take(amount)}</div>
                        <div className="text-sm text-fg-2">{give ? r.giveSub(amount) : r.takeSub(amount)}</div>
                        <div className="mt-1 text-xs text-fg-3">{r.target(f.tk(s.rec.target_cash_tk), f.tk(s.rec.evidence.cash_tk))}</div>
                      </div>
                    </div>
                    <a
                      href={`https://www.google.com/maps/dir/?api=1&destination=${s.agent.lat},${s.agent.lon}&travelmode=driving`}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand px-4 text-sm font-semibold text-white hover:opacity-90"
                    >
                      <Bike aria-hidden className="size-4" /> {r.directions} <ExternalLink aria-hidden className="size-3.5" />
                    </a>
                  </div>
                </li>
              );
            })}
          </ol>

          <div className="flex items-start gap-2 text-xs text-fg-3">
            <Provenance kind="assumption" />
            <p>{r.note}</p>
          </div>
        </>
      )}
    </div>
  );
}
