"use client";

import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, Info, Search } from "lucide-react";
import Link from "next/link";
import { Fragment, Suspense, useMemo, useState, type ReactNode } from "react";

import { DayControl } from "@/components/day";
import { DecisionControls, DriverList, ExplanationBlock, ReasonList } from "@/components/evidence";
import { Staff } from "@/components/shell";
import {
  AnomalyBadge,
  Button,
  Count,
  cx,
  Empty,
  ErrorNotice,
  PageHeader,
  ReviewBadge,
  RiskBadge,
  Segmented,
  Select,
  Skeleton,
  TH,
  THEAD,
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
  const { t, f, lang } = useLang();
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

  const n = (x: number | undefined) => (items ? f.num(x ?? 0) : "…");
  const option = (value: StatusFilter, label: string, count: number | undefined) => ({
    value,
    label: (
      <>
        {label} <Count n={n(count)} active={status === value} />
      </>
    ),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t.queue.title}
        subtitle={t.queue.subtitle}
        actions={<DayControl meta={meta.data} day={day} onChange={setDay} />}
      />

      {role === "analyst" && (
        <p className="flex items-center gap-2.5 rounded-xl border border-brand/20 bg-brand-tint px-3.5 py-2.5 text-sm text-brand">
          <Info aria-hidden className="size-4 shrink-0" />
          {t.queue.analystNote}
        </p>
      )}

      <ErrorNotice error={plan.error} onRetry={plan.reload} />

      <section className="rounded-2xl border border-line bg-tray p-1">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-2 py-1.5">
          <Segmented<StatusFilter>
            label={t.queue.filterStatus}
            size="sm"
            value={status}
            onChange={setStatus}
            options={[
              option("all", t.common.all, items?.length),
              option("pending", t.status.pending, counts.pending),
              option("approved", t.status.approved, counts.approved),
              option("rejected", t.status.rejected, counts.rejected),
            ]}
          />
          {items && (
            <span className="num ml-auto text-xs text-fg-3">{t.queue.showing(shown.length, items.length)}</span>
          )}
        </div>

        <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
          <div className="flex flex-wrap items-center gap-2.5 border-b border-line px-3 py-2.5">
            <label className="relative">
              <span className="sr-only">{t.common.search}</span>
              <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-fg-3" />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t.queue.searchPlaceholder}
                className="h-8 w-52 rounded-lg border border-line-strong bg-surface pr-2 pl-8 text-sm shadow-xs outline-none placeholder:text-fg-3 focus:border-brand focus:ring-2 focus:ring-brand/20"
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-fg-3">
              {t.queue.filterTerritory}
              <Select value={territory} onChange={(e) => setTerritory(e.target.value)}>
                <option value="all">{t.common.all}</option>
                {meta.data.territories.map((ter) => (
                  <option key={ter.territory} value={ter.territory}>
                    {ter.territory} · {lang === "bn" ? ter.district_bn : ter.district_en}
                  </option>
                ))}
              </Select>
            </label>
            <label
              className={cx(
                "inline-flex h-8 cursor-pointer items-center gap-2 rounded-lg border px-2.5 text-[13px] shadow-xs transition-colors",
                reviewOnly ? "border-accent bg-accent-tint text-ink" : "border-line-strong bg-surface text-fg hover:bg-tray",
              )}
            >
              <input
                type="checkbox"
                checked={reviewOnly}
                onChange={(e) => setReviewOnly(e.target.checked)}
                className="size-4 accent-[#0c55a4]"
              />
              {t.queue.filterReview}
              <Count n={n(counts.review)} active />
            </label>
          </div>

          <ul className="divide-y divide-line md:hidden">
            {!items && !plan.error && (
              <li className="space-y-2 p-3">
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
              </li>
            )}
            {items && shown.length === 0 && (
              <li>
                <Empty>{items.length ? t.queue.emptyFiltered : t.queue.empty}</Empty>
              </li>
            )}
            {visible.map((r) => (
              <Card
                key={r.id}
                rec={r}
                day={day}
                open={!!open[r.id]}
                anomaly={flagged.has(r.agent_id)}
                onToggle={() => setOpen((o) => ({ ...o, [r.id]: !o[r.id] }))}
              />
            ))}
          </ul>

          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-245 text-sm">
              <thead className={THEAD}>
                <tr>
                  <th scope="col" className={`${TH} pl-4`}>
                    {t.queue.colAgent}
                  </th>
                  <th scope="col" className={TH}>
                    {t.queue.colRunner}
                  </th>
                  <th scope="col" className={`${TH} text-right`}>
                    {t.queue.colBalance}
                  </th>
                  <th scope="col" className={TH}>
                    {t.queue.colRisk} <span className="normal-case">({t.provenance.prediction})</span>
                  </th>
                  <th scope="col" className={`${TH} text-right`}>
                    {t.queue.colTarget}
                  </th>
                  <th scope="col" className={`${TH} text-right`}>
                    {t.queue.colValue}
                  </th>
                  <th scope="col" className={`${TH} pr-4`}>
                    {t.queue.colDecision}
                  </th>
                </tr>
              </thead>
              <tbody>
                {!items && !plan.error && (
                  <tr>
                    <td colSpan={7} className="p-4">
                      <div className="space-y-2">
                        <Skeleton className="h-10" />
                        <Skeleton className="h-10" />
                        <Skeleton className="h-10" />
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
                      <tr id={`why-${r.id}`} className="border-b border-line bg-tray">
                        <td colSpan={7} className="px-3 py-3">
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
              className="flex items-center justify-between gap-3 border-t border-line bg-tray/50 px-4 py-2.5 text-sm"
              aria-label={t.queue.pagination}
            >
              <span className="num text-xs text-fg-2">
                {t.queue.range(page * PAGE_SIZE + 1, Math.min(shown.length, (page + 1) * PAGE_SIZE), shown.length)}
              </span>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => goTo(page - 1)} disabled={page === 0}>
                  <ChevronLeft aria-hidden className="size-4" /> {t.queue.prevPage}
                </Button>
                <Button size="sm" onClick={() => goTo(page + 1)} disabled={page >= pages - 1}>
                  {t.queue.nextPage} <ChevronRight aria-hidden className="size-4" />
                </Button>
              </div>
            </nav>
          )}
        </div>
      </section>
    </div>
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
    <tr className={cx("border-b border-line align-top transition-colors", open ? "bg-tray" : "hover:bg-tray/50")}>
      <td className="px-3 py-3 pl-4">
        <Link
          href={`/agents/${r.agent_id}?day=${r.plan_date}`}
          className="mono font-semibold text-fg hover:text-brand hover:underline"
        >
          {r.agent_id}
        </Link>
        <div className="mono text-xs text-fg-3">{r.territory}</div>
        {(ev.review?.flag || anomaly) && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {ev.review?.flag && <ReviewBadge />}
            {anomaly && <AnomalyBadge />}
          </div>
        )}
        <div className="mt-1.5">
          <WhyToggle open={open} controls={`why-${r.id}`} onToggle={onToggle} />
        </div>
      </td>
      <td className="mono px-3 py-3 whitespace-nowrap text-fg-2">{r.runner_id}</td>
      <td className="num px-3 py-3 text-right">
        <div>{f.tk(ev.cash_tk)}</div>
        <div className="text-xs text-fg-3">{f.tk(ev.efloat_tk)}</div>
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-col items-start gap-1">
          <RiskBadge p={ev.p_stockout_cash} side={t.common.cash} />
          <RiskBadge p={ev.p_stockout_efloat} side={t.common.efloat} />
        </div>
      </td>
      <td className="num px-3 py-3 text-right">{f.tk(r.target_cash_tk)}</td>
      <td className="num px-3 py-3 text-right font-semibold">{f.tk(r.value_tk)}</td>
      <td className="px-3 py-3 pr-4">
        <DecisionControls rec={r} />
      </td>
    </tr>
  );
}

function WhyToggle({ open, controls, onToggle }: { open: boolean; controls: string; onToggle: () => void }) {
  const { t } = useLang();
  return (
    <button
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={controls}
      className={cx(
        "inline-flex h-6 items-center gap-0.5 rounded-md border pr-2 pl-1 text-xs font-medium transition-colors",
        open ? "border-ink bg-ink text-white" : "border-line bg-surface text-fg-2 shadow-xs hover:bg-tray hover:text-fg",
      )}
    >
      {open ? <ChevronDown aria-hidden className="size-3.5" /> : <ChevronRight aria-hidden className="size-3.5" />}
      {open ? t.queue.hideWhy : t.queue.why}
    </button>
  );
}

// The same visit as a card, for phones: what an approver needs to decide, then the evidence.
function Card({
  rec: r,
  day,
  open,
  anomaly,
  onToggle,
}: {
  rec: Recommendation;
  day: string;
  open: boolean;
  anomaly: boolean;
  onToggle: () => void;
}) {
  const { t, f } = useLang();
  const ev = r.evidence;
  return (
    <li className={cx("p-3", open && "bg-tray")}>
      <div className="flex gap-3">
        <span aria-hidden className="w-0.75 shrink-0 rounded-full bg-ink" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <Link href={`/agents/${r.agent_id}?day=${r.plan_date}`} className="mono font-semibold text-fg hover:text-brand">
                {r.agent_id}
              </Link>
              <div className="truncate text-xs text-fg-3">
                <span className="mono">{r.territory}</span> · {t.common.runner} <span className="mono">{r.runner_id}</span>
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className="num font-semibold">{f.tk(r.value_tk)}</div>
              <div className="text-[11px] text-fg-3">{t.queue.colValue}</div>
            </div>
          </div>
          {(ev.review?.flag || anomaly) && (
            <div className="mt-2 flex flex-wrap gap-1">
              {ev.review?.flag && <ReviewBadge />}
              {anomaly && <AnomalyBadge />}
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-1">
            <RiskBadge p={ev.p_stockout_cash} side={t.common.cash} />
            <RiskBadge p={ev.p_stockout_efloat} side={t.common.efloat} />
          </div>
          <dl className="mt-2.5 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-tray px-2.5 py-2">
              <dt className="text-fg-3">{t.queue.colBalance}</dt>
              <dd className="num mt-0.5 text-fg">
                {f.tk(ev.cash_tk)} · {f.tk(ev.efloat_tk)}
              </dd>
            </div>
            <div className="rounded-lg bg-tray px-2.5 py-2">
              <dt className="text-fg-3">{t.queue.colTarget}</dt>
              <dd className="num mt-0.5 text-fg">{f.tk(r.target_cash_tk)}</dd>
            </div>
          </dl>
          <div className="mt-3 flex flex-wrap items-start justify-between gap-2">
            <WhyToggle open={open} controls={`why-m-${r.id}`} onToggle={onToggle} />
            <DecisionControls rec={r} />
          </div>
        </div>
      </div>
      {open && (
        <div id={`why-m-${r.id}`} className="mt-3">
          <Why rec={r} day={day} />
        </div>
      )}
    </li>
  );
}

function WhyCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
      <h3 className="eyebrow mb-3 text-fg-3">{title}</h3>
      {children}
    </div>
  );
}

function Why({ rec, day }: { rec: Recommendation; day: string }) {
  const { t } = useLang();
  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
      <WhyCard title={t.why.explanation}>
        <ExplanationBlock rec={rec} />
      </WhyCard>
      <WhyCard title={t.why.drivers}>
        <DriverList drivers={rec.evidence.drivers} />
      </WhyCard>
      <WhyCard title={t.why.reasons}>
        <ReasonList review={rec.evidence.review} />
        <Link
          href={`/agents/${rec.agent_id}?day=${day}`}
          className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline"
        >
          {t.why.openTrace} <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </WhyCard>
    </div>
  );
}
