"use client";

import { ArrowLeft, Bot, Calculator, Cpu, FileText, MapPin, Route, Sparkles, Store, UserCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type ReactNode } from "react";

import { DataTable, DrainRanges, Legend, ProbabilityChart } from "@/components/charts";
import { DayControl } from "@/components/day";
import { DecisionControls, DriverList, ExplanationBlock, ReasonList } from "@/components/evidence";
import { Staff } from "@/components/shell";
import {
  AnomalyBadge,
  cx,
  ErrorNotice,
  Panel,
  Provenance,
  ReviewBadge,
  RiskBadge,
  Skeleton,
  StatusBadge,
  TableToggle,
} from "@/components/ui";
import { RISK_BANDS } from "@/lib/format";
import type { AgentDay, AuditEntry, Recommendation, TraceStep } from "@/lib/api";
import { useAgent, useDay, useMeta, useNetwork, usePlan, useTrace } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";

const CASH = "#0c55a4";
const EFLOAT = "#d9730d";

export default function Page() {
  return (
    <Staff>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <AgentView />
      </Suspense>
    </Staff>
  );
}

function AgentView() {
  const { t, f, lang } = useLang();
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const meta = useMeta();
  const [day, setDay] = useDay(meta.data);
  const agent = useAgent(id);
  const plan = usePlan(day);
  const [table, setTable] = useState(false);

  const rec = useMemo(
    () => (plan.data?.plan_date === day ? plan.data?.items.find((r) => r.agent_id === id) : undefined),
    [plan.data, day, id],
  );

  if (meta.error) return <ErrorNotice error={meta.error} onRetry={meta.reload} />;
  if (agent.error) {
    return (
      <div className="space-y-4">
        <BackLink day={day} />
        <ErrorNotice error={agent.error} onRetry={agent.reload} />
      </div>
    );
  }
  if (!meta.data || !day || !agent.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const a = agent.data.agent;
  const days = agent.data.days;
  const i = days.findIndex((d) => d.plan_date === day);
  const today: AgentDay | undefined = days[i];
  const flagsToday = agent.data.anomalies.filter((x) => x.plan_date === day);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <BackLink day={day} />
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <h1 className="mono text-[28px] leading-8 font-semibold tracking-tight">{a.agent_id}</h1>
            {today?.evidence.review?.flag && <ReviewBadge />}
            {flagsToday.length > 0 && <AnomalyBadge />}
          </div>
          <ul className="mt-3 flex flex-wrap gap-1.5 text-xs text-fg-2">
            <Chip Icon={MapPin}>
              {lang === "bn" ? a.district_bn : a.district_en} <span className="mono text-fg-3">({a.territory})</span>
            </Chip>
            <Chip Icon={Store}>
              {t.agent.setting[a.setting] ?? a.setting} · {t.agent.size[a.size_class] ?? a.size_class}
            </Chip>
            <Chip Icon={Route}>{t.agent.hub(f.num(a.hub_road_km, 1))}</Chip>
          </ul>
        </div>
        <DayControl meta={meta.data} day={day} onChange={setDay} />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <Panel
            title={t.agent.riskChart}
            aside={
              <>
                <Provenance kind="prediction" />
                <TableToggle open={table} onToggle={() => setTable((x) => !x)} />
              </>
            }
          >
            <p className="mb-3 text-xs text-fg-2">{t.agent.riskChartNote}</p>
            <div className="mb-2">
              <Legend
                items={[
                  { name: t.common.cash, color: CASH },
                  { name: t.common.efloat, color: EFLOAT },
                ]}
              />
            </div>
            <ProbabilityChart
              label={t.agent.riskChart}
              dates={days.map((d) => d.plan_date)}
              series={[
                { key: "cash", name: t.common.cash, color: CASH, values: days.map((d) => d.evidence.p_stockout_cash) },
                { key: "efloat", name: t.common.efloat, color: EFLOAT, values: days.map((d) => d.evidence.p_stockout_efloat) },
              ]}
              marks={days.map((d) => d.runner_id !== null)}
              selected={i >= 0 ? i : undefined}
              onSelect={(k) => setDay(days[k].plan_date)}
            />
            {table && (
              <div className="mt-4 max-h-72 overflow-y-auto">
                <DataTable
                  caption={t.agent.riskChart}
                  head={[t.agent.dateCol, t.common.cash, t.common.efloat, t.common.runner]}
                  rows={days.map((d) => [
                    f.day(d.plan_date),
                    f.pct(d.evidence.p_stockout_cash),
                    f.pct(d.evidence.p_stockout_efloat),
                    d.runner_id ?? "—",
                  ])}
                />
              </div>
            )}
          </Panel>

          {today && (
            <Panel title={t.agent.drainChart} aside={<Provenance kind="prediction" />}>
              <p className="mb-4 text-xs text-fg-2">{t.agent.drainChartNote}</p>
              <DrainRanges
                rows={[
                  {
                    key: "cash",
                    name: t.common.cash,
                    color: CASH,
                    balance: today.evidence.cash_tk,
                    q50: today.evidence.drain_cash_q50,
                    q90: today.evidence.drain_cash_q90,
                    q99: today.evidence.drain_cash_q99,
                  },
                  {
                    key: "efloat",
                    name: t.common.efloat,
                    color: EFLOAT,
                    balance: today.evidence.efloat_tk,
                    q50: today.evidence.drain_efloat_q50,
                    q90: today.evidence.drain_efloat_q90,
                    q99: today.evidence.drain_efloat_q99,
                  },
                ]}
              />
              <div className="mt-4">
                <DataTable
                  caption={t.agent.drainChart}
                  head={["", t.agent.balance, t.agent.q50, t.agent.q90, t.agent.q99, t.queue.colRisk]}
                  rows={(["cash", "efloat"] as const).map((s) => [
                    s === "cash" ? t.common.cash : t.common.efloat,
                    f.tk(today.evidence[`${s}_tk`]),
                    f.tk(today.evidence[`drain_${s}_q50`]),
                    f.tk(today.evidence[`drain_${s}_q90`]),
                    f.tk(today.evidence[`drain_${s}_q99`]),
                    <RiskBadge key={s} p={today.evidence[`p_stockout_${s}`]} compact />,
                  ])}
                />
              </div>
            </Panel>
          )}

          {today?.runner_id && <TracePanel rec={rec} />}
        </div>

        {/* on a phone the decision comes first, the charts and the trace after it */}
        <div className="order-first min-w-0 space-y-5 xl:order-none">
          <Panel title={t.agent.recommendation} aside={rec && <StatusBadge status={rec.status} />}>
            {!today?.runner_id ? (
              <div className="space-y-1 text-sm text-fg-2">
                <p>{t.agent.noVisit}</p>
                {today?.candidate && <p>{t.agent.candidate}</p>}
              </div>
            ) : (
              <div className="space-y-4">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <Fact label={t.common.runner} value={today.runner_id} />
                  <Fact
                    label={t.agent.sideAtRisk}
                    value={today.evidence.side === "efloat" ? t.common.efloat : t.common.cash}
                  />
                  <Fact label={t.agent.targetCash} value={f.tk(today.target_cash_tk)} />
                  <Fact label={t.agent.value} value={f.tk(today.value_tk)} />
                  <Fact label={t.agent.needCash} value={f.tk(today.evidence.need_cash_tk)} />
                  <Fact label={t.agent.needEfloat} value={f.tk(today.evidence.need_efloat_tk)} />
                </dl>
                <div className="rounded-xl border border-line bg-tray/60 p-3">
                  {rec ? <DecisionControls rec={rec} layout="stack" /> : <Skeleton className="h-8 w-48" />}
                </div>
                {rec && (
                  <div className="border-t border-line pt-4">
                    <ExplanationBlock rec={rec} />
                  </div>
                )}
              </div>
            )}
          </Panel>

          {today?.evidence.drivers && (
            <Panel title={t.why.drivers}>
              <DriverList drivers={today.evidence.drivers} />
            </Panel>
          )}

          {today?.runner_id && (
            <Panel title={t.why.reasons}>
              <ReasonList review={today.evidence.review} />
            </Panel>
          )}

          <Panel title={t.agent.flags} aside={<span className="text-[11px] text-fg-3">{t.anomaly.advisory}</span>}>
            {agent.data.anomalies.length === 0 ? (
              <p className="text-sm text-fg-2">{t.anomaly.agentNone}</p>
            ) : (
              <ul className="space-y-2">
                {agent.data.anomalies.map((x) => (
                  <li
                    key={x.plan_date}
                    className={cx(
                      "rounded-lg border px-3 py-2 text-sm",
                      x.plan_date === day ? "border-ink/60 bg-surface font-medium" : "border-line bg-tray/60",
                    )}
                  >
                    <button className="num text-xs font-semibold text-brand hover:underline" onClick={() => setDay(x.plan_date)}>
                      {f.day(x.plan_date)}
                    </button>{" "}
                    <span className="text-xs text-fg-3">{t.anomaly.onDay(f.dayShort(x.date))}</span>
                    <div lang={lang} className="mt-0.5 text-fg-2">
                      {x.text[lang]}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs leading-relaxed text-fg-3">{t.anomaly.note}</p>
          </Panel>

          <PeerSwap id={id} day={day} />
        </div>
      </div>
    </div>
  );
}

// Peer swap idea (on-site R5, D-035): a nearby agent at risk on the other side holds what this
// agent lacks, so the two could swap cash for e-float directly. Advisory and not evaluated.
const PEER_KM = 3;

function PeerSwap({ id, day }: { id: string; day: string | null }) {
  const { t, f } = useLang();
  const network = useNetwork(day);
  const peers = useMemo(() => {
    const all = network.data?.plan_date === day ? network.data.agents : [];
    const me = all.find((a) => a.agent_id === id);
    if (!me) return null;
    const side = me.p_stockout_cash >= me.p_stockout_efloat ? "cash" : "efloat";
    const mine = side === "cash" ? me.p_stockout_cash : me.p_stockout_efloat;
    if (mine < RISK_BANDS.medium) return { side, list: [] };
    const r = Math.PI / 180;
    const km = (a: { lat: number; lon: number }) =>
      2 * 6371 * Math.asin(Math.sqrt(
        Math.sin(((a.lat - me.lat) * r) / 2) ** 2 +
          Math.cos(me.lat * r) * Math.cos(a.lat * r) * Math.sin(((a.lon - me.lon) * r) / 2) ** 2,
      ));
    const other = (a: (typeof all)[number]) => (side === "cash" ? a.p_stockout_efloat : a.p_stockout_cash);
    const list = all
      .filter((a) => a.agent_id !== id && a.territory === me.territory && other(a) >= RISK_BANDS.medium)
      .map((a) => ({ a, km: km(a), p: other(a) }))
      .filter((x) => x.km <= PEER_KM)
      .sort((x, y) => x.km - y.km)
      .slice(0, 3);
    return { side, list };
  }, [network.data, day, id]);

  if (!peers) return null;
  const s = t.peer;
  return (
    <Panel title={s.title} aside={<Provenance kind="assumption" />}>
      {peers.list.length === 0 ? (
        <p className="text-sm text-fg-2">{s.none(f.num(PEER_KM))}</p>
      ) : (
        <>
          <p className="text-sm text-fg-2">{peers.side === "cash" ? s.leadCash : s.leadEfloat}</p>
          <ul className="mt-2.5 space-y-2">
            {peers.list.map(({ a, km, p }) => (
              <li key={a.agent_id} className="flex items-center gap-3 rounded-lg border border-line bg-tray/60 px-3 py-2 text-sm">
                <Link href={`/agents/${a.agent_id}?day=${day}`} className="mono font-semibold hover:underline">
                  {a.agent_id}
                </Link>
                <span className="num text-xs text-fg-3">{f.num(km, 1)} km</span>
                <span className="ml-auto">
                  <RiskBadge p={p} side={peers.side === "cash" ? "efloat" : "cash"} compact />
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-3 text-xs leading-relaxed text-fg-3">{s.note}</p>
    </Panel>
  );
}

function BackLink({ day }: { day: string | null }) {
  const { t } = useLang();
  return (
    <Link
      href={day ? `/?day=${day}` : "/"}
      className="inline-flex h-7 items-center gap-1 rounded-md border border-line bg-surface pr-2.5 pl-1.5 text-xs font-medium text-fg-2 shadow-xs hover:bg-tray hover:text-fg"
    >
      <ArrowLeft aria-hidden className="size-3.5" /> {t.agent.back}
    </Link>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-tray px-3 py-2.5">
      <dt className="text-xs text-fg-3">{label}</dt>
      <dd className="num mt-1 text-[15px] font-semibold">{value}</dd>
    </div>
  );
}

function Chip({ Icon, children }: { Icon: typeof MapPin; children: ReactNode }) {
  return (
    <li className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface py-1 pr-2.5 pl-2 shadow-xs">
      <Icon aria-hidden className="size-3.5 text-fg-3" />
      {children}
    </li>
  );
}

const BY_ICON: Record<TraceStep["by"], typeof Cpu> = {
  model: Sparkles,
  "model explanation": Sparkles,
  rule: Calculator,
  optimizer: Cpu,
  template: FileText,
  human: UserCheck,
};

function TracePanel({ rec }: { rec?: Recommendation }) {
  const { t, f } = useLang();
  const trace = useTrace(rec?.id ?? null);
  // a decision made on this page changes the last step; refetch when the status moves
  const { reload } = trace;
  const traced = trace.data?.status;
  const status = rec?.status;
  useEffect(() => {
    if (traced && status && traced !== status) reload();
  }, [traced, status, reload]);
  return (
    <Panel title={t.agent.trace} aside={<span className="text-[11px] text-fg-3">{t.agent.traceNote}</span>}>
      <ErrorNotice error={trace.error} onRetry={trace.reload} />
      {!trace.data ? (
        <div className="space-y-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : (
        <ol className="relative">
          {trace.data.steps.map((s, k) => {
            const Icon = BY_ICON[s.by] ?? Bot;
            const last = k === trace.data!.steps.length - 1;
            return (
              <li key={s.step} className="relative flex gap-3 pb-4 last:pb-0">
                {!last && <span aria-hidden className="absolute top-9 bottom-0 left-[17px] w-px bg-line-strong" />}
                <span
                  className={cx(
                    "relative z-10 flex size-9 shrink-0 items-center justify-center rounded-xl border shadow-xs",
                    s.by === "human" ? "border-accent bg-accent text-ink" : "border-line bg-surface text-brand",
                  )}
                >
                  <Icon aria-hidden className="size-4" />
                </span>
                <div className="min-w-0 flex-1 rounded-xl border border-line bg-tray/50 px-3 py-2.5">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="mono text-xs text-fg-3">{String(k + 1).padStart(2, "0")}</span>
                    <span className="text-sm font-semibold">
                      {(t.trace as unknown as Record<string, string>)[s.step] ?? s.step}
                    </span>
                    <span className="rounded-full border border-line bg-surface px-2 py-0.5 text-[11px] font-medium text-fg-2">
                      {t.trace.by[s.by] ?? s.by}
                    </span>
                    {s.config?.hash && (
                      <code className="mono ml-auto text-[11px] text-fg-3" title={`${s.config.name} config hash`}>
                        {t.agent.config} {s.config.name}@{s.config.hash.slice(0, 8)}
                      </code>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-fg-2">{t.trace.what[s.step] ?? s.what}</p>
                  <StepOutputs step={s} audit={trace.data!.audit} />
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {trace.data && (
        <p className="mono mt-4 border-t border-line pt-3 text-[11px] text-fg-3">
          bundle <code>{trace.data.bundle_id}</code> · {f.day(trace.data.plan_date)}
        </p>
      )}
    </Panel>
  );
}

function StepOutputs({ step, audit }: { step: TraceStep; audit: AuditEntry[] }) {
  const { t, f, lang } = useLang();
  const o = step.outputs as Record<string, unknown>;
  const num = (k: string) => (typeof o[k] === "number" ? (o[k] as number) : null);
  const chips: string[] = [];
  if (step.step === "forecast") {
    (["cash", "efloat"] as const).forEach((s) => {
      const q50 = num(`drain_${s}_q50`);
      const q90 = num(`drain_${s}_q90`);
      if (q50 !== null && q90 !== null)
        chips.push(`${s === "cash" ? t.common.cash : t.common.efloat}: ${t.agent.q50} ${f.tk(q50)} · ${t.agent.q90} ${f.tk(q90)}`);
    });
  }
  if (step.step === "stock_out_chance") {
    const c = num("p_stockout_cash");
    const e = num("p_stockout_efloat");
    if (c !== null) chips.push(`${t.common.cash} ${f.pct(c)}`);
    if (e !== null) chips.push(`${t.common.efloat} ${f.pct(e)}`);
  }
  if (step.step === "need_and_value") {
    const nc = num("need_cash_tk");
    const ne = num("need_efloat_tk");
    const v = num("value_tk");
    if (nc !== null) chips.push(`${t.agent.needCash} ${f.tk(nc)}`);
    if (ne !== null) chips.push(`${t.agent.needEfloat} ${f.tk(ne)}`);
    if (v !== null) chips.push(`${t.agent.value} ${f.tk(v)}`);
  }
  if (step.step === "dispatch") {
    if (typeof o.runner_id === "string") chips.push(`${t.common.runner} ${o.runner_id}`);
    const tc = num("target_cash_tk");
    if (tc !== null) chips.push(`${t.agent.targetCash} ${f.tk(tc)}`);
  }
  if (step.step === "drivers" && Array.isArray(o.drivers)) {
    (o.drivers as { label: Record<string, string>; effect_pct: number }[]).forEach((d) =>
      chips.push(`${d.label[lang]} ${f.signed(d.effect_pct)}%`),
    );
  }
  if (step.step === "guardrails") {
    const review = o.review as { flag: boolean; reasons: { text: Record<string, string> }[] } | undefined;
    if (review?.flag) review.reasons.forEach((r) => chips.push(`⚑ ${r.text[lang]}`));
    else chips.push(t.common.none);
  }
  if (step.step === "decision") {
    const status = o.status as Recommendation["status"] | undefined;
    return (
      <div className="mt-2 space-y-1.5">
        {status && status !== "pending" ? <StatusBadge status={status} /> : <span className="text-xs text-fg-3">{t.trace.pending}</span>}
        {typeof o.decided_at === "string" && <span className="ml-2 text-xs text-fg-3">{f.when(o.decided_at)}</span>}
        {typeof o.decision_note === "string" && o.decision_note && (
          <p className="text-xs break-words text-fg-2">“{o.decision_note}”</p>
        )}
        {audit.length > 0 && (
          <ul className="mt-1 space-y-0.5 text-[11px] text-fg-3">
            {audit.map((x) => (
              <li key={x.id}>
                #{x.id} · {x.action} · {x.actor_role} · {f.when(x.at)}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }
  if (!chips.length) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" lang={lang}>
      {chips.map((c) => (
        <li key={c} className="num rounded-md border border-line bg-surface px-2 py-0.5 text-xs text-fg">
          {c}
        </li>
      ))}
    </ul>
  );
}
