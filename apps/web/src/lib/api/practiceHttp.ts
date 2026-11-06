import type {
  AnswerResult,
  ItemReportRequest,
  PracticeApi,
  PracticeItemReport,
  PracticePreview,
  PracticeRecommendation,
  PracticeSubject,
  PreviewRequest,
  ProgressSkill,
  Report,
  ReviewItem,
  RevealResult,
  Session,
  SessionSummary,
  StartSessionRequest,
} from "../practice/types";

type Request = <T>(
  method: string,
  path: string,
  opts?: { query?: Record<string, string | number | undefined>; json?: unknown },
) => Promise<T>;

/** `/api/practice` (CONTRACTS 10.3) over the gateway's session cookie. */
export class HttpPractice implements PracticeApi {
  constructor(private readonly req: Request) {}

  subjects() {
    return this.req<PracticeSubject[]>("GET", "/practice/subjects");
  }
  preview(body: PreviewRequest) {
    return this.req<PracticePreview>("POST", "/practice/preview", { json: body });
  }
  start(body: StartSessionRequest) {
    return this.req<Session>("POST", "/practice/sessions", { json: body });
  }
  skipDiagnostic(subject: string) {
    return this.req<{ ok: boolean }>("POST", "/practice/diagnostic/skip", { json: { subject } });
  }
  active(subject?: string) {
    return this.req<Session | null>("GET", "/practice/sessions/active", { query: { subject } });
  }
  get(id: string) {
    return this.req<Session>("GET", `/practice/sessions/${encodeURIComponent(id)}`);
  }
  answer(id: string, body: { position: number; answer: string | null; time_spent_sec: number }) {
    return this.req<AnswerResult>("POST", `/practice/sessions/${encodeURIComponent(id)}/answer`, { json: body });
  }
  hint(id: string, position: number) {
    return this.req<{ hint: string }>("POST", `/practice/sessions/${encodeURIComponent(id)}/hint`, { json: { position } });
  }
  reveal(id: string, position: number) {
    return this.req<RevealResult>("POST", `/practice/sessions/${encodeURIComponent(id)}/reveal`, { json: { position } });
  }
  flag(id: string, position: number, flagged: boolean) {
    return this.req<{ ok: boolean }>("POST", `/practice/sessions/${encodeURIComponent(id)}/flag`, { json: { position, flagged } });
  }
  tick(id: string, position: number, elapsedSec: number) {
    return this.req<{ remaining_sec?: number | null }>("POST", `/practice/sessions/${encodeURIComponent(id)}/tick`, {
      json: { position, elapsed_sec: elapsedSec },
    });
  }
  finish(id: string) {
    return this.req<Report>("POST", `/practice/sessions/${encodeURIComponent(id)}/finish`);
  }
  list(opts: { subject?: string; limit?: number } = {}) {
    return this.req<SessionSummary[]>("GET", "/practice/sessions", { query: { subject: opts.subject, limit: opts.limit ?? 30 } });
  }
  review(id: string) {
    return this.req<{ items: ReviewItem[] } | ReviewItem[]>("GET", `/practice/sessions/${encodeURIComponent(id)}/review`);
  }
  progress(subject?: string) {
    return this.req<{ skills: ProgressSkill[] }>("GET", "/practice/progress", { query: { subject } });
  }
  recommendations(subject?: string) {
    return this.req<PracticeRecommendation[]>("GET", "/practice/recommendations", { query: { subject } });
  }
  reportItem(itemId: string, body: ItemReportRequest) {
    return this.req<{ id: string | number; status: string }>("POST", `/practice/items/${encodeURIComponent(itemId)}/report`, { json: body });
  }
  itemReports() {
    return this.req<PracticeItemReport[]>("GET", "/practice/items/reports");
  }
}
