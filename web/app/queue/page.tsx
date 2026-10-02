"use client";

import { ChevronDown, ChevronRight, Info, Search } from "lucide-react";
import Link from "next/link";
import { Fragment, Suspense, useMemo, useState } from "react";

import { DayControl } from "@/components/day";
import { DecisionControls, DriverList, ExplanationBlock, ReasonList } from "@/components/evidence";
import { Staff } from "@/components/shell";
import {
  AnomalyBadge,
  Button,
  cx,
  Empty,
  ErrorNotice,
  PageHeader,
  ReviewBadge,
  RiskBadge,
  Segmented,
  Skeleton,
} from "@/components/ui";
import type { Recommendation, Status } from "@/lib/api";
import { useAnomalies, useDay, useMeta, usePlan } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function Page() {
  return (
    <Staff>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <QueueView />
      </Suspense>
    </Staff>
  );
}

type StatusFilter = "all" | Status;

const PAGE_SIZE = 50;

function QueueView() {
  const { t, lang } = useLang();
  const { role } = useSession();
  const meta = useMeta();
  const [day, setDay] = useDay(meta.data);
  const plan = usePlan(day);
  const anomalies = useAnomalies(day);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [territory, setTerritory] = useState("all");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [pageAt, setPageAt] = useState({ key: "", page: 0 });

  const items = useMemo(() => (plan.data?.plan_date === day ? plan.data.items : undefined), [plan.data, day]);
  const flagged = useMemo(() => new Set((anomalies.data?.items ?? []).map((a) => a.agent_id)), [anomalies.data]);
  const shown = useMemo(() => {
    const q = query.trim().toUpperCase();
    return (items ?? []).filter(
      (r) =>
        (status === "all" || r.status === status) &&
        (territory === "all" || r.territory === territory) &&
        (!reviewOnly || r.evidence.review?.flag) &&
        (!q || r.agent_id.includes(q) || r.runner_id.includes(q)),
    );
  }, [items, status, territory, reviewOnly, query]);
  // a new day or filter starts again at the first page
  const filterKey = `${day}|${status}|${territory}|${reviewOnly}|${query}`;
  const page = pageAt.key === filterKey ? pageAt.page : 0;
  const pages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const visible = shown.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const goTo = (p: number) => setPageAt({ key: filterKey, page: Math.max(0, Math.min(pages - 1, p)) });

  const counts = useMemo(() => {
    const c = { pending: 0, approved: 0, rejected: 0, review: 0 };
    items?.forEach((r) => {
      c[r.status]++;
      if (r.evidence.review?.flag) c.review++;
    });
    return c;
  }, [items]);

  if (meta.error) return <ErrorNotice error={meta.error} onRetry={meta.reload} />;
  if (!meta.data || !day) return <Skeleton className="h-96 w-full" />;

  return (
    <div className="space-y-5">
      <PageHeader
        title={t.queue.title}
        subtitle={t.queue.subtitle}
        actions={<DayControl meta={meta.data} day={day} onChange={setDay} />}
      />

      {role === "analyst" && (
        <p className="flex items-center gap-2 rounded-md border border-brand/20 bg-brand-tint px-3 py-2 text-sm text-brand">
          <Info aria-hidden className="size-4 shrink-0" />
          {t.queue.analystNote}
        </p>
      )}

      <ErrorNotice error={plan.error} onRetry={plan.reload} />

      <section className="rounded-lg border border-line bg-surface">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line px-4 py-3 text-sm">
          <Count n={items?.length} label={t.common.total} strong />
          <Count n={items && counts.pending} label={t.queue.summary.pending} />
          <Count n={items && counts.approved} label={t.queue.summary.approved} />
          <Count n={items && counts.rejected} label={t.queue.summary.rejected} />
          <Count n={items && counts.review} label={t.queue.summary.review} />
        </div>

        <div className="flex flex-wrap items-center gap-3 border-b border-line bg-page/60 px-4 py-2.5">
          <label className="relative">
            <span className="sr-only">{t.common.search}</span>
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-fg-3" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.queue.searchPlaceholder}
              className="h-8 w-48 rounded-md border border-line-strong bg-surface pr-2 pl-8 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-fg-2">
            {t.queue.filterTerritory}
            <select
              value={territory}
              onChange={(e) => setTerritory(e.target.value)}
              className="h-8 rounded-md border border-line-strong bg-surface px-2 text-sm text-fg"
            >
              <option value="all">{t.common.all}</option>
              {meta.data.territories.map((ter) => (
                <option key={ter.territory} value={ter.territory}>
                  {ter.territory} · {lang === "bn" ? ter.district_bn : ter.district_en}
                </option>
              ))}
            </select>
          </label>
          <Segmented<StatusFilter>
            label={t.queue.filterStatus}
            size="sm"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: t.common.all },
              { value: "pending", label: t.status.pending },
              { value: "approved", label: t.status.approved },
              { value: "rejected", label: t.status.rejected },
            ]}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={reviewOnly}
              onChange={(e) => setReviewOnly(e.target.checked)}
              className="size-4 accent-[#0c55a4]"
            />
            {t.queue.filterReview}
          </label>
          {items && (
            <span className="ml-auto text-xs text-fg-3">{t.queue.showing(shown.length, items.length)}</span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <thead className="text-left text-xs text-fg-2">
              <tr className="border-b border-line">
                <th scope="col" className="px-3 py-2 pl-4 font-medium">
                  {t.queue.colAgent}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t.queue.colRunner}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {t.queue.colBalance}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t.queue.colRisk} <span className="font-normal text-fg-3">({t.provenance.prediction})</span>
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {t.queue.colTarget}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {t.queue.colValue}
                </th>
                <th scope="col" className="px-3 py-2 pr-4 font-medium">
                  {t.queue.colDecision}
                </th>
              </tr>
            </thead>
            <tbody>
              {!items && !plan.error && (
                <tr>
                  <td colSpan={7} className="p-4">
                    <div className="space-y-2">
                      <Skeleton className="h-9" />
                      <Skeleton className="h-9" />
                      <Skeleton className="h-9" />
                    </div>
                  </td>
                </tr>
              )}
              {items && shown.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <Empty>{items.length ? t.queue.emptyFiltered : t.queue.empty}</Empty>
                  </td>
                </tr>
              )}
              {visible.map((r) => (
                <Fragment key={r.id}>
                  <Row
                    rec={r}
                    open={!!open[r.id]}
                    anomaly={flagged.has(r.agent_id)}
                    onToggle={() => setOpen((o) => ({ ...o, [r.id]: !o[r.id] }))}
                  />
                  {open[r.id] && (
                    <tr id={`why-${r.id}`} className="border-b border-line bg-page/70">
                      <td colSpan={7} className="px-4 py-4">
                        <Why rec={r} day={day} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        {shown.length > PAGE_SIZE && (
          <nav
            className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5 text-sm"
            aria-label={t.queue.pagination}
          >
            <span className="num text-xs text-fg-2">
              {t.queue.range(page * PAGE_SIZE + 1, Math.min(shown.length, (page + 1) * PAGE_SIZE), shown.length)}
            </span>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => goTo(page - 1)} disabled={page === 0}>
                ← {t.queue.prevPage}
              </Button>
              <Button size="sm" onClick={() => goTo(page + 1)} disabled={page >= pages - 1}>
                {t.queue.nextPage} →
              </Button>
            </div>
          </nav>
        )}
      </section>
    </div>
  );
}

function Count({ n, label, strong }: { n: number | undefined; label: string; strong?: boolean }) {
  const { f } = useLang();
  return (
    <span className="text-fg-2">
      <span className={cx("num font-semibold", strong ? "text-fg" : "text-fg")}>{n === undefined ? "…" : f.num(n)}</span>{" "}
      {label}
    </span>
  );
}

function Row({
  rec: r,
  open,
  anomaly,
  onToggle,
}: {
  rec: Recommendation;
  open: boolean;
  anomaly: boolean;
  onToggle: () => void;
}) {
  const { t, f } = useLang();
  const ev = r.evidence;
  return (
    <tr className={cx("border-b border-line align-top", open && "border-b-0 bg-page/70")}>
      <td className="px-3 py-2.5 pl-4">
        <Link href={`/agents/${r.agent_id}?day=${r.plan_date}`} className="font-semibold text-fg hover:text-brand hover:underline">
          {r.agent_id}
        </Link>
        <div className="text-xs text-fg-3">{r.territory}</div>
        {(ev.review?.flag || anomaly) && (
          <div className="mt-1 flex flex-wrap gap-1">
            {ev.review?.flag && <ReviewBadge />}
            {anomaly && <AnomalyBadge />}
          </div>
        )}
        <button
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={`why-${r.id}`}
          className="mt-1 inline-flex items-center gap-0.5 text-xs font-medium text-brand hover:underline"
        >
          {open ? <ChevronDown aria-hidden className="size-3.5" /> : <ChevronRight aria-hidden className="size-3.5" />}
          {open ? t.queue.hideWhy : t.queue.why}
        </button>
      </td>
      <td className="px-3 py-2.5 text-fg-2">{r.runner_id}</td>
      <td className="num px-3 py-2.5 text-right">
        <div>{f.tk(ev.cash_tk)}</div>
        <div className="text-xs text-fg-3">{f.tk(ev.efloat_tk)}</div>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-col items-start gap-1">
          <RiskBadge p={ev.p_stockout_cash} side={t.common.cash} />
          <RiskBadge p={ev.p_stockout_efloat} side={t.common.efloat} />
        </div>
      </td>
      <td className="num px-3 py-2.5 text-right">{f.tk(r.target_cash_tk)}</td>
      <td className="num px-3 py-2.5 text-right font-medium">{f.tk(r.value_tk)}</td>
      <td className="px-3 py-2.5 pr-4">
        <DecisionControls rec={r} />
      </td>
    </tr>
  );
}

function Why({ rec, day }: { rec: Recommendation; day: string }) {
  const { t } = useLang();
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-fg-2 uppercase">{t.why.explanation}</h3>
        <ExplanationBlock rec={rec} />
      </div>
      <div>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-fg-2 uppercase">{t.why.drivers}</h3>
        <DriverList drivers={rec.evidence.drivers} />
      </div>
      <div>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-fg-2 uppercase">{t.why.reasons}</h3>
        <ReasonList review={rec.evidence.review} />
        <Link
          href={`/agents/${rec.agent_id}?day=${day}`}
          className="mt-4 inline-block text-sm font-medium text-brand hover:underline"
        >
          {t.why.openTrace} →
        </Link>
      </div>
    </div>
  );
}
