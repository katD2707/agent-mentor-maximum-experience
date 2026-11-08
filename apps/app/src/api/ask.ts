import { API_BASE } from "./http";
import type { Lang } from "./types";
import type { Media, TreeChapter } from "./course";
import { mockAskStream } from "./mock-ask";

/** Hỏi đáp (CONTRACTS.md section 13): POST /ask answers as a Server-Sent Events stream, POST /guide is Mực's chat. */

export interface AskCard {
  course_id: string;
  title: string;
  cover_sha256: string;
  description_short: string;
  language: Lang;
  lessons_count: number;
  est_minutes: number;
  /** chapters, as in GET /courses/{id} */
  tree: TreeChapter[] | { tree?: TreeChapter[] } | null;
  age_band?: string;
  score?: number | null;
  enrolled: boolean;
  /** "coming_soon": a placeholder that cannot be added or started; absent means live */
  status?: "live" | "coming_soon";
  first_lesson: { lesson_id: string; title: string } | null;
  media?: Media[];
}

export interface AskProblem {
  id: string;
  label: string;
  text: string;
}
export interface AskStep {
  title: string;
  md: string;
}
export type AskStage = "listening" | "reading" | "solving";
export type PhotoReason = "blurry" | "too_dark" | "low_contrast" | "missing_area" | "low_resolution" | "skewed" | "blank_page";
export type MessageKind = "retake" | "no_speech" | "no_last_step" | "bad_image" | "no_problem" | "empty";

/** One SSE event of POST /ask, parsed. */
export type AskEvent =
  | { event: "thread"; data: { thread_id: string } }
  | { event: "status"; data: { stage: AskStage } }
  | { event: "transcript"; data: { text: string } }
  | { event: "intent"; data: { intent: "learn" | "solve" | "other" } }
  | { event: "answer"; data: { text: string } }
  | { event: "courses"; data: { items: AskCard[]; suggested_all_ages?: boolean; start_with?: { course_id: string; lesson_id?: string; title?: string } | null } }
  | { event: "quality"; data: { ok: boolean; reasons?: PhotoReason[] } }
  | { event: "message"; data: { kind: MessageKind; text: string; where?: string; reasons?: PhotoReason[]; tips?: string[]; offer_readable?: boolean } }
  | { event: "choices"; data: { problems: AskProblem[]; reason: "multiple" | "partial" } }
  | { event: "problem"; data: AskProblem }
  | { event: "solution"; data: { problem_id: string; problem_md?: string; steps: AskStep[]; last_step_withheld: boolean; tip?: string | null } }
  | { event: "last_step"; data: { problem_id?: string; step: AskStep } }
  | { event: "similar"; data: { items: { problem_md: string; answer_md: string }[] } }
  | { event: "error"; data: { code: "model_unavailable" | "internal" | string; message?: string } }
  | { event: "done"; data: { thread_id?: string } };

export type AskAction = "choose" | "last_step" | "simpler" | "similar";

export interface AskRequest {
  text?: string;
  thread_id?: string | null;
  lang: Lang;
  action?: AskAction;
  problem_id?: string;
  /** a jpeg/png/webp/heic Blob, sent as multipart `image` */
  image?: Blob;
  /** the microphone recording, sent as multipart `audio` */
  audio?: Blob;
}

export class AskError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
    this.name = "AskError";
  }
}

// ---------------------------------------------------------------- SSE parsing

export interface SseMessage {
  event: string;
  data: string;
}

/**
 * Incremental parser for `text/event-stream`. Feed it text as it arrives (chunks may end anywhere, even between the
 * "\r" and "\n" of a line break) and it returns the messages completed by that chunk.
 */
export class SseParser {
  private buf = "";
  private event = "";
  private data: string[] = [];

  push(chunk: string): SseMessage[] {
    this.buf += chunk;
    const out: SseMessage[] = [];
    for (;;) {
      const m = /\r\n|\n|\r(?!$)/.exec(this.buf);
      if (!m) break;
      const line = this.buf.slice(0, m.index);
      this.buf = this.buf.slice(m.index + m[0].length);
      const msg = this.line(line);
      if (msg) out.push(msg);
    }
    return out;
  }

  /** The stream ended: a last line without its line break, and an event not closed by a blank line, still count. */
  end(): SseMessage[] {
    const out: SseMessage[] = [];
    if (this.buf) {
      const msg = this.line(this.buf.replace(/\r$/, ""));
      this.buf = "";
      if (msg) out.push(msg);
    }
    const last = this.line("");
    if (last) out.push(last);
    return out;
  }

  private line(line: string): SseMessage | null {
    if (line === "") {
      if (!this.data.length) {
        this.event = "";
        return null;
      }
      const msg = { event: this.event || "message", data: this.data.join("\n") };
      this.event = "";
      this.data = [];
      return msg;
    }
    if (line.startsWith(":")) return null;
    const i = line.indexOf(":");
    const field = i < 0 ? line : line.slice(0, i);
    let value = i < 0 ? "" : line.slice(i + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    return null;
  }
}

const KNOWN = new Set(["thread", "status", "transcript", "intent", "answer", "courses", "quality", "message", "choices", "problem", "solution", "last_step", "similar", "error", "done"]);

/** SSE message to a typed event; null for an unknown event name or data that is not JSON. */
export function toAskEvent(m: SseMessage): AskEvent | null {
  if (!KNOWN.has(m.event)) return null;
  try {
    return { event: m.event, data: JSON.parse(m.data) } as AskEvent;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- transport

const isMock = () => import.meta.env.VITE_API_MOCK === "1";

const audioName = (mime: string) => (mime.includes("ogg") ? "voice.ogg" : mime.includes("mp4") || mime.includes("aac") ? "voice.m4a" : mime.includes("wav") ? "voice.wav" : "voice.webm");

export function askBody(req: AskRequest): { body: BodyInit; headers: Record<string, string> } {
  const fields: Record<string, string | undefined> = {
    text: req.text || undefined,
    thread_id: req.thread_id || undefined,
    lang: req.lang,
    action: req.action,
    problem_id: req.problem_id,
  };
  if (req.image || req.audio) {
    const f = new FormData();
    for (const [k, v] of Object.entries(fields)) if (v !== undefined) f.append(k, v);
    if (req.image) f.append("image", req.image, "photo.jpg");
    if (req.audio) f.append("audio", req.audio, audioName(req.audio.type));
    return { body: f, headers: {} };
  }
  return { body: JSON.stringify(Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined))), headers: { "Content-Type": "application/json" } };
}

async function errorCode(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { error?: string; detail?: { error?: string } | string };
    return j.error ?? (typeof j.detail === "object" ? j.detail?.error : undefined) ?? "unknown";
  } catch {
    return "unknown";
  }
}

/**
 * POST /ask and call `onEvent` for every event as it arrives. Resolves when the stream ends; rejects with `AskError`
 * (HTTP status, code "network" when the server cannot be reached) or an AbortError when `signal` fires.
 */
export async function streamAsk(token: string, req: AskRequest, onEvent: (e: AskEvent) => void, signal?: AbortSignal): Promise<void> {
  if (isMock()) return mockAskStream(req, onEvent, signal);
  const { body, headers } = askBody(req);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ask`, { method: "POST", headers: { ...headers, Authorization: `Bearer ${token}`, Accept: "text/event-stream" }, body, signal });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new AskError(0, "network");
  }
  if (!res.ok) throw new AskError(res.status, await errorCode(res));
  if (!res.body) throw new AskError(res.status, "no_stream");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  const parser = new SseParser();
  const emit = (msgs: SseMessage[]) => {
    for (const m of msgs) {
      const ev = toAskEvent(m);
      if (ev) onEvent(ev);
    }
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      emit(parser.push(dec.decode(value, { stream: true })));
    }
    emit(parser.push(dec.decode()));
    emit(parser.end());
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new AskError(0, "network");
  }
}

/** POST /guide: Mực's answer about using the app, given the screen and the data-guide areas that are visible. */
export async function postGuide(token: string, body: { question: string; lang: Lang; screen?: string; visible_keys?: string[] }): Promise<string> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/guide`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(body) });
  } catch {
    throw new AskError(0, "network");
  }
  if (!res.ok) throw new AskError(res.status, await errorCode(res));
  const j = (await res.json()) as { answer?: string };
  if (!j.answer) throw new AskError(res.status, "empty");
  return j.answer;
}

