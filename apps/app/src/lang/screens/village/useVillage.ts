import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../../state/auth";
import { lg, type Village } from "../../api";
import { onXp, takeLevelUps } from "../../xp";

export interface LevelUp {
  chicken: string;
  level: number;
}

/** What got higher between two looks at the village: a chicken's level (a level-up moment). */
export function levelUps(before: Village | null, after: Village): LevelUp[] {
  if (!before) return [];
  const old = new Map(before.chickens.map((c) => [c.id, c.level]));
  return after.chickens.filter((c) => (old.get(c.id) ?? c.level) < c.level).map((c) => ({ chicken: c.id, level: c.level }));
}

/**
 * GET /village for the village screen. Reloaded when the window comes back to the front (the person may have studied
 * elsewhere in the app meanwhile) and on `refresh()`; a level that went up since the last look is reported once.
 */
export function useVillage() {
  const { token } = useAuth();
  const [village, setVillage] = useState<Village | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [up, setUp] = useState<LevelUp[]>([]);
  const last = useRef<Village | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return null;
    setStatus((s) => (s === "error" ? "loading" : s));
    try {
      const v = await lg.getVillage(token);
      const ups = levelUps(last.current, v);
      // a level that went up elsewhere in the app (lesson, practice, study room) while the village was not on screen
      for (const id of takeLevelUps()) {
        const c = v.chickens.find((x) => x.id === id);
        if (c && !ups.some((u) => u.chicken === id)) ups.push({ chicken: id, level: c.level });
      }
      last.current = v;
      setVillage(v);
      setStatus("ready");
      if (ups.length) setUp((l) => [...l, ...ups]);
      return v;
    } catch {
      setStatus((s) => (s === "ready" ? s : "error"));
      return null;
    }
  }, [token]);

  useEffect(() => {
    void refresh();
    const onVis = () => document.visibilityState === "visible" && void refresh();
    document.addEventListener("visibilitychange", onVis);
    const off = onXp(() => void refresh()); // XP paid while the village is open (the chat tray's quick practice)
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      off();
    };
  }, [refresh]);

  const clearUp = useCallback(() => setUp([]), []);
  return { village, status, refresh, levelUps: up, clearLevelUps: clearUp };
}
