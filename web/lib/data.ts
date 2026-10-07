"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

// A small client cache: one entry per resource key, shared by every component that reads it,
// with in-flight requests deduplicated. A refetch keeps the previous data on screen.
// `quiet` marks a background refresh (live sync): the data stays on screen and no loading bar shows.
type Entry = { data?: unknown; error?: unknown; loading: boolean; quiet?: boolean; at?: number };

const entries = new Map<string, Entry>();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

// The latest data of a group of keys (say, every day's network), kept so a view can hold its
// previous frame while the next key loads instead of flashing empty.
const lastOf = (group: string) => `last:${group}`;

export function load<T>(
  key: string,
  fetcher: () => Promise<T>,
  force = false,
  group?: string,
  quiet = false,
): Promise<void> {
  const prev = entries.get(key);
  if (prev?.loading) return Promise.resolve();
  if (prev && !force && prev.data !== undefined && !prev.error) return Promise.resolve();
  entries.set(key, { data: prev?.data, error: quiet ? prev?.error : undefined, loading: true, quiet });
  emit();
  return fetcher().then(
    (data) => {
      entries.set(key, { data, loading: false, at: Date.now() });
      if (group) entries.set(lastOf(group), { data, loading: false });
      emit();
    },
    (error) => {
      // a failed background refresh keeps the last good data and says nothing
      const kept = quiet && prev?.data !== undefined;
      entries.set(key, kept ? { ...prev, loading: false, quiet: false } : { data: prev?.data, error, loading: false });
      emit();
    },
  );
}

// Refresh a resource in the background, only if some view has loaded it already.
const fetchers = new Map<string, { fetcher: () => Promise<unknown>; group?: string }>();

export function refresh(key: string) {
  const known = fetchers.get(key);
  if (known && entries.get(key)?.data !== undefined) return load(key, known.fetcher, true, known.group, true);
  return Promise.resolve();
}

export function cachedKeys(prefix: string) {
  return [...entries.keys()].filter((k) => k.startsWith(prefix) && entries.get(k)?.data !== undefined);
}

// True while a view waits for data it does not have yet (the top loading bar).
const isBusy = () => [...entries.values()].some((e) => e.loading && !e.quiet);

export function useBusy() {
  return useSyncExternalStore(subscribe, isBusy, () => false);
}

export function mutate<T>(key: string, change: (data: T) => T) {
  const e = entries.get(key);
  if (e?.data === undefined) return;
  entries.set(key, { ...e, data: change(e.data as T) });
  emit();
}

export function clearCache() {
  entries.clear();
  fetchers.clear();
  emit();
}

// Whatever is cached under a key, without fetching it. Reading a plan publishes that day, so
// side views (the sidebar's count, the command menu) only ever look at what a page loaded.
export function usePeek<T>(key: string | null): T | undefined {
  const entry = useSyncExternalStore(
    subscribe,
    () => (key ? entries.get(key) : undefined),
    () => undefined,
  );
  return entry?.data as T | undefined;
}

export type Resource<T> = {
  data: T | undefined;
  // the group's latest data while this key loads (see `lastOf`)
  previous: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  // a background refresh that keeps the data on screen (live sync)
  refresh: () => void;
  // when the data on screen was fetched (ms since the epoch)
  updatedAt: number | undefined;
};

export function useResource<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  group?: string,
  // refetch when a view mounts (the audit log changes under every decision)
  fresh = false,
): Resource<T> {
  const latest = useRef(fetcher);
  useEffect(() => {
    latest.current = fetcher;
  });
  const entry = useSyncExternalStore(
    subscribe,
    () => (key ? entries.get(key) : undefined),
    () => undefined,
  );
  const last = useSyncExternalStore(
    subscribe,
    () => (group ? entries.get(lastOf(group)) : undefined),
    () => undefined,
  );
  useEffect(() => {
    if (!key) return;
    fetchers.set(key, { fetcher: () => latest.current(), group });
    load(key, () => latest.current(), fresh, group);
  }, [key, group, fresh]);
  const reload = useCallback(() => {
    if (key) load(key, () => latest.current(), true, group);
  }, [key, group]);
  const refreshMe = useCallback(() => {
    if (key) load(key, () => latest.current(), true, group, true);
  }, [key, group]);
  return {
    data: entry?.data as T | undefined,
    previous: (entry?.data ?? last?.data) as T | undefined,
    error: entry?.error,
    loading: (!!entry?.loading && !entry.quiet) || (key !== null && entry === undefined),
    reload,
    refresh: refreshMe,
    updatedAt: entry?.at,
  };
}
