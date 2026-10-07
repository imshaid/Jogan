"use client";

import { Bell, Check, CircleAlert, Info, ScrollText, TriangleAlert, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { AuditEntry } from "@/lib/api";
import { useBusy } from "@/lib/data";
import { useLang } from "@/lib/i18n";
import {
  dismissToast,
  markActivitySeen,
  toast,
  useActivity,
  useActivitySync,
  useHealth,
  useNow,
  useToasts,
  type ToastTone,
} from "@/lib/live";
import { useSession } from "@/lib/session";

import { cx } from "./ui";

// "12 s ago", ticking. Time itself is never colour-coded.
export function Ago({ at, className }: { at: number | string; className?: string }) {
  const { f } = useLang();
  const now = useNow();
  const t = typeof at === "string" ? Date.parse(at) : at;
  if (!now) return null;
  return (
    <time dateTime={new Date(t).toISOString()} className={cx("num", className)} suppressHydrationWarning>
      {f.ago(Math.max(0, now - t))}
    </time>
  );
}

// API and database status, polled every minute while the tab is visible: a word, a dot and the
// round-trip time, so the state never rests on the dot's colour.
export function LiveStatus({ compact }: { compact?: boolean }) {
  const { t, f } = useLang();
  const h = useHealth();
  const l = t.live;
  const word = { checking: l.checking, live: l.live, slow: l.slow, down: l.down }[h.state];
  const dot = {
    checking: "bg-fg-3",
    live: "bg-ok-text",
    slow: "bg-warn-mark",
    down: "bg-danger",
  }[h.state];
  const title = h.state === "down" ? l.downTitle : h.ms !== null ? l.statusTitle(f.num(h.ms)) : l.checking;
  return (
    <span
      role="status"
      title={title}
      className={cx(
        "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        h.state === "down" ? "border-danger/30 bg-danger-tint text-danger-text" : "border-line bg-surface text-fg-2",
      )}
    >
      <span aria-hidden className="relative flex size-2">
        {h.state === "live" && <span className="live-ping absolute inset-0 rounded-full bg-ok-text" />}
        <span className={cx("relative size-2 rounded-full", dot)} />
      </span>
      <span className={compact ? "sr-only" : undefined}>{word}</span>
      {!compact && h.ms !== null && h.state !== "down" && (
        <span className="num hidden text-fg-3 xl:inline">{f.num(h.ms)} ms</span>
      )}
    </span>
  );
}

// A thin bar at the top while a page waits for data or a link is opening.
export function TopProgress() {
  const busy = useBusy();
  const pathname = usePathname();
  const params = useSearchParams();
  const [navigating, setNavigating] = useState(false);
  const where = `${pathname}?${params.toString()}`;
  const [lastWhere, setLastWhere] = useState(where);
  if (where !== lastWhere) {
    setLastWhere(where);
    setNavigating(false);
  }
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement | null)?.closest("a");
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin) return;
      if (url.pathname === location.pathname && url.search === location.search) return;
      setNavigating(true);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);
  const on = busy || navigating;
  return (
    <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 z-60 h-0.5 overflow-hidden">
      <AnimatePresence>
        {on && (
          <motion.div
            key="bar"
            className="top-progress h-full bg-brand"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.4 } }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

const TONE: Record<ToastTone, { Icon: typeof Check; cls: string }> = {
  ok: { Icon: Check, cls: "bg-ok-tint text-ok-text" },
  info: { Icon: Info, cls: "bg-brand-tint text-brand" },
  warn: { Icon: TriangleAlert, cls: "bg-warn-tint text-warn-text" },
  danger: { Icon: CircleAlert, cls: "bg-danger-tint text-danger-text" },
};
const TOAST_MS = 6000;

function ToastCard({ id, tone, title, body, href }: { id: number; tone: ToastTone; title: string; body?: string; href?: string }) {
  const { t } = useLang();
  const [hold, setHold] = useState(false);
  useEffect(() => {
    if (hold) return;
    const timer = setTimeout(() => dismissToast(id), TOAST_MS);
    return () => clearTimeout(timer);
  }, [id, hold]);
  const { Icon, cls } = TONE[tone];
  const content = (
    <>
      <span className={cx("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full", cls)}>
        <Icon aria-hidden className="size-3.5" strokeWidth={2.5} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-fg">{title}</span>
        {body && <span className="mt-0.5 block text-xs leading-relaxed text-fg-2">{body}</span>}
      </span>
    </>
  );
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 40, transition: { duration: 0.2 } }}
      transition={{ type: "spring", bounce: 0.2, duration: 0.45 }}
      onPointerEnter={() => setHold(true)}
      onPointerLeave={() => setHold(false)}
      className="pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-xl border border-line bg-surface/95 py-3 pr-9 pl-3 shadow-pop backdrop-blur"
    >
      {href ? (
        <Link href={href} className="flex min-w-0 flex-1 items-start gap-3" onClick={() => dismissToast(id)}>
          {content}
        </Link>
      ) : (
        content
      )}
      <button
        type="button"
        onClick={() => dismissToast(id)}
        aria-label={t.live.dismiss}
        className="absolute top-2 right-2 flex size-6 items-center justify-center rounded-md text-fg-3 hover:bg-tray hover:text-fg"
      >
        <X aria-hidden className="size-3.5" />
      </button>
      {!hold && (
        <span
          aria-hidden
          className="toast-timer absolute inset-x-0 bottom-0 h-0.5 origin-left bg-line-strong"
          style={{ animationDuration: `${TOAST_MS}ms` }}
        />
      )}
    </motion.li>
  );
}

export function Toaster() {
  const items = useToasts();
  return (
    <ol
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-24 z-50 flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2 lg:bottom-5"
    >
      <AnimatePresence initial={false}>
        {items.map((x) => (
          <ToastCard key={x.id} {...x} />
        ))}
      </AnimatePresence>
    </ol>
  );
}

// Keeps the audit-log feed current while signed in, and tells the person about decisions made in
// another session (another approver, or the same demo account elsewhere).
export function ActivitySync() {
  const { t, f } = useLang();
  const { token, role } = useSession();
  useActivitySync(token && role ? token : null, ({ entry, agent, day }) => {
    const approved = entry.action === "recommendation.approved";
    toast({
      tone: approved ? "ok" : "info",
      title: approved ? t.live.remoteApproved(agent ?? `#${entry.recommendation_id}`) : t.live.remoteRejected(agent ?? `#${entry.recommendation_id}`),
      body: day ? t.live.remoteBody(f.day(day)) : undefined,
      href: agent && day ? `/agents/${agent}?day=${day}` : undefined,
    });
  });
  return null;
}

export function activityText(a: AuditEntry, t: ReturnType<typeof useLang>["t"], f: ReturnType<typeof useLang>["f"]) {
  const agent = typeof a.detail.agent_id === "string" ? a.detail.agent_id : null;
  const n = typeof a.detail.recommendations === "number" ? a.detail.recommendations : null;
  const who = a.actor_role === "system" ? t.audit.system : t.user.role[a.actor_role];
  if (a.action === "recommendation.approved") return { who, what: t.live.approved(agent ?? `#${a.recommendation_id}`) };
  if (a.action === "recommendation.rejected") return { who, what: t.live.rejected(agent ?? `#${a.recommendation_id}`) };
  if (a.action === "plan.published") return { who, what: t.live.published(n === null ? "—" : f.num(n)) };
  return { who, what: t.audit.actions[a.action] ?? a.action };
}

const DOT: Record<string, string> = {
  "recommendation.approved": "bg-ok-text",
  "recommendation.rejected": "bg-fg-3",
  "plan.published": "bg-brand",
};

// The latest audit rows as a feed; new rows slide in at the top.
export function ActivityList({ items, limit = 8, dense }: { items: AuditEntry[]; limit?: number; dense?: boolean }) {
  const { t, f } = useLang();
  return (
    <ol className="relative">
      <AnimatePresence initial={false}>
        {items.slice(0, limit).map((a) => {
          const { who, what } = activityText(a, t, f);
          const agent = typeof a.detail.agent_id === "string" ? a.detail.agent_id : null;
          const day = typeof a.detail.plan_date === "string" ? a.detail.plan_date : null;
          const note = typeof a.detail.note === "string" && a.detail.note ? a.detail.note : null;
          return (
            <motion.li
              key={a.id}
              layout
              initial={{ opacity: 0, y: -8, backgroundColor: "rgba(12,85,164,0.10)" }}
              animate={{ opacity: 1, y: 0, backgroundColor: "rgba(12,85,164,0)" }}
              transition={{ duration: 0.5, backgroundColor: { duration: 2.5 } }}
              className={cx("relative flex gap-3 rounded-lg px-2", dense ? "py-1.5" : "py-2")}
            >
              <span aria-hidden className={cx("mt-1.5 size-2 shrink-0 rounded-full ring-[3px] ring-surface", DOT[a.action] ?? "bg-fg-3")} />
              <div className="min-w-0 flex-1 text-sm">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0 truncate">
                    {agent && day ? (
                      <Link href={`/agents/${agent}?day=${day}`} className="font-medium text-fg hover:text-brand hover:underline">
                        {what}
                      </Link>
                    ) : (
                      <span className="font-medium text-fg">{what}</span>
                    )}
                  </span>
                  <Ago at={a.at} className="shrink-0 text-[11px] text-fg-3" />
                </div>
                <div className="truncate text-xs text-fg-3">
                  {who}
                  {day && <> · {f.dayShort(day)}</>}
                  {a.detail.manual_review === true && <> · ⚑ {t.audit.reviewed}</>}
                  {note && <> · “{note}”</>}
                </div>
              </div>
            </motion.li>
          );
        })}
      </AnimatePresence>
    </ol>
  );
}

// Bell in the header: unread count since last opened, the feed in a popover.
export function ActivityMenu() {
  const { t, f } = useLang();
  const a = useActivity();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const unread = a.items.filter((x) => x.id > a.seenId).length;
  useEffect(() => {
    if (!open) return;
    markActivitySeen();
    const onDown = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, a.items]);
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={unread ? `${t.live.activity} · ${t.live.newCount(f.num(unread))}` : t.live.activity}
        title={t.live.activity}
        onClick={() => setOpen((o) => !o)}
        className={cx(
          "relative inline-flex size-9 items-center justify-center rounded-lg border bg-surface text-fg-2 shadow-xs transition-colors hover:bg-tray hover:text-fg",
          open ? "border-line-strong" : "border-line",
        )}
      >
        <Bell aria-hidden className={cx("size-4", unread > 0 && "bell-ring")} key={unread} />
        <AnimatePresence>
          {unread > 0 && (
            <motion.span
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="num absolute -top-1.5 -right-1.5 flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold text-ink ring-2 ring-page"
            >
              {f.num(Math.min(unread, 99))}
            </motion.span>
          )}
        </AnimatePresence>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label={t.live.activity}
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ type: "spring", bounce: 0.15, duration: 0.3 }}
            className="absolute top-11 right-0 z-40 w-[min(360px,calc(100vw-2rem))] origin-top-right rounded-2xl border border-line bg-tray p-1 shadow-pop"
          >
            <div className="flex items-center justify-between px-3 py-2">
              <span className="eyebrow text-fg-2">{t.live.activity}</span>
              <span className="text-[11px] text-fg-3">
                {a.syncedAt ? (
                  <>
                    {t.live.synced} <Ago at={a.syncedAt} />
                  </>
                ) : (
                  t.live.checking
                )}
              </span>
            </div>
            <div className="max-h-96 overflow-y-auto rounded-xl border border-line bg-surface p-1.5 shadow-card">
              {a.items.length ? (
                <ActivityList items={a.items} limit={15} dense />
              ) : (
                <p className="px-3 py-6 text-center text-sm text-fg-2">{t.live.empty}</p>
              )}
            </div>
            <Link
              href="/audit"
              onClick={() => setOpen(false)}
              className="mt-1 flex h-9 items-center justify-center gap-1.5 rounded-xl text-[13px] font-medium text-brand hover:bg-surface"
            >
              <ScrollText aria-hidden className="size-4" /> {t.live.openAudit}
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
