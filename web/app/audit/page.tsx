"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Ago } from "@/components/live";
import { Tween } from "@/components/motion";
import { Staff } from "@/components/shell";
import { cx, Empty, ErrorNotice, PageHeader, Segmented, Select, Skeleton, TH, THEAD } from "@/components/ui";
import type { AuditEntry } from "@/lib/api";
import { useAudit } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/lib/live";

const LIMITS = ["50", "100", "200"] as const;

export default function Page() {
  return (
    <Staff>
      <AuditView />
    </Staff>
  );
}

function AuditView() {
  const { t } = useLang();
  const [limit, setLimit] = useState<(typeof LIMITS)[number]>("50");
  const [action, setAction] = useState("all");
  const audit = useAudit(Number(limit));
  const items = audit.data?.items;
  // live: new rows arrive every 15 s while the page is open, and flash once
  usePoll(audit.refresh, 15_000, !!items);
  const [baseline, setBaseline] = useState<number | null>(null);
  if (items && baseline === null) setBaseline(items[0]?.id ?? 0);
  const syncedAt = audit.updatedAt;
  const actions = useMemo(() => [...new Set((items ?? []).map((a) => a.action))].sort(), [items]);
  const shown = (items ?? []).filter((a) => action === "all" || a.action === action);

  return (
    <div className="space-y-5">
      <PageHeader
        title={t.audit.title}
        subtitle={
          <span className="inline-flex items-center gap-1.5">
            <Lock aria-hidden className="size-3.5" /> {t.audit.subtitle}
          </span>
        }
        actions={
          syncedAt ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-fg-3">
              <span aria-hidden className="relative flex size-2">
                <span className="live-ping absolute inset-0 rounded-full bg-ok-text" />
                <span className="relative size-2 rounded-full bg-ok-text" />
              </span>
              {t.live.live} · {t.live.synced} <Ago at={syncedAt} />
            </span>
          ) : null
        }
      />
      <ErrorNotice error={audit.error} onRetry={audit.reload} />
      {items && <Oversight items={items} />}
      <section className="rounded-2xl border border-line bg-tray p-1">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-2.5 py-1.5">
          <label className="flex items-center gap-2 text-xs text-fg-3">
            {t.audit.filterAction}
            <Select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="all">{t.common.all}</option>
              {actions.map((a) => (
                <option key={a} value={a}>
                  {t.audit.actions[a] ?? a}
                </option>
              ))}
            </Select>
          </label>
          <div className="flex items-center gap-2 text-xs text-fg-3">
            {t.audit.limit}
            <Segmented label={t.audit.limit} size="sm" value={limit} onChange={setLimit} options={LIMITS.map((l) => ({ value: l, label: <span className="num">{l}</span> }))} />
          </div>
        </div>
        <div
          className={cx(
            "overflow-hidden rounded-xl border border-line bg-surface shadow-card",
            audit.loading && items && "opacity-60 transition-opacity",
          )}
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead className={THEAD}>
                <tr>
                  <th scope="col" className={`${TH} pl-4`}>#</th>
                  <th scope="col" className={TH}>{t.audit.colTime}</th>
                  <th scope="col" className={TH}>{t.audit.colAction}</th>
                  <th scope="col" className={TH}>{t.audit.colActor}</th>
                  <th scope="col" className={TH}>{t.audit.colRec}</th>
                  <th scope="col" className={`${TH} pr-4`}>{t.audit.colDetail}</th>
                </tr>
              </thead>
              <tbody>
                {!items && !audit.error && (
                  <tr>
                    <td colSpan={6} className="p-4">
                      <Skeleton className="h-40" />
                    </td>
                  </tr>
                )}
                {items && shown.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <Empty>{t.audit.empty}</Empty>
                    </td>
                  </tr>
                )}
                {shown.map((a) => (
                  <AuditRow key={a.id} entry={a} fresh={baseline !== null && a.id > baseline} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}

function AuditRow({ entry: a, fresh }: { entry: AuditEntry; fresh: boolean }) {
  const { t, f, lang } = useLang();
  const d = a.detail;
  const agent = typeof d.agent_id === "string" ? d.agent_id : null;
  const day = typeof d.plan_date === "string" ? d.plan_date : null;
  const tone =
    a.action === "recommendation.approved"
      ? ["text-ok-text", "bg-ok-text"]
      : a.action === "recommendation.rejected"
        ? ["text-fg-2", "bg-fg-3"]
        : ["text-brand", "bg-brand"];
  return (
    <tr className={cx("border-b border-line align-top transition-colors last:border-0 hover:bg-tray/50", fresh && "anim-flash")}>
      <td className="num px-4 py-2.5 text-fg-3">{a.id}</td>
      <td className="num px-3 py-2.5 whitespace-nowrap">{f.when(a.at)}</td>
      <td className="px-3 py-2.5">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${tone[0]}`}
        >
          <span aria-hidden className={`size-1.5 rounded-full ${tone[1]}`} />
          {t.audit.actions[a.action] ?? a.action}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <div>{a.actor_role === "system" ? t.audit.system : t.user.role[a.actor_role]}</div>
        {a.actor && <code className="mono text-[11px] text-fg-3">{a.actor.slice(0, 8)}</code>}
      </td>
      <td className="px-3 py-2.5">
        {/* ids are names, not quantities: never grouped or translated */}
        {a.recommendation_id !== null && <span className="num">#{a.recommendation_id}</span>}
        {agent && day && (
          <div>
            <Link href={`/agents/${agent}?day=${day}`} className="mono font-medium text-brand hover:underline">
              {agent}
            </Link>{" "}
            <span className="text-xs text-fg-3">{f.dayShort(day)}</span>
          </div>
        )}
        {!agent && day && <span className="text-xs text-fg-2">{f.day(day)}</span>}
      </td>
      <td className="px-3 py-2.5 pr-4 text-xs text-fg-2" lang={lang}>
        {d.manual_review === true && <span className="mr-2 font-semibold text-ink">⚑ {t.audit.reviewed}</span>}
        {typeof d.note === "string" && d.note && (
          <span className="break-words">
            {t.audit.noteLabel}: “{d.note}”
          </span>
        )}
        {typeof d.recommendations === "number" && (
          <span className="num">
            {f.num(d.recommendations)} {t.common.visitsShort}
          </span>
        )}
      </td>
    </tr>
  );
}

// Human-override monitoring (on-site R7, D-037): from the audit rows already loaded, the share of
// decisions that were rejections against the review threshold in docs/06-responsible-ai.md §10.2.
const OVERRIDE_ALERT = 0.3; // ASSUMPTION, as in the monitoring table

function Oversight({ items }: { items: AuditEntry[] }) {
  const { t, f } = useLang();
  const o = t.audit.oversight;
  const approved = items.filter((a) => a.action === "recommendation.approved");
  const rejected = items.filter((a) => a.action === "recommendation.rejected").length;
  const decided = approved.length + rejected;
  const noted = approved.filter((a) => a.detail?.manual_review === true).length;
  const people = new Set(items.filter((a) => a.actor_role === "approver").map((a) => a.actor)).size;
  const published = items.filter((a) => a.action === "plan.published").length;
  const rate = decided ? rejected / decided : 0;
  const tiles = [
    [o.decided, decided],
    [o.approved, approved.length],
    [o.rejected, rejected],
    [o.noted, noted],
    [o.approvers, people],
    [o.published, published],
  ] as const;
  return (
    <section className="rounded-2xl border border-line bg-tray p-1" aria-labelledby="oversight">
      <div className="flex items-center justify-between px-3 py-2.5">
        <h2 id="oversight" className="eyebrow text-fg-2">
          {o.title}
        </h2>
        <span className="text-[11px] text-fg-3">{o.scope(f.num(items.length))}</span>
      </div>
      <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
        <dl className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {tiles.map(([k, v], i) => (
            <div key={k} className="anim-rise flex flex-col justify-between" style={{ ["--i" as string]: i }}>
              <dt className="eyebrow text-fg-3">{k}</dt>
              <dd className="mt-1 text-xl font-semibold">
                <Tween value={v} format={(x) => f.num(x)} from={0} />
              </dd>
            </div>
          ))}
        </dl>
        {decided > 0 && (
          <div className="mt-4">
            <div className="flex items-baseline justify-between text-xs text-fg-2">
              <span>{o.rate}</span>
              <span className="num font-semibold text-fg">{f.pct(rate, 0)}</span>
            </div>
            <div className="relative mt-1.5 flex h-2.5 gap-[2px] overflow-hidden rounded-full" role="img" aria-label={`${o.approved} ${approved.length}, ${o.rejected} ${rejected}`}>
              <span className="anim-grow-x h-full rounded-l-full bg-brand transition-[width] duration-700" style={{ width: `${(1 - rate) * 100}%` }} />
              <span className="h-full rounded-r-full bg-line-strong transition-[width] duration-700" style={{ width: `${rate * 100}%` }} />
              <span aria-hidden className="absolute inset-y-[-3px] w-[2px] bg-ink" style={{ left: `${(1 - OVERRIDE_ALERT) * 100}%` }} />
            </div>
            <p className="mt-2 text-xs text-fg-2">
              {rate > OVERRIDE_ALERT ? o.over(f.pct(OVERRIDE_ALERT)) : o.under(f.pct(OVERRIDE_ALERT))}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
