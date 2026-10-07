"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { api, type AuditEntry } from "./api";
import { API_BASE_URL } from "./config";
import { cachedKeys, refresh } from "./data";
import { keys } from "./hooks";

// The live layer (D-039): what keeps an open page current without a reload. Everything here
// reads the existing API; nothing writes, and nothing runs while the tab is hidden.

// --- Small external stores ------------------------------------------------------------------

function store<T>(initial: T) {
  let value = initial;
  const ls = new Set<() => void>();
  return {
    get: () => value,
    set: (next: T) => {
      value = next;
      ls.forEach((l) => l());
    },
    subscribe: (l: () => void) => {
      ls.add(l);
      return () => {
        ls.delete(l);
      };
    },
  };
}

// --- Visibility and polling -----------------------------------------------------------------

function subscribeVisibility(cb: () => void) {
  document.addEventListener("visibilitychange", cb);
  return () => document.removeEventListener("visibilitychange", cb);
}

export function useVisible() {
  return useSyncExternalStore(subscribeVisibility, () => document.visibilityState === "visible", () => true);
}

// Run `task` every `ms` while the tab is visible, and once right away when it comes back.
export function usePoll(task: () => void, ms: number, enabled = true) {
  const latest = useRef(task);
  useEffect(() => {
    latest.current = task;
  });
  const visible = useVisible();
  useEffect(() => {
    if (!enabled || !visible) return;
    const id = setInterval(() => latest.current(), ms);
    return () => clearInterval(id);
  }, [enabled, visible, ms]);
  const wasHidden = useRef(false);
  useEffect(() => {
    if (!visible) wasHidden.current = true;
    else if (wasHidden.current && enabled) {
      wasHidden.current = false;
      latest.current();
    }
  }, [visible, enabled]);
}

// One shared clock for relative times ("12 s ago"), ticking only while someone shows one.
const clock = store(0);
let clockUsers = 0;
let clockTimer: ReturnType<typeof setInterval> | undefined;

export function useNow() {
  useEffect(() => {
    clockUsers++;
    if (clockUsers === 1) {
      clock.set(Date.now());
      clockTimer = setInterval(() => clock.set(Date.now()), 1000);
    }
    return () => {
      clockUsers--;
      if (clockUsers === 0) clearInterval(clockTimer);
    };
  }, []);
  return useSyncExternalStore(clock.subscribe, clock.get, () => 0);
}

// --- API status -----------------------------------------------------------------------------

// GET /health/db answers for the API and the database (cached 60 s on the server, so polling
// it never turns into a stream of database queries). A cold Cloud Run start shows as "slow".
// Polling is sized for a venue where many people share one address: the API allows 240
// requests a minute per address (configs/api), and an open tab spends about 6 a minute here.
export type HealthState = "checking" | "live" | "slow" | "down";
export type Health = { state: HealthState; ms: number | null; at: number | null };

const HEALTH_MS = 60_000;
const SLOW_MS = 1500;
const health = store<Health>({ state: "checking", ms: null, at: null });
let healthUsers = 0;
let healthTimer: ReturnType<typeof setInterval> | undefined;

async function checkHealth() {
  if (document.visibilityState !== "visible") return;
  const t0 = performance.now();
  try {
    const res = await fetch(`${API_BASE_URL}/health/db`, { cache: "no-store" });
    const ms = Math.round(performance.now() - t0);
    health.set({ state: !res.ok ? "down" : ms > SLOW_MS ? "slow" : "live", ms, at: Date.now() });
  } catch {
    health.set({ state: "down", ms: null, at: Date.now() });
  }
}

export function useHealth() {
  useEffect(() => {
    healthUsers++;
    if (healthUsers === 1) {
      checkHealth();
      healthTimer = setInterval(checkHealth, HEALTH_MS);
      document.addEventListener("visibilitychange", checkHealth);
    }
    return () => {
      healthUsers--;
      if (healthUsers === 0) {
        clearInterval(healthTimer);
        document.removeEventListener("visibilitychange", checkHealth);
      }
    };
  }, []);
  return useSyncExternalStore(health.subscribe, health.get, health.get);
}

// --- Toasts ---------------------------------------------------------------------------------

export type ToastTone = "ok" | "info" | "warn" | "danger";
export type Toast = { id: number; tone: ToastTone; title: string; body?: string; href?: string; at: number };

const toasts = store<Toast[]>([]);
let toastId = 0;
const MAX_TOASTS = 4;

export function toast(t: Omit<Toast, "id" | "at">) {
  const next = [...toasts.get(), { ...t, id: ++toastId, at: Date.now() }];
  toasts.set(next.slice(-MAX_TOASTS));
}

export function dismissToast(id: number) {
  toasts.set(toasts.get().filter((t) => t.id !== id));
}

export function useToasts() {
  return useSyncExternalStore(toasts.subscribe, toasts.get, toasts.get);
}

// --- Activity: the audit log, polled ---------------------------------------------------------

// Decisions made in this tab, so the feed does not announce them back as someone else's.
const own = new Set<number>();
export function markOwnDecision(recommendationId: number) {
  own.add(recommendationId);
}

export type Activity = {
  items: AuditEntry[];
  syncedAt: number | null;
  error: boolean;
  // newest id when the person last opened the activity menu
  seenId: number;
};

const ACTIVITY_MS = 15_000;
const ACTIVITY_ROWS = 30;
const activity = store<Activity>({ items: [], syncedAt: null, error: false, seenId: 0 });

export function useActivity() {
  return useSyncExternalStore(activity.subscribe, activity.get, activity.get);
}

export function markActivitySeen() {
  const a = activity.get();
  const top = a.items[0]?.id ?? 0;
  if (top !== a.seenId) activity.set({ ...a, seenId: top });
}

export function resetActivity() {
  activity.set({ items: [], syncedAt: null, error: false, seenId: 0 });
}

export type DecisionEvent = { entry: AuditEntry; agent: string | null; day: string | null };

const decided = (a: AuditEntry) => a.action === "recommendation.approved" || a.action === "recommendation.rejected";

// Poll the audit log while signed in. A decision from another session refreshes that day's plan
// (and the decision's trace) if a page has it, and is announced through `onRemote`.
export function useActivitySync(token: string | null, onRemote: (e: DecisionEvent) => void) {
  const latest = useRef(onRemote);
  useEffect(() => {
    latest.current = onRemote;
  });
  const [tick, setTick] = useState(0);
  // after a failed poll (a refusal, a cold start), skip a growing number of turns, up to 4
  const skip = useRef({ left: 0, next: 1 });
  usePoll(
    () => {
      if (skip.current.left > 0) skip.current.left--;
      else setTick((n) => n + 1);
    },
    ACTIVITY_MS,
    !!token,
  );
  useEffect(() => {
    if (!token) return;
    let live = true;
    api.audit(token, ACTIVITY_ROWS).then(
      ({ items }) => {
        if (!live) return;
        skip.current = { left: 0, next: 1 };
        const before = activity.get();
        const known = before.items[0]?.id ?? null;
        const fresh = known === null ? [] : items.filter((a) => a.id > known);
        activity.set({
          items,
          syncedAt: Date.now(),
          error: false,
          // the first load counts as seen, so the badge only counts what arrives while open
          seenId: known === null ? (items[0]?.id ?? 0) : before.seenId,
        });
        const days = new Set<string>();
        for (const a of fresh.reverse()) {
          if (!decided(a)) continue;
          const day = typeof a.detail.plan_date === "string" ? a.detail.plan_date : null;
          if (day) days.add(day);
          if (a.recommendation_id !== null) refresh(keys.trace(a.recommendation_id));
          if (a.recommendation_id !== null && own.has(a.recommendation_id)) continue;
          latest.current({ entry: a, agent: typeof a.detail.agent_id === "string" ? a.detail.agent_id : null, day });
        }
        days.forEach((d) => refresh(keys.plan(d)));
        if (fresh.length) cachedKeys("audit:").forEach((k) => refresh(k));
      },
      () => {
        if (!live) return;
        skip.current = { left: skip.current.next, next: Math.min(4, skip.current.next * 2) };
        activity.set({ ...activity.get(), error: true });
      },
    );
    return () => {
      live = false;
    };
  }, [token, tick]);
}
