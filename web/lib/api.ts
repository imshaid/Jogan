import { createClient } from "@supabase/supabase-js";

import { API_BASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "./config";

export const supabase = createClient(SUPABASE_URL || "http://localhost", SUPABASE_PUBLISHABLE_KEY || "missing");

export type Role = "analyst" | "approver";
export type Status = "pending" | "approved" | "rejected";

export type Evidence = {
  cash_tk: number;
  efloat_tk: number;
  p_stockout_cash: number;
  p_stockout_efloat: number;
  drain_cash_q50: number;
  drain_cash_q90: number;
  drain_cash_q99: number;
  drain_efloat_q50: number;
  drain_efloat_q90: number;
  drain_efloat_q99: number;
  need_cash_tk: number;
  need_efloat_tk: number;
  needs_fit: boolean;
};

export type Recommendation = {
  id: number;
  bundle_id: string;
  plan_date: string;
  agent_id: string;
  territory: string;
  runner_id: string;
  action: "visit";
  target_cash_tk: number;
  value_tk: number;
  evidence: Evidence;
  trace: Record<string, unknown>;
  status: Status;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
};

export type AuditEntry = {
  id: number;
  at: string;
  actor: string | null;
  actor_role: "system" | Role;
  action: string;
  recommendation_id: number | null;
  detail: Record<string, unknown>;
};

export type Territory = {
  territory: string;
  district_en: string;
  district_bn: string;
  setting: string;
};

export type Meta = {
  bundle_id: string;
  profile: string;
  seed: number;
  test_window: [string, string];
  plan_dates: string[];
  plan_hour: number;
  counts: { agents: number; runners: number; territories: number; recommendations: number };
  lost_customer_value_tk: number;
  territories: Territory[];
  simulated: true;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, token?: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "The API is not reachable. It may be starting up; try again in a few seconds.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export const api = {
  meta: () => call<Meta>("/v1/meta"),
  me: (token: string) => call<{ role: Role | null }>("/v1/me", token),
  plan: (token: string, day: string) =>
    call<{ bundle_id: string; plan_date: string; items: Recommendation[] }>(`/v1/plans/${day}`, token),
  decide: (token: string, id: number, decision: "approved" | "rejected", note?: string) =>
    call<Recommendation>(`/v1/recommendations/${id}/decision`, token, {
      method: "POST",
      body: JSON.stringify({ decision, note: note || null }),
    }),
  audit: (token: string, limit = 20) => call<{ items: AuditEntry[] }>(`/v1/audit?limit=${limit}`, token),
};
