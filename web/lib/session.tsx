"use client";

import type { Session } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, supabase, type Role } from "./api";
import { clearCache } from "./data";

type SessionState = {
  ready: boolean;
  session: Session | null;
  token: string | null;
  email: string | null;
  // undefined while loading, null when the account has no Jogan role
  role: Role | null | undefined;
  roleError: unknown;
  signOut: () => Promise<void>;
};

const Ctx = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [role, setRole] = useState<{ user: string; role: Role | null } | null>(null);
  const [roleError, setRoleError] = useState<unknown>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const token = session?.access_token ?? null;
  const userId = session?.user.id ?? null;

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

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    clearCache();
    setRole(null);
  }, []);

  const value = useMemo<SessionState>(
    () => ({
      ready,
      session,
      token,
      email: session?.user.email ?? null,
      role: role && role.user === userId ? role.role : undefined,
      roleError,
      signOut,
    }),
    [ready, session, token, role, userId, roleError, signOut],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}
