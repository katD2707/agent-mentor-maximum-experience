import { useEffect, useState } from "react";
import { api, type Lang, type Today } from "../api";
import { useAuth } from "../state/auth";

/** GET /today for the hub lines and the "today" block. The last answer is kept on the device so both still show offline. */
const key = (userId: string) => `mentor.today.${userId}`;

function readCache(userId: string): Today | null {
  try {
    const raw = localStorage.getItem(key(userId));
    return raw ? (JSON.parse(raw) as Today) : null;
  } catch {
    return null;
  }
}

export interface TodayState {
  today: Today | null;
  status: "loading" | "ready" | "error";
}

export function useToday(): TodayState {
  const { token, user } = useAuth();
  const [state, setState] = useState<TodayState>(() => ({ today: user ? readCache(user.id) : null, status: "loading" }));
  useEffect(() => {
    if (!token || !user || user.role !== "student") return;
    let alive = true;
    const load = async () => {
      try {
        const today = await api.getToday(token);
        try {
          localStorage.setItem(key(user.id), JSON.stringify(today));
        } catch {
          /* ignore */
        }
        if (alive) setState({ today, status: "ready" });
      } catch {
        if (alive) setState((s) => ({ today: s.today ?? readCache(user.id), status: "error" }));
      }
    };
    void load();
    const id = setInterval(load, 5 * 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [token, user]);
  return state;
}

/** The text in the UI language (`line_vi` / `line_en`, `title_vi` / ...). */
export function pickLang(o: object, base: string, lang: string): string {
  const rec = o as Record<string, unknown>;
  const l: Lang = lang === "en" ? "en" : "vi";
  const v = rec[`${base}_${l}`] ?? rec[`${base}_vi`];
  return typeof v === "string" ? v : "";
}
