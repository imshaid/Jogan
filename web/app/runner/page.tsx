"use client";

import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Check,
  Clock3,
  ExternalLink,
  Info,
  MapPinOff,
  Navigation,
  RotateCcw,
  TriangleAlert,
  Undo2,
  Warehouse,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { DayControl } from "@/components/day";
import { Tween } from "@/components/motion";
import { RouteMap, type Pin } from "@/components/route-map";
import { BagChart, HourAxis, HourGrid, ScheduleChart, TimeBar, timeDomain } from "@/components/runner-charts";
import { Staff } from "@/components/shell";
import {
  cx,
  Empty,
  ErrorNotice,
  PageHeader,
  Panel,
  Provenance,
  RiskBadge,
  Segmented,
  Select,
  Skeleton,
  Stat,
  TableToggle,
} from "@/components/ui";
import { DataTable } from "@/components/charts";
import type { Meta, NetworkAgent, Recommendation, RunnerSettings } from "@/lib/api";
import { useDay, useMeta, useNetwork, usePlan } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/lib/live";
import { directionsUrl, orderStops, planRoute, type Order, type Point, type RoutePlan, type StopInput } from "@/lib/route";

// Runner routes (on-site R4, D-034; redesigned in D-039): the fleet for a plan day, one runner's
// route on a map with times and the cash bag, and a checklist for the phone. Read-only towards
// Jogan: it shows the plan, and nothing here changes a decision. Locations are simulated.

export default function Page() {
  return (
    <Staff>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <RunnerView />
      </Suspense>
    </Staff>
  );
}

type Scope = "approved" | "plan";

type Runner = {
  id: string;
  territory: string;
  district: string;
  setting: string;
  hub: Point;
  approved: Recommendation[];
  pending: Recommendation[];
  plan: RoutePlan;
};

const sideP = (r: Recommendation) =>
  r.evidence.side === "efloat" ? r.evidence.p_stockout_efloat : r.evidence.p_stockout_cash;

function centroid(agents: NetworkAgent[]): Point {
  return {
    lat: agents.reduce((s, a) => s + a.lat, 0) / agents.length,
    lon: agents.reduce((s, a) => s + a.lon, 0) / agents.length,
  };
}

function buildFleet(
  items: Recommendation[],
  agents: Map<string, NetworkAgent>,
  meta: Meta,
  rules: RunnerSettings,
  scope: Scope,
  order: Order,
  lang: "en" | "bn",
): Runner[] {
  const by = new Map<string, Recommendation[]>();
  for (const r of items) {
    if (r.status === "rejected" || !agents.has(r.agent_id)) continue;
    by.set(r.runner_id, [...(by.get(r.runner_id) ?? []), r]);
  }
  const places = new Map(meta.territories.map((t) => [t.territory, t]));
  return [...by.entries()]
    .map(([id, recs]) => {
      const territory = recs[0].territory;
      const place = places.get(territory);
      const setting = place?.setting ?? agents.get(recs[0].agent_id)!.setting;
      const hub =
        rules.hubs[territory] ?? centroid([...agents.values()].filter((a) => a.territory === territory));
      const approved = recs.filter((r) => r.status === "approved");
      const pending = recs.filter((r) => r.status === "pending");
      const route = scope === "approved" ? approved : [...approved, ...pending];
      const inputs: StopInput[] = route.map((rec) => ({ rec, at: agents.get(rec.agent_id)!, p: sideP(rec) }));
      return {
        id,
        territory,
        district: place ? (lang === "bn" ? place.district_bn : place.district_en) : territory,
        setting,
        hub,
        approved,
        pending,
        plan: planRoute(hub, orderStops(hub, inputs, order), rules, setting),
      };
    })
    .sort((a, b) => a.territory.localeCompare(b.territory) || a.id.localeCompare(b.id));
}

// A query parameter as state (the runner in view), so a link or a reload keeps it.
function useParam(name: string): [string | null, (v: string | null) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = params.get(name);
  const set = useCallback(
    (v: string | null) => {
      const next = new URLSearchParams(params.toString());
      if (v) next.set(name, v);
      else next.delete(name);
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [name, params, pathname, router],
  );
  return [value, set];
}

// The runner's ticks, kept in this browser only (a per-device convenience, never sent anywhere).
const progressListeners = new Set<() => void>();
const progressKey = (day: string, runner: string) => `jogan-runner:${day}:${runner}`;

function readProgress(key: string) {
  try {
    return localStorage.getItem(key) ?? "[]";
  } catch {
    return "[]";
  }
}

function useProgress(day: string, runner: string): [Set<string>, (id: string, done: boolean) => void, () => void] {
  const key = progressKey(day, runner);
  const raw = useSyncExternalStore(
    (l) => {
      progressListeners.add(l);
      return () => progressListeners.delete(l);
    },
    () => readProgress(key),
    () => "[]",
  );
  const done = useMemo(() => {
    try {
      return new Set<string>(JSON.parse(raw));
    } catch {
      return new Set<string>();
    }
  }, [raw]);
  const write = (next: Set<string>) => {
    try {
      localStorage.setItem(key, JSON.stringify([...next]));
    } catch {
      // storage blocked: the ticks last until the page reloads
    }
    progressListeners.forEach((l) => l());
  };
  const mark = (id: string, isDone: boolean) => {
    const next = new Set(done);
    if (isDone) next.add(id);
    else next.delete(id);
    write(next);
  };
  return [done, mark, () => write(new Set())];
}

function RunnerView() {
  const { t, lang } = useLang();
  const r = t.runner;
  const meta = useMeta();
  const [day, setDay] = useDay(meta.data);
  const plan = usePlan(day);
  const network = useNetwork(day);
  const [runnerParam, setRunner] = useParam("runner");
  const [scopeChoice, setScope] = useState<Scope | null>(null);
  const [order, setOrder] = useState<Order>("short");
  // decisions arrive through the activity feed; a slow refresh also catches a missed one
  usePoll(plan.refresh, 60_000, !!plan.data);

  const items = useMemo(() => (plan.data?.plan_date === day ? plan.data.items : undefined), [plan.data, day]);
  const agents = useMemo(
    () => new Map((network.data?.plan_date === day ? network.data.agents : []).map((a) => [a.agent_id, a])),
    [network.data, day],
  );
  const anyApproved = !!items?.some((x) => x.status === "approved");
  // with nothing approved yet, open on the full plan so the page is never empty
  const scope: Scope = scopeChoice ?? (anyApproved ? "approved" : "plan");
  const rules = meta.data?.runners ?? null;
  const fleet = useMemo(
    () => (items && meta.data && rules && agents.size ? buildFleet(items, agents, meta.data, rules, scope, order, lang) : []),
    [items, agents, meta.data, rules, scope, order, lang],
  );
  const current = fleet.find((x) => x.id === runnerParam) ?? fleet.find((x) => x.plan.stops.length) ?? fleet[0];

  if (meta.error) return <ErrorNotice error={meta.error} onRetry={meta.reload} />;
  if (!meta.data || !day) return <Skeleton className="h-96 w-full" />;
  const error = plan.error ?? network.error;

  return (
    <div className="space-y-6">
      <PageHeader
        title={r.title}
        subtitle={r.subtitle}
        actions={<DayControl meta={meta.data} day={day} onChange={setDay} />}
      />

      {error ? (
        <ErrorNotice error={error} onRetry={() => (plan.error ? plan.reload() : network.reload())} />
      ) : !rules ? (
        <p className="flex items-center gap-2 rounded-xl border border-line bg-tray px-3.5 py-2.5 text-sm text-fg-2">
          <Info aria-hidden className="size-4 shrink-0" /> {r.noRules}
        </p>
      ) : !items || !network.data ? (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-130 w-full" />
        </div>
      ) : !current ? (
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
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <div className="flex items-center gap-2 text-xs text-fg-3">
              <span>{r.scope}</span>
              <Segmented<Scope>
                label={r.scope}
                size="sm"
                value={scope}
                onChange={setScope}
                options={[
                  { value: "approved", label: r.scopeApproved },
                  { value: "plan", label: r.scopePlan },
                ]}
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-fg-3">
              <span>{r.order}</span>
              <Segmented<Order>
                label={r.order}
                size="sm"
                value={order}
                onChange={setOrder}
                options={[
                  { value: "short", label: r.orderShort },
                  { value: "urgent", label: r.orderUrgent },
                ]}
              />
            </div>
            <span className="ml-auto">
              <Provenance kind="assumption" />
            </span>
          </div>

          <AnimatePresence initial={false}>
            {scope === "plan" && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <span className="flex items-start gap-2 rounded-xl border border-accent/70 bg-accent-tint px-3.5 py-2.5 text-sm text-ink">
                  <Clock3 aria-hidden className="mt-0.5 size-4 shrink-0" />
                  {r.previewBanner}
                </span>
              </motion.p>
            )}
          </AnimatePresence>

          <FleetBoard fleet={fleet} rules={rules} selected={current.id} onSelect={setRunner} />

          <RunnerRoute runner={current} fleet={fleet} day={day} scope={scope} onPick={setRunner} rules={rules} />

          <div className="flex items-start gap-2 text-xs text-fg-3">
            <Provenance kind="assumption" />
            <p>{r.note}</p>
          </div>
        </>
      )}
    </div>
  );
}

function StatusChips({ runner, compact }: { runner: Runner; compact?: boolean }) {
  const { t, f } = useLang();
  const r = t.runner;
  const p = runner.plan;
  const chips: { key: string; Icon: typeof Check; text: string; cls: string }[] = [];
  if (p.overShift) chips.push({ key: "shift", Icon: TriangleAlert, text: r.status.overShift, cls: "border-danger/25 bg-danger-tint text-danger-text" });
  if (p.overBagAt !== null) chips.push({ key: "bag", Icon: TriangleAlert, text: r.status.overBag, cls: "border-danger/25 bg-danger-tint text-danger-text" });
  if (runner.pending.length)
    chips.push({ key: "wait", Icon: Clock3, text: compact ? f.num(runner.pending.length) : r.waitingN(f.num(runner.pending.length)), cls: "border-accent/70 bg-accent-tint text-ink" });
  if (!chips.length && runner.approved.length) chips.push({ key: "ok", Icon: Check, text: r.status.ready, cls: "border-ok-text/20 bg-ok-tint text-ok-text" });
  return (
    <span className="flex flex-wrap gap-1">
      {chips.map((c) => (
        <span
          key={c.key}
          title={c.key === "wait" ? r.waitingN(f.num(runner.pending.length)) : c.text}
          className={cx("inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[11px] font-semibold whitespace-nowrap", c.cls)}
        >
          <c.Icon aria-hidden className="size-3" strokeWidth={2.5} />
          {c.text}
        </span>
      ))}
    </span>
  );
}

// Every runner of the day on one clock: a dispatch board.
function FleetBoard({
  fleet,
  rules,
  selected,
  onSelect,
}: {
  fleet: Runner[];
  rules: RunnerSettings;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const { t, f } = useLang();
  const r = t.runner;
  const domain = timeDomain(fleet.map((x) => x.plan), rules.shift);
  const active = fleet.filter((x) => x.plan.stops.length);
  const idle = fleet.filter((x) => !x.plan.stops.length);
  const out = active.length;
  return (
    <Panel
      title={r.fleet}
      aside={
        <span className="num text-xs text-fg-3">
          {r.runners}: {f.num(out)} / {f.num(fleet.length)}
        </span>
      }
      bodyClassName="p-0"
      footer={r.fleetNote}
    >
      <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-x-3 border-b border-line bg-tray/60 px-3 pt-2 pb-1 sm:grid-cols-[10rem_minmax(0,1fr)_7.5rem]">
        <span className="eyebrow text-fg-3">{r.pickRunner}</span>
        <HourAxis domain={domain} />
        <span className="eyebrow hidden text-right text-fg-3 sm:block">{r.kpiBack}</span>
      </div>
      <ul className="divide-y divide-line">
        {active.map((x, i) => {
          const on = x.id === selected;
          return (
            <li key={x.id} className="relative">
              {on && (
                <motion.span
                  layoutId="fleet-selected"
                  aria-hidden
                  className="absolute inset-0 border-l-[3px] border-ink bg-brand-tint/70"
                  transition={{ type: "spring", bounce: 0.15, duration: 0.4 }}
                />
              )}
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onSelect(x.id)}
                className={cx(
                  "relative grid w-full grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-x-3 px-3 py-2 text-left transition-colors sm:grid-cols-[10rem_minmax(0,1fr)_7.5rem]",
                  !on && "hover:bg-tray/70",
                )}
              >
                <span className="min-w-0">
                  <span className="mono block truncate text-[13px] font-semibold">{x.id}</span>
                  <span className="block truncate text-[11px] text-fg-3">
                    {x.district} · {f.num(x.plan.stops.length)} {t.common.visitsShort}
                  </span>
                  <span className="mt-0.5 block sm:hidden">
                    <StatusChips runner={x} compact />
                  </span>
                </span>
                <span className="relative">
                  <HourGrid domain={domain} />
                  {x.plan.stops.length ? (
                    <span className="anim-fade block" style={{ ["--i" as string]: i }}>
                      <TimeBar plan={x.plan} domain={domain} preview={new Set(x.pending.map((p) => p.agent_id))} />
                    </span>
                  ) : null}
                </span>
                <span className="hidden text-right sm:block">
                  <span className={cx("num block text-sm font-semibold", x.plan.overShift && "text-danger-text")}>
                    {x.plan.stops.length ? f.clock(x.plan.back) : "—"}
                  </span>
                  <span className="mt-0.5 flex justify-end">
                    <StatusChips runner={x} />
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {idle.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-line bg-tray/40 px-3 py-2.5">
          <span className="mr-1 text-xs text-fg-3">{r.idle(f.num(idle.length))}</span>
          {idle.map((x) => (
            <button
              key={x.id}
              type="button"
              aria-pressed={x.id === selected}
              onClick={() => onSelect(x.id)}
              className={cx(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2 text-xs transition-colors",
                x.id === selected ? "border-ink bg-ink text-white" : "border-line bg-surface hover:bg-tray",
              )}
            >
              <span className="mono font-semibold">{x.id}</span>
              {x.pending.length > 0 && (
                <span className={cx("num inline-flex items-center gap-0.5", x.id === selected ? "text-white/80" : "text-fg-3")}>
                  <Clock3 aria-hidden className="size-3" />
                  {f.num(x.pending.length)}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </Panel>
  );
}

function RunnerRoute({
  runner,
  fleet,
  day,
  scope,
  onPick,
  rules,
}: {
  runner: Runner;
  fleet: Runner[];
  day: string;
  scope: Scope;
  onPick: (id: string) => void;
  rules: RunnerSettings;
}) {
  const { t, f } = useLang();
  const r = t.runner;
  const p = runner.plan;
  const [done, mark, reset] = useProgress(day, runner.id);
  const [selected, setSelected] = useState<string | null>(null);
  // another runner or day starts with nothing selected
  const [shownFor, setShownFor] = useState(`${day}:${runner.id}`);
  if (shownFor !== `${day}:${runner.id}`) {
    setShownFor(`${day}:${runner.id}`);
    setSelected(null);
  }
  const [mapFailed, setMapFailed] = useState(false);
  const network = useNetwork(day);
  const agentAt = useMemo(() => new Map((network.data?.agents ?? []).map((a) => [a.agent_id, a])), [network.data]);
  const [table, setTable] = useState(false);
  const waiting = useMemo(() => new Set(runner.pending.map((x) => x.agent_id)), [runner.pending]);
  // only approved stops can be worked through; the next is the first not ticked
  const workable = p.stops.filter((s) => !waiting.has(s.rec.agent_id));
  const next = workable.find((s) => !done.has(s.rec.agent_id)) ?? null;
  const doneCount = workable.filter((s) => done.has(s.rec.agent_id)).length;
  const nextIndex = next ? p.stops.indexOf(next) : -1;
  const domain = timeDomain([p], rules.shift);

  const pins: Pin[] = [
    ...p.stops.map((s, i) => ({
      id: s.rec.agent_id,
      n: i + 1,
      at: s.at,
      state: waiting.has(s.rec.agent_id)
        ? ("waiting" as const)
        : done.has(s.rec.agent_id)
          ? ("done" as const)
          : s === next
            ? ("next" as const)
            : ("todo" as const),
      label: `${i + 1} · ${s.rec.agent_id}${waiting.has(s.rec.agent_id) ? ` · ${r.awaiting}` : ""}`,
    })),
    // outside the route (approved scope): visits still waiting, dashed
    ...(scope === "approved"
      ? runner.pending.map((x) => ({
          id: x.agent_id,
          n: null,
          at: agentAt.get(x.agent_id) ?? p.hub,
          state: "pending" as const,
          label: `${x.agent_id} · ${r.awaiting}`,
        }))
      : []),
  ];

  const pick = (id: string) => setSelected(id);
  const legUrl = directionsUrl(workable.filter((s) => !done.has(s.rec.agent_id)).map((s) => s.at));

  return (
    // on a phone the next stop and the list come first; on wide screens the figures lead
    <section aria-labelledby="runner-title" className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="eyebrow text-fg-3">{r.hubOf(runner.district)}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <h2 id="runner-title" className="mono text-[22px] leading-7 font-semibold tracking-tight">
              {runner.id}
            </h2>
            <StatusChips runner={runner} />
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-fg-3">
          {r.pickRunner}
          <Select value={runner.id} onChange={(e) => onPick(e.target.value)}>
            {fleet.map((x) => (
              <option key={x.id} value={x.id}>
                {x.id} · {f.num(x.plan.stops.length)}
              </option>
            ))}
          </Select>
        </label>
      </div>

      <div className="order-2 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:order-none xl:grid-cols-6">
        <Stat label={r.kpiStops} value={<Tween value={p.stops.length} format={(v) => f.num(v)} from={0} />} hint={runner.pending.length ? r.waitingN(f.num(runner.pending.length)) : r.approvedN(f.num(runner.approved.length))} />
        <Stat label={r.kpiKm} value={<Tween value={p.roadKm} format={(v) => `${f.num(v, 1)} ${r.km}`} from={0} />} hint={r.kmEst} />
        <Stat label={r.kpiTime} value={f.duration(p.back - p.start)} hint={`${f.clock(p.start)} – ${f.clock(p.back)}`} />
        <Stat
          label={r.kpiBack}
          value={p.stops.length ? f.clock(p.back) : "—"}
          tone={p.overShift ? "danger" : undefined}
          hint={r.shiftEnds(f.clock(p.shiftEnd))}
        />
        <Stat label={r.kpiLoad} value={<Tween value={p.load} format={f.tk} from={0} />} hint={r.usualLoad(f.tk(rules.bag_start_tk))} />
        <Stat
          label={r.kpiPeak}
          value={<Tween value={p.peak} format={f.tk} from={0} />}
          tone={p.overBagAt !== null ? "danger" : undefined}
          hint={r.ofLimit(f.tk(p.capacity))}
        />
      </div>

      {(p.overShift || p.overBagAt !== null) && (
        <div role="alert" className="order-1 space-y-1.5 rounded-xl border border-danger/30 bg-danger-tint px-3.5 py-2.5 text-sm text-danger-text xl:order-none">
          {p.overShift && (
            <p className="flex gap-2">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              {r.overShift(f.clock(p.back), f.clock(p.shiftEnd))}
            </p>
          )}
          {p.overBagAt !== null && (
            <p className="flex gap-2">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              {p.overBagAt < 0 ? r.overBagHub : r.overBag(f.num(p.overBagAt + 1))}
            </p>
          )}
        </div>
      )}

      <div className="order-1 grid grid-cols-1 gap-5 xl:order-none xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] xl:items-start">
        <section className="rounded-2xl border border-line bg-tray p-1 xl:sticky xl:top-20" aria-label={r.map}>
          <div className="flex min-h-10 flex-wrap items-center justify-between gap-2 px-3 py-1.5">
            <h3 className="eyebrow text-fg-2">{r.map}</h3>
            <span className="inline-flex items-center gap-1.5 text-[11px] text-fg-3">
              <Warehouse aria-hidden className="size-3.5" /> {r.hub}
            </span>
          </div>
          <div className="relative h-90 overflow-hidden rounded-xl border border-line bg-sunken shadow-card sm:h-130">
            <RouteMap
              hub={p.hub}
              hubLabel={r.hubOf(runner.district)}
              pins={pins}
              selected={selected}
              onSelect={pick}
              fitKey={`${day}:${runner.id}:${scope}`}
              label={r.map}
              onError={() => setMapFailed(true)}
            />
            {mapFailed && (
              <div className="absolute inset-x-4 top-4 flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-sm text-fg-2 shadow-pop">
                <MapPinOff aria-hidden className="size-4" />
                {t.network.mapError}
              </div>
            )}
          </div>
          <p className="px-3 pt-2 pb-1 text-xs text-fg-3">{r.mapNote}</p>
        </section>

        <div className="order-first space-y-4 xl:order-none">
          <NextStop
            stop={next}
            index={nextIndex}
            total={p.stops.length}
            doneCount={doneCount}
            workable={workable.length}
            onDone={() => next && mark(next.rec.agent_id, true)}
            onReset={reset}
            legUrl={legUrl}
            day={day}
          />
          <Panel
            title={r.stopsList}
            aside={<span className="num text-xs text-fg-3">{r.progress(f.num(doneCount), f.num(workable.length))}</span>}
            bodyClassName="p-0"
          >
            <StopList
              plan={p}
              waiting={waiting}
              done={done}
              next={next?.rec.agent_id ?? null}
              selected={selected}
              onSelect={pick}
              onMark={mark}
              day={day}
            />
            {scope === "approved" && runner.pending.length > 0 && (
              <Link
                href={`/queue?day=${day}&q=${encodeURIComponent(runner.id)}&status=pending`}
                className="flex items-center justify-between gap-2 border-t border-line bg-accent-tint/60 px-4 py-2.5 text-sm font-medium text-ink hover:bg-accent-tint"
              >
                <span className="inline-flex items-center gap-2">
                  <Clock3 aria-hidden className="size-4" /> {r.reviewPending(f.num(runner.pending.length))}
                </span>
                <span aria-hidden>→</span>
              </Link>
            )}
          </Panel>
          <p className="text-xs leading-relaxed text-fg-3">{r.deviceNote}</p>
        </div>
      </div>

      <div className="order-3 grid grid-cols-1 gap-5 xl:order-none xl:grid-cols-2">
        <Panel title={r.timeline} footer={r.timelineNote(f.num(p.speedKmh), f.num(p.visitMinutes))}>
          {p.stops.length ? (
            <ScheduleChart
              plan={p}
              domain={domain}
              done={done}
              next={next?.rec.agent_id ?? null}
              waiting={waiting}
              selected={selected}
              onPick={pick}
            />
          ) : (
            <p className="text-sm text-fg-2">{r.noStops}</p>
          )}
          <TimelineLegend />
        </Panel>
        <Panel
          title={r.bag}
          aside={<TableToggle open={table} onToggle={() => setTable((x) => !x)} />}
          footer={r.bagNote}
        >
          {p.stops.length ? <BagChart plan={p} label={r.bag} /> : <p className="text-sm text-fg-2">{r.noStops}</p>}
          {table && (
            <div className="mt-4">
              <DataTable
                caption={r.bag}
                head={["#", t.common.agent, r.kpiLoad, r.bag]}
                rows={[
                  [r.bagStart, "—", "—", f.tk(p.load)],
                  ...p.stops.map((s, i) => [
                    String(i + 1),
                    s.rec.agent_id,
                    s.handOver >= 0 ? r.give(f.tk(s.handOver)) : r.take(f.tk(-s.handOver)),
                    f.tk(s.bagAfter),
                  ]),
                ]}
              />
            </div>
          )}
        </Panel>
      </div>
    </section>
  );
}

function TimelineLegend() {
  const { t } = useLang();
  const r = t.runner;
  return (
    <ul className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-2">
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-3 w-4 rounded-[3px] bg-brand" /> {t.status.approved}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-3 w-4 rounded-[3px] border border-dashed border-ink/60 bg-accent-soft" /> {r.awaiting}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-3 w-4 rounded-[3px] bg-mark-muted" /> {r.doneLabel}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-0.5 w-4 rounded bg-line-strong" /> {r.travel}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-3 w-0.5 rounded bg-ink" /> {r.shiftEnd}
      </li>
    </ul>
  );
}

function Action({ handOver, big }: { handOver: number; big?: boolean }) {
  const { t, f } = useLang();
  const r = t.runner;
  const give = handOver >= 0;
  const amount = f.tk(Math.abs(handOver));
  const Icon = give ? ArrowUpFromLine : ArrowDownToLine;
  return (
    <div className="flex items-start gap-2.5">
      <span className={cx("flex shrink-0 items-center justify-center rounded-lg bg-brand-tint text-brand", big ? "size-9" : "size-7")}>
        <Icon aria-hidden className={big ? "size-5" : "size-4"} />
      </span>
      <div className="min-w-0">
        <div className={cx("num font-semibold", big ? "text-xl" : "text-[15px]")}>{give ? r.give(amount) : r.take(amount)}</div>
        <div className="text-xs text-fg-2">{give ? r.giveSub(amount) : r.takeSub(amount)}</div>
      </div>
    </div>
  );
}

function NextStop({
  stop,
  index,
  total,
  doneCount,
  workable,
  onDone,
  onReset,
  legUrl,
  day,
}: {
  stop: RoutePlan["stops"][number] | null;
  index: number;
  total: number;
  doneCount: number;
  workable: number;
  onDone: () => void;
  onReset: () => void;
  legUrl: string | null;
  day: string;
}) {
  const { t, f } = useLang();
  const r = t.runner;
  const share = workable ? doneCount / workable : 0;
  return (
    <section className="overflow-hidden rounded-2xl border border-ink/80 bg-ink p-1 text-white shadow-pop" aria-live="polite">
      <div className="flex items-center justify-between gap-3 px-3 py-2">
        <span className="eyebrow text-white/70">{r.next}</span>
        <span className="flex items-center gap-2">
          <span className="num text-xs text-white/70">{r.progress(f.num(doneCount), f.num(workable))}</span>
          {doneCount > 0 && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex h-6 items-center gap-1 rounded-md px-1.5 text-[11px] font-medium text-white/80 hover:bg-white/10 hover:text-white"
            >
              <RotateCcw aria-hidden className="size-3" /> {r.resetProgress}
            </button>
          )}
        </span>
      </div>
      <div aria-hidden className="mx-3 mb-2 h-1 overflow-hidden rounded-full bg-white/15">
        <motion.div
          className="h-full rounded-full bg-accent"
          initial={false}
          animate={{ width: `${share * 100}%` }}
          transition={{ type: "spring", bounce: 0, duration: 0.6 }}
        />
      </div>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={stop?.rec.agent_id ?? "done"}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -24 }}
          transition={{ duration: 0.25 }}
          className="rounded-xl bg-surface p-4 text-fg"
        >
          {!stop ? (
            <p className="flex items-center gap-2 text-sm font-medium">
              <Check aria-hidden className="size-4 text-ok-text" />
              {workable ? r.allDone : r.noStops}
            </p>
          ) : (
            <>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-xs text-fg-3">{r.stopOf(f.num(index + 1), f.num(total))}</div>
                  <Link href={`/agents/${stop.rec.agent_id}?day=${day}`} className="mono text-lg font-semibold hover:underline">
                    {stop.rec.agent_id}
                  </Link>
                  <div className="num text-xs text-fg-2">
                    {r.eta(f.clock(stop.arrive))} · {r.legKm(f.num(stop.legKm, 1), index === 0)}
                  </div>
                </div>
                <RiskBadge p={stop.p} side={stop.rec.evidence.side === "efloat" ? t.common.efloat : t.common.cash} compact />
              </div>
              <div className="mt-3">
                <Action handOver={stop.handOver} big />
                <p className="mt-1.5 text-xs text-fg-3">{r.target(f.tk(stop.rec.target_cash_tk), f.tk(stop.rec.evidence.cash_tk))}</p>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <a
                  href={`https://www.google.com/maps/dir/?api=1&destination=${stop.at.lat},${stop.at.lon}&travelmode=driving`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex min-h-11 items-center justify-center gap-2 rounded-xl border border-line-strong bg-surface px-3 text-sm font-semibold shadow-xs transition-transform hover:bg-tray active:scale-[0.97]"
                >
                  <Navigation aria-hidden className="size-4" /> {r.navigate}
                </a>
                <button
                  type="button"
                  onClick={onDone}
                  className="flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand px-3 text-sm font-semibold text-white shadow-xs transition-transform hover:bg-brand-strong active:scale-[0.97]"
                >
                  <Check aria-hidden className="size-4" strokeWidth={2.5} /> {r.markDone}
                </button>
              </div>
              {legUrl && (
                <a
                  href={legUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 flex items-center justify-center gap-1.5 text-xs font-medium text-brand hover:underline"
                >
                  {r.navigateLeg} <ExternalLink aria-hidden className="size-3" />
                </a>
              )}
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}

function StopList({
  plan,
  waiting,
  done,
  next,
  selected,
  onSelect,
  onMark,
  day,
}: {
  plan: RoutePlan;
  waiting: Set<string>;
  done: Set<string>;
  next: string | null;
  selected: string | null;
  onSelect: (id: string) => void;
  onMark: (id: string, done: boolean) => void;
  day: string;
}) {
  const { t, f } = useLang();
  const r = t.runner;
  const refs = useRef(new Map<string, HTMLLIElement>());
  useEffect(() => {
    if (selected) refs.current.get(selected)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);
  if (!plan.stops.length) return <p className="px-4 py-6 text-sm text-fg-2">{r.noStops}</p>;
  return (
    <ol className="max-h-130 divide-y divide-line overflow-y-auto">
      {plan.stops.map((s, i) => {
        const id = s.rec.agent_id;
        const isWaiting = waiting.has(id);
        const isDone = done.has(id);
        const isNext = next === id;
        return (
          <motion.li
            key={s.rec.id}
            layout="position"
            ref={(el) => {
              if (el) refs.current.set(id, el);
              else refs.current.delete(id);
            }}
            className={cx(
              "relative px-3 py-2.5 transition-colors",
              selected === id ? "bg-brand-tint/60" : "hover:bg-tray/60",
              isDone && "opacity-60",
            )}
          >
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => onSelect(id)}
                aria-label={`${i + 1} · ${id}`}
                className={cx(
                  "num flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors",
                  isWaiting
                    ? "border-2 border-dashed border-fg-2 bg-accent-tint text-ink"
                    : isDone
                      ? "bg-sunken text-fg-2"
                      : isNext
                        ? "bg-brand text-white ring-2 ring-brand/30 ring-offset-1"
                        : "border-2 border-brand bg-surface text-fg",
                )}
              >
                {isDone ? <Check aria-hidden className="size-3.5" strokeWidth={3} /> : i + 1}
              </button>
              <button type="button" onClick={() => onSelect(id)} className="min-w-0 flex-1 text-left">
                <span className="flex items-center gap-2">
                  <span className="mono text-sm font-semibold">{id}</span>
                  {isWaiting && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-accent/70 bg-accent-tint px-1.5 text-[10px] font-semibold text-ink">
                      <Clock3 aria-hidden className="size-2.5" /> {r.awaiting}
                    </span>
                  )}
                </span>
                <span className="num block truncate text-xs text-fg-3">
                  {f.clock(s.arrive)} · {r.legKm(f.num(s.legKm, 1), i === 0)}
                </span>
              </button>
              <span className="num shrink-0 text-right text-sm font-semibold">
                <span className="sr-only">{s.handOver >= 0 ? r.give(f.tk(s.handOver)) : r.take(f.tk(-s.handOver))}</span>
                <span aria-hidden className="inline-flex items-center gap-1">
                  {s.handOver >= 0 ? <ArrowUpFromLine className="size-3.5 text-brand" /> : <ArrowDownToLine className="size-3.5 text-brand" />}
                  {f.tk(Math.abs(s.handOver))}
                </span>
              </span>
            </div>
            <AnimatePresence initial={false}>
              {selected === id && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.22 }}
                  className="overflow-hidden"
                >
                  <div className="mt-2.5 space-y-2.5 rounded-xl border border-line bg-surface p-3 shadow-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Action handOver={s.handOver} />
                      <RiskBadge p={s.p} side={s.rec.evidence.side === "efloat" ? t.common.efloat : t.common.cash} />
                    </div>
                    <p className="text-xs text-fg-3">{r.target(f.tk(s.rec.target_cash_tk), f.tk(s.rec.evidence.cash_tk))}</p>
                    <div className="flex flex-wrap gap-2">
                      <a
                        href={`https://www.google.com/maps/dir/?api=1&destination=${s.at.lat},${s.at.lon}&travelmode=driving`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-2.5 text-[13px] font-medium shadow-xs hover:bg-tray"
                      >
                        <Navigation aria-hidden className="size-3.5" /> {r.navigate}
                      </a>
                      {!isWaiting && (
                        <button
                          type="button"
                          onClick={() => onMark(id, !isDone)}
                          className={cx(
                            "inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium shadow-xs transition-transform active:scale-[0.97]",
                            isDone ? "border border-line-strong bg-surface hover:bg-tray" : "bg-brand text-white hover:bg-brand-strong",
                          )}
                        >
                          {isDone ? <Undo2 aria-hidden className="size-3.5" /> : <Check aria-hidden className="size-3.5" />}
                          {isDone ? r.undo : r.markDone}
                        </button>
                      )}
                      <Link
                        href={`/agents/${id}?day=${day}`}
                        className="inline-flex h-8 items-center rounded-lg px-2.5 text-[13px] font-medium text-brand hover:bg-brand-tint"
                      >
                        {t.common.viewAgent}
                      </Link>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.li>
        );
      })}
    </ol>
  );
}
