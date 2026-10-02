"use client";

import { AlertTriangle, Bot, Check, ChevronDown, Clock3, FileText, Flag, FlaskConical, Inbox, Sparkles, X } from "lucide-react";
import {
  useEffect,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import { ApiError, type Status } from "@/lib/api";
import { RISK_SHAPE, riskLevel, type RiskLevel } from "@/lib/format";
import { useLang } from "@/lib/i18n";

export function cx(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON: Record<Variant, string> = {
  primary:
    "bg-brand text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_1px_2px_rgb(5_6_8/0.2)] hover:bg-brand-strong disabled:bg-brand/55 disabled:shadow-none",
  secondary: "border border-line-strong bg-surface text-fg shadow-xs hover:bg-tray disabled:text-fg-3",
  ghost: "text-fg-2 hover:bg-sunken hover:text-fg disabled:text-fg-3",
  danger: "border border-line-strong bg-surface text-danger-text shadow-xs hover:bg-danger-tint disabled:text-fg-3",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed",
        size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm",
        BUTTON[variant],
        className,
      )}
      {...props}
    />
  );
}

// Square icon-only button; `label` is its accessible name and tooltip.
export function IconButton({
  label,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-line bg-surface text-fg-2 shadow-xs transition-colors hover:bg-tray hover:text-fg disabled:text-line-strong",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

// A tray: a grey frame with a small caps title, holding a white card.
export function Panel({
  title,
  aside,
  children,
  className,
  bodyClassName,
  footer,
  id,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  footer?: ReactNode;
  id?: string;
}) {
  return (
    <section className={cx("flex flex-col rounded-2xl border border-line bg-tray p-1", className)} aria-labelledby={id}>
      {(title || aside) && (
        <header className="flex min-h-10 flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-3 py-1.5">
          {title && (
            <h2 id={id} className="eyebrow flex items-center gap-2 text-fg-2">
              {title}
            </h2>
          )}
          {aside && <div className="flex flex-wrap items-center gap-2">{aside}</div>}
        </header>
      )}
      <div className={cx("flex-1 rounded-xl border border-line bg-surface p-4 shadow-card", bodyClassName)}>{children}</div>
      {footer && <div className="px-3 pt-2 pb-1.5 text-xs text-fg-3">{footer}</div>}
    </section>
  );
}

// Thin bars of a short series, the current one dark (decorative: the number sits beside it).
export function MiniBars({ values, active }: { values: number[]; active?: number }) {
  const max = Math.max(1, ...values);
  return (
    <span aria-hidden className="flex h-7 shrink-0 items-end gap-[3px]">
      {values.map((v, i) => (
        <span
          key={i}
          className={cx("w-[3px] rounded-full", i === active ? "bg-ink" : "bg-line-strong")}
          style={{ height: `${Math.max(10, (v / max) * 100)}%` }}
        />
      ))}
    </span>
  );
}

// A KPI card: small caps label, a large mono value, an optional series, and a footer line.
export function Stat({
  label,
  value,
  hint,
  tone,
  spark,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "danger" | "warn";
  spark?: { values: number[]; active?: number };
}) {
  return (
    <div className="flex min-w-0 flex-col rounded-2xl border border-line bg-tray p-1">
      <div className="flex min-w-0 flex-1 flex-col justify-between gap-2.5 rounded-xl border border-line bg-surface px-3.5 pt-3 pb-3 shadow-card">
        <div className="eyebrow line-clamp-2 text-fg-3">{label}</div>
        <div className="flex items-end justify-between gap-2">
          <div
            className={cx(
              "num text-[26px] leading-none font-semibold tracking-[-0.02em]",
              tone === "danger" ? "text-danger-text" : tone === "warn" ? "text-warn-text" : "text-fg",
            )}
          >
            {value}
          </div>
          {spark && <MiniBars values={spark.values} active={spark.active} />}
        </div>
      </div>
      <div className="min-h-7 truncate px-2.5 pt-1.5 pb-1 text-xs text-fg-3">{hint ?? " "}</div>
    </div>
  );
}

const RISK_STYLE: Record<RiskLevel, string> = {
  high: "border-danger/25 bg-danger-tint text-danger-text",
  medium: "border-warn-mark/45 bg-warn-tint text-warn-text",
  low: "border-line bg-surface text-fg-2",
};

// Risk as shape + word + number; colour only repeats what the words say.
export function RiskBadge({ p, side, compact }: { p: number; side?: string; compact?: boolean }) {
  const { t, f } = useLang();
  const level = riskLevel(p);
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap",
        RISK_STYLE[level],
      )}
    >
      <span aria-hidden className="text-[10px] leading-none">
        {RISK_SHAPE[level]}
      </span>
      {side && <span className="font-normal">{side}</span>}
      <span className="num font-semibold">{f.pct(p)}</span>
      {compact ? <span className="sr-only">{t.risk[level]}</span> : <span>{t.risk[level]}</span>}
    </span>
  );
}

export function StatusBadge({ status }: { status: Status }) {
  const { t } = useLang();
  const style = {
    pending: "border-accent/70 bg-accent-tint text-ink",
    approved: "border-ok-text/20 bg-ok-tint text-ok-text",
    rejected: "border-line-strong bg-surface text-fg-2",
  }[status];
  const Icon = { pending: Clock3, approved: Check, rejected: X }[status];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border py-0.5 pr-2 pl-1.5 text-xs font-semibold whitespace-nowrap",
        style,
      )}
    >
      <Icon aria-hidden className="size-3.5" strokeWidth={2.5} />
      {t.status[status]}
    </span>
  );
}

export function ReviewBadge() {
  const { t } = useLang();
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-accent py-0.5 pr-2 pl-1.5 text-xs font-semibold whitespace-nowrap text-ink"
      title={t.review.tip}
    >
      <Flag aria-hidden className="size-3" strokeWidth={2.5} />
      {t.review.tag}
    </span>
  );
}

export function AnomalyBadge() {
  const { t } = useLang();
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-ink/70 bg-surface py-0.5 pr-2 pl-1.5 text-xs font-semibold whitespace-nowrap text-ink"
      title={t.anomaly.note}
    >
      <AlertTriangle aria-hidden className="size-3" strokeWidth={2.5} />
      {t.anomaly.tag}
    </span>
  );
}

export type ProvenanceKind = "prediction" | "assumption" | "ai" | "template" | "evaluation";

// Every output says what it is: a model's prediction, an assumption, AI-written text, a
// template, or a measured evaluation result.
export function Provenance({ kind }: { kind: ProvenanceKind }) {
  const { t } = useLang();
  const meta = {
    prediction: { Icon: Sparkles, label: t.provenance.prediction, tip: t.provenance.predictionTip },
    assumption: { Icon: FlaskConical, label: t.provenance.assumption, tip: t.provenance.assumptionTip },
    ai: { Icon: Bot, label: t.provenance.ai, tip: t.provenance.aiTip },
    template: { Icon: FileText, label: t.provenance.template, tip: t.provenance.templateTip },
    evaluation: { Icon: Check, label: t.provenance.evaluation, tip: t.provenance.evaluationTip },
  }[kind];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2 py-0.5 text-[11px] font-medium whitespace-nowrap text-fg-2 shadow-xs"
      title={meta.tip}
    >
      <meta.Icon aria-hidden className="size-3" />
      {meta.label}
    </span>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  size = "md",
}: {
  label: string;
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg bg-sunken p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "inline-flex items-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors",
            size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]",
            value === o.value
              ? "bg-surface text-fg shadow-xs ring-1 ring-line"
              : "text-fg-2 hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// A count inside a segmented option or a nav item.
export function Count({ n, active }: { n: ReactNode; active?: boolean }) {
  return (
    <span
      className={cx(
        "num rounded px-1 text-[11px] leading-4",
        active ? "bg-sunken text-fg" : "bg-surface/70 text-fg-3",
      )}
    >
      {n}
    </span>
  );
}

// Native select with the app's frame and chevron.
export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={cx("relative inline-flex", className)}>
      <select
        className="h-8 w-full cursor-pointer appearance-none rounded-lg border border-line-strong bg-surface pr-8 pl-2.5 text-sm text-fg shadow-xs outline-none hover:bg-tray focus:border-brand focus:ring-2 focus:ring-brand/20"
        {...props}
      >
        {children}
      </select>
      <ChevronDown aria-hidden className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-fg-3" />
    </span>
  );
}

// Table head cells and rows share these.
export const TH = "eyebrow px-3 py-2.5 text-left font-medium text-fg-3 whitespace-nowrap";
export const THEAD = "border-b border-line bg-tray";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-lg bg-sunken", className)} />;
}

// One way to show an API refusal. A 429 counts down its Retry-After before offering a retry.
const errorIds = new WeakMap<object, number>();
let lastErrorId = 0;

function errorId(e: unknown) {
  if (typeof e !== "object" || e === null) return 0;
  if (!errorIds.has(e)) errorIds.set(e, ++lastErrorId);
  return errorIds.get(e)!;
}

export function ErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  return <ErrorBody key={errorId(error)} error={error} onRetry={onRetry} />;
}

function ErrorBody({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useLang();
  const retryAfter = error instanceof ApiError ? error.retryAfterS : null;
  const [left, setLeft] = useState(retryAfter ?? 0);
  useEffect(() => {
    if (!retryAfter) return;
    const started = Date.now();
    const id = setInterval(() => {
      const rest = Math.max(0, retryAfter - Math.floor((Date.now() - started) / 1000));
      setLeft(rest);
      if (rest === 0) clearInterval(id);
    }, 250);
    return () => clearInterval(id);
  }, [retryAfter]);
  let message = error instanceof Error ? error.message : String(error);
  if (error instanceof ApiError && error.status === 0) message = t.common.unreachable;
  if (error instanceof ApiError && error.status === 429) message = t.common.retryIn(left);
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-xl border border-danger/30 bg-danger-tint px-3.5 py-2.5 text-sm text-danger-text"
    >
      <AlertTriangle aria-hidden className="size-4 shrink-0" />
      <span className="min-w-0 flex-1">{message}</span>
      {onRetry && (
        <Button size="sm" onClick={onRetry} disabled={left > 0}>
          {t.common.retry}
        </Button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-12 text-center text-sm text-fg-2">
      <span className="flex size-10 items-center justify-center rounded-xl border border-line bg-tray text-fg-3">
        <Inbox aria-hidden className="size-5" />
      </span>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2 text-fg-3">{eyebrow}</div>}
        <h1 className="text-[26px] leading-8 font-semibold tracking-[-0.02em] text-fg">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-3xl text-sm text-fg-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function TableToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { t } = useLang();
  return (
    <button
      type="button"
      className="h-7 rounded-md border border-line bg-surface px-2 text-xs font-medium text-fg-2 shadow-xs hover:bg-tray hover:text-fg"
      aria-expanded={open}
      onClick={onToggle}
    >
      {open ? t.common.hideTable : t.common.showTable}
    </button>
  );
}
