import { API_BASE } from "./http";
import { ResearchError } from "./research-error";
import { SseParser, type SseMessage } from "./ask";
import { mockResearchApi, mockPaperAsk } from "./mock-research";
import type {
  AddPaperRequest,
  AgendaInput,
  ActionItemPatch,
  AskInput,
  Experiment,
  ExperimentInput,
  ExperimentList,
  ExperimentPatch,
  JobStarted,
  Meeting,
  MeetingInput,
  Milestone,
  MilestoneInput,
  MilestonePatch,
  PaperAskEvent,
  PaperDetail,
  PaperFeedback,
  PaperNote,
  PaperQA,
  ReadingEntry,
  ReadingList,
  ReadStatus,
  RelatedPapers,
  ResearchJob,
  ResearchOverview,
  ResearchProfile,
  ResearchProfileInput,
  ReviewRequest,
  SearchParams,
  SearchResponse,
  SourceKeysStatus,
  SourceName,
  SuggestionList,
} from "./research-types";

export * from "./research-types";

export { ResearchError };

/** Nghiên cứu (CONTRACTS.md section 15). Real HTTP and the mock implement the same object. */
export interface ResearchApi {
  overview(token: string): Promise<ResearchOverview>;
  getProfile(token: string): Promise<ResearchProfile>;
  putProfile(token: string, body: ResearchProfileInput): Promise<ResearchProfile>;
  sourceKeys(token: string): Promise<SourceKeysStatus>;
  putSourceKey(token: string, source: SourceName, key: string): Promise<SourceKeysStatus>;
  deleteSourceKey(token: string, source: SourceName): Promise<SourceKeysStatus>;
  search(token: string, p: SearchParams): Promise<SearchResponse>;
  related(token: string, paperId: string): Promise<RelatedPapers>;
  startReview(token: string, body: ReviewRequest): Promise<JobStarted>;
  getJob(token: string, id: string): Promise<ResearchJob>;
  startDiscovery(token: string): Promise<JobStarted>;
  suggestions(token: string): Promise<SuggestionList>;
  acceptSuggestion(token: string, id: string): Promise<ReadingEntry>;
  dismissSuggestion(token: string, id: string): Promise<void>;
  readingList(token: string): Promise<ReadingList>;
  addPaper(token: string, body: AddPaperRequest): Promise<ReadingEntry>;
  removePaper(token: string, id: string): Promise<void>;
  setStatus(token: string, id: string, status: ReadStatus): Promise<ReadingEntry>;
  paper(token: string, id: string): Promise<PaperDetail>;
  putSummary(token: string, id: string, text: string): Promise<PaperNote>;
  feedback(token: string, id: string): Promise<PaperFeedback>;
  qa(token: string, id: string): Promise<PaperQA[]>;
  experiments(token: string, opts?: { limit?: number; before?: string }): Promise<ExperimentList>;
  createExperiment(token: string, body: ExperimentInput): Promise<Experiment>;
  patchExperiment(token: string, id: string, body: ExperimentPatch): Promise<Experiment>;
  upload(token: string, file: Blob, name?: string): Promise<{ path: string; mime_type: string }>;
  meetings(token: string, status?: "scheduled" | "done" | "all"): Promise<Meeting[]>;
  nextMeeting(token: string): Promise<Meeting | null>;
  createMeeting(token: string, body: MeetingInput): Promise<Meeting>;
  putAgenda(token: string, id: string, body: AgendaInput): Promise<Meeting>;
  draftAgenda(token: string, id: string): Promise<Meeting>;
  putNotes(token: string, id: string, notes_md: string): Promise<Meeting>;
  patchAction(token: string, meetingId: string, actionId: string, body: ActionItemPatch): Promise<Meeting>;
  deadlines(token: string, includeDone?: boolean): Promise<Milestone[]>;
  createDeadline(token: string, body: MilestoneInput): Promise<Milestone>;
  patchDeadline(token: string, id: string, body: MilestonePatch): Promise<Milestone>;
  deleteDeadline(token: string, id: string): Promise<void>;
}

const enc = encodeURIComponent;

async function failure(res: Response): Promise<ResearchError> {
  let code = res.status === 401 ? "unauthorized" : "unknown";
  const extra: { job_id?: string; retry_after?: number } = {};
  try {
    const j = (await res.json()) as { error?: string; job_id?: string; retry_after?: number };
    if (j.error) code = j.error;
    if (j.job_id) extra.job_id = j.job_id;
    if (typeof j.retry_after === "number") extra.retry_after = j.retry_after;
  } catch {
    /* no JSON body */
  }
  return new ResearchError(res.status, code, extra);
}

async function call<T>(method: string, path: string, token: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + "/research" + path, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ResearchError(0, "network");
  }
  if (!res.ok) throw await failure(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const q = (o: Record<string, string | number | boolean | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== "" && v !== false) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const httpResearchApi: ResearchApi = {
  overview: (t) => call("GET", "", t),
  getProfile: (t) => call("GET", "/profile", t),
  putProfile: (t, b) => call("PUT", "/profile", t, b),
  sourceKeys: (t) => call("GET", "/source-keys", t),
  putSourceKey: (t, s, key) => call("PUT", `/source-keys/${s}`, t, { key }),
  deleteSourceKey: (t, s) => call("DELETE", `/source-keys/${s}`, t),
  search: (t, p) => call("GET", "/search" + q({ q: p.q, year_min: p.year_min, pdf: p.pdf, page: p.page, depth: p.depth }), t),
  related: (t, id) => call("GET", `/papers/${enc(id)}/related`, t),
  startReview: (t, b) => call("POST", "/review", t, b),
  getJob: (t, id) => call("GET", `/jobs/${enc(id)}`, t),
  startDiscovery: (t) => call("POST", "/discovery", t),
  suggestions: (t) => call("GET", "/suggestions", t),
  acceptSuggestion: (t, id) => call("POST", `/suggestions/${enc(id)}/accept`, t),
  dismissSuggestion: (t, id) => call("POST", `/suggestions/${enc(id)}/dismiss`, t),
  readingList: (t) => call("GET", "/reading-list", t),
  addPaper: (t, b) => call("POST", "/reading-list", t, b),
  removePaper: (t, id) => call("DELETE", `/reading-list/${enc(id)}`, t),
  setStatus: (t, id, status) => call("PUT", `/papers/${enc(id)}/status`, t, { status }),
  paper: (t, id) => call("GET", `/papers/${enc(id)}`, t),
  putSummary: (t, id, text) => call("PUT", `/papers/${enc(id)}/summary`, t, { text }),
  feedback: (t, id) => call("POST", `/papers/${enc(id)}/feedback`, t),
  qa: (t, id) => call("GET", `/papers/${enc(id)}/qa`, t),
  experiments: (t, o) => call("GET", "/experiments" + q({ limit: o?.limit, before: o?.before }), t),
  createExperiment: (t, b) => call("POST", "/experiments", t, b),
  patchExperiment: (t, id, b) => call("PATCH", `/experiments/${enc(id)}`, t, b),
  async upload(t, file, name = "file") {
    const f = new FormData();
    f.append("file", file, name);
    let res: Response;
    try {
      res = await fetch(API_BASE + "/uploads", { method: "POST", headers: { Authorization: `Bearer ${t}` }, body: f });
    } catch {
      throw new ResearchError(0, "network");
    }
    if (!res.ok) throw await failure(res);
    return (await res.json()) as { path: string; mime_type: string };
  },
  meetings: (t, status) => call("GET", "/meetings" + q({ status }), t),
  nextMeeting: (t) => call("GET", "/meetings/next", t),
  createMeeting: (t, b) => call("POST", "/meetings", t, b),
  putAgenda: (t, id, b) => call("PUT", `/meetings/${enc(id)}/agenda`, t, b),
  draftAgenda: (t, id) => call("POST", `/meetings/${enc(id)}/agenda/draft`, t),
  putNotes: (t, id, notes_md) => call("PUT", `/meetings/${enc(id)}/notes`, t, { notes_md }),
  patchAction: (t, mid, aid, b) => call("PATCH", `/meetings/${enc(mid)}/actions/${enc(aid)}`, t, b),
  deadlines: (t, done) => call("GET", "/deadlines" + q({ include_done: done }), t),
  createDeadline: (t, b) => call("POST", "/deadlines", t, b),
  patchDeadline: (t, id, b) => call("PATCH", `/deadlines/${enc(id)}`, t, b),
  deleteDeadline: (t, id) => call("DELETE", `/deadlines/${enc(id)}`, t),
};

const isMock = () => import.meta.env.VITE_API_MOCK === "1";
export const researchApi: ResearchApi = isMock() ? mockResearchApi : httpResearchApi;

// ---------------------------------------------------------------- paper Q&A (SSE)
const KNOWN = new Set(["status", "qa", "error", "done"]);
export function toPaperAskEvent(m: SseMessage): PaperAskEvent | null {
  if (!KNOWN.has(m.event)) return null;
  try {
    return { event: m.event, data: JSON.parse(m.data) } as PaperAskEvent;
  } catch {
    return null;
  }
}

export type PaperAskBody = AskInput | { audio: Blob; lang?: "vi" | "en" };

/**
 * POST /research/papers/{id}/ask and call `onEvent` for each event as it arrives. Resolves when the stream ends.
 * Rejects with `ResearchError` (code "network" when the server cannot be reached) or an AbortError when `signal` fires.
 */
export async function streamPaperAsk(token: string, paperId: string, input: PaperAskBody, onEvent: (e: PaperAskEvent) => void, signal?: AbortSignal): Promise<void> {
  if (isMock()) return mockPaperAsk(paperId, input, onEvent, signal);
  let body: BodyInit;
  const headers: Record<string, string> = { Authorization: `Bearer ${token}`, Accept: "text/event-stream" };
  if ("audio" in input) {
    const f = new FormData();
    f.append("audio", input.audio, input.audio.type.includes("mp4") ? "voice.m4a" : "voice.webm");
    if (input.lang) f.append("lang", input.lang);
    body = f;
  } else {
    body = JSON.stringify(input);
    headers["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/research/papers/${enc(paperId)}/ask`, { method: "POST", headers, body, signal });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ResearchError(0, "network");
  }
  if (!res.ok) throw await failure(res);
  if (!res.body) throw new ResearchError(res.status, "no_stream");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  const parser = new SseParser();
  const emit = (msgs: SseMessage[]) => {
    for (const m of msgs) {
      const ev = toPaperAskEvent(m);
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
    throw new ResearchError(0, "network");
  }
}

/** How often the app asks a review or discovery job how far it is (CONTRACTS.md 15.4); tests shorten it. */
export const researchPoll = { ms: 1500 };
