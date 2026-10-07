import { createClient } from "@supabase/supabase-js";

import { API_BASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "./config";

export const supabase = createClient(SUPABASE_URL || "http://localhost", SUPABASE_PUBLISHABLE_KEY || "missing");

export type Role = "analyst" | "approver";
export type Status = "pending" | "approved" | "rejected";

export type Lang = "en" | "bn";

export type Bilingual = Record<Lang, string>;

// label and value_text are the template's display text (jogan/api/views.py, D-025)
export type Driver = {
  feature: string;
  value: number | string | null;
  effect_pct: number;
  label: Bilingual;
  value_text: Bilingual;
};

export type Review = {
  flag: boolean;
  reasons: ({ code: string; text: Bilingual } & Record<string, unknown>)[];
};

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
  side: "cash" | "efloat";
  drivers: Driver[];
  review: Review;
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
  explanation: Record<Lang, string>;
};

// The template explanation, or Gemini's rewording of it when that passed every check.
export type Explanation = {
  recommendation_id: number;
  lang: Lang;
  text: string;
  template: string;
  source: "gemini" | "template";
  model: string | null;
  note: string | null;
};

export type AnomalyFlag = {
  agent_id: string;
  territory: string;
  date: string;
  score: number;
  items: { feature: string; value: number }[];
  text: Record<Lang, string>;
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
  counts: {
    agents: number;
    runners: number;
    territories: number;
    recommendations: number;
    manual_review: number;
    anomaly_flags: number;
  };
  lost_customer_value_tk: number;
  territories: Territory[];
  days: DayCount[];
  // null when the API's configs differ from the ones the bundle was built with (D-039)
  runners?: RunnerSettings | null;
  simulated: true;
};

// The runner rules the served world ran under (configs/sim runners and geo, configs/ops env).
export type RunnerSettings = {
  shift: [number, number];
  visit_minutes: number;
  max_visits: number;
  bag_capacity_tk: number;
  bag_start_tk: number;
  settings: Record<string, { speed_kmh: number; road_factor: number }>;
  hubs: Record<string, { lat: number; lon: number }>;
};

export type DayCount = { date: string; visits: number; manual_review: number; anomaly_flags: number };

// One agent on the map (GET /v1/network/{day}).
export type NetworkAgent = {
  agent_id: string;
  territory: string;
  setting: string;
  size_class: string;
  lat: number;
  lon: number;
  cash_tk: number;
  efloat_tk: number;
  p_stockout_cash: number;
  p_stockout_efloat: number;
  runner_id: string | null;
  value_tk: number | null;
  side: "cash" | "efloat" | null;
  manual_review: boolean;
  anomaly: boolean;
};

// Evidence of a day without a visit has no side, drivers or review.
export type AgentDay = {
  plan_date: string;
  runner_id: string | null;
  candidate: boolean;
  target_cash_tk: number;
  value_tk: number;
  evidence: Omit<Evidence, "side" | "drivers" | "review"> & Partial<Pick<Evidence, "side" | "drivers" | "review">>;
};

export type AgentDetail = {
  bundle_id: string;
  agent: {
    agent_id: string;
    territory: string;
    setting: string;
    size_class: string;
    lat: number;
    lon: number;
    hub_road_km: number;
    district_en: string;
    district_bn: string;
  };
  days: AgentDay[];
  anomalies: (Omit<AnomalyFlag, "territory"> & { plan_date: string })[];
};

// What one layer produced for a recommendation (GET /v1/recommendations/{id}/trace, D-024).
export type TraceStep = {
  step:
    | "forecast"
    | "stock_out_chance"
    | "drivers"
    | "need_and_value"
    | "dispatch"
    | "guardrails"
    | "explanation"
    | "decision";
  by: "model" | "model explanation" | "rule" | "optimizer" | "template" | "human";
  what: string;
  config: { name: string; hash: string | null } | null;
  outputs: Record<string, unknown>;
};

export type DecisionTrace = {
  recommendation_id: number;
  bundle_id: string;
  served_bundle: boolean;
  plan_date: string;
  agent_id: string;
  territory: string;
  status: Status;
  trace: Record<string, unknown>;
  steps: TraceStep[];
  explanation: Record<Lang, string>;
  anomaly: Omit<AnomalyFlag, "text"> | null;
  audit: AuditEntry[];
};

// Every refusal has the body { detail, code } (D-024); 429 adds Retry-After.
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code: string = "error",
    public retryAfterS: number | null = null,
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
    const code = typeof body.code === "string" ? body.code : "error";
    const retry = Number(res.headers.get("Retry-After"));
    throw new ApiError(res.status, detail, code, Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  return body as T;
}

export const api = {
  meta: () => call<Meta>("/v1/meta"),
  me: (token: string) => call<{ user_id: string; role: Role | null }>("/v1/me", token),
  plan: (token: string, day: string) =>
    call<{ bundle_id: string; plan_date: string; items: Recommendation[] }>(`/v1/plans/${day}`, token),
  decide: (token: string, id: number, decision: "approved" | "rejected", note?: string) =>
    call<Recommendation>(`/v1/recommendations/${id}/decision`, token, {
      method: "POST",
      body: JSON.stringify({ decision, note: note || null }),
    }),
  audit: (token: string, limit = 50, recommendationId?: number) =>
    call<{ items: AuditEntry[] }>(
      `/v1/audit?limit=${limit}${recommendationId ? `&recommendation_id=${recommendationId}` : ""}`,
      token,
    ),
  trace: (token: string, id: number) => call<DecisionTrace>(`/v1/recommendations/${id}/trace`, token),
  explanation: (token: string, id: number, lang: Lang) =>
    call<Explanation>(`/v1/recommendations/${id}/explanation?lang=${lang}`, token),
  anomalies: (token: string, day: string) =>
    call<{ plan_date: string; advisory: true; items: AnomalyFlag[] }>(`/v1/anomalies/${day}`, token),
  network: (token: string, day: string) =>
    call<{ plan_date: string; agents: NetworkAgent[] }>(`/v1/network/${day}`, token),
  agent: (token: string, id: string) => call<AgentDetail>(`/v1/agents/${encodeURIComponent(id)}`, token),
};
