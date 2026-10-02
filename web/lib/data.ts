"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

// A small client cache: one entry per resource key, shared by every component that reads it,
// with in-flight requests deduplicated. A refetch keeps the previous data on screen.
type Entry = { data?: unknown; error?: unknown; loading: boolean };

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

export function load<T>(key: string, fetcher: () => Promise<T>, force = false, group?: string): Promise<void> {
  const prev = entries.get(key);
  if (prev && !force && (prev.loading || (prev.data !== undefined && !prev.error))) return Promise.resolve();
  entries.set(key, { data: prev?.data, loading: true });
  emit();
  return fetcher().then(
    (data) => {
      entries.set(key, { data, loading: false });
      if (group) entries.set(lastOf(group), { data, loading: false });
      emit();
    },
    (error) => {
      entries.set(key, { data: prev?.data, error, loading: false });
      emit();
    },
  );
}

export function mutate<T>(key: string, change: (data: T) => T) {
  const e = entries.get(key);
  if (e?.data === undefined) return;
  entries.set(key, { ...e, data: change(e.data as T) });
  emit();
}

export function clearCache() {
  entries.clear();
  emit();
}

export type Resource<T> = {
  data: T | undefined;
  // the group's latest data while this key loads (see `lastOf`)
  previous: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
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
    if (key) load(key, () => latest.current(), fresh, group);
  }, [key, group, fresh]);
  const reload = useCallback(() => {
    if (key) load(key, () => latest.current(), true, group);
  }, [key, group]);
  return {
    data: entry?.data as T | undefined,
    previous: (entry?.data ?? last?.data) as T | undefined,
    error: entry?.error,
    loading: !!entry?.loading || (key !== null && entry === undefined),
    reload,
  };
}
