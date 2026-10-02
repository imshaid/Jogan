"use client";

import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";

import type { Meta } from "@/lib/api";
import { useLang } from "@/lib/i18n";

import { cx } from "./ui";

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

  const step = "flex size-9 items-center justify-center text-fg-2 hover:bg-page hover:text-fg disabled:text-line-strong disabled:hover:bg-transparent";
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-9 items-stretch overflow-hidden rounded-md border border-line-strong bg-surface">
        <button className={step} onClick={() => onChange(dates[i - 1])} disabled={i <= 0} aria-label={t.common.prevDay}>
          <ChevronLeft className="size-4" />
        </button>
        <label className="flex items-center border-x border-line">
          <span className="sr-only">{t.common.planDay}</span>
          <select
            className="h-full cursor-pointer bg-transparent pr-2 pl-3 text-sm font-medium outline-none"
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
        <button
          className="flex size-9 items-center justify-center rounded-md border border-line-strong bg-surface text-fg-2 hover:bg-page hover:text-fg"
          onClick={() => {
            if (!playing && i >= dates.length - 1) onChange(dates[0]);
            setPlaying((p) => !p);
          }}
          aria-pressed={playing}
          aria-label={playing ? t.common.pause : t.common.play}
          title={playing ? t.common.pause : t.common.play}
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>
      )}
      <span className="hidden text-xs text-fg-3 xl:inline">{t.common.plannedAt(f.hour(meta.plan_hour))}</span>
    </div>
  );
}

// Planned visits per plan day as small columns; each column picks its day.
export function Timeline({ meta, day, onChange }: { meta: Meta; day: string; onChange: (d: string) => void }) {
  const { t, f } = useLang();
  const max = Math.max(1, ...meta.days.map((d) => d.visits));
  const [lo, hi] = meta.test_window;
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h2 className="text-xs font-semibold text-fg-2">{t.network.timeline}</h2>
        <span className="text-xs text-fg-3">
          {f.dayShort(lo)} – {f.dayShort(hi)}
        </span>
      </div>
      <div className="flex items-end gap-[3px] overflow-x-auto pb-1" role="group" aria-label={t.network.timeline}>
        {meta.days.map((d) => {
          const selected = d.date === day;
          const label = `${f.day(d.date)}: ${d.visits ? `${f.num(d.visits)} ${t.common.visitsShort}` : t.common.noRunners}`;
          return (
            <button
              key={d.date}
              onClick={() => onChange(d.date)}
              aria-pressed={selected}
              aria-label={label}
              title={label}
              className={cx(
                "group flex min-w-[26px] flex-1 flex-col items-center gap-1 rounded-md px-0.5 pt-1 pb-0.5",
                selected ? "bg-brand-tint" : "hover:bg-page",
              )}
            >
              <span className="flex h-10 w-full items-end justify-center">
                {d.visits ? (
                  <span
                    className={cx(
                      "w-full max-w-[14px] rounded-t-[3px]",
                      selected ? "bg-brand" : "bg-brand/30 group-hover:bg-brand/50",
                    )}
                    style={{ height: `${Math.max(8, (d.visits / max) * 100)}%` }}
                  />
                ) : (
                  <span className="mb-0.5 text-[10px] leading-none text-fg-3">–</span>
                )}
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
  );
}
