import type { QuizItem } from "../api/course";

/** What the learner gave for one item, by type. */
export type Answer =
  | { kind: "choice"; id: string } //                      SINGLE_CHOICE, PICTURE_CHOICE
  | { kind: "tf"; values: Record<string, boolean> } //     TRUE_FALSE_GROUP
  | { kind: "text"; value: string } //                     SHORT_ANSWER
  | { kind: "count"; value: number }; //                   TAP_COUNT

export interface Verdict {
  correct: boolean;
  /** TRUE_FALSE_GROUP: ids of the statements answered wrong or left blank. */
  wrong?: string[];
  /** choice types: the option that should light up green. */
  correctOptionId?: string;
}

/** "0,5" and "0.5" are the same number; spaces and thousands dots are ignored: "1 000" -> 1000. */
export function parseNumber(s: string): number | null {
  const t = s.trim().toLowerCase().replace(/\s+/g, "").replace(/,/g, ".").replace(/×10\^?/g, "e").replace(/·10\^/g, "e").replace(/\*10\^/g, "e");
  if (!/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

/**
 * SHORT_ANSWER: matches one of `accepted` as text (case and spacing ignored) or, when both sides are numbers,
 * numerically. `tolerance` is relative (0.01 = within 1%); against an accepted value of 0 it is absolute.
 */
export function checkShortAnswer(value: string, accepted: string[], tolerance?: number): boolean {
  const v = norm(value);
  if (!v) return false;
  const vn = parseNumber(v);
  return accepted.some((a) => {
    if (norm(a) === v) return true;
    const an = parseNumber(a);
    if (vn === null || an === null) return false;
    if (vn === an) return true;
    if (!tolerance) return false;
    return Math.abs(vn - an) <= tolerance * (an === 0 ? 1 : Math.abs(an));
  });
}

export function checkAnswer(item: QuizItem, answer: Answer): Verdict {
  const key = item.answer_key;
  switch (item.type) {
    case "SINGLE_CHOICE":
    case "PICTURE_CHOICE": {
      const right = String(key.correct_option_id);
      return { correct: answer.kind === "choice" && answer.id === right, correctOptionId: right };
    }
    case "TRUE_FALSE_GROUP": {
      const expected = (key.statements ?? {}) as Record<string, boolean>;
      const given = answer.kind === "tf" ? answer.values : {};
      const wrong = Object.keys(expected).filter((id) => given[id] !== expected[id]);
      return { correct: wrong.length === 0, wrong };
    }
    case "SHORT_ANSWER": {
      const accepted = ((key.accepted ?? []) as unknown[]).map(String);
      const tol = typeof key.tolerance === "number" ? key.tolerance : undefined;
      return { correct: answer.kind === "text" && checkShortAnswer(answer.value, accepted, tol) };
    }
    case "TAP_COUNT":
      return { correct: answer.kind === "count" && answer.value === key.count };
  }
}

/** Can the learner submit yet? (TRUE_FALSE_GROUP needs every statement answered, SHORT_ANSWER some text, TAP_COUNT a tap.) */
export function canSubmit(item: QuizItem, answer: Answer | null): boolean {
  if (!answer) return false;
  if (answer.kind === "tf") return item.statements.every((s) => s.id in answer.values);
  if (answer.kind === "text") return answer.value.trim().length > 0;
  if (answer.kind === "count") return answer.value > 0;
  return true;
}
