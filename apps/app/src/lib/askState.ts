import type { AskCard, AskEvent, AskProblem, AskStage, AskStep, MessageKind, PhotoReason } from "../api/ask";

/** State of one Hỏi đáp thread (kept for the session only; there is no history). */

export interface MeTurn {
  id: number;
  role: "me";
  text?: string;
  /** object URL of the photo that was sent */
  photo?: string;
  /** a recording was sent; `text` is filled by the `transcript` event */
  audio?: boolean;
  /** the photo that could not be read fully (red dashed frame in the thread) */
  badPhoto?: boolean;
}

export interface AiTurn {
  id: number;
  role: "ai";
  /** progress line while the server works ("Đang đọc đề…") */
  stage: AskStage | null;
  /** the stream is still open */
  open: boolean;
  answer?: string;
  courses?: { items: AskCard[]; suggestedAllAges: boolean; startWith: { course_id: string; lesson_id?: string; title?: string } | null };
  message?: { kind: MessageKind; text: string; where?: string; reasons?: PhotoReason[]; tips?: string[]; offerReadable?: boolean };
  choices?: { problems: AskProblem[]; reason: "multiple" | "partial" };
  problem?: AskProblem;
  solution?: { problemId: string; problemMd?: string; steps: AskStep[]; lastStepWithheld: boolean; tip?: string | null };
  lastStep?: AskStep;
  similar?: { problem_md: string; answer_md: string }[];
  /** no_last_step and other short notes that belong to the solution */
  note?: string;
  error?: { code: string; message?: string };
  cancelled?: boolean;
}

export type Turn = MeTurn | AiTurn;

export interface AskState {
  threadId: string | null;
  turns: Turn[];
  /** index of the AI turn that incoming events apply to; -1 when no request is running */
  target: number;
  nextId: number;
}

export const initialAsk: AskState = { threadId: null, turns: [], target: -1, nextId: 1 };

export type AskAct =
  /** a request starts: add what the learner sent and the empty answer (`inPlace`: events go to the latest solution, e.g. "Xem bước cuối") */
  | { type: "send"; me?: Omit<MeTurn, "id" | "role">; inPlace?: boolean }
  | { type: "event"; ev: AskEvent }
  /** the request failed before or during the stream (network, HTTP error) */
  | { type: "fail"; code: string }
  | { type: "cancel" }
  | { type: "forgetThread" }
  | { type: "reset" };

const patchAt = (turns: Turn[], i: number, p: Partial<AiTurn>): Turn[] => turns.map((t, k) => (k === i && t.role === "ai" ? { ...t, ...p } : t));

function lastIndex(turns: Turn[], pred: (t: Turn) => boolean): number {
  for (let i = turns.length - 1; i >= 0; i--) if (pred(turns[i])) return i;
  return -1;
}

export function askReducer(s: AskState, a: AskAct): AskState {
  switch (a.type) {
    case "reset":
      return initialAsk;
    case "forgetThread":
      return { ...s, threadId: null };
    case "send": {
      if (a.inPlace) {
        const i = lastIndex(s.turns, (t) => t.role === "ai" && !!t.solution);
        if (i >= 0) return { ...s, target: i, turns: patchAt(s.turns, i, { open: true, note: undefined, error: undefined, stage: null }) };
      }
      const turns: Turn[] = [...s.turns];
      let id = s.nextId;
      if (a.me) turns.push({ ...a.me, id: id++, role: "me" });
      turns.push({ id: id++, role: "ai", stage: null, open: true });
      return { ...s, turns, target: turns.length - 1, nextId: id };
    }
    case "cancel": {
      if (s.target < 0) return s;
      const t = s.turns[s.target];
      const empty = t.role === "ai" && !t.answer && !t.courses && !t.solution && !t.choices && !t.message && !t.similar;
      return { ...s, target: -1, turns: patchAt(s.turns, s.target, { open: false, stage: null, cancelled: empty }) };
    }
    case "fail": {
      if (s.target < 0) return s;
      return { ...s, target: -1, turns: patchAt(s.turns, s.target, { open: false, stage: null, error: { code: a.code } }) };
    }
    case "event":
      return onEvent(s, a.ev);
  }
}

function onEvent(s: AskState, ev: AskEvent): AskState {
  if (ev.event === "thread") return { ...s, threadId: ev.data.thread_id };
  const i = s.target;
  if (i < 0) return s;
  const set = (p: Partial<AiTurn>): AskState => ({ ...s, turns: patchAt(s.turns, i, p) });
  switch (ev.event) {
    case "status":
      return set({ stage: ev.data.stage });
    case "transcript": {
      const m = lastIndex(s.turns.slice(0, i), (t) => t.role === "me");
      return { ...s, turns: s.turns.map((t, k) => (k === m && t.role === "me" ? { ...t, text: ev.data.text } : t)) };
    }
    case "intent":
      return s;
    case "answer":
      return set({ answer: ev.data.text, stage: null });
    case "courses":
      return set({ courses: { items: ev.data.items ?? [], suggestedAllAges: !!ev.data.suggested_all_ages, startWith: ev.data.start_with ?? null }, stage: null });
    case "quality": {
      if (ev.data.ok) return s;
      // mark the photo the learner sent as only partly readable
      const m = lastIndex(s.turns.slice(0, i), (t) => t.role === "me");
      return { ...s, turns: s.turns.map((t, k) => (k === m && t.role === "me" && t.photo ? { ...t, badPhoto: true } : t)) };
    }
    case "message": {
      const d = ev.data;
      if (d.kind === "no_last_step") return set({ note: d.text, stage: null });
      return set({ message: { kind: d.kind, text: d.text, where: d.where, reasons: d.reasons, tips: d.tips, offerReadable: d.offer_readable }, stage: null });
    }
    case "choices":
      return set({ choices: { problems: ev.data.problems ?? [], reason: ev.data.reason }, stage: null });
    case "problem":
      return set({ problem: ev.data });
    case "solution":
      return set({
        solution: { problemId: ev.data.problem_id, problemMd: ev.data.problem_md, steps: ev.data.steps ?? [], lastStepWithheld: !!ev.data.last_step_withheld, tip: ev.data.tip },
        lastStep: undefined,
        similar: undefined,
        stage: null,
      });
    case "last_step":
      return set({ lastStep: ev.data.step, stage: null });
    case "similar":
      return set({ similar: ev.data.items ?? [], stage: null });
    case "error":
      return set({ error: { code: ev.data.code, message: ev.data.message }, stage: null });
    case "done":
      return { ...s, target: -1, turns: patchAt(s.turns, i, { open: false, stage: null }) };
    default:
      return s;
  }
}
