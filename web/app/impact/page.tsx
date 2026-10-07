"use client";

import { CheckCircle2, CircleSlash, MinusCircle, TriangleAlert, XCircle } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { BarIntervals, DataTable, IntervalPlot, PairedBars, type IntervalRow } from "@/components/charts";
import { Tween } from "@/components/motion";
import { Public } from "@/components/shell";
import { cx, PageHeader, Panel, Provenance, Segmented, TableToggle } from "@/components/ui";
import impact from "@/lib/impact.json";
import { useMeta } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";

// Every number on this page is read from lib/impact.json, a copy of artifacts/metrics.json made
// by `make impact` and checked against it in CI (D-025). Nothing here is typed by hand.

type Window = "test" | "eid";
type Interval = { mean: number; low: number; high: number; n: number; sign?: string };
type Metric = "lost_per_1000" | "runner_km" | "known_cost_tk";

const POLICY_ORDER = ["fixed_round", "threshold", "safety_stock", impact.jogan, "oracle"] as const;
const BASELINES = impact.baselines as ("fixed_round" | "threshold" | "safety_stock")[];
const METRICS: Metric[] = ["lost_per_1000", "runner_km", "known_cost_tk"];

const KPIS = [
  "failed_requests",
  "value_turned_away_tk",
  "cash_out_turned_away_tk",
  "agent_commission_lost_tk",
  "runner_km",
  "runner_cost_tk",
  "agents_own_bank_trips",
  "known_cost_tk",
] as const;
type Kpi = (typeof KPIS)[number];

const policyKey = (p: string) => (p === impact.jogan ? "jogan" : p);

export default function Page() {
  return (
    <Public>
      <ImpactView />
    </Public>
  );
}

function ImpactView() {
  const { t, f } = useLang();
  const [w, setW] = useState<Window>("test");
  const versus = impact.versus;
  const vsQuo = versus.fixed_round[w].lost_per_1000 as Interval;
  const best = impact.fairness.best_baseline as "threshold";
  const vsBest = versus[best][w].lost_per_1000 as Interval;
  const [from, to] = impact.windows.test;
  const fmt: Record<Metric, (v: number) => string> = {
    lost_per_1000: (v) => f.signed(v, 1),
    runner_km: (v) => f.signed(v, 0),
    known_cost_tk: (v) => (v > 0 ? "+" : "") + f.tk(v),
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t.impact.title}
        subtitle={t.impact.subtitle(
          impact.seeds.length,
          f.day(from),
          f.day(to),
          `${f.num(impact.interval_level * 100)}%`,
        )}
        actions={
          <>
            <Provenance kind="evaluation" />
            <Segmented<Window>
              label={t.impact.window.test}
              value={w}
              onChange={setW}
              options={[
                { value: "test", label: t.impact.window.test },
                { value: "eid", label: t.impact.window.eid },
              ]}
            />
          </>
        }
      />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
        <div className="flex flex-col rounded-2xl border border-line bg-tray p-1 lg:col-span-2">
          <div className="flex flex-1 flex-col rounded-xl border border-line bg-surface p-5 shadow-card">
            <div className="eyebrow text-fg-3">{t.impact.hero}</div>
            <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[56px] leading-none font-semibold tracking-[-0.03em] text-brand tabular-nums">
                <Tween value={vsQuo.mean} format={(v) => f.signed(v, 1)} from={0} />
              </span>
              <span className="text-sm text-fg-2">{t.impact.heroUnit}</span>
            </div>
            <HeroBars w={w} />
          </div>
          <div className="px-3 pt-2 pb-1.5 text-xs text-fg-2">
            {t.impact.heroVs(t.impact.policiesShort.fixed_round)} ·{" "}
            <span className="num">{t.impact.interval(f.signed(vsQuo.low, 1), f.signed(vsQuo.high, 1))}</span>
          </div>
        </div>
        <DiffTile
          label={`${t.impact.metric.lost_per_1000} · ${t.impact.heroVs(t.impact.policiesShort[best])}`}
          iv={vsBest}
          format={fmt.lost_per_1000}
        />
        <div className="grid grid-cols-1 gap-3">
          <DiffTile
            label={`${t.impact.metric.runner_km} · ${t.impact.heroVs(t.impact.policiesShort.fixed_round)}`}
            iv={versus.fixed_round[w].runner_km as Interval}
            format={fmt.runner_km}
            compact
          />
          <DiffTile
            label={`${t.impact.metric.known_cost_tk} · ${t.impact.heroVs(t.impact.policiesShort.fixed_round)}`}
            iv={versus.fixed_round[w].known_cost_tk as Interval}
            format={fmt.known_cost_tk}
            compact
          />
        </div>
      </div>

      <BusinessPanel w={w} />

      <EventsPanel />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <LostByPolicy w={w} />
        <VersusPanel w={w} fmt={fmt} />
      </div>

      <Hypotheses />

      <NotWin />

      <Fairness />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <ForecastQuality />
        <AnomalyQuality />
      </div>

      <Ablations />

      <footer className="rounded-2xl border border-line bg-tray px-4 py-3.5 text-xs text-fg-2">
        <div className="eyebrow text-fg-3">{t.impact.source}</div>
        <p className="mt-1">{t.impact.sourceNote(impact.source, impact.generated_by)}</p>
        <p className="mt-1">
          {t.impact.configs}:{" "}
          {Object.entries(impact.config_hashes).map(([k, v]) => (
            <code key={k} className="mono mr-2 inline-block text-fg-3">
              {k}@{v}
            </code>
          ))}
        </p>
      </footer>
    </div>
  );
}

// Lost requests per 1,000 for Jogan and the status quo, on a scale from zero so the gap is not
// drawn bigger than it is.
function HeroBars({ w }: { w: Window }) {
  const { t, f } = useLang();
  const rows = [
    { key: "jogan", label: t.impact.policiesShort.jogan, v: impact.policies[impact.jogan as "jogan@20"][w].lost_per_1000.mean },
    { key: "fixed_round", label: t.impact.policiesShort.fixed_round, v: impact.policies.fixed_round[w].lost_per_1000.mean },
  ];
  const max = Math.max(...rows.map((r) => r.v));
  return (
    <dl className="mt-auto space-y-2 pt-6">
      {rows.map((r) => (
        <div key={r.key} className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-3 text-sm">
          <dt className={cx("truncate", r.key === "jogan" ? "font-semibold text-fg" : "text-fg-2")}>{r.label}</dt>
          <span aria-hidden className="h-2.5 rounded-full bg-sunken">
            <span
              className={cx("anim-grow-x block h-full rounded-full transition-[width] duration-700", r.key === "jogan" ? "bg-brand" : "bg-mark-muted")}
              style={{ width: `${(r.v / max) * 100}%` }}
            />
          </span>
          <dd className="num font-semibold">{f.num(r.v, 1)}</dd>
        </div>
      ))}
    </dl>
  );
}

function verdictOf(iv: Interval) {
  if (iv.sign === "lower") return "better" as const;
  if (iv.sign === "higher") return "worse" as const;
  return "same" as const;
}

function Verdict({ iv, lowerIsBetter = true }: { iv: Interval; lowerIsBetter?: boolean }) {
  const { t } = useLang();
  let v = verdictOf(iv);
  if (!lowerIsBetter && v !== "same") v = v === "better" ? "worse" : "better";
  const map = {
    better: { Icon: CheckCircle2, cls: "text-ok-text", label: t.impact.better },
    worse: { Icon: TriangleAlert, cls: "text-danger-text", label: t.impact.worse },
    same: { Icon: MinusCircle, cls: "text-fg-2", label: t.impact.noDiff },
  }[v];
  return (
    <span className={cx("inline-flex items-center gap-1 text-xs font-semibold", map.cls)}>
      <map.Icon aria-hidden className="size-3.5" />
      {map.label}
    </span>
  );
}

function DiffTile({
  label,
  iv,
  format,
  compact,
}: {
  label: string;
  iv: Interval;
  format: (v: number) => string;
  compact?: boolean;
}) {
  const { t } = useLang();
  return (
    <div className="anim-rise flex flex-col rounded-2xl border border-line bg-tray p-1">
      <div className="flex-1 rounded-xl border border-line bg-surface px-4 py-3.5 shadow-card">
        <div className="eyebrow text-fg-3">{label}</div>
        <div className={cx("num mt-2 leading-none font-semibold tracking-[-0.02em]", compact ? "text-[26px]" : "text-[34px]")}>
          <Tween value={iv.mean} format={format} from={0} />
        </div>
        <div className="num mt-2 text-xs text-fg-3">{t.impact.interval(format(iv.low), format(iv.high))}</div>
      </div>
      <div className="px-3 pt-1.5 pb-1">
        <Verdict iv={iv} />
      </div>
    </div>
  );
}

function LostByPolicy({ w }: { w: Window }) {
  const { t, f } = useLang();
  const [table, setTable] = useState(false);
  const rows: IntervalRow[] = POLICY_ORDER.map((p) => {
    const iv = impact.policies[p as keyof typeof impact.policies][w].lost_per_1000 as Interval;
    return { key: p, label: t.impact.policies[policyKey(p)], ...iv, emphasis: p === impact.jogan };
  });
  return (
    <Panel title={t.impact.lostChart} aside={<TableToggle open={table} onToggle={() => setTable((x) => !x)} />}>
      <p className="mb-4 text-xs text-fg-2">{t.impact.lostChartNote}</p>
      <BarIntervals rows={rows} format={(v) => f.num(v, 1)} />
      {table && (
        <div className="mt-4">
          <DataTable
            caption={t.impact.lostChart}
            head={[t.impact.tablePolicy, t.impact.tableMean, t.impact.tableLow, t.impact.tableHigh]}
            rows={rows.map((r) => [r.label, f.num(r.mean, 1), f.num(r.low, 1), f.num(r.high, 1)])}
          />
        </div>
      )}
    </Panel>
  );
}

function VersusPanel({ w, fmt }: { w: Window; fmt: Record<Metric, (v: number) => string> }) {
  const { t } = useLang();
  const [table, setTable] = useState(false);
  return (
    <Panel title={t.impact.diffChart} aside={<TableToggle open={table} onToggle={() => setTable((x) => !x)} />}>
      <p className="mb-4 text-xs text-fg-2">{t.impact.diffChartNote}</p>
      <div className="space-y-5">
        {METRICS.map((m) => {
          const rows: IntervalRow[] = BASELINES.map((b) => ({
            key: b,
            label: t.impact.policiesShort[b],
            ...(impact.versus[b][w][m] as Interval),
            emphasis: true,
          }));
          return (
            <div key={m}>
              <h3 className="mb-2 text-xs font-semibold text-fg">{t.impact.metric[m]}</h3>
              <IntervalPlot rows={rows} format={fmt[m]} height={28} zeroLabel="0" />
              {table && (
                <DataTable
                  caption={t.impact.metric[m]}
                  head={[t.impact.tablePolicy, t.impact.tableMean, t.impact.tableLow, t.impact.tableHigh]}
                  rows={rows.map((r) => [r.label, fmt[m](r.mean), fmt[m](r.low), fmt[m](r.high)])}
                />
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

// How the plan meets Bangladesh's calendar (D-035): visits a day and losses per day type, the
// status quo against Jogan. Two charts, one measure each; a table view of both.
const DAY_TYPES = ["eid", "pre_eid", "payday", "holiday", "bank_weekend", "ordinary"] as const;

function EventsPanel() {
  const { t, f } = useLang();
  const e = t.impact.events;
  const [table, setTable] = useState(false);
  const ev = impact.events as Record<string, { days: number; policies: Record<string, Record<string, Interval>>; versus_quo: Record<string, Interval> }>;
  const kinds = DAY_TYPES.filter((k) => k in ev);
  const rows = (m: "visits_per_day" | "lost_per_1000") =>
    kinds.map((k) => ({
      key: k,
      label: `${e.types[k]} · ${e.days(f.num(ev[k].days))}`,
      a: ev[k].policies.fixed_round[m].mean,
      b: ev[k].policies[impact.jogan][m].mean,
    }));
  const quo = t.impact.policiesShort.fixed_round;
  return (
    <Panel title={e.title} aside={<TableToggle open={table} onToggle={() => setTable((x) => !x)} />}>
      <p className="mb-4 max-w-3xl text-sm text-fg-2">{e.lead}</p>
      {table ? (
        <DataTable
          caption={e.title}
          head={[e.type, e.visits, e.visitsDiff, e.lost, e.lostDiff]}
          rows={kinds.map((k) => {
            const p = ev[k].policies;
            const v = ev[k].versus_quo;
            return [
              e.types[k],
              `${f.num(p.fixed_round.visits_per_day.mean, 1)} / ${f.num(p[impact.jogan].visits_per_day.mean, 1)}`,
              f.signed(v.visits_per_day.mean, 1),
              `${f.num(p.fixed_round.lost_per_1000.mean, 1)} / ${f.num(p[impact.jogan].lost_per_1000.mean, 1)}`,
              f.signed(v.lost_per_1000.mean, 1),
            ];
          })}
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <div>
            <h3 className="eyebrow mb-2 text-fg-3">{e.visits}</h3>
            <PairedBars rows={rows("visits_per_day")} aLabel={quo} bLabel="Jogan" format={(v) => f.num(v, 0)} />
          </div>
          <div>
            <h3 className="eyebrow mb-2 text-fg-3">{e.lost}</h3>
            <PairedBars rows={rows("lost_per_1000")} aLabel={quo} bLabel="Jogan" format={(v) => f.num(v, 0)} />
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-fg-3">{e.note}</p>
    </Panel>
  );
}

// Business KPIs per 1,000 agents a month, Jogan minus a baseline (D-033); negative is a saving.
function BusinessPanel({ w }: { w: Window }) {
  const { t, f } = useLang();
  const biz = impact.business;
  const best = impact.fairness.best_baseline as "threshold";
  const fmt = (k: Kpi, v: number) => (k.endsWith("_tk") ? (v > 0 ? "+" : "") + f.tk(v) : f.signed(v, 0));
  const cell = (k: Kpi, iv: Interval) => (
    <td className="px-4 py-2.5 align-top">
      <div className="num font-semibold">{fmt(k, iv.mean)}</div>
      <div className="num hidden text-xs text-fg-3 sm:block">{t.impact.interval(fmt(k, iv.low), fmt(k, iv.high))}</div>
      <Verdict iv={iv} />
    </td>
  );
  const vs = (b: "fixed_round" | "threshold") => biz.versus[b][w].kpis;
  const saving = vs("fixed_round").known_cost_tk.per_1000_agents_month as Interval;
  return (
    <Panel title={t.impact.business.title} aside={<Provenance kind="evaluation" />} bodyClassName="p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm sm:min-w-[34rem]">
          <thead className="eyebrow text-left text-fg-3">
            <tr className="border-b border-line">
              <th scope="col" className="px-4 py-2.5 font-medium">
                {t.impact.business.kpi}
              </th>
              <th scope="col" className="px-4 py-2.5 font-medium">
                {t.impact.heroVs(t.impact.policiesShort.fixed_round)}
              </th>
              <th scope="col" className="px-4 py-2.5 font-medium">
                {t.impact.heroVs(t.impact.policiesShort[best])}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {KPIS.map((k) => (
              <tr key={k}>
                <th scope="row" className="px-4 py-2.5 text-left align-top font-medium">
                  {t.impact.business.kpis[k]}
                </th>
                {cell(k, vs("fixed_round")[k].per_1000_agents_month as Interval)}
                {cell(k, vs(best)[k].per_1000_agents_month as Interval)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-1.5 border-t border-line px-4 py-3 text-sm text-fg-2">
        <p className="font-medium text-fg">
          {t.impact.business.roi(f.tk(-saving.mean), f.tk(-saving.high), f.tk(-saving.low))}
        </p>
        <p className="text-xs">{t.impact.business.note(f.num(biz.agents))}</p>
      </div>
    </Panel>
  );
}

function HoldsTag({ holds }: { holds: boolean }) {
  const { t } = useLang();
  return holds ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-ok-text/20 bg-ok-tint py-0.5 pr-2 pl-1.5 text-xs font-semibold whitespace-nowrap text-ok-text">
      <CheckCircle2 aria-hidden className="size-3.5" /> {t.impact.holds}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full border border-danger/25 bg-danger-tint py-0.5 pr-2 pl-1.5 text-xs font-semibold whitespace-nowrap text-danger-text">
      <XCircle aria-hidden className="size-3.5" /> {t.impact.fails}
    </span>
  );
}

function Hypotheses() {
  const { t } = useLang();
  const h = impact.hypotheses;
  return (
    <Panel title={t.impact.hypotheses} bodyClassName="p-0">
      <ul className="divide-y divide-line">
        {(Object.keys(h) as (keyof typeof h)[]).map((k) => (
          <li key={k} className="flex flex-wrap items-start gap-x-4 gap-y-2 px-4 py-3.5">
            <span className="mono flex h-6 w-9 shrink-0 items-center justify-center rounded-md bg-ink text-xs font-semibold text-white">
              {k}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-fg first-letter:uppercase">{t.impact.hypothesis[k] ?? h[k].statement}</p>
              {k === "H1" && (
                <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-2">
                  {BASELINES.map((b) => (
                    <li key={b}>
                      {t.impact.policiesShort[b]}: {t.impact.verdict[impact.versus[b].test.break_even] ?? impact.versus[b].test.break_even}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {h[k].holds === null ? (
              <span className="text-xs text-fg-2">{t.impact.perBaseline}</span>
            ) : (
              <HoldsTag holds={h[k].holds as boolean} />
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function NotWin() {
  const { t, f } = useLang();
  const split = impact.anomaly.windows_by_pattern.split;
  const items: ReactNode[] = [
    t.impact.notWinH4(impact.fairness.worse_groups.map((g) => g.split("=")[1]).join(", ")),
    t.impact.notWinH3(impact.coverage_misses.cells, impact.coverage_misses.overall),
    t.impact.notWinOracle(f.num(impact.oracle_gap.mean, 1)),
    t.impact.notWinAnomaly(split.detected, split.windows),
    t.impact.notWinCosts,
  ];
  return (
    <section id="not-win" className="rounded-2xl border border-warn-mark/50 bg-warn-tint p-1" aria-labelledby="not-win-title">
      <div className="px-3 py-2">
        <h2 id="not-win-title" className="flex items-center gap-2 text-sm font-semibold text-ink">
          <CircleSlash aria-hidden className="size-4" /> {t.impact.notWin}
        </h2>
        <p className="mt-0.5 text-xs text-warn-text">{t.impact.notWinLead}</p>
      </div>
      <ul className="divide-y divide-line rounded-xl border border-warn-mark/30 bg-surface text-sm text-fg shadow-card">
        {items.map((x, i) => (
          <li key={i} className="flex gap-3 px-4 py-2.5">
            <span aria-hidden className="mono mt-px text-xs text-warn-text">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span>{x}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Fairness() {
  const { t, f, lang } = useLang();
  const meta = useMeta();
  const [table, setTable] = useState(false);
  const names = new Map(
    (meta.data?.territories ?? []).map((x) => [x.territory, lang === "bn" ? x.district_bn : x.district_en]),
  );
  const groups = impact.fairness.groups;
  const best = impact.fairness.best_baseline;
  const groupLabel = (col: string, g: string) =>
    col === "territory" ? `${names.get(g) ?? g} (${g})` : col === "setting" ? displaySetting(g, t) : displaySize(g, t);
  return (
    <Panel
      title={t.impact.fairness}
      aside={<TableToggle open={table} onToggle={() => setTable((x) => !x)} />}
    >
      <p className="mb-4 text-xs text-fg-2">{t.impact.fairnessNote(t.impact.policiesShort[best])}</p>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {(Object.keys(groups) as (keyof typeof groups)[]).map((col) => {
          const entries = Object.entries(groups[col]) as [string, { difference: Interval }][];
          const rows: IntervalRow[] = entries.map(([g, v]) => {
            const worse = v.difference.sign === "higher";
            return {
              key: g,
              label: (
                <>
                  {groupLabel(col, g)}
                  {worse && <span className="ml-1 font-semibold text-danger-text">▲ {t.impact.worse}</span>}
                </>
              ),
              ...v.difference,
              emphasis: worse,
            };
          });
          return (
            <div key={col}>
              <h3 className="mb-2 text-xs font-semibold text-fg">{t.impact.group[col]}</h3>
              <IntervalPlot rows={rows} format={(v) => f.signed(v, 1)} height={30} zeroLabel="0" />
              {table && (
                <DataTable
                  caption={t.impact.group[col]}
                  head={[t.impact.tableGroup, t.impact.tableMean, t.impact.tableLow, t.impact.tableHigh]}
                  rows={entries.map(([g, v]) => [groupLabel(col, g), f.signed(v.difference.mean, 1), f.signed(v.difference.low, 1), f.signed(v.difference.high, 1)])}
                />
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

type Dict = ReturnType<typeof useLang>["t"];

function displaySetting(g: string, t: Dict) {
  return t.agent.setting[g] ?? g;
}

function displaySize(g: string, t: Dict) {
  return t.agent.size[g] ?? g;
}

function ForecastQuality() {
  const { t, f } = useLang();
  const fc = impact.forecast;
  const levels = Object.keys(fc.cash.intervals_truth) as (keyof typeof fc.cash.intervals_truth)[];
  return (
    <Panel title={t.impact.forecast} aside={<Provenance kind="evaluation" />}>
      <p className="mb-3 text-xs text-fg-2">{t.impact.forecastNote}</p>
      <DataTable
        caption={t.impact.forecast}
        head={[t.impact.nominal, `${t.impact.coverage} · ${t.common.cash}`, `${t.impact.coverage} · ${t.common.efloat}`]}
        rows={levels.map((l) => [
          `${f.num(Number(l))}%`,
          f.pct(fc.cash.intervals_truth[l].coverage, 1),
          f.pct(fc.efloat.intervals_truth[l].coverage, 1),
        ])}
      />
      <h3 className="mt-5 mb-1 text-xs font-semibold text-fg">{t.impact.brier}</h3>
      <DataTable
        head={["", t.common.cash, t.common.efloat]}
        rows={[
          [t.impact.brierModel, f.num(fc.cash.stockout.model_cqr.brier, 3), f.num(fc.efloat.stockout.model_cqr.brier, 3)],
          [t.impact.brierEmpirical, f.num(fc.cash.stockout.empirical.brier, 3), f.num(fc.efloat.stockout.empirical.brier, 3)],
        ]}
      />
    </Panel>
  );
}

function AnomalyQuality() {
  const { t, f } = useLang();
  const a = impact.anomaly;
  const patterns = Object.entries(a.windows_by_pattern) as [string, { detected: number; windows: number }][];
  return (
    <Panel title={t.impact.anomaly} aside={<Provenance kind="evaluation" />}>
      <p className="mb-3 text-xs text-fg-2">{t.impact.anomalyNote}</p>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Mini label={t.impact.precision} value={f.pct(a.flag_precision, 1)} />
        <Mini label={t.impact.baseRate} value={f.pct(a.base_rate, 2)} />
        {(Object.keys(a.precision_at_k_mean) as (keyof typeof a.precision_at_k_mean)[]).slice(0, 2).map((k) => (
          <Mini key={k} label={t.impact.precisionAtK(f.num(Number(k)))} value={f.pct(a.precision_at_k_mean[k])} />
        ))}
      </dl>
      <h3 className="mt-5 mb-2 text-xs font-semibold text-fg">{t.impact.windowsCaught}</h3>
      <ul className="space-y-2">
        {patterns.map(([p, v]) => (
          <li key={p} className="text-sm">
            <div className="flex justify-between gap-3">
              <span>{t.impact.pattern[p] ?? p}</span>
              <span className="num font-semibold">
                {f.num(v.detected)} / {f.num(v.windows)}
              </span>
            </div>
            <div aria-hidden className="mt-1.5 flex h-2 gap-[3px]">
              {Array.from({ length: v.windows }, (_, i) => (
                <span key={i} className={cx("flex-1 rounded-[2px]", i < v.detected ? "bg-brand" : "bg-sunken")} />
              ))}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-tray px-3 py-2.5">
      <dt className="text-[11px] text-fg-3">{label}</dt>
      <dd className="num mt-1 text-lg font-semibold">{value}</dd>
    </div>
  );
}

function Ablations() {
  const { t, f } = useLang();
  const ab = impact.ablations;
  const keys = Object.keys(ab) as (keyof typeof ab)[];
  return (
    <Panel title={t.impact.ablations}>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {(["lost_per_1000", "runner_km"] as const).map((m) => (
          <div key={m}>
            <h3 className="mb-2 text-xs font-semibold text-fg">{t.impact.metric[m]}</h3>
            <IntervalPlot
              rows={keys.map((k) => ({ key: k, label: t.impact.ablation[k] ?? k, ...(ab[k][m] as Interval), emphasis: true }))}
              format={(v) => f.signed(v, m === "runner_km" ? 0 : 1)}
              height={36}
              zeroLabel="0"
            />
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-fg-2">
        <Link href="/about" className="text-brand hover:underline">
          {t.nav.about} →
        </Link>
      </p>
    </Panel>
  );
}
