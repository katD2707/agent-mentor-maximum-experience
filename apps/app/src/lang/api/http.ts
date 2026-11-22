import { request, qs } from "../../api/http";
import type { Chicken, FocusActive, FocusDone, LgApi, XpWeek, Market, ArenaPaper, ChatMessage, NotesSet, Village } from "./types";

export const httpLg: LgApi = {
  getVillage: (token) => request<Village>("GET", "/village", { token }),
  getMarket: (token) => request<Market>("GET", "/market", { token }),
  takeChicken: (token, chicken) => request<Chicken>("POST", "/chickens", { token, body: { chicken } }),
  letGo: (token, chicken) => request<void>("DELETE", `/chickens/${encodeURIComponent(chicken)}`, { token }),
  async getChicken(token, chicken) {
    const r = await request<{ chicken: Chicken; week_xp: number[] }>("GET", `/chickens/${encodeURIComponent(chicken)}`, { token });
    return { chicken: r.chicken, week_xp: r.week_xp };
  },
  xpWeek: (token) => request<XpWeek>("GET", "/xp/week", { token }),
  focusStart: (token, body) => request<FocusActive>("POST", "/focus", { token, body }),
  async focusFinish(token, id, minutesDone) {
    // the gateway answers {xp: [rows], gained, minutes_done, daily_cap, chicken}; the screen wants the gained number
    const r = await request<Omit<FocusDone, "xp"> & { gained: number }>("POST", `/focus/${encodeURIComponent(id)}/finish`, { token, body: { minutes_done: minutesDone } });
    return { xp: r.gained, minutes_done: r.minutes_done, daily_cap: r.daily_cap, chicken: r.chicken };
  },
  async focusActive(token) {
    try {
      const r = await request<FocusActive | null>("GET", "/focus/active", { token });
      return r && r.id ? r : null;
    } catch {
      return null;
    }
  },
  listNotes: (token) => request<NotesSet[]>("GET", "/ask/notes", { token }),
  arenaPapers: (token, q) => request<ArenaPaper[]>("GET", "/arena/papers" + qs({ chicken: q?.chicken, year: q?.year ? String(q.year) : undefined }), { token }),
  chatHistory: (token, chicken, limit = 30) => request<ChatMessage[]>("GET", `/chat/${encodeURIComponent(chicken)}/history` + qs({ limit: String(limit) }), { token }),
};
