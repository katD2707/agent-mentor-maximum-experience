/**
 * In-browser fake of `/api/practice` (CONTRACTS 10.3) for tests and `pnpm dev` without the gateway. It follows the
 * contract's behaviour (no key before the answer, mock answers hidden until finish, deadline enforced here) over a
 * tiny invented bank. Selection is a seeded shuffle, not the real engine.
 */
import { ApiError } from "../client";
import { decodeTF, encodeTF, parseShortAnswer, STATEMENT_POINTS } from "../../practice/logic";
import type {
  AnswerResult,
  AnswerState,
  ClientItem,
  ItemReportRequest,
  MockProfile,
  PartResult,
  PracticeApi,
  PracticeGoal,
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
  SessionKind,
  SessionPart,
  SessionSummary,
  StartSessionRequest,
  TopicResult,
} from "../../practice/types";
import { bankFor, BANK, SUBJECT_META, type BankItem } from "./practiceBank";

const STORAGE_KEY = "mentor-mock-practice-v1";

interface Stored {
  id: string;
  kind: SessionKind;
  subject: string;
  profileId?: string;
  label: string;
  startedAt: number;
  finishedAt?: number;
  limitSec: number | null;
  elapsed: number;
  position: number;
  itemIds: string[];
  parts?: SessionPart[];
  disclaimer?: string;
  answers: Record<string, AnswerState & { hints?: number; hintText?: string; revealed?: boolean; time?: number }>;
  report?: Report;
}

interface State {
  sessions: Stored[];
  mastery: Record<string, { m: number; n: number }>; // key subject|topic
  skipped: Record<string, boolean>;
  done: Record<string, boolean>;
  reports: PracticeItemReport[];
  reportCount: { day: string; n: number };
}

const MOCK_FORMAT = "math.format-2025-mock";

/** Mock learner is in grade 11; "calculus" is a grade-12 topic (CONTRACTS 10.11). */
const LEARNER_GRADE = 11;
const TOPIC_GRADE: Record<string, number> = { calculus: 12 };
const topicGrade = (topic: string): number | null => TOPIC_GRADE[topic] ?? null;
const isAbove = (topic: string): boolean => (topicGrade(topic) ?? 0) > LEARNER_GRADE;

/** Gateway-style error: `{detail, code, ...}` (CONTRACTS 10.9). */
function fail(status: number, detail: string, code: string, extra: Record<string, unknown> = {}): never {
  throw new ApiError(status, detail, { detail, code, ...extra });
}

function profilesFor(subject: string): (MockProfile & { parts?: { label: string; type: string; count: number; each: number }[] })[] {
  const mcq = (id: string, n: number, min: number, label: string): MockProfile => ({
    id,
    label,
    type: "MCQ_PRACTICE_MOCK",
    item_count: n,
    time_limit_sec: min * 60,
    disclaimer: "Đề luyện tập chỉ gồm câu nhiều lựa chọn, KHÔNG phải cấu trúc đề chính thức.",
  });
  if (subject === "math") {
    return [
      mcq("math.mcq-mock.2026", 8, 12, "Thi thử trắc nghiệm Toán (8 câu · 12 phút)"),
      {
        id: MOCK_FORMAT,
        label: "Thi thử Toán 3 phần theo cấu trúc 2025 (12 câu · 15 phút)",
        type: "OFFICIAL_FORMAT_MOCK",
        item_count: 12,
        time_limit_sec: 900,
        disclaimer:
          "Đề luyện tập theo cấu trúc và cách tính điểm công bố cho kì thi từ 2025 (Phần II tính 0,1/0,25/0,5/1 điểm cho 1/2/3/4 ý đúng). Câu hỏi do dự án biên soạn, KHÔNG phải cấu trúc đề chính thức; điểm KHÔNG dự báo điểm thi thật.",
        parts: [
          { label: "Phần I · Trắc nghiệm nhiều lựa chọn", type: "SINGLE_CHOICE", count: 6, each: 0.5 },
          { label: "Phần II · Đúng/Sai", type: "TRUE_FALSE_GROUP", count: 2, each: 1 },
          { label: "Phần III · Trả lời ngắn", type: "SHORT_ANSWER", count: 4, each: 0.5 },
        ],
      },
    ];
  }
  if (subject === "physics") return [mcq("physics.mcq-mock.2026", 5, 8, "Thi thử trắc nghiệm Vật lí (5 câu · 8 phút)")];
  return [mcq("english.mcq-mock.2026", 5, 7, "Thi thử trắc nghiệm Tiếng Anh (5 câu · 7 phút)")];
}

/** mulberry32: a tiny seeded PRNG so a started set equals its preview. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffled<T>(arr: T[], seed: number): T[] {
  const r = rng(seed);
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function masteryLabel(m: number | null, evidence: number): string {
  if (m == null || evidence === 0) return "Chưa có dữ liệu";
  if (evidence < 3) return "Cần thêm dữ liệu";
  if (m < 0.45) return "Cần củng cố";
  if (m < 0.75) return "Đang tiến bộ";
  return "Vững";
}

const asClient = (b: BankItem, position: number): ClientItem => ({
  position,
  id: b.id,
  type: b.type,
  stem: b.stem,
  options: b.options,
  statements: b.statements?.map(({ id, text }) => ({ id, text })),
  short_answer: b.sa ? { max_chars: b.sa.max_chars, decimals: b.sa.decimals, unit: b.sa.unit ?? null } : undefined,
  assets: b.assets ?? [],
  topic: b.topic,
  topic_title: b.topicTitle,
  level: b.level,
  estimated_seconds: b.seconds,
  has_hint: !!b.hint,
});

export interface MockPracticeOptions {
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  now?: () => number;
  latencyMs?: number;
}

export class MockPractice implements PracticeApi {
  private state: State;
  private readonly now: () => number;
  private readonly storage: MockPracticeOptions["storage"];
  private readonly latencyMs: number;

  constructor(opts: MockPracticeOptions = {}) {
    this.now = opts.now ?? (() => Date.now());
    this.storage = opts.storage ?? null;
    this.latencyMs = opts.latencyMs ?? 0;
    this.state = this.load() ?? { sessions: [], mastery: {}, skipped: {}, done: {}, reports: [], reportCount: { day: "", n: 0 } };
  }

  // ------------------------------------------------------------------ plumbing

  private load(): State | null {
    try {
      const raw = this.storage?.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as State) : null;
    } catch {
      return null;
    }
  }

  private save() {
    try {
      this.storage?.setItem(STORAGE_KEY, JSON.stringify(this.state));
    } catch {
      // storage full or blocked: keep going in memory
    }
  }

  private async lag() {
    if (this.latencyMs > 0) await new Promise((r) => setTimeout(r, this.latencyMs));
  }

  /** Test helper. */
  reset() {
    this.state = { sessions: [], mastery: {}, skipped: {}, done: {}, reports: [], reportCount: { day: "", n: 0 } };
    this.save();
  }

  private find(id: string): Stored {
    const s = this.state.sessions.find((x) => x.id === id);
    if (!s) fail(404, "Không tìm thấy phiên làm bài.", "not_found");
    return s;
  }

  private bankItem(id: string): BankItem {
    const b = BANK.find((x) => x.id === id);
    if (!b) throw new ApiError(404, "Không tìm thấy câu hỏi.");
    return b;
  }

  /** The server enforces the deadline: a timed session past its limit is finished before anything else. */
  private enforceDeadline(s: Stored): boolean {
    if (s.finishedAt) return false;
    if (s.limitSec != null && this.now() - s.startedAt >= s.limitSec * 1000) {
      this.finishNow(s);
      return true;
    }
    return false;
  }

  private view(s: Stored): Session {
    const answers: Session["answers"] = {};
    for (const [pos, a] of Object.entries(s.answers)) {
      const hideResult = s.kind !== "practice" && !s.finishedAt;
      answers[pos] = {
        answer: hideResult && s.kind !== "practice" ? null : (a.answer ?? null),
        draft: s.finishedAt ? null : (a.draft ?? null),
        flagged: !!a.flagged,
        checked: !!a.checked,
        correct: hideResult ? undefined : a.correct,
        points: hideResult ? undefined : a.points,
        result: s.kind === "practice" ? (a.result ?? null) : undefined,
        hint: s.kind === "practice" ? (a.hintText ?? null) : undefined,
        revealed: a.revealed,
      };
    }
    return {
      id: s.id,
      kind: s.kind,
      subject: s.subject,
      profile_id: s.profileId ?? null,
      started_at: new Date(s.startedAt).toISOString(),
      deadline: s.limitSec != null ? new Date(s.startedAt + s.limitSec * 1000).toISOString() : null,
      remaining_sec: s.limitSec != null && !s.finishedAt ? Math.max(0, s.limitSec - Math.floor((this.now() - s.startedAt) / 1000)) : null,
      status: s.finishedAt ? "finished" : "active",
      position: s.position,
      items: s.itemIds.map((id, i) => asClient(this.bankItem(id), i)),
      answers,
      parts: s.parts ?? null,
      disclaimer: s.disclaimer ?? null,
      label: s.label,
      finished: !!s.finishedAt,
    };
  }

  // ------------------------------------------------------------------ catalogue

  async subjects(): Promise<PracticeSubject[]> {
    await this.lag();
    return Object.entries(SUBJECT_META).map(([id, meta]) => ({
      id,
      label: meta.label,
      topics: Object.entries(meta.topics).map(([tid, title]) => ({
        id: `${id}.${tid}`,
        title,
        item_count: bankFor(id).filter((b) => b.topic === tid).length,
        grade: topicGrade(tid),
        above_grade: isAbove(tid),
      })),
      learner_grade: LEARNER_GRADE,
      diagnostic: this.state.done[id] ? "done" : this.state.skipped[id] ? "skipped" : "none",
      mock_profiles: profilesFor(id).map((p) => ({ id: p.id, label: p.label, type: p.type, item_count: p.item_count, time_limit_sec: p.time_limit_sec, disclaimer: p.disclaimer, above_grade: false, note: null })),
    }));
  }

  private pickPractice(req: { subject: string; minutes: number; goal: PracticeGoal; topics?: string[]; include_above_grade?: boolean }, seed: number): BankItem[] {
    const topicIds = (req.topics ?? []).map((t) => t.split(".").pop()!);
    const above = topicIds.filter(isAbove);
    if (above.length > 0 && !req.include_above_grade) {
      fail(422, "Có chủ đề thuộc lớp trên mà bạn chưa học. Bật “Thử cả chủ đề lớp trên” nếu vẫn muốn thử.", "above_grade_topic", { topics: above });
    }
    let pool = bankFor(req.subject).filter((b) => (topicIds.length === 0 ? req.include_above_grade || !isAbove(b.topic) : topicIds.includes(b.topic)));
    if (req.goal === "challenge") pool = [...pool].sort((a, b) => b.level - a.level);
    else if (req.goal === "weak") {
      const weak = (b: BankItem) => this.state.mastery[`${b.subject}|${b.topic}`]?.m ?? 0.5;
      pool = [...pool].sort((a, b) => weak(a) - weak(b));
    } else pool = shuffled(pool, seed);
    const want = Math.max(3, Math.round(req.minutes / 2));
    if (pool.length < 3) fail(422, "Chưa đủ câu hỏi cho lựa chọn này. Hãy chọn thêm chủ đề.", "insufficient_content", { available: pool.length, required: 3 });
    const picked = pool.slice(0, want);
    return req.goal === "balanced" ? picked : shuffled(picked, seed);
  }

  async preview(body: PreviewRequest): Promise<PracticePreview> {
    await this.lag();
    const seed = Math.floor(this.now() % 100000);
    const items = this.pickPractice(body, seed);
    const mix = [0, 0, 0, 0];
    const per = new Map<string, { title: string; count: number }>();
    for (const b of items) {
      mix[b.level - 1]++;
      const k = `${b.subject}.${b.topic}`;
      per.set(k, { title: b.topicTitle, count: (per.get(k)?.count ?? 0) + 1 });
    }
    const minutes = Math.max(1, Math.round(items.reduce((s, b) => s + b.seconds, 0) / 60));
    return { seed, item_count: items.length, minutes, level_mix: mix, per_topic: [...per].map(([topic, v]) => ({ topic, ...v })) };
  }

  // ------------------------------------------------------------------ sessions

  async start(body: StartSessionRequest): Promise<Session> {
    await this.lag();
    const subject = body.subject;
    if (!SUBJECT_META[subject]) fail(404, "Không có môn này.", "unknown_subject");
    for (const old of this.state.sessions) {
      if (old.subject !== subject || old.finishedAt) continue;
      this.enforceDeadline(old);
      if (old.finishedAt) continue;
      if (old.kind === "practice") this.finishNow(old);
      else fail(409, "Bạn đang có một bài chưa xong ở môn này.", "active_session", { session_id: old.id, kind: old.kind });
    }
    const id = `p-${this.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
    let stored: Stored;
    if (body.kind === "practice") {
      const seed = Number(body.seed ?? 1);
      const items = this.pickPractice({ subject, minutes: body.minutes ?? 20, goal: body.goal ?? "balanced", topics: body.topics, include_above_grade: body.include_above_grade }, seed);
      stored = { id, kind: "practice", subject, label: `Luyện tập ${body.minutes ?? 20} phút`, startedAt: this.now(), limitSec: null, elapsed: 0, position: 0, itemIds: items.map((b) => b.id), answers: {} };
    } else if (body.kind === "diagnostic") {
      const mcqs = bankFor(subject).filter((b) => b.type === "SINGLE_CHOICE");
      const items = shuffled(mcqs, 7).slice(0, 6);
      stored = { id, kind: "diagnostic", subject, label: "Đánh giá nhanh", startedAt: this.now(), limitSec: 15 * 60, elapsed: 0, position: 0, itemIds: items.map((b) => b.id), answers: {} };
    } else {
      const profile = profilesFor(subject).find((p) => p.id === body.profile_id) ?? profilesFor(subject)[0];
      let items: BankItem[];
      let parts: SessionPart[] | undefined;
      if (profile.parts) {
        items = [];
        parts = [];
        for (const p of profile.parts) {
          const pool = shuffled(bankFor(subject).filter((b) => b.type === p.type), 3).slice(0, p.count);
          parts.push({ label: p.label, positions: pool.map((_, i) => items.length + i), points_each: p.each });
          items.push(...pool);
        }
      } else {
        items = shuffled(bankFor(subject).filter((b) => b.type === "SINGLE_CHOICE"), 5).slice(0, profile.item_count);
      }
      stored = { id, kind: "mock", subject, profileId: profile.id, label: profile.label, startedAt: this.now(), limitSec: profile.time_limit_sec, elapsed: 0, position: 0, itemIds: items.map((b) => b.id), parts, disclaimer: profile.disclaimer, answers: {} };
    }
    this.state.sessions.unshift(stored);
    this.save();
    return this.view(stored);
  }

  async skipDiagnostic(subject: string) {
    await this.lag();
    this.state.skipped[subject] = true;
    this.save();
    return { ok: true };
  }

  async active(subject?: string): Promise<Session | null> {
    await this.lag();
    for (const s of this.state.sessions) {
      if (s.finishedAt || (subject && s.subject !== subject)) continue;
      this.enforceDeadline(s);
      if (!s.finishedAt) return this.view(s);
    }
    this.save();
    return null;
  }

  async get(id: string): Promise<Session> {
    await this.lag();
    const s = this.find(id);
    this.enforceDeadline(s);
    this.save();
    return this.view(s);
  }

  private grade(b: BankItem, answer: string | null): { correct: boolean; points: number; max: number; correctAnswer: string; statements?: boolean[] } {
    if (b.type === "TRUE_FALSE_GROUP") {
      const given = decodeTF(answer);
      const truths = b.statements!.map((s) => s.truth);
      const results = truths.map((t, i) => given[i] === t);
      const right = results.filter(Boolean).length;
      return { correct: right === 4, points: STATEMENT_POINTS[right], max: 1, correctAnswer: encodeTF(truths), statements: results };
    }
    if (b.type === "SHORT_ANSWER") {
      const given = parseShortAnswer(answer, b.sa!.unit);
      const fits = given !== null && (b.sa!.max_chars == null || given.length <= b.sa!.max_chars);
      const ok = fits && Number(given!.replace(",", ".")) === Number(b.sa!.answer.replace(",", "."));
      return { correct: ok, points: ok ? 1 : 0, max: 1, correctAnswer: b.sa!.answer };
    }
    const ok = answer === b.key;
    return { correct: ok, points: ok ? 1 : 0, max: 1, correctAnswer: b.key! };
  }

  private result(b: BankItem, answer: string, blank: boolean): AnswerResult {
    const g = this.grade(b, blank ? null : answer);
    const fb: Record<string, string> = {};
    if (b.type === "SINGLE_CHOICE") for (const [k, v] of Object.entries(b.optionFeedback ?? {})) if (k !== b.key) fb[k] = v;
    const given = decodeTF(answer);
    return {
      correct: blank ? null : g.correct,
      points: blank ? 0 : g.points,
      max_points: g.max,
      correct_answer: g.correctAnswer,
      option_feedback: Object.keys(fb).length ? fb : null,
      statement_results: b.statements
        ? b.statements.map((st, i) => ({ id: st.id, given: blank ? null : given[i], truth: st.truth, correct: !blank && given[i] === st.truth, explanation: st.explanation }))
        : null,
    } as AnswerResult;
  }

  async answer(id: string, body: { position: number; answer: string | null; time_spent_sec: number }): Promise<AnswerResult> {
    await this.lag();
    const s = this.find(id);
    if (this.enforceDeadline(s)) fail(409, "Hết giờ, bài đã được nộp.", "expired");
    if (s.finishedAt) fail(409, "Bài làm đã kết thúc.", "finished");
    const b = this.bankItem(s.itemIds[body.position] ?? "");
    const prev = s.answers[String(body.position)] ?? {};
    if (s.kind === "practice") {
      if (prev.checked && prev.result) return prev.result; // replaying a checked position returns the stored result
      const blank = !body.answer;
      const r = this.result(b, body.answer ?? "", blank);
      s.answers[String(body.position)] = {
        ...prev,
        answer: body.answer ?? "",
        checked: true,
        correct: r.correct,
        points: r.points,
        result: r,
        time: body.time_spent_sec,
      };
      s.position = Math.min(s.itemIds.length - 1, body.position + 1);
      this.save();
      return r;
    }
    s.answers[String(body.position)] = { ...prev, answer: body.answer, draft: body.answer, time: body.time_spent_sec };
    this.save();
    return { saved: true };
  }

  async hint(id: string, position: number) {
    await this.lag();
    const s = this.find(id);
    if (s.kind !== "practice") fail(403, "Không có gợi ý trong thi thử.", "hints_locked");
    const a = s.answers[String(position)] ?? {};
    if (a.checked) fail(403, "Câu này đã được kiểm tra.", "hints_locked");
    const text = this.bankItem(s.itemIds[position]).hint;
    s.answers[String(position)] = { ...a, hints: 1, hintText: text };
    this.save();
    return { hint: text };
  }

  async reveal(id: string, position: number): Promise<RevealResult> {
    await this.lag();
    const s = this.find(id);
    if (s.kind !== "practice" && !s.finishedAt) fail(403, "Chỉ xem lời giải sau khi nộp bài.", "reveal_locked");
    const a = s.answers[String(position)];
    if (s.kind === "practice" && !a?.checked && !s.finishedAt) fail(409, "Hãy kiểm tra đáp án trước.", "not_answered");
    if (a) a.revealed = true;
    this.save();
    const b = this.bankItem(s.itemIds[position]);
    return { explanation: b.explanation, tip: b.tip ?? null, assets: b.solutionAssets ?? [] };
  }

  async flag(id: string, position: number, flagged: boolean) {
    await this.lag();
    const s = this.find(id);
    if (s.kind !== "mock") fail(403, "Chỉ đánh dấu câu trong thi thử.", "flag_locked");
    s.answers[String(position)] = { ...(s.answers[String(position)] ?? {}), flagged };
    this.save();
    return { ok: true };
  }

  /** `elapsed_sec` is seconds spent on the item (not the session clock); the deadline is wall-clock on the server. */
  async tick(id: string, position: number): Promise<{ remaining_sec?: number | null; expired?: boolean }> {
    await this.lag();
    const s = this.find(id);
    const expired = this.enforceDeadline(s) || (!!s.finishedAt && s.limitSec != null);
    if (!s.finishedAt) s.position = position;
    this.save();
    if (s.limitSec == null) return {};
    if (expired) return { remaining_sec: 0, expired: true };
    return { remaining_sec: Math.max(0, s.limitSec - Math.floor((this.now() - s.startedAt) / 1000)) };
  }

  // ------------------------------------------------------------------ finish and report

  private finishNow(s: Stored): Report {
    if (s.report) return s.report;
    s.finishedAt = s.limitSec != null ? Math.min(this.now(), s.startedAt + s.limitSec * 1000) : this.now();
    const items = s.itemIds.map((id) => this.bankItem(id));
    const topicMap = new Map<string, { title: string; right: number; total: number; key: string }>();
    let correct = 0;
    let answered = 0;
    let hints = 0;
    let pointsTotal = 0;
    let maxTotal = 0;
    const partResults: PartResult[] = (s.parts ?? []).map((p, pi) => ({ label: p.label, part: pi + 1, total: p.positions.length, answered: 0, correct: 0, points: 0, max_points: 0 }));
    items.forEach((b, i) => {
      const a = s.answers[String(i)] ?? {};
      hints += a.hints ?? 0;
      const given = s.kind === "practice" ? (a.checked ? a.answer : null) : a.answer ?? a.draft ?? null;
      const g = given ? this.grade(b, given) : null;
      if (g) {
        a.correct = g.correct;
        a.points = g.points;
        a.checked = true;
        a.answer = given;
        answered++;
        if (g.correct) correct++;
      }
      const part = s.parts?.findIndex((p) => p.positions.includes(i)) ?? -1;
      const each = part >= 0 ? s.parts![part].points_each : 1;
      if (g) pointsTotal += g.points * each;
      maxTotal += each;
      if (part >= 0) {
        const r = partResults[part];
        r.max_points += each;
        if (g) {
          r.answered = (r.answered ?? 0) + 1;
          r.points += g.points * each;
          if (g.correct) r.correct = (r.correct ?? 0) + 1;
        }
      }
      if (!g && s.kind !== "mock") return; // an unanswered item adds no evidence for its topic
      const key = `${b.subject}|${b.topic}`;
      const t = topicMap.get(key) ?? { title: b.topicTitle, right: 0, total: 0, key: `${b.subject}.${b.topic}` };
      t.total++;
      if (g?.correct) t.right++;
      topicMap.set(key, t);
    });
    const per_topic: TopicResult[] = [];
    for (const [k, t] of topicMap) {
      const prev = this.state.mastery[k];
      const answeredHere = items.filter((b, i) => `${b.subject}|${b.topic}` === k && !!s.answers[String(i)]?.answer).length;
      const evidence = (prev?.n ?? 0) + answeredHere;
      const sample = t.total ? t.right / t.total : 0;
      const after = answeredHere === 0 ? (prev?.m ?? null) : prev ? (prev.m * prev.n + sample * answeredHere) / evidence : sample;
      if (after != null) this.state.mastery[k] = { m: after, n: evidence };
      per_topic.push({ topic: t.key, title: t.title, right: t.right, total: t.total, mastery_before: prev?.m ?? null, mastery_after: after, label: masteryLabel(after, evidence) });
    }
    if (s.kind === "diagnostic") this.state.done[s.subject] = true;
    const report: Report = {
      session: { id: s.id, kind: s.kind, subject: s.subject, started_at: new Date(s.startedAt).toISOString(), finished_at: new Date(s.finishedAt).toISOString() },
      correct,
      total: s.kind === "mock" ? items.length : answered,
      answered,
      score_10: s.kind === "mock" && maxTotal > 0 ? Math.round((pointsTotal / maxTotal) * 1000) / 100 : null,
      minutes: Math.max(1, Math.round((s.finishedAt - s.startedAt) / 60000)),
      hints,
      per_topic,
      per_part: partResults.length ? partResults : null,
      recommendations: this.recs(s.subject),
      disclaimer: s.disclaimer ?? (s.kind === "mock" ? "Điểm thi thử KHÔNG dự báo điểm thi thật." : null),
    };
    s.report = report;
    return report;
  }

  async finish(id: string): Promise<Report> {
    await this.lag();
    const s = this.find(id);
    const r = this.finishNow(s);
    this.save();
    return r;
  }

  async list(opts: { subject?: string; limit?: number } = {}): Promise<SessionSummary[]> {
    await this.lag();
    return this.state.sessions
      .filter((s) => s.finishedAt && (!opts.subject || s.subject === opts.subject))
      .slice(0, opts.limit ?? 30)
      .map((s) => ({
        id: s.id,
        kind: s.kind,
        subject: s.subject,
        started_at: new Date(s.startedAt).toISOString(),
        finished_at: new Date(s.finishedAt!).toISOString(),
        score_10: s.report?.score_10 ?? null,
        correct: s.report?.correct ?? 0,
        total: s.report?.total ?? s.itemIds.length,
        minutes: s.report?.minutes ?? 0,
      }));
  }

  async review(id: string) {
    await this.lag();
    const s = this.find(id);
    if (!s.finishedAt) throw new ApiError(403, "Chỉ xem lại sau khi kết thúc.");
    const items: ReviewItem[] = s.itemIds.map((bid, i) => {
      const b = this.bankItem(bid);
      const a = s.answers[String(i)] ?? {};
      const g = a.answer ? this.grade(b, a.answer) : null;
      const fb: Record<string, string> = {};
      if (b.type === "SINGLE_CHOICE") for (const [k, v] of Object.entries(b.optionFeedback ?? {})) fb[k] = v;
      return {
        ...asClient(b, i),
        answer: a.answer ?? null,
        correct: g ? g.correct : null,
        points: g?.points ?? 0,
        max_points: 1,
        correct_answer: this.grade(b, null).correctAnswer,
        explanation: b.explanation,
        tip: b.tip ?? null,
        hint: b.hint,
        option_feedback: Object.keys(fb).length ? fb : null,
        statement_results: g?.statements ?? null,
        statements: b.statements?.map((st) => ({ id: st.id, text: st.text, truth: st.truth, explanation: st.explanation ?? null })),
        solution_assets: b.solutionAssets ?? [],
      };
    });
    return { session: this.view(s), items };
  }

  // ------------------------------------------------------------------ progress, recommendations, reports

  async progress(subject?: string): Promise<{ skills: ProgressSkill[] }> {
    await this.lag();
    const skills: ProgressSkill[] = [];
    for (const [subj, meta] of Object.entries(SUBJECT_META)) {
      if (subject && subj !== subject) continue;
      for (const [tid, title] of Object.entries(meta.topics)) {
        const m = this.state.mastery[`${subj}|${tid}`];
        skills.push({
          skill_id: `${subj}.${tid}`,
          title,
          topic: `${subj}.${tid}`,
          mastery: m?.m ?? null,
          evidence: m?.n ?? 0,
          confidence: (m?.n ?? 0) >= 8 ? "high" : (m?.n ?? 0) >= 3 ? "medium" : "low",
          label: masteryLabel(m?.m ?? null, m?.n ?? 0),
          trend: m ? [{ at: new Date(this.now()).toISOString(), mastery: m.m }] : [],
        });
      }
    }
    return { skills };
  }

  private recs(subject?: string): PracticeRecommendation[] {
    const subj = subject ?? "math";
    const out: PracticeRecommendation[] = [];
    const topicStats = Object.entries(this.state.mastery).filter(([k]) => k.startsWith(`${subj}|`));
    if (!this.state.done[subj] && !this.state.skipped[subj]) {
      out.push({ code: "TAKE_DIAGNOSTIC", subject: subj, title: "Làm đánh giá nhanh", reason: "Vì sao: chưa có dữ liệu để xếp đề vừa sức cho bạn.", action: { kind: "diagnostic", params: { subject: subj } } });
    }
    const weak = topicStats.filter(([, v]) => v.m < 0.6).sort((a, b) => a[1].m - b[1].m)[0];
    if (weak) {
      const tid = weak[0].split("|")[1];
      out.push({ code: "PRACTICE_WEAK", subject: subj, title: `Luyện thêm: ${SUBJECT_META[subj].topics[tid]}`, reason: "Vì sao: chủ đề này còn cần củng cố.", action: { kind: "practice", params: { subject: subj, minutes: 20, goal: "weak", topics: [`${subj}.${tid}`] } } });
    }
    out.push({ code: "TAKE_MOCK", subject: subj, title: "Thử một bài thi thử", reason: "Vì sao: luyện cả đề giúp quen nhịp thời gian.", action: { kind: "mock", params: { subject: subj } } });
    out.push({ code: "PRACTICE_BALANCED", subject: subj, title: "Luyện tập cân bằng 20 phút", reason: "Vì sao: một buổi ngắn trải đều các chủ đề.", action: { kind: "practice", params: { subject: subj, minutes: 20, goal: "balanced" } } });
    return out.slice(0, 3);
  }

  async recommendations(subject?: string) {
    await this.lag();
    return this.recs(subject);
  }

  async reportItem(itemId: string, body: ItemReportRequest) {
    await this.lag();
    const s = this.find(body.session_id);
    const idx = s.itemIds.indexOf(itemId);
    const a = idx >= 0 ? s.answers[String(idx)] : undefined;
    const shown = s.finishedAt || (s.kind === "practice" && a?.checked);
    if (!shown) throw new ApiError(409, "Chỉ báo lỗi sau khi đã xem đáp án.");
    const day = new Date(this.now()).toISOString().slice(0, 10);
    if (this.state.reportCount.day !== day) this.state.reportCount = { day, n: 0 };
    if (this.state.reportCount.n >= 10) throw new ApiError(429, "Hôm nay bạn đã báo đủ 10 lỗi. Mai gửi tiếp nhé.");
    this.state.reportCount.n++;
    const rep: PracticeItemReport = { id: `r-${this.state.reports.length + 1}`, item_id: itemId, reason: body.reason, status: "open", created_at: new Date(this.now()).toISOString() };
    this.state.reports.unshift(rep);
    this.save();
    return { id: rep.id, status: rep.status };
  }

  async itemReports() {
    await this.lag();
    return this.state.reports;
  }
}
