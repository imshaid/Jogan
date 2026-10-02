"use client";

import { ArrowRight, ArrowUpRight, MapPinOff, X } from "lucide-react";
import Link from "next/link";
import { Suspense, useMemo, useState } from "react";

import { DayControl, Timeline } from "@/components/day";
import { NetworkMap, sideP, type RiskSide, type ShowFilter } from "@/components/network-map";
import { Staff } from "@/components/shell";
import {
  AnomalyBadge,
  ErrorNotice,
  PageHeader,
  Panel,
  Provenance,
  ReviewBadge,
  RiskBadge,
  Segmented,
  Skeleton,
  Stat,
  StatusBadge,
  TH,
  THEAD,
} from "@/components/ui";
import type { DayCount, Meta, NetworkAgent, Recommendation } from "@/lib/api";
import { RISK_BANDS, RISK_SHAPE } from "@/lib/format";
import { useDay, useMeta, useNetwork, usePlan } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";

export default function Page() {
  return (
    <Staff>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <NetworkView />
      </Suspense>
    </Staff>
  );
}

const SPARK_DAYS = 10;

// The last few plan days up to the one in view, for a KPI's bars.
function spark(days: DayCount[], i: number, key: "visits" | "manual_review" | "anomaly_flags") {
  if (i < 0) return undefined;
  const start = Math.max(0, i - SPARK_DAYS + 1);
  return { values: days.slice(start, i + 1).map((d) => d[key]), active: i - start };
}

function NetworkView() {
  const { t, f } = useLang();
  const meta = useMeta();
  const [day, setDay] = useDay(meta.data);
  const network = useNetwork(day);
  const plan = usePlan(day);
  const [side, setSide] = useState<RiskSide>("max");
  const [show, setShow] = useState<ShowFilter>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [mapFailed, setMapFailed] = useState(false);

  const agents = network.previous?.agents;
  const recs = useMemo(() => new Map((plan.data?.items ?? []).map((r) => [r.agent_id, r])), [plan.data]);
  const stats = useMemo(() => {
    if (!agents) return null;
    return {
      agents: agents.length,
      high: agents.filter((a) => sideP(a, side) >= RISK_BANDS.high).length,
      visits: agents.filter((a) => a.runner_id).length,
      review: agents.filter((a) => a.manual_review).length,
      flags: agents.filter((a) => a.anomaly).length,
    };
  }, [agents, side]);
  const pending = plan.data?.items.filter((r) => r.status === "pending").length;

  if (meta.error) return <ErrorNotice error={meta.error} onRetry={meta.reload} />;
  if (!meta.data || !day) return <Skeleton className="h-96 w-full" />;
  const chosen = agents?.find((a) => a.agent_id === selected) ?? null;
  const days = meta.data.days;
  const i = days.findIndex((d) => d.date === day);
  const delta = i > 0 ? days[i].visits - days[i - 1].visits : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t.network.title}
        subtitle={t.network.subtitle}
        actions={<DayControl meta={meta.data} day={day} onChange={setDay} playable />}
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <Stat
          label={t.network.kpiAgents}
          value={stats ? f.num(stats.agents) : "…"}
          hint={t.network.kpiTerritories(f.num(meta.data.territories.length))}
        />
        <Stat
          label={
            <>
              <span aria-hidden>{RISK_SHAPE.high}</span> {t.network.kpiHigh}
            </>
          }
          value={stats ? f.num(stats.high) : "…"}
          hint={side === "max" ? t.risk.higherSide : side === "cash" ? t.common.cash : t.common.efloat}
          tone="danger"
        />
        <Stat
          label={t.network.kpiVisits}
          value={stats ? f.num(stats.visits) : "…"}
          spark={spark(days, i, "visits")}
          hint={
            delta === null ? (
              t.network.kpiFirstDay
            ) : (
              <>
                <span className="num font-medium text-fg-2">{f.signed(delta)}</span>{" "}
                {t.network.kpiVsPrev(f.dayShort(days[i - 1].date))}
              </>
            )
          }
        />
        <Stat
          label={t.network.kpiReview}
          value={stats ? f.num(stats.review) : "…"}
          tone="warn"
          spark={spark(days, i, "manual_review")}
          hint={stats ? t.network.kpiOfVisits(f.num(stats.visits)) : undefined}
        />
        <Stat
          label={t.network.kpiFlags}
          value={stats ? f.num(stats.flags) : "…"}
          spark={spark(days, i, "anomaly_flags")}
          hint={t.anomaly.advisory}
        />
        <Stat
          label={t.network.kpiPending}
          value={pending === undefined ? "…" : f.num(pending)}
          hint={
            <Link href={`/queue?day=${day}`} className="inline-flex items-center gap-0.5 font-medium text-brand hover:underline">
              {t.nav.queue} <ArrowUpRight aria-hidden className="size-3.5" />
            </Link>
          }
        />
      </div>

      <Timeline meta={meta.data} day={day} onChange={setDay} />

      <ErrorNotice error={network.error} onRetry={network.reload} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_380px] xl:items-start">
        <section className="rounded-2xl border border-line bg-tray p-1" aria-label={t.network.mapLabel}>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-2.5 py-1.5">
            <div className="flex items-center gap-2 text-xs text-fg-3">
              <span className="hidden sm:inline">{t.network.riskOn}</span>
              <Segmented<RiskSide>
                label={t.network.riskOn}
                size="sm"
                value={side}
                onChange={setSide}
                options={[
                  { value: "max", label: t.risk.higherSide },
                  { value: "cash", label: t.common.cash },
                  { value: "efloat", label: t.common.efloat },
                ]}
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-fg-3">
              <span className="hidden sm:inline">{t.network.show}</span>
              <Segmented<ShowFilter>
                label={t.network.show}
                size="sm"
                value={show}
                onChange={setShow}
                options={[
                  { value: "all", label: t.network.showAll },
                  { value: "visits", label: t.network.showVisits },
                  { value: "high", label: t.network.showHigh },
                ]}
              />
            </div>
            <span className="ml-auto">
              <Provenance kind="prediction" />
            </span>
          </div>
          <div className="relative h-110 overflow-hidden rounded-xl border border-line bg-sunken shadow-card sm:h-145">
            {agents ? (
              <NetworkMap
                agents={agents}
                side={side}
                show={show}
                selected={selected}
                onSelect={setSelected}
                label={t.network.mapLabel}
                onError={() => setMapFailed(true)}
              />
            ) : (
              <Skeleton className="absolute inset-0 rounded-none" />
            )}
            {mapFailed && (
              <div className="absolute inset-x-4 top-4 flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-sm text-fg-2 shadow-pop">
                <MapPinOff aria-hidden className="size-4" />
                {t.network.mapError}
              </div>
            )}
            {chosen && day && (
              <AgentCard agent={chosen} rec={recs.get(chosen.agent_id)} day={day} onClose={() => setSelected(null)} />
            )}
            <Legend />
          </div>
        </section>

        <div className="space-y-5">
          <TerritoryTable meta={meta.data} agents={agents} side={side} />
          <HighRiskList agents={agents} side={side} day={day} recs={recs} onPick={setSelected} />
        </div>
      </div>
    </div>
  );
}

function Legend() {
  const { t } = useLang();
  const item = (shape: string, cls: string, label: string) => (
    <li className="flex items-center gap-2">
      <span aria-hidden className={`w-3 text-center text-[11px] leading-none ${cls}`}>
        {shape}
      </span>
      {label}
    </li>
  );
  return (
    <div className="absolute bottom-3 left-3 rounded-xl border border-line bg-surface/95 px-3 py-2.5 text-xs text-fg-2 shadow-pop backdrop-blur">
      <div className="eyebrow mb-1.5 text-fg-3">{t.network.legend}</div>
      <ul className="space-y-1">
        {item(RISK_SHAPE.high, "text-danger-text", `${t.risk.high} ≥ 50%`)}
        {item(RISK_SHAPE.medium, "text-warn-mark [text-shadow:0_0_1px_#050608]", `${t.risk.medium} ≥ 20%`)}
        {item(RISK_SHAPE.low, "text-[#7d8796]", t.risk.low)}
        <li className="flex items-center gap-2">
          <span aria-hidden className="inline-block size-3 rounded-full border-[1.75px] border-brand bg-brand/10" />
          {t.network.legendVisit}
        </li>
      </ul>
    </div>
  );
}

function AgentCard({
  agent,
  rec,
  day,
  onClose,
}: {
  agent: NetworkAgent;
  rec?: Recommendation;
  day: string;
  onClose: () => void;
}) {
  const { t, f } = useLang();
  return (
    <div
      className="absolute top-3 left-3 w-75 max-w-[calc(100%-1.5rem)] overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
      role="dialog"
      aria-label={agent.agent_id}
    >
      <div className="flex items-start justify-between gap-2 px-3.5 pt-3 pb-2">
        <div>
          <div className="mono text-[15px] font-semibold">{agent.agent_id}</div>
          <div className="text-xs text-fg-3">
            {agent.territory} · {t.agent.setting[agent.setting] ?? agent.setting}
          </div>
        </div>
        <button
          onClick={onClose}
          className="flex size-7 items-center justify-center rounded-md text-fg-3 hover:bg-tray hover:text-fg"
          aria-label="×"
        >
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <dl className="mx-3.5 grid grid-cols-2 gap-2">
        {(
          [
            [t.common.cash, agent.cash_tk],
            [t.common.efloat, agent.efloat_tk],
          ] as const
        ).map(([k, v]) => (
          <div key={k} className="rounded-lg bg-tray px-2.5 py-2">
            <dt className="eyebrow text-fg-3">{k}</dt>
            <dd className="num mt-0.5 text-sm font-semibold">{f.tk(v)}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap gap-1.5 px-3.5 pt-2.5 pb-3">
        <RiskBadge p={agent.p_stockout_cash} side={t.common.cash} />
        <RiskBadge p={agent.p_stockout_efloat} side={t.common.efloat} />
      </div>
      <div className="space-y-2.5 border-t border-line bg-tray/60 px-3.5 py-3 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-fg-2">{agent.runner_id ? t.network.visitBy(agent.runner_id) : t.network.noVisit}</span>
          {rec && <StatusBadge status={rec.status} />}
        </div>
        {(agent.manual_review || agent.anomaly) && (
          <div className="flex flex-wrap gap-1.5">
            {agent.manual_review && <ReviewBadge />}
            {agent.anomaly && <AnomalyBadge />}
          </div>
        )}
        <Link
          href={`/agents/${agent.agent_id}?day=${day}`}
          className="flex h-8 items-center justify-center gap-1 rounded-lg bg-ink text-[13px] font-medium text-white hover:bg-ink/85"
        >
          {t.common.viewAgent} <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </div>
    </div>
  );
}

function TerritoryTable({ meta, agents, side }: { meta: Meta; agents?: NetworkAgent[]; side: RiskSide }) {
  const { t, f, lang } = useLang();
  const rows = meta.territories.map((ter) => {
    const mine = agents?.filter((a) => a.territory === ter.territory) ?? [];
    return {
      ...ter,
      agents: mine.length,
      high: mine.filter((a) => sideP(a, side) >= RISK_BANDS.high).length,
      visits: mine.filter((a) => a.runner_id).length,
    };
  });
  return (
    <Panel title={t.network.territories} bodyClassName="overflow-hidden p-0">
      <table className="w-full text-sm">
        <thead className={THEAD}>
          <tr>
            <th scope="col" className={`${TH} pl-4`}>
              {t.common.territory}
            </th>
            <th scope="col" className={`${TH} px-2 text-right`}>
              {t.common.agents}
            </th>
            <th scope="col" className={`${TH} px-2 text-right`}>
              <span aria-hidden>{RISK_SHAPE.high}</span> {t.risk.high}
            </th>
            <th scope="col" className={`${TH} pr-4 text-right`}>
              {t.common.visits}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.territory} className="hover:bg-tray/60">
              <td className="px-4 py-2.5">
                <div className="font-medium">{lang === "bn" ? r.district_bn : r.district_en}</div>
                <div className="text-xs whitespace-nowrap text-fg-3">
                  <span className="mono">{r.territory}</span> · {t.agent.setting[r.setting] ?? r.setting}
                </div>
              </td>
              <td className="num px-2 py-2.5 text-right">{agents ? f.num(r.agents) : "…"}</td>
              <td className="num px-2 py-2.5 text-right font-medium text-danger-text">{agents ? f.num(r.high) : "…"}</td>
              <td className="num px-4 py-2.5 text-right">{agents ? f.num(r.visits) : "…"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

const TOP = 8;

function HighRiskList({
  agents,
  side,
  day,
  recs,
  onPick,
}: {
  agents?: NetworkAgent[];
  side: RiskSide;
  day: string;
  recs: Map<string, Recommendation>;
  onPick: (id: string) => void;
}) {
  const { t } = useLang();
  const top = (agents ?? [])
    .filter((a) => sideP(a, side) >= RISK_BANDS.high)
    .sort((a, b) => sideP(b, side) - sideP(a, side))
    .slice(0, TOP);
  return (
    <Panel
      title={t.network.highRiskList}
      aside={<Provenance kind="prediction" />}
      bodyClassName="p-0"
      footer={t.risk.bandsNote}
    >
      {!agents ? (
        <div className="space-y-2 p-4">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : top.length === 0 ? (
        <p className="px-4 py-6 text-sm text-fg-2">{t.network.highRiskEmpty}</p>
      ) : (
        <ul className="divide-y divide-line">
          {top.map((a) => {
            const rec = recs.get(a.agent_id);
            return (
              <li key={a.agent_id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-tray/60">
                <span aria-hidden className="h-8 w-0.75 shrink-0 rounded-full bg-ink" />
                <button className="min-w-0 flex-1 text-left" onClick={() => onPick(a.agent_id)} title={t.network.mapLabel}>
                  <div className="mono text-sm font-medium">{a.agent_id}</div>
                  <div className="truncate text-xs text-fg-3">
                    {a.runner_id ? `${t.common.runner} ${a.runner_id}` : t.network.noVisit}
                  </div>
                </button>
                <RiskBadge p={sideP(a, side)} compact />
                {rec && <StatusBadge status={rec.status} />}
                <Link
                  href={`/agents/${a.agent_id}?day=${day}`}
                  className="flex size-7 items-center justify-center rounded-md border border-line text-fg-2 shadow-xs hover:bg-tray hover:text-brand"
                  aria-label={`${t.common.viewAgent} ${a.agent_id}`}
                >
                  <ArrowRight className="size-3.5" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
