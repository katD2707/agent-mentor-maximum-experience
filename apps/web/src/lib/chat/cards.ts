/**
 * Client-side state of chat cards (CONTRACTS 9, Built H) and the time maths behind them. Pure: components render
 * this state; each click also goes to the gateway as `card_action`, and the server's `card_echo` draws the
 * learner's bubble. A refused click rolls the card back.
 */
import { TZ } from "../format";
import type { ChatCard, FlashcardCard, FocusCard } from "../types";

export interface CardUiState {
  /** flashcard: the choice text the learner picked */
  chosen?: string;
  /** flashcard without choices: the typed answer */
  answerText?: string;
  /** flashcard: skipped */
  skipped?: boolean;
  /** flashcard: grading; null = the card cannot tell (reveal names no choice), the mentor answers in chat */
  correct?: boolean | null;
  /** focus: ended (locally, until the server's updated card arrives with `ended_at`) */
  focusDone?: boolean;
  /** focus: optimistic end time after "extend" (ISO), dropped when the updated card arrives */
  endsAt?: string;
  /** checkin: picked option */
  picked?: string;
  /** deadline: marked done / started a focus session */
  deadline?: "done" | "start_focus";
  /** celebration: confetti and the mascot celebrate already played (or must never play: history, crisis) */
  played?: boolean;
}

export type CardEvent =
  | { type: "flash_choose"; value: string }
  | { type: "flash_answer"; text: string }
  | { type: "flash_skip" }
  | { type: "focus_done" }
  | { type: "focus_extend"; minutes: number; now: number }
  | { type: "checkin_pick"; value: string }
  | { type: "deadline_done" }
  | { type: "deadline_focus"; minutes: number }
  | { type: "celebration_played" };

export const FOCUS_EXTEND_MINUTES = 10;
export const DEADLINE_FOCUS_MINUTES = 25;

/** "A".."D" for a choice (Built H sends answers as the letter). */
export function choiceLetter(card: Pick<FlashcardCard, "choices">, value: string): string | null {
  const i = card.choices?.indexOf(value) ?? -1;
  return i >= 0 && i < 4 ? "ABCD"[i] : null;
}

/** The card_action the gateway receives for a UI event; null = local only. */
export function cardActionFor(card: ChatCard, ev: CardEvent): { action: string; value?: string } | null {
  switch (ev.type) {
    case "flash_choose":
      return card.kind === "flashcard" ? { action: "answer", value: choiceLetter(card, ev.value) ?? ev.value } : null;
    case "flash_answer":
      return { action: "answer", value: ev.text };
    case "flash_skip":
      return { action: "skip" };
    case "focus_done":
      return { action: "done" };
    case "focus_extend":
      return { action: "extend", value: String(ev.minutes) };
    case "checkin_pick":
      return { action: "answer", value: ev.value };
    case "deadline_done":
      return { action: "done" };
    case "deadline_focus":
      return { action: "start_focus", value: String(ev.minutes) };
    default:
      return null;
  }
}

/**
 * The UI event a recorded click stands for (history: user items carry `card_action`), so a replayed card shows
 * what the learner already did. Extensions are not replayed: history holds the card's newest content.
 */
export function eventFromCardAction(card: ChatCard, action: string, value?: string | null): CardEvent | null {
  const v = value ?? "";
  switch (card.kind) {
    case "flashcard": {
      if (action === "skip") return { type: "flash_skip" };
      if (action !== "answer") return null;
      const choices = card.choices ?? [];
      const byLetter = /^[A-D]$/i.test(v) ? choices["ABCD".indexOf(v.toUpperCase())] : undefined;
      const choice = byLetter ?? choices.find((c) => c === v);
      return choice ? { type: "flash_choose", value: choice } : v ? { type: "flash_answer", text: v } : null;
    }
    case "checkin":
      return action === "answer" && v ? { type: "checkin_pick", value: v } : null;
    case "deadline":
      return action === "done" ? { type: "deadline_done" } : action === "start_focus" ? { type: "deadline_focus", minutes: Number(v) || DEADLINE_FOCUS_MINUTES } : null;
    case "focus":
      return action === "done" ? { type: "focus_done" } : null;
    default:
      return null;
  }
}

const norm = (s: string) =>
  s
    .normalize("NFC")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();

const SEP = /^[\s.:,;)—–-]/;

/**
 * Grades a flashcard choice against `reveal`, which by convention starts with the correct choice: its text or its
 * letter (`B`, `B.`, `B)`), optionally followed by an explanation. Returns null when `reveal` names no choice:
 * the card then stays neutral and the mentor grades in chat (it always does, server-side).
 */
export function gradeFlashcard(card: Pick<FlashcardCard, "choices" | "reveal">, chosen: string): boolean | null {
  if (!card.reveal || !card.choices?.length) return null;
  const r = norm(card.reveal);
  const startsWith = (n: string) => r === n || (r.startsWith(n) && SEP.test(r.slice(n.length)));
  // The longest matching choice text wins ("x = 2" vs "x = 2 hoặc x = 3"), then a leading letter.
  let correct = [...card.choices].sort((a, b) => b.length - a.length).find((c) => startsWith(norm(c)));
  if (!correct) {
    const m = /^([a-d])(?:[.):]|\s|$)/.exec(r);
    if (m) correct = card.choices["abcd".indexOf(m[1])];
  }
  if (!correct) return null;
  return norm(correct) === norm(chosen);
}

/** Has the learner answered (reveal may show)? */
export function flashcardAnswered(ui: CardUiState): boolean {
  return ui.chosen !== undefined || ui.answerText !== undefined || ui.skipped === true;
}

export function cardReducer(card: ChatCard, ui: CardUiState, ev: CardEvent): CardUiState {
  switch (ev.type) {
    case "flash_choose":
      if (card.kind !== "flashcard" || flashcardAnswered(ui)) return ui; // one answer per card
      return { ...ui, chosen: ev.value, correct: gradeFlashcard(card, ev.value) };
    case "flash_answer":
      if (card.kind !== "flashcard" || flashcardAnswered(ui) || !ev.text.trim()) return ui;
      return { ...ui, answerText: ev.text.trim(), correct: null };
    case "flash_skip":
      return card.kind === "flashcard" && !flashcardAnswered(ui) ? { ...ui, skipped: true } : ui;
    case "focus_done":
      return card.kind === "focus" && !ui.focusDone && !card.ended_at ? { ...ui, focusDone: true } : ui;
    case "focus_extend": {
      if (card.kind !== "focus" || ui.focusDone || card.ended_at) return ui;
      const base = Math.max(ev.now, Date.parse(ui.endsAt ?? card.ends_at) || ev.now);
      return { ...ui, endsAt: new Date(base + ev.minutes * 60_000).toISOString() };
    }
    case "checkin_pick":
      return card.kind === "checkin" && ui.picked === undefined ? { ...ui, picked: ev.value } : ui;
    case "deadline_done":
      return card.kind === "deadline" && !ui.deadline ? { ...ui, deadline: "done" } : ui;
    case "deadline_focus":
      return card.kind === "deadline" && !ui.deadline ? { ...ui, deadline: "start_focus" } : ui;
    case "celebration_played":
      return { ...ui, played: true };
    default:
      return ui;
  }
}

/**
 * The server sent a newer version of a card already on screen (focus extended or ended): its fields win, and
 * optimistic local overrides that it now answers are dropped.
 */
export function mergeCardUpdate(next: ChatCard, ui: CardUiState): CardUiState {
  if (next.kind !== "focus") return ui;
  const rest = { ...ui };
  delete rest.endsAt;
  if (next.ended_at) rest.focusDone = true;
  return rest;
}

// ---- deadline countdown (VN time, calm wording) ----

export interface Countdown {
  past: boolean;
  totalMs: number;
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}

export function countdown(dueIso: string, nowMs: number): Countdown {
  const due = Date.parse(dueIso);
  const total = Number.isNaN(due) ? 0 : due - nowMs;
  const ms = Math.max(0, total);
  return {
    past: total <= 0,
    totalMs: total,
    days: Math.floor(ms / 86_400_000),
    hours: Math.floor((ms % 86_400_000) / 3_600_000),
    minutes: Math.floor((ms % 3_600_000) / 60_000),
    seconds: Math.floor((ms % 60_000) / 1000),
  };
}

/** "còn 2 ngày 4 giờ" / "còn 3 giờ 12 phút" / "còn 8 phút" / "còn chưa tới 1 phút" / "đã tới hạn". No seconds: no pressure. */
export function formatCountdown(c: Countdown): string {
  if (c.past) return "đã tới hạn";
  if (c.days > 0) return c.hours > 0 ? `còn ${c.days} ngày ${c.hours} giờ` : `còn ${c.days} ngày`;
  if (c.hours > 0) return c.minutes > 0 ? `còn ${c.hours} giờ ${c.minutes} phút` : `còn ${c.hours} giờ`;
  if (c.minutes > 0) return `còn ${c.minutes} phút`;
  return "còn chưa tới 1 phút";
}

/** How often the countdown needs to re-render (it shows minutes at most): 0 = never again. */
export function countdownTickMs(c: Countdown): number {
  if (c.past) return 0;
  return c.totalMs <= 3_600_000 ? 15_000 : 30_000;
}

const DUE_FMT = new Intl.DateTimeFormat("vi-VN", {
  timeZone: TZ,
  weekday: "long",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Due time in VN time, e.g. "20:00, thứ Năm 06/11". */
export function formatDue(dueIso: string): string {
  const d = new Date(dueIso);
  if (Number.isNaN(d.getTime())) return dueIso;
  const parts = Object.fromEntries(DUE_FMT.formatToParts(d).map((p) => [p.type, p.value]));
  return `${parts.hour}:${parts.minute}, ${parts.weekday} ${parts.day}/${parts.month}`;
}

/** Calm tone: more than 2 days away is "far", the last 24 h "soon"; never alarming colours. */
export function deadlineTone(c: Countdown): "far" | "near" | "soon" | "past" {
  if (c.past) return "past";
  if (c.totalMs <= 86_400_000) return "soon";
  if (c.totalMs <= 2 * 86_400_000) return "near";
  return "far";
}

// ---- focus timer ----

export interface FocusProgress {
  /** 0..1 of the session elapsed */
  fraction: number;
  remainingMs: number;
  /** time is up, or the session was ended */
  finished: boolean;
  /** ended by the learner (or the server says so) */
  ended: boolean;
}

/** `minutes` is the total planned time and `ends_at` the current end, so the start is `ends_at - minutes`. */
export function focusProgress(card: Pick<FocusCard, "minutes" | "ends_at" | "ended_at">, ui: CardUiState, nowMs: number): FocusProgress {
  const serverEnd = Date.parse(card.ends_at);
  const start = serverEnd - card.minutes * 60_000;
  const end = ui.endsAt ? Date.parse(ui.endsAt) : serverEnd;
  const endedAt = card.ended_at ? Date.parse(card.ended_at) : NaN;
  const ended = ui.focusDone === true || !Number.isNaN(endedAt);
  const now = Number.isNaN(endedAt) ? nowMs : Math.min(nowMs, endedAt);
  const span = Math.max(1, end - start);
  const remaining = ended ? 0 : Math.max(0, end - now);
  return {
    fraction: ended ? 1 : Math.min(1, Math.max(0, (now - start) / span)),
    remainingMs: remaining,
    finished: ended || remaining === 0,
    ended,
  };
}

/** "24:05" style clock for the focus ring. */
export function formatClock(ms: number): string {
  const s = Math.ceil(ms / 1000);
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
