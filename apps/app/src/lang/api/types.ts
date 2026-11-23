/** Làng gà endpoints (CONTRACTS-LANGGA.md section 2). */
export interface Chicken {
  id: string;
  name_vi: string;
  name_en: string;
  art: string;
  level: number;
  xp: number;
  xp_in_level: number;
  stage: 1 | 2 | 3 | 4;
  courses: number;
  active_course: { id: string; title: string; percent: number } | null;
  done_today: boolean;
  taken_at: string;
}

export interface SpeakerAction {
  kind: "lesson" | "review" | "practice" | "research" | "mock" | "break" | string;
  deep_link: string;
  minutes: number;
}
export interface Speaker {
  chicken: string;
  line_vi: string;
  line_en: string;
  action: SpeakerAction | null;
}
export interface NewsItem {
  id: string;
  chicken: string | null;
  kind: "level_up" | "reminder" | "course" | string;
  text_vi: string;
  text_en: string;
  at: string;
}
export interface Village {
  chickens: Chicken[];
  speaker: Speaker | null;
  news: NewsItem[];
  streak: { days: number; today_done: boolean };
  week: { done: number; planned: number };
}

export interface MarketChicken {
  id: string;
  name_vi: string;
  name_en: string;
  art: string;
  courses: number;
  owned: boolean;
}
export interface Market {
  stage: string;
  chickens: MarketChicken[];
}

export interface XpGain {
  chicken: string;
  source: string;
  amount: number;
  level_up: boolean;
}

export interface FocusStart {
  id: string;
  ends_at: string;
}
export interface FocusDone {
  /** XP the session paid (the gateway's `gained`; the focus part plus the +5 for a full session) */
  xp: number;
  minutes_done: number;
  daily_cap: number;
  chicken: Chicken;
}

/** One chicken's week in GET /xp/week: seven day sums (oldest first, the last is today) and the sums by source. */
export interface XpWeekChicken {
  chicken: string;
  owned: boolean;
  level: number;
  xp: number;
  xp_in_level: number;
  stage: number;
  week: number[];
  week_total: number;
  by_source: Record<string, number>;
}
export interface XpWeek {
  days: string[];
  chickens: XpWeekChicken[];
  total: number;
}
export interface FocusActive extends FocusStart {
  chicken?: string;
  minutes?: number;
  remaining_sec?: number;
  started_at?: string;
  status?: "active" | "paused";
  paused_at?: string;
}

export interface NotesSet {
  notes_id: string;
  title: string;
  pages: number;
  items: number;
  created_at: string;
  next_review_at: string;
}

export interface ArenaPaper {
  id: string;
  kind: "thpt" | "minh-hoa" | "dgnl" | "cuoi-ky";
  title_vi: string;
  title_en: string;
  year: number;
  minutes: number;
  items: number;
  chicken: string;
  boss: { name_vi: string; name_en: string; art: string };
  best_score: number | null;
  beaten: boolean;
  placeholder: boolean;
  band?: string;
  note_vi?: string | null;
  note_en?: string | null;
  source?: { name: string; url: string } | null;
}

export interface ChatAction {
  label_vi: string;
  label_en: string;
  deep_link: string;
}
export interface ChatMessage {
  role: "me" | "chicken";
  text: string;
  at: string;
}

export interface LgApi {
  getVillage(token: string): Promise<Village>;
  getMarket(token: string): Promise<Market>;
  takeChicken(token: string, chicken: string): Promise<Chicken>;
  letGo(token: string, chicken: string): Promise<void>;
  getChicken(token: string, chicken: string): Promise<{ chicken: Chicken; week_xp: number[] }>;
  xpWeek(token: string): Promise<XpWeek>;
  focusStart(token: string, body: { minutes: number; chicken: string }): Promise<FocusActive>;
  focusFinish(token: string, id: string, minutesDone: number): Promise<FocusDone>;
  focusActive(token: string): Promise<FocusActive | null>;
  /** stop the clock on the server; `agoSec`: the tab went away that long ago */
  focusPause(token: string, id: string, agoSec?: number): Promise<FocusActive>;
  focusResume(token: string, id: string): Promise<FocusActive>;
  /** same as focusPause but survives the page closing (fetch keepalive); never throws */
  focusPauseOnLeave(token: string, id: string): void;
  listNotes(token: string): Promise<NotesSet[]>;
  arenaPapers(token: string, q?: { chicken?: string; year?: number }): Promise<ArenaPaper[]>;
  chatHistory(token: string, chicken: string, limit?: number): Promise<ChatMessage[]>;
}
