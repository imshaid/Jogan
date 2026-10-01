"use client";

import type { Session } from "@supabase/supabase-js";
import { useCallback, useEffect, useState } from "react";

import { ApiError, api, supabase, type AuditEntry, type Meta, type Recommendation, type Role } from "@/lib/api";
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from "@/lib/config";
import { pct, riskLevel, tk, when } from "@/lib/format";

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  if (!ready) return <main className="mx-auto max-w-6xl px-4 py-8 text-muted">Loading…</main>;
  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      {session ? <Queue session={session} /> : <SignIn />}
    </main>
  );
}

function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signIn(e: string, p: string) {
    setBusy(true);
    setError("");
    const { error } = await supabase.auth.signInWithPassword({ email: e, password: p });
    if (error) setError(error.message);
    setBusy(false);
  }

  return (
    <section className="mx-auto max-w-md rounded-lg border border-line bg-white p-6">
      <h1 className="text-xl font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">
        Analysts see the day&apos;s recommended runner visits. Approvers approve or reject them; every decision is
        written to an append-only audit log.
      </p>
      <form
        className="mt-4 space-y-3"
        onSubmit={(ev) => {
          ev.preventDefault();
          signIn(email, password);
        }}
      >
        <label className="block text-sm font-medium">
          Email
          <input
            className="mt-1 w-full rounded border border-line px-3 py-2"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            required
          />
        </label>
        <label className="block text-sm font-medium">
          Password
          <input
            className="mt-1 w-full rounded border border-line px-3 py-2"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            required
          />
        </label>
        <button
          className="w-full rounded bg-brand px-4 py-2 font-semibold text-white disabled:opacity-60"
          disabled={busy}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      {DEMO_PASSWORD && (
        <div className="mt-4 border-t border-line pt-4">
          <p className="text-sm text-muted">Demo accounts (simulated data only):</p>
          <div className="mt-2 flex gap-2">
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.email}
                className="flex-1 rounded border border-brand px-3 py-2 text-sm font-semibold text-brand disabled:opacity-60"
                disabled={busy}
                onClick={() => signIn(a.email, DEMO_PASSWORD)}
              >
                Sign in as {a.role}
              </button>
            ))}
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger-text">
          ⚠ {error}
        </p>
      )}
    </section>
  );
}

function Queue({ session }: { session: Session }) {
  const token = session.access_token;
  const [meta, setMeta] = useState<Meta | null>(null);
  const [role, setRole] = useState<Role | null | undefined>(undefined);
  const [day, setDay] = useState("");
  const [items, setItems] = useState<Recommendation[] | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  useEffect(() => {
    api
      .meta()
      .then((m) => {
        setMeta(m);
        setDay((d) => d || m.plan_dates[0]);
      })
      .catch(fail);
    api
      .me(token)
      .then((r) => setRole(r.role))
      .catch(fail);
  }, [token]);

  const refreshAudit = useCallback(() => {
    api
      .audit(token)
      .then((r) => setAudit(r.items))
      .catch(fail);
  }, [token]);

  useEffect(() => {
    if (!day || !role) return;
    api
      .plan(token, day)
      .then((r) => {
        setItems(r.items);
        refreshAudit();
      })
      .catch(fail);
  }, [token, day, role, refreshAudit]);

  async function decide(id: number, decision: "approved" | "rejected") {
    setError("");
    try {
      const updated = await api.decide(token, id, decision);
      setItems((xs) => xs?.map((x) => (x.id === id ? updated : x)) ?? null);
      refreshAudit();
    } catch (e) {
      fail(e);
    }
  }

  const counts = { pending: 0, approved: 0, rejected: 0 };
  items?.forEach((x) => counts[x.status]++);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Runner visit queue</h1>
        <label className="text-sm">
          <span className="sr-only">Plan date</span>
          <select
            className="rounded border border-line bg-white px-2 py-1"
            value={day}
            onChange={(e) => {
              setItems(null);
              setError("");
              setDay(e.target.value);
            }}
          >
            {meta?.plan_dates.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <span className="text-sm text-muted">
          planned at {meta ? `${String(meta.plan_hour).padStart(2, "0")}:00` : "…"} · {items?.length ?? "…"} visits ·{" "}
          {counts.pending} pending · {counts.approved} approved · {counts.rejected} rejected
        </span>
        <span className="ml-auto text-sm">
          {session.user.email} ·{" "}
          <strong className="rounded bg-brand-tint px-2 py-0.5 text-brand">{role ?? "no role"}</strong>{" "}
          <button className="ml-2 underline" onClick={() => supabase.auth.signOut()}>
            Sign out
          </button>
        </span>
      </div>

      {error && (
        <p role="alert" className="rounded border border-danger bg-white px-3 py-2 text-sm text-danger-text">
          ⚠ {error}
        </p>
      )}
      {role === null && <p>This account has no Jogan role yet. Ask an administrator to assign one.</p>}

      <div className="overflow-x-auto rounded-lg border border-line bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-page text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">Agent</th>
              <th className="px-3 py-2">Runner</th>
              <th className="px-3 py-2 text-right">Cash · e-float now</th>
              <th className="px-3 py-2">
                P(stock-out) 24 h <span className="normal-case">(prediction)</span>
              </th>
              <th className="px-3 py-2 text-right">Target cash</th>
              <th className="px-3 py-2 text-right">Value of visit</th>
              <th className="px-3 py-2">Decision</th>
            </tr>
          </thead>
          <tbody>
            {items === null && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-muted">
                  Loading the plan…
                </td>
              </tr>
            )}
            {items?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-muted">
                  No visits planned for this day.
                </td>
              </tr>
            )}
            {items?.map((r) => (
              <tr key={r.id} className="border-t border-line">
                <td className="px-3 py-2 font-medium">
                  {r.agent_id}
                  <div className="text-xs text-muted">{r.territory}</div>
                </td>
                <td className="px-3 py-2">{r.runner_id}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {tk(r.evidence.cash_tk)}
                  <div className="text-xs text-muted">{tk(r.evidence.efloat_tk)}</div>
                </td>
                <td className="px-3 py-2">
                  <Risk label="cash" p={r.evidence.p_stockout_cash} />
                  <Risk label="e-float" p={r.evidence.p_stockout_efloat} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{tk(r.target_cash_tk)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{tk(r.value_tk)}</td>
                <td className="px-3 py-2">
                  {r.status === "pending" && role === "approver" ? (
                    <div className="flex gap-2">
                      <button
                        className="rounded bg-brand px-2 py-1 text-xs font-semibold text-white"
                        onClick={() => decide(r.id, "approved")}
                      >
                        ✓ Approve
                      </button>
                      <button
                        className="rounded border border-line px-2 py-1 text-xs font-semibold"
                        onClick={() => decide(r.id, "rejected")}
                      >
                        ✕ Reject
                      </button>
                    </div>
                  ) : (
                    <StatusTag status={r.status} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="rounded-lg border border-line bg-white p-4">
        <h2 className="font-semibold">Audit log</h2>
        <p className="text-xs text-muted">Append-only: entries cannot be edited or deleted, not even by the server.</p>
        <ul className="mt-2 divide-y divide-line text-sm">
          {audit.length === 0 && <li className="py-2 text-muted">No entries yet.</li>}
          {audit.map((a) => (
            <li key={a.id} className="flex flex-wrap gap-x-3 py-2">
              <span className="tabular-nums text-muted">{when(a.at)}</span>
              <span className="font-medium">{a.action}</span>
              <span className="text-muted">by {a.actor_role}</span>
              {a.recommendation_id !== null && <span>#{a.recommendation_id}</span>}
              {typeof a.detail.agent_id === "string" && <span>{a.detail.agent_id}</span>}
              {typeof a.detail.plan_date === "string" && <span className="text-muted">{a.detail.plan_date}</span>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Risk({ label, p }: { label: string; p: number }) {
  const r = riskLevel(p);
  const tone = { high: "text-danger-text", medium: "text-ink", low: "text-muted" }[r.tone];
  return (
    <div className={`whitespace-nowrap text-xs ${tone}`}>
      <span aria-hidden>{r.icon}</span> {label} {pct(p)} <span className="sr-only">({r.label} risk)</span>
      <span aria-hidden className="text-muted"> {r.label}</span>
    </div>
  );
}

function StatusTag({ status }: { status: Recommendation["status"] }) {
  const style = {
    pending: "bg-accent-tint text-ink",
    approved: "bg-brand-tint text-brand",
    rejected: "bg-page text-muted",
  }[status];
  const icon = { pending: "…", approved: "✓", rejected: "✕" }[status];
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-semibold ${style}`}>
      {icon} {status}
    </span>
  );
}
