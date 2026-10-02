"use client";

import { AlertTriangle, Bot, Check, Clock3, FileText, Flag, FlaskConical, Sparkles, X } from "lucide-react";
import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

import { ApiError, type Status } from "@/lib/api";
import { RISK_SHAPE, riskLevel, type RiskLevel } from "@/lib/format";
import { useLang } from "@/lib/i18n";

export function cx(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-strong disabled:bg-brand/60",
  secondary: "border border-line-strong bg-surface text-fg hover:bg-page disabled:text-fg-3",
  ghost: "text-brand hover:bg-brand-tint disabled:text-fg-3",
  danger: "border border-line-strong bg-surface text-danger-text hover:bg-danger-tint disabled:text-fg-3",
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
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed",
        size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm",
        BUTTON[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Panel({
  title,
  aside,
  children,
  className,
  bodyClassName,
  id,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", className)} aria-labelledby={id}>
      {(title || aside) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          {title && (
            <h2 id={id} className="text-sm font-semibold text-fg">
              {title}
            </h2>
          )}
          {aside && <div className="flex items-center gap-2">{aside}</div>}
        </header>
      )}
      <div className={cx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "danger" | "warn";
}) {
  return (
    <div className="min-w-0 px-4 py-3">
      <div className="truncate text-xs font-medium text-fg-2">{label}</div>
      <div
        className={cx(
          "mt-1 text-[22px] leading-7 font-semibold tracking-tight",
          tone === "danger" ? "text-danger-text" : tone === "warn" ? "text-warn-text" : "text-fg",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 truncate text-xs text-fg-3">{hint}</div>}
    </div>
  );
}

const RISK_STYLE: Record<RiskLevel, string> = {
  high: "bg-danger-tint text-danger-text ring-danger/25",
  medium: "bg-warn-tint text-warn-text ring-warn-mark/40",
  low: "bg-sunken text-fg-2 ring-line-strong/60",
};

// Risk as shape + word + number; colour only repeats what the words say.
export function RiskBadge({ p, side, compact }: { p: number; side?: string; compact?: boolean }) {
  const { t, f } = useLang();
  const level = riskLevel(p);
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
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
    pending: "bg-accent-tint text-ink ring-accent/70",
    approved: "bg-ok-tint text-ok-text ring-ok-text/25",
    rejected: "bg-sunken text-fg-2 ring-line-strong",
  }[status];
  const Icon = { pending: Clock3, approved: Check, rejected: X }[status];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap ring-1 ring-inset",
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
      className="inline-flex items-center gap-1 rounded bg-accent px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap text-ink"
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
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap text-ink ring-1 ring-ink/70 ring-inset"
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
      className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-surface px-2 py-0.5 text-[11px] font-medium whitespace-nowrap text-fg-2"
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
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-[5px] font-medium whitespace-nowrap transition-colors",
            size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-[13px]",
            value === o.value ? "bg-brand text-white" : "text-fg-2 hover:bg-page hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded bg-sunken", className)} />;
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
      className="flex flex-wrap items-center gap-3 rounded-md border border-danger/40 bg-danger-tint px-3 py-2 text-sm text-danger-text"
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
  return <div className="px-4 py-10 text-center text-sm text-fg-2">{children}</div>;
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-fg-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function TableToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { t } = useLang();
  return (
    <button type="button" className="text-xs font-medium text-brand hover:underline" aria-expanded={open} onClick={onToggle}>
      {open ? t.common.hideTable : t.common.showTable}
    </button>
  );
}
