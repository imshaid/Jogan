"use client";

import { ArrowRight, Database, ExternalLink, KeyRound, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Public } from "@/components/shell";
import { AnomalyBadge, PageHeader, Panel, Provenance, ReviewBadge, RiskBadge, StatusBadge } from "@/components/ui";
import { RISK_BANDS } from "@/lib/format";
import { useLang } from "@/lib/i18n";

const REPO = "https://github.com/imshaid/Jogan";

export default function Page() {
  return (
    <Public>
      <AboutView />
    </Public>
  );
}

function AboutView() {
  const { t } = useLang();
  const a = t.about;
  return (
    <div className="space-y-6">
      <PageHeader title={a.title} subtitle={a.lead} />

      <section aria-labelledby="steps" className="rounded-2xl border border-line bg-tray p-1">
        <h2 id="steps" className="eyebrow px-3 py-2.5 text-fg-2">
          {a.stepsTitle}
        </h2>
        <ol className="grid grid-cols-1 gap-1 md:grid-cols-2 xl:grid-cols-4">
          {a.steps.map((s, i) => (
            <li key={s.t} className="relative rounded-xl border border-line bg-surface p-4 shadow-card">
              <div className="flex items-center gap-2.5">
                <span
                  className={
                    i === a.steps.length - 1
                      ? "mono flex h-6 min-w-8 items-center justify-center rounded-md bg-accent text-xs font-semibold text-ink"
                      : "mono flex h-6 min-w-8 items-center justify-center rounded-md bg-ink text-xs font-semibold text-white"
                  }
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="text-sm font-semibold">{s.t}</h3>
                {i < a.steps.length - 1 && (
                  <ArrowRight aria-hidden className="ml-auto hidden size-4 text-fg-3 xl:block" />
                )}
              </div>
              <p className="mt-2.5 text-sm leading-relaxed text-fg-2">{s.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel title={a.aiTitle}>
          <Bullets items={a.aiPoints} />
        </Panel>
        <Panel title={a.labelsTitle}>
          <dl className="space-y-3 text-sm">
            <LabelRow tag={<Provenance kind="prediction" />} text={t.provenance.predictionTip} />
            <LabelRow tag={<Provenance kind="template" />} text={t.provenance.templateTip} />
            <LabelRow tag={<Provenance kind="ai" />} text={t.provenance.aiTip} />
            <LabelRow tag={<Provenance kind="assumption" />} text={t.provenance.assumptionTip} />
            <LabelRow tag={<Provenance kind="evaluation" />} text={t.provenance.evaluationTip} />
            <LabelRow
              tag={
                <span className="flex flex-col items-start gap-1">
                  {/* the band edges themselves, not data */}
                  <RiskBadge p={RISK_BANDS.high} />
                  <RiskBadge p={RISK_BANDS.medium} />
                  <RiskBadge p={0} />
                </span>
              }
              text={`${t.risk.bandsNote} ${t.provenance.assumption}.`}
            />
            <LabelRow tag={<ReviewBadge />} text={t.review.tip} />
            <LabelRow tag={<AnomalyBadge />} text={t.anomaly.note} />
            <LabelRow tag={<StatusBadge status="pending" />} text={t.trace.what.decision} />
          </dl>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Panel
          title={
            <span className="flex items-center gap-2">
              <Database aria-hidden className="size-3.5 text-brand" /> {a.dataTitle}
            </span>
          }
        >
          <Bullets items={a.dataPoints} />
        </Panel>
        <Panel
          title={
            <span className="flex items-center gap-2">
              <KeyRound aria-hidden className="size-3.5 text-brand" /> {a.securityTitle}
            </span>
          }
        >
          <Bullets items={a.securityPoints} />
        </Panel>
        <Panel
          title={
            <span className="flex items-center gap-2">
              <ShieldCheck aria-hidden className="size-3.5 text-brand" /> {a.limitsTitle}
            </span>
          }
        >
          <p className="text-sm text-fg-2">{a.limitsLead}</p>
          <Link href="/impact#not-win" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
            {a.limitsLink} <ArrowRight aria-hidden className="size-3.5" />
          </Link>
          <a
            href={REPO}
            target="_blank"
            rel="noreferrer"
            className="mt-4 flex items-center gap-1 text-sm font-medium text-brand hover:underline"
          >
            {a.source} <ExternalLink aria-hidden className="size-3.5" />
          </a>
        </Panel>
      </div>
    </div>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2.5 text-sm leading-relaxed text-fg">
      {items.map((x) => (
        <li key={x} className="flex gap-2.5">
          <span aria-hidden className="mt-[9px] size-1.5 shrink-0 rounded-[2px] bg-brand" />
          <span>{x}</span>
        </li>
      ))}
    </ul>
  );
}

function LabelRow({ tag, text }: { tag: ReactNode; text: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,150px)_1fr] items-start gap-3">
      <dt>{tag}</dt>
      <dd className="text-fg-2">{text}</dd>
    </div>
  );
}
