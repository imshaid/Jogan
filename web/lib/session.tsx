"use client";

import type { Session } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, supabase, type Role } from "./api";
import { LOCAL_AUTH } from "./config";
import { clearCache } from "./data";
import { resetActivity } from "./live";

// Who is signed in: a Supabase session, or on a local run (LOCAL_AUTH) one of the in-memory
// API's fixed tokens, which are the role names themselves (jogan/api/app.py `from_env`).
type Account = { token: string; userId: string; email: string | null };

type SessionState = {
  ready: boolean;
  session: Account | null;
  token: string | null;
  email: string | null;
  // undefined while loading, null when the account has no Jogan role
  role: Role | null | undefined;
  roleError: unknown;
  signInLocal: (role: Role) => void;
  signOut: () => Promise<void>;
};

const Ctx = createContext<SessionState | null>(null);

const LOCAL_KEY = "jogan-local-role";

function localAccount(role: Role): Account {
  return { token: role, userId: `local-${role}`, email: `${role}@localhost` };
}

function savedLocalRole(): Role | null {
  try {
    const r = sessionStorage.getItem(LOCAL_KEY);
    return r === "analyst" || r === "approver" ? r : null;
  } catch {
    return null;
  }
}

function fromSupabase(s: Session | null): Account | null {
  return s ? { token: s.access_token, userId: s.user.id, email: s.user.email ?? null } : null;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);
  const [role, setRole] = useState<{ user: string; role: Role | null } | null>(null);
  const [roleError, setRoleError] = useState<unknown>(null);

  useEffect(() => {
    if (LOCAL_AUTH) {
      // read after mount, like Supabase's getSession, so the first render matches the server's
      Promise.resolve(savedLocalRole()).then((r) => {
        setAccount(r ? localAccount(r) : null);
        setReady(true);
      });
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setAccount(fromSupabase(data.session));
      setReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setAccount(fromSupabase(s)));
    return () => data.subscription.unsubscribe();
  }, []);

  const token = account?.token ?? null;
  const userId = account?.userId ?? null;

  useEffect(() => {
    if (!token || !userId) return;
    let live = true;
    api
      .me(token)
      .then((r) => {
        if (!live) return;
        setRole({ user: userId, role: r.role });
        setRoleError(null);
      })
      .catch((e) => live && setRoleError(e));
    return () => {
      live = false;
    };
    // the role belongs to the user, not to each refreshed token
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const signInLocal = useCallback((r: Role) => {
    try {
      sessionStorage.setItem(LOCAL_KEY, r);
    } catch {
      // storage blocked: signed in until the tab reloads
    }
    setAccount(localAccount(r));
  }, []);

  const signOut = useCallback(async () => {
    if (LOCAL_AUTH) {
      try {
        sessionStorage.removeItem(LOCAL_KEY);
      } catch {
        // nothing stored
      }
      setAccount(null);
    } else {
      await supabase.auth.signOut();
    }
    clearCache();
    resetActivity();
    setRole(null);
  }, []);

  const value = useMemo<SessionState>(
    () => ({
      ready,
      session: account,
      token,
      email: account?.email ?? null,
      role: role && role.user === userId ? role.role : undefined,
      roleError,
      signInLocal,
      signOut,
    }),
    [ready, account, token, role, userId, roleError, signInLocal, signOut],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}
