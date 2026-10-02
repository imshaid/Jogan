"use client";

import { CalendarDays, ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";

import type { Meta } from "@/lib/api";
import { useLang } from "@/lib/i18n";

import { cx, IconButton } from "./ui";

const PLAY_MS = 1600;

// Previous / next / pick a plan day, and play through them.
export function DayControl({
  meta,
  day,
  onChange,
  playable,
}: {
  meta: Meta;
  day: string;
  onChange: (d: string) => void;
  playable?: boolean;
}) {
  const { t, f } = useLang();
  const dates = meta.plan_dates;
  const i = dates.indexOf(day);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = setTimeout(() => {
      if (i < dates.length - 1) onChange(dates[i + 1]);
      else setPlaying(false);
    }, PLAY_MS);
    return () => clearTimeout(id);
  }, [playing, i, dates, onChange]);

  const step =
    "flex w-9 items-center justify-center text-fg-2 transition-colors hover:bg-tray hover:text-fg disabled:text-line-strong disabled:hover:bg-transparent";
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-9 items-stretch overflow-hidden rounded-lg border border-line-strong bg-surface shadow-xs">
        <button className={step} onClick={() => onChange(dates[i - 1])} disabled={i <= 0} aria-label={t.common.prevDay}>
          <ChevronLeft className="size-4" />
        </button>
        <label className="relative flex items-center border-x border-line hover:bg-tray focus-within:bg-brand-tint focus-within:ring-2 focus-within:ring-brand focus-within:ring-inset">
          <span className="sr-only">{t.common.planDay}</span>
          <CalendarDays aria-hidden className="pointer-events-none absolute left-2.5 size-4 text-fg-3" />
          <select
            className="h-full cursor-pointer appearance-none bg-transparent pr-3 pl-8 text-sm font-medium outline-none"
            value={day}
            onChange={(e) => {
              setPlaying(false);
              onChange(e.target.value);
            }}
          >
            {dates.map((d) => (
              <option key={d} value={d}>
                {f.day(d)}
              </option>
            ))}
          </select>
        </label>
        <button
          className={step}
          onClick={() => onChange(dates[i + 1])}
          disabled={i >= dates.length - 1}
          aria-label={t.common.nextDay}
        >
          <ChevronRight className="size-4" />
        </button>
      </div>
      {playable && (
        <IconButton
          label={playing ? t.common.pause : t.common.play}
          aria-pressed={playing}
          onClick={() => {
            if (!playing && i >= dates.length - 1) onChange(dates[0]);
            setPlaying((p) => !p);
          }}
          className={cx("border-line-strong", playing && "border-ink bg-ink text-white hover:bg-ink/85 hover:text-white")}
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </IconButton>
      )}
      <span className="num hidden text-xs text-fg-3 xl:inline">{t.common.plannedAt(f.hour(meta.plan_hour))}</span>
    </div>
  );
}

const ROWS = 8;

// Planned visits per plan day as columns of blocks, two blocks wide; each column picks its day.
export function Timeline({ meta, day, onChange }: { meta: Meta; day: string; onChange: (d: string) => void }) {
  const { t, f } = useLang();
  const max = Math.max(1, ...meta.days.map((d) => d.visits));
  const [lo, hi] = meta.test_window;
  return (
    <section className="rounded-2xl border border-line bg-tray p-1" aria-labelledby="timeline-title">
      <header className="flex min-h-10 flex-wrap items-center justify-between gap-x-3 px-3 py-1.5">
        <h2 id="timeline-title" className="eyebrow text-fg-2">
          {t.network.timeline}
        </h2>
        <span className="num text-xs text-fg-3">
          {f.dayShort(lo)} – {f.dayShort(hi)}
        </span>
      </header>
      <div className="rounded-xl border border-line bg-surface px-3 pt-4 pb-2 shadow-card">
        <div className="flex items-end gap-1 overflow-x-auto pb-1" role="group" aria-label={t.network.timeline}>
          {meta.days.map((d) => {
            const selected = d.date === day;
            const label = `${f.day(d.date)}: ${d.visits ? `${f.num(d.visits)} ${t.common.visitsShort}` : t.common.noRunners}`;
            // blocks filled bottom-up, left then right, so the top row shows the remainder
            const filled = d.visits ? Math.max(1, Math.round((d.visits / max) * ROWS * 2)) : 0;
            return (
              <button
                key={d.date}
                onClick={() => onChange(d.date)}
                aria-pressed={selected}
                aria-label={label}
                title={label}
                className={cx(
                  "group flex min-w-7.5 flex-1 flex-col items-center gap-1.5 rounded-lg px-0.5 pt-1.5 pb-1 transition-colors",
                  selected ? "bg-brand-tint" : "hover:bg-tray",
                )}
              >
                <span aria-hidden className="grid grid-flow-row grid-cols-2 gap-0.5">
                  {Array.from({ length: ROWS * 2 }, (_, k) => {
                    const row = ROWS - 1 - Math.floor(k / 2);
                    const on = row * 2 + (k % 2) < filled;
                    return (
                      <span
                        key={k}
                        className={cx(
                          "size-1.75 rounded-[1.5px] transition-colors",
                          !on ? "bg-sunken" : selected ? "bg-brand" : "bg-mark-muted group-hover:bg-fg-2",
                        )}
                      />
                    );
                  })}
                </span>
                <span className={cx("num text-[11px] leading-none", selected ? "font-semibold text-brand" : "text-fg-2")}>
                  {f.dayNum(d.date)}
                </span>
                <span className="text-[10px] leading-none text-fg-3">{f.weekdayNarrow(d.date)}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
