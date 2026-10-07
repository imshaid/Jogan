"use client";

import { Check, X } from "lucide-react";
import { useState } from "react";

import { api, type Driver, type Explanation, type Recommendation, type Review } from "@/lib/api";
import { useDecide } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";
import { toast } from "@/lib/live";
import { useSession } from "@/lib/session";

import { Button, cx, ErrorNotice, Provenance, StatusBadge } from "./ui";

// What pushes the forecast drain up or down: TreeSHAP effects relative to the model's average,
// as diverging bars (up = more drain, warm; down = less drain, cool), with the sign in words.
export function DriverList({ drivers }: { drivers: Driver[] }) {
  const { lang, f } = useLang();
  if (!drivers.length) return null;
  const max = Math.max(...drivers.map((d) => Math.abs(d.effect_pct)), 1);
  return (
    <ul className="space-y-3">
      {drivers.map((d) => {
        const up = d.effect_pct >= 0;
        const w = (Math.abs(d.effect_pct) / max) * 50;
        return (
          <li key={d.feature} className="text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0" lang={lang}>
                {d.label[lang]} <span className="text-fg-2">({d.value_text[lang]})</span>
              </span>
              <span className={cx("num shrink-0 text-xs font-semibold", up ? "text-warn-text" : "text-brand")}>
                <span aria-hidden>{up ? "↑" : "↓"} </span>
                {f.signed(d.effect_pct, 0)}%
              </span>
            </div>
            <div aria-hidden className="relative mt-1.5 h-1.5 rounded-full bg-sunken">
              <span className="absolute inset-y-[-2px] left-1/2 w-px bg-line-strong" />
              <span
                className={cx(
                  "anim-grow-x absolute inset-y-0 rounded-full",
                  up ? "left-1/2 bg-warn-mark" : "right-1/2 bg-brand",
                )}
                style={{ width: `${w}%`, transformOrigin: up ? "0 50%" : "100% 50%" }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function ReasonList({ review }: { review?: Review }) {
  const { t, lang } = useLang();
  if (!review || !review.flag) return <p className="text-sm text-fg-2">{t.review.none}</p>;
  return (
    <ul className="space-y-1.5">
      {review.reasons.map((r, i) => (
        <li key={`${r.code}-${i}`} className="flex gap-2 text-sm" lang={lang}>
          <span aria-hidden className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md bg-accent text-[10px] text-ink">
            ⚑
          </span>
          {r.text[lang]}
        </li>
      ))}
    </ul>
  );
}

// The explanation of record is the template; AI rewording is on request and labelled.
export function ExplanationBlock({ rec }: { rec: Recommendation }) {
  const { t, lang } = useLang();
  const { token } = useSession();
  const [reworded, setReworded] = useState<Record<string, Explanation>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const mine = reworded[lang];
  const ai = mine?.source === "gemini";

  async function reword() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.explanation(token!, rec.id, lang);
      setReworded((m) => ({ ...m, [lang]: r }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Provenance kind={ai ? "ai" : "template"} />
        <Provenance kind="prediction" />
      </div>
      <p lang={lang} className="max-w-prose text-sm leading-relaxed text-fg">
        {mine ? mine.text : rec.explanation[lang]}
      </p>
      <p className="text-xs text-fg-2">
        {ai ? (
          <>
            {t.why.aiNote(mine.model ?? "")}{" "}
            <button
              className="font-medium text-brand hover:underline"
              onClick={() =>
                setReworded((m) => {
                  const next = { ...m };
                  delete next[lang];
                  return next;
                })
              }
            >
              {t.why.showTemplate}
            </button>
          </>
        ) : mine ? (
          t.why.aiRefused(mine.note ?? "—")
        ) : (
          <>
            {t.why.templateNote}{" "}
            <button className="font-medium text-brand hover:underline disabled:text-fg-3" disabled={busy} onClick={reword}>
              {busy ? t.why.rewording : t.why.reword}
            </button>
          </>
        )}
      </p>
      <ErrorNotice error={error} />
    </div>
  );
}

// Approve / reject for approvers; a flagged visit asks for a note first. Analysts see the status.
export function DecisionControls({
  rec,
  onDecided,
  layout = "row",
}: {
  rec: Recommendation;
  onDecided?: (r: Recommendation) => void;
  layout?: "row" | "stack";
}) {
  const { t, f } = useLang();
  const { role } = useSession();
  const decide = useDecide();
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (rec.status !== "pending" || role !== "approver") {
    return (
      <div className="space-y-1">
        <StatusBadge status={rec.status} />
        {rec.decided_at && <div className="text-xs text-fg-3">{f.when(rec.decided_at)}</div>}
        {rec.decision_note && <div className="max-w-56 text-xs break-words text-fg-2">“{rec.decision_note}”</div>}
      </div>
    );
  }

  async function run(decision: "approved" | "rejected", withNote?: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await decide(rec, decision, withNote);
      setNoteOpen(false);
      setNote("");
      toast({
        tone: decision === "approved" ? "ok" : "info",
        title: decision === "approved" ? t.live.ownApproved(rec.agent_id) : t.live.ownRejected(rec.agent_id),
        body: t.live.ownBody,
      });
      onDecided?.(r);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const flagged = rec.evidence.review?.flag;
  return (
    <div className="space-y-2">
      {noteOpen ? (
        <form
          className="flex min-w-56 flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            run("approved", note);
          }}
        >
          <label className="text-xs font-medium text-fg" htmlFor={`note-${rec.id}`}>
            {t.queue.noteLabel}
          </label>
          <textarea
            id={`note-${rec.id}`}
            className="min-h-16 rounded-lg border border-line-strong bg-surface px-2.5 py-2 text-sm shadow-xs outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            maxLength={500}
            value={note}
            placeholder={t.queue.notePlaceholder}
            onChange={(e) => setNote(e.target.value)}
            required
            autoFocus
          />
          <div className="flex gap-2">
            <Button variant="primary" size="sm" disabled={busy || !note.trim()}>
              <Check aria-hidden className="size-3.5" /> {t.queue.approveWithNote}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setNoteOpen(false)}>
              {t.queue.cancel}
            </Button>
          </div>
        </form>
      ) : (
        <div className={cx("flex gap-2", layout === "stack" && "flex-col sm:flex-row")}>
          <Button
            variant="primary"
            size="sm"
            disabled={busy}
            onClick={() => (flagged ? setNoteOpen(true) : run("approved"))}
          >
            <Check aria-hidden className="size-3.5" /> {t.queue.approve}
          </Button>
          <Button variant="danger" size="sm" disabled={busy} onClick={() => run("rejected")}>
            <X aria-hidden className="size-3.5" /> {t.queue.reject}
          </Button>
        </div>
      )}
      <ErrorNotice error={error} />
    </div>
  );
}
