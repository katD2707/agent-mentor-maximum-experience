import { API_BASE } from "./http";
import { withToken, getMediaToken } from "./media";
import type { DiagramSpec } from "../lib/diagram/types";

/** Luyện tập (CONTRACTS.md section 10, 10.12). The server holds the keys: items never carry an answer. */

export type PItemType = "SINGLE_CHOICE" | "PICTURE_CHOICE" | "TAP_COUNT" | "TRUE_FALSE_GROUP" | "SHORT_ANSWER";
export type PKind = "practice" | "mock" | "diagnostic";

export interface PMedia {
  path: string;
  mime: string;
  sha256: string;
  /** `/api/courses/<id>/versions/<v>/assets/<path>`, needs `?t=<media token>` (see `practiceMediaUrl`) */
  url: string;
}

export interface PAsset {
  id: string;
  type: "diagram" | "table" | "image";
  alt_text?: string;
  caption?: string | null;
  diagram?: DiagramSpec | null;
  table?: { headers: string[]; rows: string[][] } | null;
}

export interface PItem {
  position: number;
  id: string;
  type: PItemType;
  stem: string;
  stem_audio?: PMedia | null;
  stem_image?: PMedia | null;
  options?: { id: string; text?: string | null; image?: PMedia | null; audio?: PMedia | null }[];
  statements?: { id: string; text: string; truth?: boolean; explanation?: string | null }[];
  short_answer?: { max_chars?: number | null; unit?: string | null; decimals?: number | null } | null;
  tap?: { image?: PMedia | null; total: number } | null;
  assets?: PAsset[];
  source?: { course_id: string; version: number; course_title: string; lesson_id: string; lesson_title: string; item_id: string } | null;
  topic: string;
  topic_title: string;
  level?: number;
  estimated_seconds?: number;
}

export interface StatementResult {
  id: string;
  given?: boolean | null;
  truth?: boolean;
  correct: boolean;
  explanation?: string | null;
}

export interface PResult {
  saved?: boolean;
  /** null = left blank */
  correct?: boolean | null;
  points?: number;
  max_points?: number;
  correct_answer?: string;
  option_feedback?: Record<string, string> | string | null;
  statement_results?: StatementResult[] | null;
}

export interface PAnswerState {
  answer?: string | null;
  draft?: string | null;
  flagged?: boolean;
  checked?: boolean;
  correct?: boolean | null;
  hint?: string | null;
  hints_seen?: number;
  revealed?: boolean;
  result?: PResult | null;
}

export interface PSession {
  id: string;
  kind: PKind;
  subject: string;
  profile_id?: string | null;
  status?: "active" | "finished" | "expired" | "abandoned";
  started_at: string;
  deadline?: string | null;
  remaining_sec?: number | null;
  minutes?: number;
  position: number;
  items: PItem[];
  answers: Record<string, PAnswerState>;
  parts?: { label: string; positions: number[]; points_each: number }[] | null;
  disclaimer?: string | null;
}

export interface Line {
  line_vi: string;
  line_en: string;
}

export interface PReport {
  session: { id: string; kind: PKind; subject: string; status?: string };
  correct: number;
  total: number;
  answered: number;
  score_10?: number | null;
  minutes: number;
  hints: number;
  per_topic: { topic: string; title: string; right: number; total: number; label: string }[];
  per_part?: { part?: number; label: string; total?: number; answered?: number; correct?: number; points: number; max_points: number }[] | null;
  recommendations?: unknown[];
  disclaimer?: string | null;
  takeaway?: Line | null;
  redo?: Line | null;
}

export interface PReviewItem extends PItem {
  answer?: string | null;
  correct?: boolean | null;
  points?: number | null;
  max_points?: number | null;
  hints_seen?: number;
  flagged?: boolean;
  correct_answer?: string;
  explanation?: string | null;
  tip?: string | null;
  hint?: string | null;
  option_feedback?: Record<string, string> | null;
  statement_results?: StatementResult[] | null;
}

export interface PHome {
  quick: { count: number; minutes: number; from: { course_id?: string; subject?: string; label: string; n: number }[]; seed: string | number; reason?: string | null };
  mocks: { profile_id: string; title: string; subject: string; minutes: number; items: number; last_score: number | null }[];
  by_course: { course_id: string; title: string; cover_sha256?: string | null; lessons_range: string; lessons_from: number; lessons_to: number; items: number }[];
}

export type StartSource = "quick" | `course:${string}` | `mock:${string}`;

/** A failed practice call: the gateway's `{detail, code | error, ...}` body is kept. */
export class PracticeError extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string | null = null,
    public body: Record<string, unknown> = {},
  ) {
    super(code);
    this.name = "PracticeError";
  }
}

export interface PracticeApi {
  home(token: string, seed?: string): Promise<PHome>;
  start(token: string, body: { source: StartSource; seed?: string | number }): Promise<PSession>;
  active(token: string): Promise<PSession | null>;
  get(token: string, id: string): Promise<PSession>;
  answer(token: string, id: string, body: { position: number; answer: string; time_spent_sec: number }): Promise<PResult>;
  hint(token: string, id: string, position: number): Promise<{ hint: string }>;
  reveal(token: string, id: string, position: number): Promise<{ explanation: string; tip?: string | null }>;
  flag(token: string, id: string, position: number, flagged: boolean): Promise<{ ok: boolean }>;
  tick(token: string, id: string, position: number, elapsed: number): Promise<{ remaining_sec?: number | null; expired?: boolean }>;
  finish(token: string, id: string): Promise<PReport>;
  review(token: string, id: string): Promise<{ items: PReviewItem[] } | PReviewItem[]>;
}

async function req<T>(token: string, method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + "/practice" + path, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new PracticeError(0, "network");
  }
  if (!res.ok) {
    let j: Record<string, unknown> = {};
    try {
      j = (await res.json()) as Record<string, unknown>;
    } catch {
      /* no body */
    }
    const code = typeof j.code === "string" ? j.code : typeof j.error === "string" ? j.error : res.status === 401 ? "unauthorized" : "unknown";
    throw new PracticeError(res.status, code, typeof j.detail === "string" ? j.detail : null, j);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const httpPractice: PracticeApi = {
  home: (t, seed) => req(t, "GET", "/home" + (seed ? `?seed=${enc(seed)}` : "")),
  start: (t, body) => req(t, "POST", "/sessions", body),
  active: (t) => req(t, "GET", "/sessions/active"),
  get: (t, i) => req(t, "GET", `/sessions/${enc(i)}`),
  answer: (t, i, b) => req(t, "POST", `/sessions/${enc(i)}/answer`, b),
  hint: (t, i, position) => req(t, "POST", `/sessions/${enc(i)}/hint`, { position }),
  reveal: (t, i, position) => req(t, "POST", `/sessions/${enc(i)}/reveal`, { position }),
  flag: (t, i, position, flagged) => req(t, "POST", `/sessions/${enc(i)}/flag`, { position, flagged }),
  tick: (t, i, position, elapsed_sec) => req(t, "POST", `/sessions/${enc(i)}/tick`, { position, elapsed_sec }),
  finish: (t, i) => req(t, "POST", `/sessions/${enc(i)}/finish`),
  review: (t, i) => req(t, "GET", `/sessions/${enc(i)}/review`),
};

/** The API the screens use; the mock build and tests swap it. */
let current: PracticeApi = httpPractice;
export const practice: PracticeApi = new Proxy({} as PracticeApi, { get: (_t, k) => current[k as keyof PracticeApi] });
export const setPracticeApi = (a: PracticeApi) => {
  current = a;
};

/**
 * `ClientItem` media `url` is a server path (`/api/courses/...`); an <img> needs the media token on it.
 * The origin comes from API_BASE so a desktop app pointing at another host works.
 */
export function practiceMediaUrl(token: string, m: PMedia | null | undefined): string {
  if (!m?.url) return "";
  if (/^(data|blob):/.test(m.url)) return m.url;
  if (import.meta.env.VITE_API_MOCK === "1") return /^https?:/.test(m.url) ? m.url : "";
  let abs: string;
  try {
    abs = new URL(m.url, API_BASE).toString();
  } catch {
    return "";
  }
  return withToken(abs, getMediaToken() ?? token);
}
