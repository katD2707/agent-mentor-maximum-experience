"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getApi, isApiError } from "@/lib/api";
import type { Me } from "@/lib/types";

export type SessionStatus = "loading" | "anon" | "ready" | "error";

interface SessionValue {
  status: SessionStatus;
  me: Me | null;
  error: string | null;
  refresh: () => Promise<Me | null>;
  setMe: (me: Me) => void;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [me, setMeState] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const m = await getApi().getMe();
      setMeState(m);
      setStatus("ready");
      setError(null);
      return m;
    } catch (e) {
      if (isApiError(e, 401) || isApiError(e, 403)) {
        setMeState(null);
        setStatus("anon");
        setError(null);
      } else {
        setStatus("error");
        setError(e instanceof Error ? e.message : String(e));
      }
      return null;
    }
  }, []);

  useEffect(() => {
    let alive = true;
    getApi()
      .getMe()
      .then(
        (m) => {
          if (!alive) return;
          setMeState(m);
          setStatus("ready");
        },
        (e: unknown) => {
          if (!alive) return;
          if (isApiError(e, 401) || isApiError(e, 403)) setStatus("anon");
          else {
            setStatus("error");
            setError(e instanceof Error ? e.message : String(e));
          }
        },
      );
    return () => {
      alive = false;
    };
  }, []);

  const setMe = useCallback((m: Me) => {
    setMeState(m);
    setStatus("ready");
  }, []);

  const logout = useCallback(async () => {
    try {
      await getApi().logout();
    } finally {
      setMeState(null);
      setStatus("anon");
    }
  }, []);

  const value = useMemo(() => ({ status, me, error, refresh, setMe, logout }), [status, me, error, refresh, setMe, logout]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const v = useContext(SessionContext);
  if (!v) throw new Error("useSession outside SessionProvider");
  return v;
}

/** The signed-in, onboarded user. Only call under <AuthGate>. */
export function useMe(): Me {
  const { me } = useSession();
  if (!me) throw new Error("useMe without a session");
  return me;
}
