"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { api, type Meta, type Recommendation } from "./api";
import { mutate, useResource } from "./data";
import { useSession } from "./session";

export const keys = {
  meta: "meta",
  plan: (day: string) => `plan:${day}`,
  network: (day: string) => `network:${day}`,
  anomalies: (day: string) => `anomalies:${day}`,
  agent: (id: string) => `agent:${id}`,
  audit: (limit: number, rec?: number) => `audit:${limit}:${rec ?? ""}`,
  trace: (id: number) => `trace:${id}`,
};

export function useMeta() {
  return useResource(keys.meta, api.meta);
}

// Signed-in resources wait for the role, so an account without one never fires them.
function useStaffKey(key: string | null) {
  const { token, role } = useSession();
  return { token, key: token && role && key ? key : null };
}

export function usePlan(day: string | null) {
  const { token, key } = useStaffKey(day && keys.plan(day));
  return useResource(key, () => api.plan(token!, day!), "plan");
}

export function useNetwork(day: string | null) {
  const { token, key } = useStaffKey(day && keys.network(day));
  return useResource(key, () => api.network(token!, day!), "network");
}

export function useAnomalies(day: string | null) {
  const { token, key } = useStaffKey(day && keys.anomalies(day));
  return useResource(key, () => api.anomalies(token!, day!));
}

export function useAgent(id: string | null) {
  const { token, key } = useStaffKey(id && keys.agent(id));
  return useResource(key, () => api.agent(token!, id!));
}

export function useTrace(id: number | null) {
  const { token, key } = useStaffKey(id ? keys.trace(id) : null);
  return useResource(key, () => api.trace(token!, id!));
}

export function useAudit(limit: number, recommendationId?: number) {
  const { token, key } = useStaffKey(keys.audit(limit, recommendationId));
  return useResource(key, () => api.audit(token!, limit, recommendationId), undefined, true);
}

// Approve or reject; the queue row keeps its explanation and display text, since the decision
// endpoint returns the bare row.
export function useDecide() {
  const { token } = useSession();
  return useCallback(
    async (rec: Recommendation, decision: "approved" | "rejected", note?: string) => {
      const updated = await api.decide(token!, rec.id, decision, note);
      const merged: Recommendation = {
        ...rec,
        status: updated.status,
        decided_by: updated.decided_by,
        decided_at: updated.decided_at,
        decision_note: updated.decision_note,
      };
      mutate<{ items: Recommendation[] }>(keys.plan(rec.plan_date), (p) => ({
        ...p,
        items: p.items.map((x) => (x.id === rec.id ? merged : x)),
      }));
      return merged;
    },
    [token],
  );
}

// The plan day lives in the URL (?day=), so a link or a reload keeps it.
export function useDay(meta: Meta | undefined): [string | null, (day: string) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const asked = params.get("day");
  const day = meta ? (asked && meta.plan_dates.includes(asked) ? asked : meta.plan_dates[0]) : null;
  const setDay = useCallback(
    (d: string) => {
      const next = new URLSearchParams(params.toString());
      next.set("day", d);
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );
  return [day, setDay];
}
