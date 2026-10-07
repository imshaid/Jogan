"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { useLang } from "@/lib/i18n";

import { cx } from "./ui";

// Hand-drawn SVG charts. Specs: 2px lines, ≥ 8px markers with a 2px surface ring, hairline
// solid grid, text in text colours (never the series colour), a legend for two or more series,
// a hover/focus readout, and a table twin for every chart (the caller renders it).

const SURFACE = "#ffffff";
const GRID = "#ecebe7";
const AXIS_TEXT = "#66676d";
const INK = "#111113";
const MUTED = "#86857f"; // --mark-muted
const HOVER = "#f6f6f4"; // --tray

export type Series = { key: string; name: string; color: string; values: (number | null)[] };

export function Legend({ items }: { items: { name: string; color: string; kind?: "line" | "box" | "dot" }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-2">
      {items.map((i) => (
        <li key={i.name} className="flex items-center gap-1.5">
          {i.kind === "box" ? (
            <span aria-hidden className="inline-block size-2.5 rounded-[2px]" style={{ background: i.color }} />
          ) : i.kind === "dot" ? (
            <span aria-hidden className="inline-block size-2 rounded-full" style={{ background: i.color }} />
          ) : (
            <span aria-hidden className="inline-block h-0.5 w-3.5 rounded" style={{ background: i.color }} />
          )}
          {i.name}
        </li>
      ))}
    </ul>
  );
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

// Probabilities over the plan days, with a crosshair that snaps to the nearest day.
export function ProbabilityChart({
  dates,
  series,
  marks,
  selected,
  onSelect,
  label,
}: {
  dates: string[];
  series: Series[];
  marks?: boolean[]; // days with a planned visit
  selected?: number;
  onSelect?: (i: number) => void;
  label: string;
}) {
  const { f } = useLang();
  const [attach, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const height = 220;
  const m = { top: 12, right: 16, bottom: 28, left: 40 };
  const w = width - m.left - m.right;
  const h = height - m.top - m.bottom;
  const n = dates.length;
  const x = (i: number) => m.left + (n <= 1 ? w / 2 : (i / (n - 1)) * w);
  const y = (p: number) => m.top + (1 - p) * h;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(w / 64))));
  const active = hover ?? null;
  const tipId = useId();

  function path(values: (number | null)[]) {
    let d = "";
    values.forEach((v, i) => {
      if (v === null) return;
      d += `${d && values[i - 1] !== null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    });
    return d;
  }

  function nearest(clientX: number, el: SVGSVGElement) {
    const r = el.getBoundingClientRect();
    const px = ((clientX - r.left) / r.width) * width;
    return Math.max(0, Math.min(n - 1, Math.round(((px - m.left) / w) * (n - 1))));
  }

  return (
    <div ref={attach} className="relative">
      <svg
        role="img"
        aria-label={label}
        aria-describedby={active !== null ? tipId : undefined}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block touch-pan-y"
        tabIndex={0}
        onPointerMove={(e) => setHover(nearest(e.clientX, e.currentTarget))}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => onSelect?.(nearest(e.clientX, e.currentTarget))}
        onKeyDown={(e) => {
          const cur = hover ?? selected ?? 0;
          if (e.key === "ArrowRight") setHover(Math.min(n - 1, cur + 1));
          else if (e.key === "ArrowLeft") setHover(Math.max(0, cur - 1));
          else if (e.key === "Enter" && hover !== null) onSelect?.(hover);
          else return;
          e.preventDefault();
        }}
        onBlur={() => setHover(null)}
      >
        {ticks.map((tk) => (
          <g key={tk}>
            <line x1={m.left} x2={width - m.right} y1={y(tk)} y2={y(tk)} stroke={GRID} strokeWidth={1} />
            <text x={m.left - 8} y={y(tk)} dy="0.32em" textAnchor="end" fontSize={11} fill={AXIS_TEXT} className="num">
              {f.pct(tk)}
            </text>
          </g>
        ))}
        {dates.map((d, i) =>
          i % every === 0 ? (
            <text key={d} x={x(i)} y={height - 8} textAnchor="middle" fontSize={11} fill={AXIS_TEXT} className="num">
              {f.dayShort(d)}
            </text>
          ) : null,
        )}
        {selected !== undefined && (
          <rect x={x(selected) - 7} y={m.top} width={14} height={h} fill="#eef4fb" rx={3} />
        )}
        {series.map((s) => (
          <path
            key={s.key}
            d={path(s.values)}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
        {marks &&
          series.map((s) =>
            s.values.map((v, i) =>
              marks[i] && v !== null ? (
                <circle key={`${s.key}-${i}`} cx={x(i)} cy={y(v)} r={4} fill={s.color} stroke={SURFACE} strokeWidth={2} />
              ) : null,
            ),
          )}
        {active !== null && (
          <g pointerEvents="none">
            <line x1={x(active)} x2={x(active)} y1={m.top} y2={m.top + h} stroke="#4b4c52" strokeWidth={1} strokeDasharray="3 3" />
            {series.map((s) =>
              s.values[active] !== null ? (
                <circle
                  key={s.key}
                  cx={x(active)}
                  cy={y(s.values[active]!)}
                  r={4.5}
                  fill={s.color}
                  stroke={SURFACE}
                  strokeWidth={2}
                />
              ) : null,
            )}
          </g>
        )}
      </svg>
      {active !== null && (
        <div
          id={tipId}
          role="status"
          className="pointer-events-none absolute top-1 z-10 min-w-36 rounded-lg border border-line bg-surface px-2.5 py-2 text-xs shadow-pop"
          style={x(active) > width / 2 ? { right: width - x(active) + 10 } : { left: x(active) + 10 }}
        >
          <div className="mb-1 font-medium text-fg-2">{f.day(dates[active])}</div>
          {series.map((s) => (
            <div key={s.key} className="flex items-center gap-2">
              <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} />
              <span className="num font-semibold text-fg">{s.values[active] === null ? "—" : f.pct(s.values[active]!)}</span>
              <span className="text-fg-2">{s.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// One row per side: the forecast drain's median, 90% and 99% points as a band, against the
// balance held now (an ink tick). All rows share one scale so they compare.
export function DrainRanges({
  rows,
}: {
  rows: { key: string; name: string; color: string; balance: number; q50: number; q90: number; q99: number }[];
}) {
  const { t, f } = useLang();
  const [attach, width] = useWidth();
  const max = Math.max(1, ...rows.flatMap((r) => [r.q99, r.balance])) * 1.06;
  const m = { left: 76, right: 20 };
  const w = width - m.left - m.right;
  const sx = (v: number) => m.left + (v / max) * w;
  const rowH = 54;
  const height = rows.length * rowH + 26;
  const ticks = niceTicks(max, Math.max(2, Math.floor(w / 110)));
  return (
    <div ref={attach}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block" aria-hidden>
        {ticks.map((tk) => (
          <g key={tk}>
            <line x1={sx(tk)} x2={sx(tk)} y1={4} y2={height - 22} stroke={GRID} />
            <text x={sx(tk)} y={height - 6} textAnchor="middle" fontSize={11} fill={AXIS_TEXT} className="num">
              {f.tk(tk)}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cy = 10 + i * rowH + 18;
          return (
            <g key={r.key}>
              <text x={0} y={cy} dy="0.32em" fontSize={12} fill={INK} fontWeight={600}>
                {r.name}
              </text>
              <rect x={sx(0)} y={cy - 7} width={sx(r.q99) - sx(0)} height={14} rx={3} fill={r.color} opacity={0.14} />
              <rect x={sx(0)} y={cy - 7} width={sx(r.q90) - sx(0)} height={14} rx={3} fill={r.color} opacity={0.32} />
              <rect x={sx(0)} y={cy - 7} width={Math.max(2, sx(r.q50) - sx(0))} height={14} rx={3} fill={r.color} />
              <line x1={sx(r.balance)} x2={sx(r.balance)} y1={cy - 13} y2={cy + 13} stroke={INK} strokeWidth={2} />
              <text
                x={sx(r.balance)}
                y={cy - 17}
                textAnchor={sx(r.balance) > width - 90 ? "end" : "middle"}
                fontSize={11}
                fill={INK}
              >
                {t.agent.balance}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-2">
        <Legend
          items={[
            { name: t.agent.q50, color: "#4b4c52", kind: "box" },
            { name: t.agent.q90, color: "rgba(75,76,82,0.4)", kind: "box" },
            { name: t.agent.q99, color: "rgba(75,76,82,0.18)", kind: "box" },
            { name: t.agent.balance, color: INK, kind: "line" },
          ]}
        />
      </div>
    </div>
  );
}

export function niceTicks(max: number, count: number) {
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((s) => s * mag).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = 0; v <= max; v += step) out.push(Math.round(v));
  return out;
}

export type IntervalRow = {
  key: string;
  label: ReactNode;
  mean: number;
  low: number;
  high: number;
  emphasis?: boolean;
  note?: ReactNode;
};

// Dot-and-interval rows around zero (Jogan minus another policy): below zero is better.
export function IntervalPlot({
  rows,
  format,
  height = 32,
  zeroLabel,
}: {
  rows: IntervalRow[];
  format: (v: number) => string;
  height?: number;
  zeroLabel?: string;
}) {
  const [attach, width] = useWidth();
  const [hover, setHover] = useState<string | null>(null);
  const lo = Math.min(0, ...rows.map((r) => r.low));
  const hi = Math.max(0, ...rows.map((r) => r.high));
  const pad = (hi - lo) * 0.08 || 1;
  const labelW = Math.min(180, Math.max(120, width * 0.36));
  const valueW = 76;
  const plotL = labelW + 8;
  const plotR = width - valueW - 8;
  const sx = (v: number) => plotL + ((v - (lo - pad)) / (hi + pad - (lo - pad))) * (plotR - plotL);
  const total = rows.length * height + 22;
  return (
    <div ref={attach} className="relative">
      <svg width={width} height={total} viewBox={`0 0 ${width} ${total}`} className="block" aria-hidden>
        <line x1={sx(0)} x2={sx(0)} y1={0} y2={total - 18} stroke="#4b4c52" strokeWidth={1} />
        {zeroLabel && (
          <text x={sx(0)} y={total - 4} textAnchor="middle" fontSize={11} fill={AXIS_TEXT} className="num">
            {zeroLabel}
          </text>
        )}
        {rows.map((r, i) => {
          const cy = i * height + height / 2;
          const on = hover === r.key;
          const color = r.emphasis ? "#0c55a4" : MUTED;
          return (
            <g key={r.key} onPointerEnter={() => setHover(r.key)} onPointerLeave={() => setHover(null)}>
              <rect x={0} y={cy - height / 2} width={width} height={height} fill={on ? HOVER : "transparent"} />
              <line x1={plotL} x2={plotR} y1={cy} y2={cy} stroke={GRID} />
              <line x1={sx(r.low)} x2={sx(r.high)} y1={cy} y2={cy} stroke={color} strokeWidth={2} strokeLinecap="round" />
              <line x1={sx(r.low)} x2={sx(r.low)} y1={cy - 5} y2={cy + 5} stroke={color} strokeWidth={2} />
              <line x1={sx(r.high)} x2={sx(r.high)} y1={cy - 5} y2={cy + 5} stroke={color} strokeWidth={2} />
              <circle cx={sx(r.mean)} cy={cy} r={5} fill={color} stroke={SURFACE} strokeWidth={2} />
              <text x={width} y={cy} dy="0.32em" textAnchor="end" fontSize={12} fill={INK} className="num" fontWeight={600}>
                {format(r.mean)}
              </text>
            </g>
          );
        })}
      </svg>
      {/* labels are HTML so long Bangla wraps and stays selectable */}
      <div className="pointer-events-none absolute top-0 left-0" style={{ width: labelW }}>
        {rows.map((r) => (
          <div
            key={r.key}
            className={cx("flex items-center text-xs leading-tight", r.emphasis ? "font-semibold text-fg" : "text-fg-2")}
            style={{ height }}
          >
            <span className="line-clamp-2">{r.label}</span>
          </div>
        ))}
      </div>
      {hover && (
        <div
          role="status"
          className="pointer-events-none absolute right-0 z-10 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-pop"
          style={{ top: rows.findIndex((r) => r.key === hover) * height + height }}
        >
          {(() => {
            const r = rows.find((x) => x.key === hover)!;
            return (
              <>
                <span className="num font-semibold">{format(r.mean)}</span>{" "}
                <span className="num text-fg-2">
                  [{format(r.low)}, {format(r.high)}]
                </span>
                {r.note && <div className="mt-0.5 text-fg-2">{r.note}</div>}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}

// Horizontal bars from zero with an interval whisker; one series, emphasis on one bar.
export function BarIntervals({ rows, format }: { rows: IntervalRow[]; format: (v: number) => string }) {
  const [attach, width] = useWidth();
  const [hover, setHover] = useState<string | null>(null);
  const rowH = 34;
  const labelW = Math.min(200, Math.max(120, width * 0.34));
  const valueW = 64;
  const plotL = labelW + 8;
  const plotR = width - valueW - 8;
  const max = Math.max(...rows.map((r) => r.high)) * 1.04;
  const sx = (v: number) => plotL + (v / max) * (plotR - plotL);
  const total = rows.length * rowH;
  return (
    <div ref={attach} className="relative">
      <svg width={width} height={total} viewBox={`0 0 ${width} ${total}`} className="block" aria-hidden>
        <line x1={plotL} x2={plotL} y1={0} y2={total} stroke="#d7d6d1" />
        {rows.map((r, i) => {
          const cy = i * rowH + rowH / 2;
          const color = r.emphasis ? "#0c55a4" : "#bdbcb6";
          const on = hover === r.key;
          const bw = Math.max(2, sx(r.mean) - plotL);
          return (
            <g key={r.key} onPointerEnter={() => setHover(r.key)} onPointerLeave={() => setHover(null)}>
              <rect x={0} y={cy - rowH / 2} width={width} height={rowH} fill={on ? HOVER : "transparent"} />
              <path
                d={`M${plotL},${cy - 9} h${bw - 4} a4,4 0 0 1 4,4 v10 a4,4 0 0 1 -4,4 h${-(bw - 4)} z`}
                fill={color}
                className="anim-grow-x"
                style={{ ["--i" as string]: i }}
              />
              <line x1={sx(r.low)} x2={sx(r.high)} y1={cy} y2={cy} stroke={INK} strokeWidth={1.5} />
              <line x1={sx(r.low)} x2={sx(r.low)} y1={cy - 4} y2={cy + 4} stroke={INK} strokeWidth={1.5} />
              <line x1={sx(r.high)} x2={sx(r.high)} y1={cy - 4} y2={cy + 4} stroke={INK} strokeWidth={1.5} />
              <text x={width} y={cy} dy="0.32em" textAnchor="end" fontSize={12} fill={INK} className="num" fontWeight={r.emphasis ? 700 : 500}>
                {format(r.mean)}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="pointer-events-none absolute top-0 left-0" style={{ width: labelW }}>
        {rows.map((r) => (
          <div
            key={r.key}
            className={cx("flex items-center text-xs leading-tight", r.emphasis ? "font-semibold text-fg" : "text-fg-2")}
            style={{ height: rowH }}
          >
            <span className="line-clamp-2">{r.label}</span>
          </div>
        ))}
      </div>
      {hover && (
        <div
          role="status"
          className="pointer-events-none absolute right-0 z-10 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-pop"
          style={{ top: rows.findIndex((r) => r.key === hover) * rowH + rowH }}
        >
          {(() => {
            const r = rows.find((x) => x.key === hover)!;
            return (
              <>
                <span className="num font-semibold">{format(r.mean)}</span>{" "}
                <span className="num text-fg-2">
                  [{format(r.low)}, {format(r.high)}]
                </span>
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}

export function DataTable({
  head,
  rows,
  caption,
}: {
  head: ReactNode[];
  rows: ReactNode[][];
  caption?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-line text-left text-fg-3">
            {head.map((h, i) => (
              <th key={i} scope="col" className={cx("eyebrow py-2 pr-3 font-medium", i > 0 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {r.map((c, j) => (
                <td key={j} className={cx("py-2 pr-3", j > 0 && "num text-right")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Two thin bars per row, a baseline in grey and Jogan in blue, with values at the right and a
// hover card (on-site, D-038). One measure per chart: a second measure gets its own chart.
export const PAIR_COLORS = { a: "#bdbcb6", b: "#0c55a4" } as const;
export type PairRow = { key: string; label: string; a: number; b: number };

export function PairedBars({
  rows,
  aLabel,
  bLabel,
  format,
}: {
  rows: PairRow[];
  aLabel: string;
  bLabel: string;
  format: (v: number) => string;
}) {
  const [attach, width] = useWidth();
  const [hover, setHover] = useState<string | null>(null);
  const rowH = 42;
  const barH = 10;
  const labelW = Math.min(190, Math.max(110, width * 0.36));
  const valueW = 52;
  const plotL = labelW + 8;
  const plotR = Math.max(plotL + 40, width - valueW - 6);
  const max = Math.max(1e-9, ...rows.flatMap((r) => [r.a, r.b])) * 1.04;
  const sx = (v: number) => plotL + (Math.max(v, 0) / max) * (plotR - plotL);
  const bar = (y: number, v: number) => {
    const w = Math.max(5, sx(v) - plotL);
    return `M${plotL},${y} h${w - 4} a4,4 0 0 1 4,4 v${barH - 8} a4,4 0 0 1 -4,4 h${-(w - 4)} z`;
  };
  const total = rows.length * rowH;
  return (
    <div>
      <Legend
        items={[
          { name: aLabel, color: PAIR_COLORS.a, kind: "box" },
          { name: bLabel, color: PAIR_COLORS.b, kind: "box" },
        ]}
      />
      <div ref={attach} className="relative mt-2">
        <svg width={width} height={total} viewBox={`0 0 ${width} ${total}`} className="block" aria-hidden>
          <line x1={plotL} x2={plotL} y1={0} y2={total} stroke="#d7d6d1" />
          {rows.map((r, i) => {
            const y = i * rowH + (rowH - 2 * barH - 2) / 2;
            const on = hover === r.key;
            return (
              <g key={r.key} onPointerEnter={() => setHover(r.key)} onPointerLeave={() => setHover(null)}>
                <rect x={0} y={i * rowH} width={width} height={rowH} fill={on ? HOVER : "transparent"} />
                <path d={bar(y, r.a)} fill={PAIR_COLORS.a} className="anim-grow-x" style={{ ["--i" as string]: i }} />
                <path d={bar(y + barH + 2, r.b)} fill={PAIR_COLORS.b} className="anim-grow-x" style={{ ["--i" as string]: i + 1 }} />
                <text x={width} y={y + barH / 2} dy="0.32em" textAnchor="end" fontSize={11} fill={AXIS_TEXT} className="num">
                  {format(r.a)}
                </text>
                <text x={width} y={y + barH * 1.5 + 2} dy="0.32em" textAnchor="end" fontSize={11} fill={INK} fontWeight={700} className="num">
                  {format(r.b)}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="pointer-events-none absolute top-0 left-0" style={{ width: labelW }}>
          {rows.map((r) => (
            <div key={r.key} className="flex items-center text-xs leading-tight text-fg-2" style={{ height: rowH }}>
              <span className="line-clamp-2">{r.label}</span>
            </div>
          ))}
        </div>
        {hover &&
          (() => {
            const i = rows.findIndex((x) => x.key === hover);
            const r = rows[i];
            return (
              <div
                role="status"
                className="pointer-events-none absolute right-0 z-10 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-pop"
                style={{ top: (i + 1) * rowH }}
              >
                <div className="font-medium">{r.label}</div>
                <div className="num text-fg-2">
                  {aLabel}: {format(r.a)}
                </div>
                <div className="num font-semibold">
                  {bLabel}: {format(r.b)}
                </div>
              </div>
            );
          })()}
      </div>
    </div>
  );
}
