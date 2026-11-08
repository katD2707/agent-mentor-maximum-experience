import type { PAnswerState, PItem, PResult, PSession, StatementResult } from "../api/practice";

/** Pure rules of the practice screens: answer encoding (CONTRACTS 10.9), result wording, the mock clock, resume. */

// ---------------------------------------------------------------- answer encoding

/** TRUE_FALSE_GROUP answer: one char per statement, T / F, `-` for not answered ("TF-T"). */
export function tfEncode(item: PItem, values: Record<string, boolean | undefined>): string {
  return (item.statements ?? []).map((s) => (values[s.id] === true ? "T" : values[s.id] === false ? "F" : "-")).join("");
}

export function tfDecode(item: PItem, value: string | null | undefined): Record<string, boolean | undefined> {
  const out: Record<string, boolean | undefined> = {};
  const v = (value ?? "").toUpperCase().replace(/Đ/g, "T").replace(/S/g, "F");
  (item.statements ?? []).forEach((s, i) => {
    const c = v[i];
    out[s.id] = c === "T" ? true : c === "F" ? false : undefined;
  });
  return out;
}

/** Can the learner press "Kiểm tra" (practice)? Statements all answered, some text, a tap, a chosen option. */
export function canCheck(item: PItem, value: string | null | undefined): boolean {
  const v = (value ?? "").trim();
  if (!v) return false;
  if (item.type === "TRUE_FALSE_GROUP") return !v.includes("-") && v.length === (item.statements ?? []).length;
  if (item.type === "TAP_COUNT") return Number(v) > 0;
  return true;
}

export const isBlank = (value: string | null | undefined) => !value || !value.trim() || /^-*$/.test(value.trim());

// ---------------------------------------------------------------- result wording

export type Outcome = "right" | "wrong" | "partial" | "blank";

export interface Shown {
  outcome: Outcome;
  points: number;
  max: number;
  /** TRUE_FALSE_GROUP: statements right out of all */
  tally: { right: number; total: number } | null;
}

/**
 * What the feedback line says for one answered item, by type. Choice, count and short answer are right or wrong;
 * a true/false group can be partly right (points per the scoring rules, "3/4 ý đúng").
 */
export function shown(item: Pick<PItem, "type">, r: PResult | null | undefined): Shown {
  const max = r?.max_points ?? 1;
  const points = r?.points ?? (r?.correct ? max : 0);
  if (!r || r.correct === null || r.correct === undefined && r.points === undefined) return { outcome: "blank", points: 0, max, tally: null };
  const sr = r.statement_results;
  const tally = item.type === "TRUE_FALSE_GROUP" && sr ? { right: sr.filter((x) => x.correct).length, total: sr.length } : null;
  if (r.correct === true) return { outcome: "right", points, max, tally };
  if (tally && tally.right > 0) return { outcome: "partial", points, max, tally };
  return { outcome: "wrong", points, max, tally };
}

/** "0,25 / 1" with the language's decimal mark; whole numbers stay whole. */
export function fmtNum(n: number, lang: string): string {
  const s = Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100);
  return lang === "en" ? s : s.replace(".", ",");
}

/** Score out of 10 for a mock, "7,25" in Vietnamese. */
export const fmtScore10 = (n: number, lang: string) => fmtNum(n, lang);

/** One sentence: the red pen explains the slip in a line (the first sentence, or the whole text when it is short). */
export function firstSentence(text: string | null | undefined): string {
  const s = (text ?? "").trim().replace(/\s+/g, " ");
  if (!s) return "";
  const m = /^.*?[.!?…](?=\s+[A-ZÀ-Ỹ0-9$]|$)/u.exec(s);
  const first = m ? m[0] : s;
  return first.length > 220 ? first.slice(0, 217).trimEnd() + "…" : first;
}

export function wrongStatements(r: PResult | null | undefined): StatementResult[] {
  return (r?.statement_results ?? []).filter((x) => !x.correct);
}

// ---------------------------------------------------------------- mock clock

export function clockText(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${String(m).padStart(2, "0")}:${ss}`;
}

/** Seconds left from the server's deadline (the server clock is the truth; `skewMs` = server minus client). */
export function remainingFromDeadline(deadline: string | null | undefined, nowMs: number, skewMs = 0): number | null {
  if (!deadline) return null;
  const t = Date.parse(deadline);
  if (!Number.isFinite(t)) return null;
  return Math.max(0, Math.ceil((t - nowMs - skewMs) / 1000));
}

/** First load of a session: seconds left. `remaining_sec` wins over the deadline (it is computed by the server). */
export function initialRemaining(s: PSession, nowMs: number): number | null {
  if (s.kind === "practice") return null;
  if (typeof s.remaining_sec === "number") return Math.max(0, s.remaining_sec);
  return remainingFromDeadline(s.deadline, nowMs);
}

/** The last minute is shown in the warning colour. */
export const isLow = (remaining: number | null) => remaining !== null && remaining <= 60;

// ---------------------------------------------------------------- session state

export const answerOf = (st: PAnswerState | undefined): string => (st?.answer ?? st?.draft ?? "") || "";

/** Where a reopened session continues: practice at the first item not answered yet, a mock where the learner left. */
export function resumePosition(s: PSession): number {
  const n = s.items.length;
  if (!n) return 0;
  if (s.kind === "practice") {
    const open = s.items.findIndex((it) => !s.answers[String(it.position)]?.checked);
    return open >= 0 ? open : n - 1;
  }
  return Math.min(Math.max(0, s.position ?? 0), n - 1);
}

/** Mock, before handing in: how many items are left empty or flagged. */
export function handInStats(s: PSession, answers: Record<number, string>, flags: Record<number, boolean>) {
  let blank = 0;
  let flagged = 0;
  for (const it of s.items) {
    if (isBlank(answers[it.position])) blank += 1;
    if (flags[it.position]) flagged += 1;
  }
  return { total: s.items.length, blank, flagged, answered: s.items.length - blank };
}

export const isOpen = (s: Pick<PSession, "status">) => !s.status || s.status === "active";

/** Practice home: a session of the kind "practice" with unanswered items is worth offering again. */
export function unfinished(s: PSession | null | undefined): s is PSession {
  if (!s || !isOpen(s)) return false;
  if (s.kind === "mock" && remainingFromDeadline(s.deadline, Date.now()) === 0) return false;
  return s.items.length > 0;
}

export function answeredCount(s: PSession): number {
  return Object.values(s.answers).filter((a) => a.checked || (s.kind !== "practice" && !isBlank(a.draft ?? a.answer))).length;
}
