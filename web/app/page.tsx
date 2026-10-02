"use client";

import { ArrowRight, MapPinOff } from "lucide-react";
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
} from "@/components/ui";
import type { Meta, NetworkAgent, Recommendation } from "@/lib/api";
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

  return (
    <div className="space-y-5">
      <PageHeader
        title={t.network.title}
        subtitle={t.network.subtitle}
        actions={<DayControl meta={meta.data} day={day} onChange={setDay} playable />}
      />

      <div className="grid grid-cols-2 divide-line rounded-lg border border-line bg-surface sm:grid-cols-3 sm:divide-x xl:grid-cols-6">
        <Stat label={t.network.kpiAgents} value={stats ? f.num(stats.agents) : "…"} />
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
        <Stat label={t.network.kpiVisits} value={stats ? f.num(stats.visits) : "…"} />
        <Stat label={t.network.kpiReview} value={stats ? f.num(stats.review) : "…"} tone="warn" />
        <Stat label={t.network.kpiFlags} value={stats ? f.num(stats.flags) : "…"} />
        <Stat
          label={t.network.kpiPending}
          value={pending === undefined ? "…" : f.num(pending)}
          hint={
            <Link href={`/queue?day=${day}`} className="text-brand hover:underline">
              {t.nav.queue} →
            </Link>
          }
        />
      </div>

      <div className="rounded-lg border border-line bg-surface px-4 pt-3 pb-2">
        <Timeline meta={meta.data} day={day} onChange={setDay} />
      </div>

      <ErrorNotice error={network.error} onRetry={network.reload} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px] xl:items-start">
        <section className="overflow-hidden rounded-lg border border-line bg-surface" aria-label={t.network.mapLabel}>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-2.5">
            <div className="flex items-center gap-2 text-xs text-fg-2">
              {t.network.riskOn}
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
            <div className="flex items-center gap-2 text-xs text-fg-2">
              {t.network.show}
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
          <div className="relative h-[560px] bg-sunken">
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
              <div className="absolute inset-x-4 top-4 flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm text-fg-2 shadow-sm">
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
    <li className="flex items-center gap-1.5">
      <span aria-hidden className={`text-[11px] leading-none ${cls}`}>
        {shape}
      </span>
      {label}
    </li>
  );
  return (
    <div className="absolute bottom-3 left-3 rounded-md border border-line bg-surface/95 px-3 py-2 text-xs text-fg-2 shadow-sm">
      <div className="mb-1 font-semibold text-fg">{t.network.legend}</div>
      <ul className="space-y-1">
        {item(RISK_SHAPE.high, "text-danger-text", `${t.risk.high} ≥ 50%`)}
        {item(RISK_SHAPE.medium, "text-warn-mark [text-shadow:0_0_1px_#050608]", `${t.risk.medium} ≥ 20%`)}
        {item(RISK_SHAPE.low, "text-[#7d8796]", t.risk.low)}
        <li className="flex items-center gap-1.5">
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
      className="absolute top-3 left-3 w-[300px] max-w-[calc(100%-1.5rem)] rounded-lg border border-line bg-surface shadow-lg"
      role="dialog"
      aria-label={agent.agent_id}
    >
      <div className="flex items-start justify-between gap-2 border-b border-line px-3.5 py-2.5">
        <div>
          <div className="text-sm font-semibold">{agent.agent_id}</div>
          <div className="text-xs text-fg-2">
            {agent.territory} · {t.agent.setting[agent.setting] ?? agent.setting}
          </div>
        </div>
        <button onClick={onClose} className="rounded px-1.5 text-lg leading-none text-fg-3 hover:bg-page" aria-label="×">
          ×
        </button>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 px-3.5 py-3 text-xs">
        <dt className="text-fg-2">{t.common.cash}</dt>
        <dd className="num text-right font-medium">{f.tk(agent.cash_tk)}</dd>
        <dt className="text-fg-2">{t.common.efloat}</dt>
        <dd className="num text-right font-medium">{f.tk(agent.efloat_tk)}</dd>
      </dl>
      <div className="flex flex-wrap gap-1.5 px-3.5 pb-3">
        <RiskBadge p={agent.p_stockout_cash} side={t.common.cash} />
        <RiskBadge p={agent.p_stockout_efloat} side={t.common.efloat} />
      </div>
      <div className="space-y-2 border-t border-line px-3.5 py-2.5 text-xs">
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
          className="inline-flex items-center gap-1 font-semibold text-brand hover:underline"
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
    <Panel title={t.network.territories} bodyClassName="p-0">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-fg-2">
          <tr className="border-b border-line">
            <th scope="col" className="px-4 py-2 font-medium">
              {t.common.territory}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              {t.common.agents}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              <span aria-hidden>{RISK_SHAPE.high}</span> {t.risk.high}
            </th>
            <th scope="col" className="px-4 py-2 text-right font-medium">
              {t.common.visits}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.territory} className="border-b border-line last:border-0">
              <td className="px-4 py-2">
                <div className="font-medium">{lang === "bn" ? r.district_bn : r.district_en}</div>
                <div className="text-xs text-fg-3">
                  {r.territory} · {t.agent.setting[r.setting] ?? r.setting}
                </div>
              </td>
              <td className="num px-2 py-2 text-right">{agents ? f.num(r.agents) : "…"}</td>
              <td className="num px-2 py-2 text-right font-medium text-danger-text">{agents ? f.num(r.high) : "…"}</td>
              <td className="num px-4 py-2 text-right">{agents ? f.num(r.visits) : "…"}</td>
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
    <Panel title={t.network.highRiskList} aside={<Provenance kind="prediction" />} bodyClassName="p-0">
      {!agents ? (
        <div className="space-y-2 p-4">
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
        </div>
      ) : top.length === 0 ? (
        <p className="px-4 py-6 text-sm text-fg-2">{t.network.highRiskEmpty}</p>
      ) : (
        <ul className="divide-y divide-line">
          {top.map((a) => {
            const rec = recs.get(a.agent_id);
            return (
              <li key={a.agent_id} className="flex items-center gap-3 px-4 py-2">
                <button
                  className="min-w-0 flex-1 text-left"
                  onClick={() => onPick(a.agent_id)}
                  title={t.network.mapLabel}
                >
                  <div className="text-sm font-medium">{a.agent_id}</div>
                  <div className="truncate text-xs text-fg-3">
                    {a.runner_id ? `${t.common.runner} ${a.runner_id}` : t.network.noVisit}
                  </div>
                </button>
                <RiskBadge p={sideP(a, side)} compact />
                {rec && <StatusBadge status={rec.status} />}
                <Link
                  href={`/agents/${a.agent_id}?day=${day}`}
                  className="rounded p-1 text-brand hover:bg-brand-tint"
                  aria-label={`${t.common.viewAgent} ${a.agent_id}`}
                >
                  <ArrowRight className="size-4" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <p className="border-t border-line px-4 py-2 text-[11px] text-fg-3">{t.risk.bandsNote}</p>
    </Panel>
  );
}
