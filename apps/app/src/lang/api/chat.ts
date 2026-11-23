import { API_BASE } from "../../api/http";
import { AskError, SseParser, askBody, toAskEvent, type AskEvent, type AskRequest, type SseMessage } from "../../api/ask";
import { mockAskStream } from "../../api/mock-ask";
import type { Lang } from "../../api/types";
import { chickenName, subjectOf } from "../subjects";
import type { ChatAction } from "./types";

/**
 * POST /chat/{chicken} (CONTRACTS-LANGGA.md "Chat with a chicken"): a Server-Sent Events stream with
 * thread, status, transcript, delta (streamed text), message, actions, error, done. A photo of an exercise streams the
 * Ask solve events as well (intent, solution, choices, last_step, similar ...).
 */
export type ChatEvent =
  | { event: "delta"; data: { text: string } }
  | { event: "actions"; data: { items: ChatAction[] } }
  | AskEvent;

export interface ChatRequest {
  text?: string;
  thread_id?: string | null;
  lang: Lang;
  image?: Blob;
  audio?: Blob;
  /** a follow-up button of a solution (choose / last_step / simpler / similar) */
  action?: AskRequest["action"];
  problem_id?: string;
}

/** SSE message to a typed chat event; null for an unknown name or bad JSON. */
export function toChatEvent(m: SseMessage): ChatEvent | null {
  if (m.event === "delta" || m.event === "actions") {
    try {
      const data = JSON.parse(m.data) as unknown;
      if (m.event === "delta") return { event: "delta", data: { text: typeof data === "string" ? data : String((data as { text?: string }).text ?? "") } };
      const d = data as { items?: ChatAction[]; actions?: ChatAction[] };
      const items = Array.isArray(data) ? data : (d.items ?? d.actions ?? []); // the gateway sends `actions`
      return { event: "actions", data: { items: items as ChatAction[] } };
    } catch {
      return null;
    }
  }
  return toAskEvent(m);
}

const errorCode = async (res: Response): Promise<string> => {
  try {
    const j = (await res.json()) as { error?: string };
    return j.error ?? "unknown";
  } catch {
    return "unknown";
  }
};

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((res, rej) => {
    const t = setTimeout(res, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      rej(new DOMException("aborted", "AbortError"));
    });
  });

/** What the mock chicken says to plain talk (and a photo goes through the mock Ask solver). */
async function mockChat(chicken: string, req: ChatRequest, onEvent: (e: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  onEvent({ event: "thread", data: { thread_id: req.thread_id || "mock-chat" } });
  if (req.image || req.action) {
    await mockAskStream({ ...req, lang: req.lang }, (e) => onEvent(e), signal);
    return;
  }
  let text = req.text ?? "";
  if (req.audio) {
    text = req.lang === "en" ? "How do I add two fractions?" : "Cộng hai phân số thế nào?";
    onEvent({ event: "transcript", data: { text } });
  }
  onEvent({ event: "status", data: { stage: "solving" } });
  await wait(60, signal);
  const sub = subjectOf(chicken);
  const label = req.lang === "en" ? (sub?.en ?? chicken) : (sub?.vi ?? chicken);
  const reply = req.lang === "en" ? `${chickenName(chicken, "en")} here! You said: "${text}". Let's take it one step at a time. Want a few ${label} questions?` : `${chickenName(chicken, "vi")} đây! Em hỏi: "${text}". Mình đi từng bước nhé. Làm vài câu ${label} cho chắc không?`;
  for (const part of reply.match(/.{1,18}/g) ?? []) {
    onEvent({ event: "delta", data: { text: part } });
    await wait(10, signal);
  }
  onEvent({ event: "actions", data: { items: [{ label_vi: "Luyện tập", label_en: "Practice", deep_link: "/luyen-tap" }] } });
}

/**
 * Talk to a chicken. Calls `onEvent` for every event as it arrives and resolves when the stream ends. Rejects with
 * `AskError` (HTTP status; code "network" when the server cannot be reached) or an AbortError when `signal` fires.
 */
export async function streamChat(token: string, chicken: string, req: ChatRequest, onEvent: (e: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  if (import.meta.env.VITE_API_MOCK === "1") return mockChat(chicken, req, onEvent, signal);
  const { body, headers } = askBody(req as AskRequest);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat/${encodeURIComponent(chicken)}`, { method: "POST", headers: { ...headers, Authorization: `Bearer ${token}`, Accept: "text/event-stream" }, body, signal });
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
      const ev = toChatEvent(m);
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
