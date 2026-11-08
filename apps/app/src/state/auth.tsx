import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, hasMediaToken, localTokenStorage, setMediaToken, setMediaTokenSource, type Role, type User, type UserPatch } from "../api";
import { setLang } from "../i18n";
import { flushOutbox } from "../lib/enrollments";
import { bandForBirthYear } from "../lib/age";
import type { AgeBand } from "../api/types";

type Status = "loading" | "anon" | "authed";

interface AuthValue {
  status: Status;
  user: User | null;
  /** Session token (for course/media calls). */
  token: string | null;
  login(username: string, password: string, role: Role): Promise<User>;
  logout(): Promise<void>;
  updateMe(patch: UserPatch): Promise<void>;
  setQuiet(until: string | null): Promise<void>;
}

const Ctx = createContext<AuthValue | null>(null);
const THEME_KEY = "mentor.theme";

function storedTheme() {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function applyTheme(theme: string) {
  const root = document.documentElement;
  if (theme === "light" || theme === "dark") root.dataset.theme = theme;
  else delete root.dataset.theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* ignore */
  }
}

export function AuthProvider({ children, storage = localTokenStorage }: { children: ReactNode; storage?: typeof localTokenStorage }) {
  const [status, setStatus] = useState<Status>("loading");
  const [rawUser, setUser] = useState<User | null>(null);
  const [tick, setTick] = useState(0);
  const bandRef = useRef<AgeBand | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // The band comes from the birth year and today's date, so it is worked out here on every launch (the server
  // value is only the fallback) and re-checked on focus and every few minutes: the density switches on its own
  // when the app stays open across 1 September.
  const user = useMemo<User | null>(() => {
    if (!rawUser) return null;
    const band = rawUser.birth_year != null ? bandForBirthYear(rawUser.birth_year) : null;
    bandRef.current = band;
    return band ? { ...rawUser, age_band: band } : rawUser;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawUser, tick]);

  useEffect(() => {
    if (rawUser?.birth_year == null) return;
    const birthYear = rawUser.birth_year;
    const check = () => {
      if (bandForBirthYear(birthYear) !== bandRef.current) setTick((n) => n + 1);
    };
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    const id = setInterval(check, 5 * 60000);
    return () => {
      window.removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", check);
      clearInterval(id);
    };
  }, [rawUser?.birth_year]);

  // restore the saved session
  useEffect(() => {
    let alive = true;
    (async () => {
      const saved = await storage.get();
      if (!saved) return alive && setStatus("anon");
      try {
        const me = await api.getMe(saved);
        await api.mediaToken(saved).then(setMediaToken, () => undefined); // so the first <img>/<video> already has one
        if (!alive) return;
        setToken(saved);
        setUser(me);
        setStatus("authed");
      } catch (e) {
        if (e instanceof ApiError && e.code === "unauthorized") await storage.clear();
        if (alive) setStatus("anon");
      }
    })();
    return () => {
      alive = false;
    };
  }, [storage]);

  // media token for <img>/<video> URLs; refreshed well inside its 240 minute life
  useEffect(() => {
    if (!token) {
      setMediaToken(null);
      setMediaTokenSource(null);
      return;
    }
    let alive = true;
    setMediaTokenSource(() => api.mediaToken(token)); // also used to retry a media URL that got a 401
    const get = () => api.mediaToken(token).then((m) => alive && setMediaToken(m)).catch(() => undefined);
    if (!hasMediaToken()) void get();
    const id = setInterval(get, 180 * 60000);
    return () => {
      alive = false;
      clearInterval(id);
      setMediaTokenSource(null);
    };
  }, [token]);

  // progress saved while offline is replayed at start-up and as soon as the network is back
  useEffect(() => {
    if (!token || !user || user.role !== "student") return;
    const run = () => void flushOutbox(token, user.id);
    run();
    window.addEventListener("online", run);
    return () => window.removeEventListener("online", run);
  }, [token, user]);

  // what the user chose drives the whole look: theme, age density, language
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.age = user?.age_band ?? (user ? "g10_12" : "g6_9");
    applyTheme(user ? user.theme : storedTheme());
    if (user?.language) setLang(user.language);
  }, [user]);

  const login = useCallback(
    async (username: string, password: string, role: Role) => {
      const res = await api.login(username, password, role);
      await api.mediaToken(res.token).then(setMediaToken, () => undefined);
      await storage.set(res.token);
      setToken(res.token);
      setUser(res.user);
      setStatus("authed");
      return res.user;
    },
    [storage],
  );

  const logout = useCallback(async () => {
    const t = token;
    await storage.clear();
    setToken(null);
    setUser(null);
    setStatus("anon");
    if (t) {
      try {
        await api.logout(t);
      } catch {
        /* the local session is already gone */
      }
    }
  }, [storage, token]);

  const updateMe = useCallback(
    async (patch: UserPatch) => {
      if (!token) return;
      setUser(await api.patchMe(token, patch));
    },
    [token],
  );

  const setQuiet = useCallback(
    async (until: string | null) => {
      if (!token) return;
      const res = await api.putQuiet(token, until);
      setUser((u) => (u ? { ...u, quiet_until: res.until } : u));
    },
    [token],
  );

  const value = useMemo(() => ({ status, user, token, login, logout, updateMe, setQuiet }), [status, user, token, login, logout, updateMe, setQuiet]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
