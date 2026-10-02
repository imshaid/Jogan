"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Staff } from "@/components/shell";
import { Empty, ErrorNotice, PageHeader, Segmented, Skeleton } from "@/components/ui";
import type { AuditEntry } from "@/lib/api";
import { useAudit } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";

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
      />
      <ErrorNotice error={audit.error} onRetry={audit.reload} />
      <section className="rounded-lg border border-line bg-surface">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5">
          <label className="flex items-center gap-2 text-xs text-fg-2">
            {t.audit.filterAction}
            <select
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="h-8 rounded-md border border-line-strong bg-surface px-2 text-sm text-fg"
            >
              <option value="all">{t.common.all}</option>
              {actions.map((a) => (
                <option key={a} value={a}>
                  {t.audit.actions[a] ?? a}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center gap-2 text-xs text-fg-2">
            {t.audit.limit}
            <Segmented label={t.audit.limit} size="sm" value={limit} onChange={setLimit} options={LIMITS.map((l) => ({ value: l, label: l }))} />
          </div>
        </div>
        <div className={audit.loading && items ? "opacity-60 transition-opacity" : undefined}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="text-left text-xs text-fg-2">
                <tr className="border-b border-line">
                  <th scope="col" className="px-4 py-2 font-medium">#</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t.audit.colTime}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t.audit.colAction}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t.audit.colActor}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t.audit.colRec}</th>
                  <th scope="col" className="px-3 py-2 pr-4 font-medium">{t.audit.colDetail}</th>
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
                  <AuditRow key={a.id} entry={a} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}

function AuditRow({ entry: a }: { entry: AuditEntry }) {
  const { t, f, lang } = useLang();
  const d = a.detail;
  const agent = typeof d.agent_id === "string" ? d.agent_id : null;
  const day = typeof d.plan_date === "string" ? d.plan_date : null;
  const tone =
    a.action === "recommendation.approved"
      ? "text-ok-text"
      : a.action === "recommendation.rejected"
        ? "text-fg-2"
        : "text-brand";
  return (
    <tr className="border-b border-line align-top last:border-0">
      <td className="num px-4 py-2 text-fg-3">{a.id}</td>
      <td className="num px-3 py-2 whitespace-nowrap">{f.when(a.at)}</td>
      <td className={`px-3 py-2 font-medium ${tone}`}>{t.audit.actions[a.action] ?? a.action}</td>
      <td className="px-3 py-2">
        <div>{a.actor_role === "system" ? t.audit.system : t.user.role[a.actor_role]}</div>
        {a.actor && <code className="text-[11px] text-fg-3">{a.actor.slice(0, 8)}</code>}
      </td>
      <td className="px-3 py-2">
        {/* ids are names, not quantities: never grouped or translated */}
        {a.recommendation_id !== null && <span className="num">#{a.recommendation_id}</span>}
        {agent && day && (
          <div>
            <Link href={`/agents/${agent}?day=${day}`} className="font-medium text-brand hover:underline">
              {agent}
            </Link>{" "}
            <span className="text-xs text-fg-3">{f.dayShort(day)}</span>
          </div>
        )}
        {!agent && day && <span className="text-xs text-fg-2">{f.day(day)}</span>}
      </td>
      <td className="px-3 py-2 pr-4 text-xs text-fg-2" lang={lang}>
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
