/**
 * Pure rules of the practice UI: answer normalisation, keyboard map, timer states and the words/numbers shown for
 * scores (ported from agent-mentor `AnswerFormats.kt`, `PlayerScreen.kt`, `ResultScreens.kt`). No React here.
 * Nothing in this file grades anything: points and correctness always come from the gateway.
 */
import type { AnswerState, ClientItem, ItemType, PartResult, Report, Session } from "./types";

// ---------------------------------------------------------------- short answers

/**
 * What may be typed in a short-answer box: digits, one decimal comma (a dot becomes a comma), a leading minus
 * (the Unicode minus too), at most `maxChars` characters (the answer-sheet width). `null` = no width limit.
 */
export function normalizeShortAnswerInput(raw: string, maxChars: number | null | undefined = 4): string {
  let s = raw.replace(/−/g, "-").replace(/\./g, ",").replace(/[^0-9,-]/g, "");
  let out = "";
  let comma = false;
  for (const ch of s) {
    if (ch === "-") {
      if (out.length === 0) out += ch;
    } else if (ch === ",") {
      if (!comma) {
        comma = true;
        out += ch;
      }
    } else out += ch;
  }
  s = out;
  return maxChars && maxChars > 0 ? s.slice(0, maxChars) : s;
}

/** The sheet form (`-0,5`) of a complete number, or null when the text is not a number (Enter stays disabled). */
export function parseShortAnswer(input: string | null | undefined, unit?: string | null): string | null {
  let s = (input ?? "").trim().replace(/−/g, "-");
  if (unit && unit.trim() && s.toLowerCase().endsWith(unit.trim().toLowerCase())) s = s.slice(0, -unit.trim().length).trim();
  s = s.replace(/\s+/g, "");
  const m = /^([+-]?)(\d*)(?:[.,](\d+))?$/.exec(s);
  if (!m) return null;
  const [, sign, int, frac] = m;
  if (!int && !frac) return null;
  return (sign === "-" ? "-" : "") + (int || "0") + (frac ? `,${frac}` : "");
}

/** `Ví dụ: -0,5 · tối đa 4 kí tự · làm tròn đến hàng phần mười` (the box hint). */
export function shortAnswerHint(sa: { max_chars?: number | null; decimals?: number | null; unit?: string | null } | undefined): string {
  const parts = ["Ví dụ: -0,5"];
  if (sa?.max_chars) parts.push(`tối đa ${sa.max_chars} kí tự (kể cả dấu − và dấu phẩy)`);
  const d = sa?.decimals;
  if (d === 0) parts.push("làm tròn đến hàng đơn vị");
  else if (d === 1) parts.push("làm tròn đến hàng phần mười");
  else if (d === 2) parts.push("làm tròn đến hàng phần trăm");
  else if (typeof d === "number") parts.push(`${d} chữ số thập phân`);
  if (sa?.unit) parts.push(`không cần ghi đơn vị (${sa.unit})`);
  return parts.join(" · ");
}

// ---------------------------------------------------------------- true/false groups

export type TF = boolean | null;
export const STATEMENT_COUNT = 4;

/** `TF-T` = a Đúng, b Sai, c bỏ trống, d Đúng. */
export function encodeTF(choices: TF[]): string {
  return Array.from({ length: STATEMENT_COUNT }, (_, i) => (choices[i] === true ? "T" : choices[i] === false ? "F" : "-")).join("");
}

export function decodeTF(raw: string | null | undefined): TF[] {
  const out: TF[] = Array.from({ length: STATEMENT_COUNT }, () => null);
  const t = (raw ?? "").toUpperCase().replace(/[\s,;|]/g, "");
  if (t.length !== STATEMENT_COUNT) return out;
  return [...t].map((c) => (c === "T" || c === "Đ" || c === "1" ? true : c === "F" || c === "S" || c === "0" ? false : null));
}

export function setStatement(raw: string | null | undefined, index: number, value: TF): string | null {
  const c = decodeTF(raw);
  c[index] = value;
  return c.every((v) => v === null) ? null : encodeTF(c);
}

/** Keys 1-4 on a group: blank -> Đúng -> Sai -> Đúng ... (same as the desktop player). */
export function cycleStatement(raw: string | null | undefined, index: number): string | null {
  return setStatement(raw, index, decodeTF(raw)[index] !== true);
}

/** scoring-v2 points for a group by the number of right statements (display of the rule only). */
export const STATEMENT_POINTS = [0, 0.1, 0.25, 0.5, 1] as const;

// ---------------------------------------------------------------- can the learner check?

export function canCheck(type: ItemType, answer: string | null | undefined, item?: Pick<ClientItem, "short_answer">): boolean {
  if (!answer) return false;
  if (type === "SHORT_ANSWER") return parseShortAnswer(answer, item?.short_answer?.unit) !== null;
  return true; // a choice, or at least one statement
}

// ---------------------------------------------------------------- keyboard

export type PlayerMode = "practice" | "mock" | "diagnostic" | "review";
export type Phase = "answering" | "feedback";

export type KeyAction =
  | { type: "select"; index: number }
  | { type: "primary" }
  | { type: "prev" }
  | { type: "next" }
  | { type: "hint" }
  | { type: "reveal" }
  | { type: "skip" }
  | { type: "flag" }
  | { type: "grid" }
  | { type: "pause" }
  | { type: "report" };

export interface KeyContext {
  mode: PlayerMode;
  phase: Phase;
  itemType: ItemType;
  optionCount: number;
  hasHint: boolean;
  /** Focus is in a text field (the short-answer box): only Enter and Esc work. */
  typing: boolean;
  /** A dialog or the grid is open: it owns the keyboard. */
  modalOpen: boolean;
}

/** 1-4 or A-D to an option/statement index, else null. */
export function optionIndexForKey(key: string): number | null {
  if (key.length !== 1) return null;
  const i = "1234".indexOf(key);
  if (i >= 0) return i;
  const j = "abcd".indexOf(key.toLowerCase());
  return j >= 0 ? j : null;
}

/** Maps a key press to a player action. Pure; the player decides what an action does. */
export function keyAction(e: { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean }, c: KeyContext): KeyAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  if (c.modalOpen) return null;
  if (e.key === "Escape") return { type: "pause" };
  if (e.key === "Enter") return { type: "primary" };
  if (c.typing) return null;
  const idx = optionIndexForKey(e.key);
  const answerable = c.mode !== "review" && c.phase === "answering";
  if (idx !== null) {
    if (!answerable) return null;
    if (c.itemType === "SHORT_ANSWER") return null;
    const limit = c.itemType === "TRUE_FALSE_GROUP" ? STATEMENT_COUNT : c.optionCount;
    return idx < limit ? { type: "select", index: idx } : null;
  }
  const k = e.key.toLowerCase();
  const free = c.mode === "mock" || c.mode === "review"; // free navigation
  switch (k) {
    case "h":
      return c.mode === "practice" && c.phase === "answering" && c.hasHint ? { type: "hint" } : null;
    case "e":
      return c.mode === "practice" && c.phase === "feedback" ? { type: "reveal" } : null;
    case "s":
      return c.mode === "practice" && c.phase === "answering" ? { type: "skip" } : null;
    case "f":
      return c.mode === "mock" ? { type: "flag" } : null;
    case "g":
      return c.mode === "mock" ? { type: "grid" } : null;
    case "l":
      return (c.mode === "practice" && c.phase === "feedback") || c.mode === "review" ? { type: "report" } : null;
    case "arrowleft":
      return free ? { type: "prev" } : null;
    case "arrowright":
      return free ? { type: "next" } : null;
    default:
      return null;
  }
}

// ---------------------------------------------------------------- timer

export const WARN_SECONDS = 300;
export const URGENT_SECONDS = 60;

export interface TimerView {
  /** Seconds left (mock) or elapsed (practice). */
  shown: number;
  counting: "down" | "up";
  expired: boolean;
  /** At most 5 minutes left (a calm banner, never a siren). */
  warn: boolean;
  urgent: boolean;
}

export function timerView(elapsedSec: number, limitSec: number | null | undefined): TimerView {
  if (limitSec == null) return { shown: Math.max(0, elapsedSec), counting: "up", expired: false, warn: false, urgent: false };
  const left = limitSec - elapsedSec;
  return { shown: Math.max(0, left), counting: "down", expired: left <= 0, warn: left > 0 && left <= WARN_SECONDS, urgent: left > 0 && left <= URGENT_SECONDS };
}

export function formatClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const mm = String(m).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function spokenClock(sec: number, counting: "down" | "up"): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${counting === "down" ? "Còn" : "Đã làm"} ${m} phút ${s} giây`;
}

/** Whole minutes (rounded up) for the "còn N phút" pill. */
export function minutesLeft(sec: number): number {
  return Math.ceil(Math.max(0, sec) / 60);
}

/** Time to give up: the mock paper is handed in by the player when the clock reaches zero. */
export function shouldAutoSubmit(mode: PlayerMode, elapsedSec: number, limitSec: number | null | undefined): boolean {
  return mode === "mock" && limitSec != null && elapsedSec >= limitSec;
}

/** Autosave every 5 s (and at the deadline). */
export function shouldTick(elapsedSec: number, limitSec: number | null | undefined): boolean {
  return elapsedSec % 5 === 0 || (limitSec != null && elapsedSec >= limitSec);
}

/** Remaining seconds from the session (resume): `remaining_sec`, else the deadline, else the full limit. */
export function initialElapsed(session: Pick<Session, "remaining_sec" | "elapsed_sec" | "deadline">, limitSec: number | null, nowMs: number): number {
  if (typeof session.elapsed_sec === "number") return session.elapsed_sec;
  if (limitSec == null) return 0;
  if (typeof session.remaining_sec === "number") return Math.max(0, limitSec - session.remaining_sec);
  if (session.deadline) return Math.max(0, limitSec - Math.round((Date.parse(session.deadline) - nowMs) / 1000));
  return 0;
}

export function timeLimitOf(session: Pick<Session, "kind" | "deadline" | "started_at" | "remaining_sec" | "elapsed_sec">): number | null {
  if (session.kind === "practice") return null;
  if (typeof session.remaining_sec === "number" && typeof session.elapsed_sec === "number") return session.remaining_sec + session.elapsed_sec;
  if (session.deadline) return Math.round((Date.parse(session.deadline) - Date.parse(session.started_at)) / 1000);
  return null;
}

// ---------------------------------------------------------------- progress segments and counts

export type SegmentState = "empty" | "answered" | "correct" | "wrong" | "flagged";

export function isAnswered(a: AnswerState | undefined): boolean {
  return !!a && (!!a.answer || !!a.draft || !!a.checked);
}

export function currentAnswer(a: AnswerState | undefined): string | null {
  return a?.answer ?? a?.draft ?? null;
}

export function segmentStates(items: { position: number }[], answers: Record<string, AnswerState>, mode: PlayerMode): SegmentState[] {
  return items.map((it) => {
    const a = answers[String(it.position)];
    if (mode !== "mock" && a?.correct === true) return "correct";
    if (mode !== "mock" && a?.correct === false) return "wrong";
    if (a?.flagged) return "flagged";
    return isAnswered(a) ? "answered" : "empty";
  });
}

/** Counts for the submit dialog. */
export function submitCounts(items: { position: number }[], answers: Record<string, AnswerState>): { unanswered: number; flagged: number } {
  let unanswered = 0;
  let flagged = 0;
  for (const it of items) {
    const a = answers[String(it.position)];
    if (!currentAnswer(a)) unanswered++;
    if (a?.flagged) flagged++;
  }
  return { unanswered, flagged };
}

export function submitMessage(c: { unanswered: number; flagged: number }): string {
  const parts = [c.unanswered === 0 ? "Bạn đã trả lời tất cả các câu." : `Còn ${c.unanswered} câu chưa trả lời (tính 0 điểm).`];
  if (c.flagged > 0) parts.push(`${c.flagged} câu đang được đánh dấu xem lại.`);
  return parts.join(" ");
}

export function nextStreak(prev: number, correct: boolean): number {
  return correct ? prev + 1 : 0;
}

// ---------------------------------------------------------------- scores and words

export const LEVEL_NAMES = ["Nhận biết", "Thông hiểu", "Vận dụng", "Vận dụng cao"] as const;

/** 0,25 / 1 / 0,5 : at most two decimals, a decimal comma, no trailing zeros. */
export function formatPoints(v: number): string {
  const r = Math.round(v * 100) / 100;
  return String(r).replace(".", ",");
}

/** Score on the 10-point scale, always two decimals: `7,25`. */
export function formatScore10(v: number): string {
  return v.toFixed(2).replace(".", ",");
}

export function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

/** "Chưa có dữ liệu -> 62% (Đang tiến bộ)" for a topic row; the label is the gateway's, never recomputed here. */
export function masteryChange(t: { mastery_before: number | null; mastery_after: number | null; label: string }): { text: string; direction: "up" | "down" | "flat" | "none" } {
  const { mastery_before: b, mastery_after: a } = t;
  if (a == null) return { text: t.label, direction: "none" };
  if (b == null) return { text: `mới: ${pct(a)}`, direction: "none" };
  const d = Math.round((a - b) * 100);
  if (d === 0) return { text: `${pct(b)} → ${pct(a)} (giữ nguyên)`, direction: "flat" };
  return { text: `${pct(b)} → ${pct(a)} (${d > 0 ? "▲ +" : "▼ "}${d}%)`, direction: d > 0 ? "up" : "down" };
}

export function accuracyOf(r: Pick<Report, "correct" | "total" | "answered">, kind: string): number {
  const base = kind === "mock" ? r.total : r.answered;
  return base > 0 ? r.correct / base : 0;
}

/** Kind of headline for the summary; says "partial" when the learner stopped early. */
export function summaryHeadline(r: Report, kind: string): string {
  const acc = accuracyOf(r, kind);
  if (kind === "diagnostic") return "Xong phần đánh giá!";
  if (kind === "practice" && r.answered < r.total / 2) return "Khởi động tốt!";
  if (acc >= 0.8) return "Xuất sắc!";
  if (acc >= 0.6) return "Làm tốt lắm!";
  if (acc >= 0.4) return "Đang tiến bộ!";
  return "Khởi đầu tốt, mình cùng củng cố nhé";
}

/** Confetti only at 60 % or better, never for an empty session. */
export function earnsConfetti(r: Pick<Report, "correct" | "total" | "answered">, kind: string): boolean {
  return r.answered > 0 && accuracyOf(r, kind) >= 0.6;
}

export function kindLabel(kind: string): string {
  return kind === "mock" ? "Thi thử" : kind === "diagnostic" ? "Đánh giá nhanh" : "Luyện tập";
}

/** Heading under an answered practice item. */
export function feedbackHeadline(type: ItemType, r: { correct: boolean; points?: number; max_points?: number; right?: number; keyLabel: string }): string {
  if (type === "TRUE_FALSE_GROUP") {
    const right = r.right ?? 0;
    const pts = formatPoints(r.points ?? 0);
    return right === STATEMENT_COUNT ? `Chính xác cả 4 ý! · ${pts} điểm` : `Đúng ${right}/4 ý · ${pts}/${formatPoints(r.max_points ?? 1)} điểm`;
  }
  if (r.correct) return "Chính xác!";
  return `Chưa đúng, đáp án đúng là ${r.keyLabel}`;
}

/** Per-statement results from either shape the gateway may send. */
export function statementOutcome(results: unknown, count = STATEMENT_COUNT): (boolean | null)[] {
  const arr = Array.isArray(results) ? results : [];
  return Array.from({ length: count }, (_, i) => {
    const r = arr[i];
    if (typeof r === "boolean") return r;
    if (r && typeof r === "object" && typeof (r as { correct?: unknown }).correct === "boolean") return (r as { correct: boolean }).correct;
    return null;
  });
}

/** Display of the correct key: `Đ S Đ S` for groups, the number for short answers, a letter for a choice. */
export function keyLabelOf(type: ItemType, correctAnswer: string): string {
  if (type === "TRUE_FALSE_GROUP") return decodeTF(correctAnswer).map((v) => (v === true ? "Đ" : v === false ? "S" : "–")).join(" ");
  return correctAnswer;
}

/** Counts of a `per_part` entry whichever spelling the gateway used. */
export function partCounts(p: PartResult): { items: number; fullyCorrect: number; truefalse: boolean } {
  return {
    items: p.items ?? p.total ?? 0,
    fullyCorrect: p.fully_correct ?? p.correct ?? 0,
    truefalse: p.type === "TRUE_FALSE_GROUP" || p.part === 2 || /Đúng\/Sai/.test(p.label),
  };
}

/** A session that is no longer running (finished, expired or abandoned) goes to its summary. */
export function isOver(s: { finished?: boolean; status?: string }): boolean {
  return !!s.finished || (!!s.status && s.status !== "active");
}

/** A running mock or diagnostic blocks a new session (409 `active_session`): where to resume. */
export function blockedFrom(e: unknown): { id: string; kind: string } | null {
  const b = (e as { status?: number; body?: { code?: string; session_id?: string; kind?: string } } | null) ?? null;
  if (b?.status !== 409 || b.body?.code !== "active_session" || !b.body.session_id) return null;
  return { id: b.body.session_id, kind: b.body.kind ?? "mock" };
}

/** Friendly Vietnamese `detail` of the grade-filter 422s (CONTRACTS 10.11), shown as-is; null for any other error. */
export function gradeDetail(e: unknown): string | null {
  const x = e as { status?: number; body?: { code?: string; detail?: unknown } } | null;
  if (x?.status !== 422) return null;
  const code = x.body?.code;
  if ((code === "insufficient_content" || code === "above_grade" || code === "above_grade_topic") && typeof x.body?.detail === "string") return x.body.detail;
  return null;
}

/** `{code}` of a gateway error body (CONTRACTS 10.9), e.g. `expired`, `active_session`. */
export function errorCode(body: unknown): string | null {
  const c = (body as { code?: unknown } | null | undefined)?.code;
  return typeof c === "string" ? c : null;
}

export function partsOf(r: Report): PartResult[] {
  return r.per_part ?? [];
}

/** Position range label for the three-part paper: "Phần II · câu 2/4". */
export function partOf(session: Pick<Session, "parts">, position: number): { label: string; index: number; count: number } | null {
  const part = session.parts?.find((p) => p.positions.includes(position));
  if (!part) return null;
  return { label: part.label, index: part.positions.indexOf(position) + 1, count: part.positions.length };
}

/** The most-urgent chat/UI wording for a recommendation action (ports `recommendationAction`). */
export function actionLabel(kind: string): string {
  switch (kind) {
    case "diagnostic":
      return "Đánh giá ngay";
    case "mock":
      return "Thi thử…";
    case "progress":
      return "Xem tiến bộ";
    case "break":
      return "Nghỉ một chút";
    default:
      return "Luyện ngay";
  }
}

export const REPORT_REASONS: { id: string; label: string }[] = [
  { id: "wrong_key", label: "Đáp án đúng bị sai" },
  { id: "wrong_solution", label: "Lời giải sai hoặc thiếu" },
  { id: "unclear", label: "Đề khó hiểu, thiếu dữ kiện" },
  { id: "typo", label: "Lỗi chính tả hoặc công thức" },
  { id: "other", label: "Lỗi khác" },
];
