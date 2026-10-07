"use client";

import { useEffect, useId, useRef, useState } from "react";

import { useLang } from "@/lib/i18n";
import type { RoutePlan } from "@/lib/route";

import { niceTicks, useWidth } from "./charts";
import { cx } from "./ui";

// Runner charts (D-039), following the app's chart rules (D-025, D-038): thin marks with rounded
// ends, one measure per chart, hairline grid, values in text colours, a hover card and a table
// view (the stop list on the runner page is the table of both).

const GRID = "#ecebe7";
const AXIS_TEXT = "#66676d";
const INK = "#111113";
const BLUE = "#0c55a4";
const SURFACE = "#ffffff";

export type Domain = [number, number]; // minutes after midnight

export function timeDomain(plans: (RoutePlan | null)[], shift: [number, number]): Domain {
  const end = Math.max(shift[1] * 60, ...plans.map((p) => (p ? p.back : 0)));
  return [shift[0] * 60, Math.ceil(end / 60) * 60];
}

function hours([a, b]: Domain) {
  const out = [];
  for (let m = a; m <= b; m += 60) out.push(m);
  return out;
}

// One runner's day as a bar on a clock: thin lines for travel, blocks for time at a shop, dashed
// for the ride back; the shift end is an ink rule and time after it is hatched.
export function TimeBar({
  plan,
  domain,
  size = "sm",
  done,
  next,
  onPick,
  preview,
}: {
  plan: RoutePlan;
  domain: Domain;
  size?: "sm" | "lg";
  done?: Set<string>;
  next?: string | null;
  onPick?: (id: string) => void;
  preview?: Set<string>; // stops still waiting for approval
}) {
  const { t, f } = useLang();
  const [hover, setHover] = useState<number | null>(null);
  const span = domain[1] - domain[0];
  const x = (m: number) => `${((m - domain[0]) / span) * 100}%`;
  const w = (a: number, b: number) => `${(Math.max(0, b - a) / span) * 100}%`;
  const lg = size === "lg";
  const s = hover !== null ? plan.stops[hover] : null;
  // blocks are buttons only where picking one does something (never inside another button)
  const Block = onPick ? "button" : "span";
  return (
    <div className={cx("relative", lg ? "h-14" : "h-7")}>
      {plan.shiftEnd < domain[1] && (
        <span
          aria-hidden
          className="hatch absolute inset-y-0 rounded-r-md"
          style={{ left: x(plan.shiftEnd), width: w(plan.shiftEnd, domain[1]) }}
        />
      )}
      <span aria-hidden className="absolute inset-y-0 w-0.5 rounded-full bg-ink" style={{ left: x(plan.shiftEnd) }} />
      <div className="anim-grow-x absolute inset-0" style={{ ["--i" as string]: 0 }}>
        {plan.stops.map((st, i) => {
          const from = i === 0 ? plan.start : plan.stops[i - 1].depart;
          const isDone = done?.has(st.rec.agent_id);
          const isNext = next === st.rec.agent_id;
          const waiting = preview?.has(st.rec.agent_id);
          return (
            <span key={st.rec.id}>
              <span
                aria-hidden
                className="absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-line-strong"
                style={{ left: x(from), width: w(from, st.arrive) }}
              />
              <Block
                tabIndex={onPick ? 0 : undefined}
                aria-label={`${i + 1} · ${st.rec.agent_id} · ${f.clock(st.arrive)}`}
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                onClick={(e: React.MouseEvent) => {
                  if (!onPick) return;
                  e.stopPropagation();
                  onPick(st.rec.agent_id);
                }}
                className={cx(
                  "absolute top-1/2 -translate-y-1/2 rounded-[3px] transition-[filter,transform]",
                  lg ? "h-7 min-w-1.5" : "h-3.5 min-w-1",
                  onPick ? "cursor-pointer hover:brightness-110" : "pointer-events-auto cursor-default",
                  isDone ? "bg-mark-muted" : waiting ? "border border-dashed border-ink/60 bg-accent-soft" : "bg-brand",
                  isNext && "ring-2 ring-ink ring-offset-1",
                  hover === i && "z-10",
                )}
                style={{ left: x(st.arrive), width: w(st.arrive, st.depart) }}
              >
                {lg && (
                  <span
                    className={cx(
                      "num pointer-events-none absolute inset-0 flex items-center justify-center text-[10px] font-bold",
                      isDone ? "text-white" : waiting ? "text-ink" : "text-white",
                    )}
                  >
                    {i + 1}
                  </span>
                )}
              </Block>
            </span>
          );
        })}
        {plan.stops.length > 0 && (
          <span
            aria-hidden
            className="absolute top-1/2 h-0 -translate-y-1/2 border-t-2 border-dashed border-brand/50"
            style={{ left: x(plan.stops[plan.stops.length - 1].depart), width: w(plan.stops[plan.stops.length - 1].depart, plan.back) }}
          />
        )}
      </div>
      {s && (
        <div
          role="status"
          className="pointer-events-none absolute bottom-full z-20 mb-1.5 w-max max-w-60 -translate-x-1/2 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-pop"
          style={{ left: x((s.arrive + s.depart) / 2) }}
        >
          <div className="font-semibold">
            <span className="num">{hover! + 1}</span> · <span className="mono">{s.rec.agent_id}</span>
          </div>
          <div className="num text-fg-2">
            {f.clock(s.arrive)}–{f.clock(s.depart)} · {t.runner.legKm(f.num(s.legKm, 1), hover === 0)}
          </div>
        </div>
      )}
    </div>
  );
}

// Hour labels for a TimeBar column.
export function HourAxis({ domain, className }: { domain: Domain; className?: string }) {
  const { f } = useLang();
  // measured without the charts' 240 px floor: a phone's fleet column can be narrower
  const attach = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = attach.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(1, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const span = domain[1] - domain[0];
  const hs = hours(domain);
  // a label needs about 40 px; skip hours until they fit
  const every = Math.max(1, Math.ceil(40 / (width / Math.max(1, hs.length - 1))));
  return (
    <div ref={attach} aria-hidden className={cx("relative h-4", className)}>
      {hs.map((m, k) =>
        k % every === 0 && (k === hs.length - 1 || hs.length - 1 - k >= every) ? (
          <span
            key={m}
            className={cx(
              "num absolute top-0 text-[10px] whitespace-nowrap text-fg-3",
              k === 0 ? "" : k === hs.length - 1 ? "-translate-x-full" : "-translate-x-1/2",
            )}
            style={{ left: `${((m - domain[0]) / span) * 100}%` }}
          >
            {f.clock(m)}
          </span>
        ) : null,
      )}
    </div>
  );
}

// Hairline hour grid behind a column of TimeBars.
export function HourGrid({ domain }: { domain: Domain }) {
  const span = domain[1] - domain[0];
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      {hours(domain).map((m) => (
        <span key={m} className="absolute inset-y-0 w-px bg-line" style={{ left: `${((m - domain[0]) / span) * 100}%` }} />
      ))}
    </div>
  );
}

// The selected runner's day stop by stop (a waterfall schedule): one row per stop with the ride
// there as a thin line and the time at the shop as a block, then the ride back. Rows pick a stop.
export function ScheduleChart({
  plan,
  domain,
  done,
  next,
  waiting,
  selected,
  onPick,
}: {
  plan: RoutePlan;
  domain: Domain;
  done: Set<string>;
  next: string | null;
  waiting: Set<string>;
  selected: string | null;
  onPick: (id: string) => void;
}) {
  const { t, f } = useLang();
  const r = t.runner;
  const span = domain[1] - domain[0];
  const x = (m: number) => `${((m - domain[0]) / span) * 100}%`;
  const w = (a: number, b: number) => `${(Math.max(0, b - a) / span) * 100}%`;
  const last = plan.stops[plan.stops.length - 1];
  const grid = "grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 sm:grid-cols-[7.5rem_minmax(0,1fr)]";
  return (
    <div>
      <div className={grid}>
        <span />
        <HourAxis domain={domain} className="mb-1" />
      </div>
      <div className="relative">
        <div className={cx(grid, "pointer-events-none absolute inset-0")} aria-hidden>
          <span />
          <span className="relative">
            <HourGrid domain={domain} />
            {plan.shiftEnd < domain[1] && (
              <span className="hatch absolute inset-y-0" style={{ left: x(plan.shiftEnd), width: w(plan.shiftEnd, domain[1]) }} />
            )}
            <span className="absolute inset-y-0 w-0.5 bg-ink" style={{ left: x(plan.shiftEnd) }} />
          </span>
        </div>
        <ol className="relative">
          {plan.stops.map((s, i) => {
            const id = s.rec.agent_id;
            const from = i === 0 ? plan.start : plan.stops[i - 1].depart;
            const isDone = done.has(id);
            const isWaiting = waiting.has(id);
            const late = s.depart > plan.shiftEnd;
            return (
              <li key={s.rec.id}>
                <button
                  type="button"
                  onClick={() => onPick(id)}
                  aria-label={`${i + 1} · ${id} · ${r.eta(f.clock(s.arrive))}`}
                  className={cx(
                    grid,
                    "w-full items-center rounded-md py-0.5 text-left transition-colors",
                    selected === id ? "bg-brand-tint" : "hover:bg-tray",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-1.5 pl-1 text-xs">
                    <span
                      className={cx(
                        "num flex size-4.5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                        isWaiting ? "border border-dashed border-fg-2 bg-accent-tint text-ink" : isDone ? "bg-sunken text-fg-2" : next === id ? "bg-brand text-white" : "border border-brand text-fg",
                      )}
                    >
                      {i + 1}
                    </span>
                    <span className="mono truncate font-medium">{id}</span>
                  </span>
                  <span className="relative h-5.5">
                    <span
                      className="anim-grow-x absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-line-strong"
                      style={{ left: x(from), width: w(from, s.arrive), ["--i" as string]: i }}
                    />
                    <span
                      className={cx(
                        "anim-fade absolute top-1/2 h-3.5 min-w-1.5 -translate-y-1/2 rounded-[3px]",
                        isDone ? "bg-mark-muted" : isWaiting ? "border border-dashed border-ink/60 bg-accent-soft" : "bg-brand",
                        next === id && "ring-2 ring-ink ring-offset-1",
                      )}
                      style={{ left: x(s.arrive), width: w(s.arrive, s.depart), ["--i" as string]: i, ["--d" as string]: "200ms" }}
                    />
                    <span
                      className={cx("num absolute top-1/2 -translate-y-1/2 pl-1.5 text-[11px] whitespace-nowrap", late ? "font-semibold text-danger-text" : "text-fg-2")}
                      style={s.depart > domain[1] - span * 0.12 ? { right: `calc(100% - ${x(s.arrive)})`, paddingRight: 6 } : { left: x(s.depart) }}
                    >
                      {f.clock(s.arrive)}
                      {late && <span aria-hidden> ▲</span>}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
          {last && (
            <li className={cx(grid, "items-center py-0.5")}>
              <span className="flex items-center gap-1.5 pl-1 text-xs text-fg-2">
                <span aria-hidden className="flex size-4.5 shrink-0 items-center justify-center rounded-[4px] bg-ink text-[9px] font-bold text-white">
                  H
                </span>
                {r.bagEnd}
              </span>
              <span className="relative h-5.5">
                <span
                  className="absolute top-1/2 h-0 -translate-y-1/2 border-t-2 border-dashed border-brand/60"
                  style={{ left: x(last.depart), width: w(last.depart, plan.back) }}
                />
                <span
                  className={cx("num absolute top-1/2 -translate-y-1/2 pl-1.5 text-[11px] font-semibold whitespace-nowrap", plan.overShift ? "text-danger-text" : "text-fg")}
                  style={plan.back > domain[1] - span * 0.12 ? { right: `calc(100% - ${x(last.depart)})`, paddingRight: 6 } : { left: x(plan.back) }}
                >
                  {f.clock(plan.back)}
                </span>
              </span>
            </li>
          )}
        </ol>
      </div>
    </div>
  );
}

// Cash in the runner's bag along the route: the load at the hub, then after each stop. A step
// line, since the bag changes at the shops and holds between them.
export function BagChart({ plan, label }: { plan: RoutePlan; label: string }) {
  const { t, f } = useLang();
  const [attach, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const tipId = useId();
  const r = t.runner;
  const values = [plan.load, ...plan.stops.map((s) => s.bagAfter)];
  const n = values.length; // stations: hub, then each stop; the ride back holds the last value
  const showCap = plan.peak >= plan.capacity * 0.5;
  const max = Math.max(1, plan.peak * 1.12, showCap ? plan.capacity * 1.06 : 0);
  const height = 230;
  const m = { top: 16, right: 16, bottom: 30, left: 64 };
  const w = width - m.left - m.right;
  const h = height - m.top - m.bottom;
  const x = (i: number) => m.left + (i / n) * w; // n + 1 positions: hub … last stop, back
  const y = (v: number) => m.top + (1 - v / max) * h;
  const ticks = niceTicks(max, 4).filter((v) => v <= max);
  let d = `M${x(0)},${y(values[0])}`;
  for (let i = 1; i < n; i++) d += ` H${x(i)} V${y(values[i])}`;
  d += ` H${x(n)}`;
  const area = `${d} V${y(0)} H${x(0)} Z`;
  const every = Math.max(1, Math.ceil((n + 1) / Math.max(4, Math.floor(w / 34))));
  const stationLabel = (i: number) => (i === 0 ? r.bagStart : i === n ? r.bagEnd : String(i));
  const tip = hover === null ? null : hover;
  return (
    <div ref={attach} className="relative">
      <svg
        role="img"
        aria-label={label}
        aria-describedby={tip !== null ? tipId : undefined}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block touch-pan-y"
        tabIndex={0}
        onPointerMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - box.left) / box.width) * width;
          setHover(Math.max(0, Math.min(n - 1, Math.round(((px - m.left) / w) * n))));
        }}
        onPointerLeave={() => setHover(null)}
        onKeyDown={(e) => {
          const cur = hover ?? 0;
          if (e.key === "ArrowRight") setHover(Math.min(n - 1, cur + 1));
          else if (e.key === "ArrowLeft") setHover(Math.max(0, cur - 1));
          else return;
          e.preventDefault();
        }}
        onBlur={() => setHover(null)}
      >
        <defs>
          <linearGradient id={`${tipId}-fill`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor={BLUE} stopOpacity={0.16} />
            <stop offset="1" stopColor={BLUE} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={m.left} x2={width - m.right} y1={y(v)} y2={y(v)} stroke={GRID} />
            <text x={m.left - 8} y={y(v)} dy="0.32em" textAnchor="end" fontSize={11} fill={AXIS_TEXT} className="num">
              {f.tk(v)}
            </text>
          </g>
        ))}
        {Array.from({ length: n + 1 }, (_, i) =>
          i % every === 0 || i === n ? (
            <text key={i} x={x(i)} y={height - 9} textAnchor="middle" fontSize={11} fill={AXIS_TEXT} className="num">
              {stationLabel(i)}
            </text>
          ) : null,
        )}
        <path d={area} fill={`url(#${tipId}-fill)`} className="anim-fade" style={{ ["--d" as string]: "500ms" }} />
        {showCap && (
          <g>
            <line x1={m.left} x2={width - m.right} y1={y(plan.capacity)} y2={y(plan.capacity)} stroke={INK} strokeWidth={1.5} strokeDasharray="5 4" />
            <text x={width - m.right} y={y(plan.capacity) - 6} textAnchor="end" fontSize={11} fill={INK} fontWeight={600}>
              {r.bagLimit(f.tk(plan.capacity))}
            </text>
          </g>
        )}
        <path d={d} pathLength={1} fill="none" stroke={BLUE} strokeWidth={2} strokeLinejoin="round" className="anim-draw-1" />
        {values.map((v, i) => (
          <circle
            key={i}
            cx={x(i)}
            cy={y(v)}
            r={tip === i ? 5.5 : 4}
            fill={plan.overBagAt !== null && i - 1 >= plan.overBagAt && v > plan.capacity ? "#b5121b" : BLUE}
            stroke={SURFACE}
            strokeWidth={2}
            className="anim-fade"
            style={{ ["--i" as string]: i, ["--d" as string]: "300ms" }}
          />
        ))}
        {tip !== null && (
          <line x1={x(tip)} x2={x(tip)} y1={m.top} y2={m.top + h} stroke="#4b4c52" strokeWidth={1} strokeDasharray="3 3" pointerEvents="none" />
        )}
      </svg>
      {tip !== null && (
        <div
          id={tipId}
          role="status"
          className="pointer-events-none absolute top-2 z-10 min-w-40 rounded-lg border border-line bg-surface px-2.5 py-2 text-xs shadow-pop"
          style={x(tip) > width / 2 ? { right: width - x(tip) + 10 } : { left: x(tip) + 10 }}
        >
          {tip === 0 ? (
            <div className="font-medium text-fg-2">{r.loadAtHub}</div>
          ) : (
            <>
              <div className="font-medium text-fg-2">
                {r.afterStop(f.num(tip))} · <span className="mono">{plan.stops[tip - 1].rec.agent_id}</span>
              </div>
              <div className="num text-fg-2">
                {plan.stops[tip - 1].handOver >= 0
                  ? r.give(f.tk(plan.stops[tip - 1].handOver))
                  : r.take(f.tk(-plan.stops[tip - 1].handOver))}
              </div>
            </>
          )}
          <div className="num mt-0.5 font-semibold text-fg">{r.inBag(f.tk(values[tip]))}</div>
        </div>
      )}
    </div>
  );
}
