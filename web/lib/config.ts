// Public settings, baked in at build time (Vercel project environment variables).
// None of these is a secret: the publishable key is browser-safe and row-level security applies.
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";
// Optional: when set, the sign-in card offers one-click demo accounts (DECISIONS.md D-022).
export const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD ?? "";
// Local runs only (`make run`): sign in with the in-memory API's fixed tokens, without Supabase.
// Honoured only for an API on this machine; the deployed API rejects these tokens anyway.
export const LOCAL_AUTH =
  process.env.NEXT_PUBLIC_LOCAL_AUTH === "1" && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(API_BASE_URL);

export const DEMO_ACCOUNTS = [
  { email: "jogan.analyst@example.com", role: "analyst" },
  { email: "jogan.approver@example.com", role: "approver" },
] as const;

// The chosen UI language, read by the server layout so the first paint is in that language.
export const LANG_COOKIE = "jogan-lang";
// The sidebar's width on wide screens ("rail" = icons only), read by the server layout too.
export const SIDEBAR_COOKIE = "jogan-sidebar";

// Base map style. OpenFreeMap needs no key or account (openfreemap.org, checked 2026-10-02);
// any MapLibre style URL, such as a keyed MapTiler style, can replace it.
export const MAP_STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL || "https://tiles.openfreemap.org/styles/positron";
