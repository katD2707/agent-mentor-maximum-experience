import { PracticeError, type PHome, type PItem, type PReport, type PResult, type PReviewItem, type PSession, type PracticeApi } from "./practice";
import { checkShortAnswer } from "../lib/quiz";

/** In-browser stand-in for `/api/practice` (VITE_API_MOCK=1 and the tests). Keys live here, never in the items. */

interface Key {
  correct: string;
  explanation: string;
  feedback?: Record<string, string>;
  truth?: Record<string, boolean>;
}

type Entry = { item: Omit<PItem, "position">; key: Key };
interface BankSet {
  entries: Entry[];
  course: { id: string; title: string };
  hint: string;
  takeaway: { vi: string; en: string };
}
type Say = (vi: string, en: string) => string;

/** One small bank per age band: counting for the little ones, fractions and geometry for 6-9, algebra and physics from 10. */
const BANKS: Record<string, (say: Say) => BankSet> = {
  g1_5: (say): BankSet => {
    const topic = { topic: "t", topic_title: say("Đếm táo", "Counting apples") };
    return {
      course: { id: "dev-sample-dem-tao", title: topic.topic_title },
      hint: say("Đếm chậm từng quả.", "Count them slowly, one by one."),
      takeaway: { vi: "Tốt rồi. Chỉ còn lỗi đếm thiếu.", en: "Good. Only a miscount left." },
      entries: [
        {
          item: { id: "c:1", type: "SINGLE_CHOICE", stem: say("Bao nhiêu quả táo trong 2 + 3?", "How many apples is 2 + 3?"), options: [{ id: "A", text: "4" }, { id: "B", text: "5" }, { id: "C", text: "6" }], ...topic },
          key: { correct: "B", explanation: say("2 + 3 = 5. Đếm tiếp 3 quả sau số 2.", "2 + 3 = 5. Count on 3 more after 2."), feedback: { A: say("Em đếm thiếu một quả.", "You counted one too few.") } },
        },
        {
          item: { id: "c:2", type: "PICTURE_CHOICE", stem: say("Chọn hình có 3 quả táo", "Pick the picture with 3 apples"), options: [{ id: "A", text: "3" }, { id: "B", text: "4" }], ...topic },
          key: { correct: "A", explanation: say("Hình A có ba quả.", "Picture A has three apples.") },
        },
        {
          item: { id: "c:3", type: "TAP_COUNT", stem: say("Chạm đếm các quả táo (có 3 quả)", "Tap to count the apples (there are 3)"), tap: { total: 5 }, ...topic },
          key: { correct: "3", explanation: say("Đếm lần lượt từng quả: 1, 2, 3.", "Count them one at a time: 1, 2, 3.") },
        },
        {
          item: {
            id: "c:4",
            type: "TRUE_FALSE_GROUP",
            stem: say("Đúng hay sai?", "True or false?"),
            statements: [{ id: "a", text: "2 + 2 = 4" }, { id: "b", text: "3 + 1 = 5" }, { id: "c", text: "5 - 1 = 4" }],
            ...topic,
          },
          key: { correct: "TFT", explanation: say("3 + 1 = 4, không phải 5.", "3 + 1 = 4, not 5."), truth: { a: true, b: false, c: true } },
        },
        {
          item: { id: "c:5", type: "SHORT_ANSWER", stem: say("1 / 2 bằng bao nhiêu (số thập phân)?", "What is 1 / 2 as a decimal?"), short_answer: { max_chars: 24 }, ...topic },
          key: { correct: "0,5", explanation: say("Một nửa là 0,5.", "Half is 0.5.") },
        },
      ],
    };
  },
  g6_9: (say): BankSet => {
    const topic = { topic: "t", topic_title: say("Phân số và hình học", "Fractions and geometry") };
    return {
      course: { id: "dev-sample-phan-so", title: topic.topic_title },
      hint: say("Đổi các phân số về số thập phân rồi so sánh.", "Turn the fractions into decimals, then compare."),
      takeaway: { vi: "Tốt rồi. Chỉ còn nhầm ở chu vi.", en: "Good. Only the perimeter slipped." },
      entries: [
        {
          item: { id: "f:1", type: "SINGLE_CHOICE", stem: say("Phân số nào lớn nhất?", "Which fraction is the largest?"), options: [{ id: "A", text: "1/2" }, { id: "B", text: "3/4" }, { id: "C", text: "2/3" }], ...topic },
          key: { correct: "B", explanation: say("3/4 = 0,75, lớn hơn 2/3 (khoảng 0,67) và 1/2.", "3/4 = 0.75, more than 2/3 (about 0.67) and 1/2."), feedback: { C: say("2/3 khoảng 0,67, còn 3/4 là 0,75.", "2/3 is about 0.67, and 3/4 is 0.75.") } },
        },
        {
          item: {
            id: "f:2",
            type: "SINGLE_CHOICE",
            stem: say("Hình chữ nhật dài 6 cm, rộng 4 cm. Chu vi là bao nhiêu?", "A rectangle is 6 cm long and 4 cm wide. What is its perimeter?"),
            options: [{ id: "A", text: "10 cm" }, { id: "B", text: "20 cm" }, { id: "C", text: "24 cm" }],
            ...topic,
          },
          key: { correct: "B", explanation: "(6 + 4) × 2 = 20 cm.", feedback: { A: say("Em mới cộng dài với rộng, còn phải nhân đôi.", "You added length and width, now double it."), C: say("24 là diện tích, không phải chu vi.", "24 is the area, not the perimeter.") } },
        },
        {
          item: {
            id: "f:3",
            type: "TRUE_FALSE_GROUP",
            stem: say("Đúng hay sai?", "True or false?"),
            statements: [{ id: "a", text: say("12 chia hết cho 4", "12 is divisible by 4") }, { id: "b", text: say("15 là số nguyên tố", "15 is a prime number") }, { id: "c", text: "7 × 8 = 56" }],
            ...topic,
          },
          key: { correct: "TFT", explanation: say("15 chia hết cho 3 và 5 nên không phải số nguyên tố.", "15 is divisible by 3 and 5, so it is not prime."), truth: { a: true, b: false, c: true } },
        },
        {
          item: { id: "f:4", type: "SHORT_ANSWER", stem: say("Tính: 2,5 × 4", "Work out: 2.5 × 4"), short_answer: { max_chars: 24 }, ...topic },
          key: { correct: "10", explanation: say("Hai lần 2,5 là 5, hai lần nữa là 10.", "Two 2.5s make 5, two more make 10.") },
        },
        {
          item: { id: "f:5", type: "SHORT_ANSWER", stem: say("Xe đi 60 km trong 2 giờ. Vận tốc trung bình là bao nhiêu km/h?", "A car goes 60 km in 2 hours. What is its average speed in km/h?"), short_answer: { max_chars: 24, unit: "km/h" }, ...topic },
          key: { correct: "30", explanation: "60 / 2 = 30 km/h." },
        },
      ],
    };
  },
  g10_12: (say): BankSet => {
    const topic = { topic: "t", topic_title: say("Cấp số cộng và điện trường", "Arithmetic sequences and electric fields") };
    return {
      course: { id: "dev-sample-dien-truong", title: topic.topic_title },
      hint: say("Thử viết ra từng số hạng liên tiếp.", "Try writing out the terms one after another."),
      takeaway: { vi: "Tốt rồi. Chỉ còn lẫn công thức.", en: "Good. Only a formula mix-up left." },
      entries: [
        {
          item: { id: "h:1", type: "SINGLE_CHOICE", stem: say("Cấp số cộng có số hạng đầu 2, công sai 3. Số hạng thứ 5 là?", "An arithmetic sequence starts at 2 with common difference 3. What is the 5th term?"), options: [{ id: "A", text: "14" }, { id: "B", text: "17" }, { id: "C", text: "11" }], ...topic },
          key: { correct: "A", explanation: "u₅ = 2 + 4 × 3 = 14.", feedback: { B: say("17 là số hạng thứ 6.", "17 is the 6th term.") } },
        },
        {
          item: { id: "h:2", type: "SINGLE_CHOICE", stem: say("Hai điện tích cùng dấu đặt gần nhau thì chúng:", "Two charges of the same sign placed close together:"), options: [{ id: "A", text: say("hút nhau", "attract each other") }, { id: "B", text: say("đẩy nhau", "repel each other") }, { id: "C", text: say("không tác dụng lên nhau", "do not act on each other") }], ...topic },
          key: { correct: "B", explanation: say("Cùng dấu thì đẩy, trái dấu thì hút.", "Like charges repel, unlike charges attract.") },
        },
        {
          item: {
            id: "h:3",
            type: "TRUE_FALSE_GROUP",
            stem: say("Đúng hay sai?", "True or false?"),
            statements: [{ id: "a", text: say("Đạo hàm của x² là 2x", "The derivative of x² is 2x") }, { id: "b", text: "sin²x + cos²x = 2" }, { id: "c", text: "log₁₀ 100 = 2" }],
            ...topic,
          },
          key: { correct: "TFT", explanation: say("sin²x + cos²x luôn bằng 1.", "sin²x + cos²x is always 1."), truth: { a: true, b: false, c: true } },
        },
        {
          item: { id: "h:4", type: "SHORT_ANSWER", stem: say("Giải phương trình 2x + 6 = 14. x bằng bao nhiêu?", "Solve 2x + 6 = 14. What is x?"), short_answer: { max_chars: 24 }, ...topic },
          key: { correct: "4", explanation: say("2x = 14 - 6 = 8, nên x = 4.", "2x = 14 - 6 = 8, so x = 4.") },
        },
        {
          item: { id: "h:5", type: "SINGLE_CHOICE", stem: say("Lực điện tác dụng lên điện tích q trong điện trường E có độ lớn:", "The electric force on a charge q in a field E has magnitude:"), options: [{ id: "A", text: "F = qE" }, { id: "B", text: "F = q/E" }, { id: "C", text: "F = E/q" }], ...topic },
          key: { correct: "A", explanation: say("E = F/q, nên F = qE.", "E = F/q, so F = qE.") },
        },
      ],
    };
  },
};
BANKS.uni = BANKS.g10_12;

interface Rec {
  s: PSession;
  bank: BankSet;
  keys: Key[];
  results: Record<number, PResult>;
  finished?: PReport;
}

function grade(item: PItem, key: Key, given: string): PResult {
  const v = given.trim();
  if (!v || /^-*$/.test(v)) return { correct: null, points: 0, max_points: 1, correct_answer: key.correct };
  if (item.type === "TRUE_FALSE_GROUP") {
    const ids = (item.statements ?? []).map((s) => s.id);
    const rs = ids.map((id, i) => ({ id, given: v[i] === "T", truth: key.truth![id], correct: (v[i] === "T") === key.truth![id] }));
    const right = rs.filter((r) => r.correct).length;
    return { correct: right === ids.length, points: right / ids.length, max_points: 1, correct_answer: key.correct, statement_results: rs };
  }
  const ok = item.type === "SHORT_ANSWER" ? checkShortAnswer(v, [key.correct]) : v === key.correct;
  return { correct: ok, points: ok ? 1 : 0, max_points: 1, correct_answer: key.correct, option_feedback: key.feedback ?? null };
}

/** Who is practising: picks the bank (age band) and its language. Without it: the counting bank, in Vietnamese. */
export type Learner = (token: string) => { age_band: string | null; language: string | null };

export function createMockPractice(opts: { mockMinutes?: number; enough?: boolean; learner?: Learner } = {}): PracticeApi {
  const sessions = new Map<string, Rec>();
  let n = 0;
  const enough = opts.enough ?? true;
  const bankFor = (token: string): BankSet => {
    const u = opts.learner?.(token) ?? { age_band: "g1_5", language: "vi" };
    return (BANKS[u.age_band ?? "g10_12"] ?? BANKS.g10_12)((vi, en) => (u.language === "en" ? en : vi));
  };

  const rec = (id: string) => {
    const r = sessions.get(id);
    if (!r) throw new PracticeError(404, "not_found");
    return r;
  };
  const remaining = (r: Rec) => (r.s.deadline ? Math.max(0, Math.ceil((Date.parse(r.s.deadline) - Date.now()) / 1000)) : null);
  const view = (r: Rec): PSession => {
    const rem = remaining(r);
    return { ...r.s, ...(rem !== null ? { remaining_sec: rem } : {}), answers: JSON.parse(JSON.stringify(r.s.answers)) };
  };
  const finishRec = (r: Rec): PReport => {
    if (r.finished) return r.finished;
    const mock = r.s.kind === "mock";
    let correct = 0;
    let answered = 0;
    r.s.items.forEach((it, i) => {
      const st = r.s.answers[String(i)] ?? { flagged: false };
      const given = (st.answer ?? st.draft ?? "") as string;
      const res = mock ? grade(it, r.keys[i], given) : r.results[i];
      if (res && res.correct !== null && res.correct !== undefined) answered += 1;
      if (res?.correct) correct += 1;
      if (mock) {
        st.answer = given;
        st.correct = res?.correct ?? null;
        r.results[i] = res;
        r.s.answers[String(i)] = st;
      }
    });
    r.s.status = "finished";
    r.finished = {
      session: { id: r.s.id, kind: r.s.kind, subject: r.s.subject, status: "finished" },
      correct,
      total: mock ? r.s.items.length : answered,
      answered,
      score_10: mock ? Math.round((correct / r.s.items.length) * 1000) / 100 : null,
      minutes: 1,
      hints: 0,
      per_topic: [{ topic: "t", title: r.s.items[0]?.topic_title ?? "", right: correct, total: mock ? r.s.items.length : answered, label: "Đang tiến bộ" }],
      takeaway: correct < answered ? { line_vi: r.bank.takeaway.vi, line_en: r.bank.takeaway.en } : null,
      redo: correct < answered ? { line_vi: "Mentor sẽ cho em làm lại câu sai vào thứ Năm, giờ em hay học.", line_en: "Mentor will bring back the ones you missed on Thursday." } : null,
    };
    return r.finished;
  };

  return {
    async home(token) {
      const { course } = bankFor(token);
      const home: PHome = {
        quick: { count: enough ? 5 : 0, minutes: 6, from: [{ course_id: course.id, label: course.title, n: 5 }], seed: "2026-11-07", ...(enough ? {} : { reason: "insufficient_content" }) },
        mocks: [{ profile_id: "demo", title: "Thi thử mẫu", subject: "toan", minutes: opts.mockMinutes ?? 20, items: 5, last_score: null }],
        by_course: [{ course_id: course.id, title: course.title, cover_sha256: null, lessons_range: "Bài 1–2", lessons_from: 1, lessons_to: 2, items: 5 }],
      };
      return home;
    },
    async start(token, body) {
      if (body.source === "quick" && !enough) throw new PracticeError(422, "insufficient_content", "Chưa đủ câu hỏi.", {});
      const mock = body.source.startsWith("mock:");
      for (const r of sessions.values()) if (mock && r.s.kind === "mock" && r.s.status === "active") throw new PracticeError(409, "active_session", null, { session_id: r.s.id });
      n += 1;
      const id = `p-${n}`;
      const bank = bankFor(token);
      const items = bank.entries.map((x, i) => ({ ...x.item, position: i }) as PItem);
      const s: PSession = {
        id,
        kind: mock ? "mock" : "practice",
        subject: mock ? "toan" : "quick",
        status: "active",
        started_at: new Date().toISOString(),
        deadline: mock ? new Date(Date.now() + (opts.mockMinutes ?? 20) * 60000).toISOString() : null,
        position: 0,
        items,
        answers: {},
        disclaimer: mock ? "Đề thi thử để luyện, không phải đề thật." : null,
      };
      sessions.set(id, { s, bank, keys: bank.entries.map((x) => x.key), results: {} });
      return view(sessions.get(id)!);
    },
    async active() {
      for (const r of sessions.values()) if (r.s.status === "active") return view(r);
      return null;
    },
    async get(_t, id) {
      return view(rec(id));
    },
    async answer(_t, id, b) {
      const r = rec(id);
      if (r.s.status !== "active" || (r.s.deadline && remaining(r) === 0)) throw new PracticeError(409, "expired");
      const it = r.s.items[b.position];
      const st = (r.s.answers[String(b.position)] ??= { flagged: false });
      if (r.s.kind === "mock") {
        st.draft = b.answer;
        return { saved: true };
      }
      if (st.checked) return r.results[b.position];
      const res = grade(it, r.keys[b.position], b.answer);
      st.checked = true;
      st.answer = b.answer;
      st.correct = res.correct;
      st.result = res;
      r.results[b.position] = res;
      return res;
    },
    async hint(_t, id, position) {
      const r = rec(id);
      const st = (r.s.answers[String(position)] ??= { flagged: false });
      st.hint = r.bank.hint;
      st.hints_seen = 1;
      return { hint: st.hint };
    },
    async reveal(_t, id, position) {
      const r = rec(id);
      if (!r.s.answers[String(position)]?.checked) throw new PracticeError(409, "not_answered");
      return { explanation: r.keys[position].explanation };
    },
    async flag(_t, id, position, flagged) {
      const r = rec(id);
      (r.s.answers[String(position)] ??= {}).flagged = flagged;
      return { ok: true };
    },
    async tick(_t, id, position) {
      const r = rec(id);
      r.s.position = position;
      const rem = remaining(r);
      if (rem === 0 && r.s.status === "active") return { remaining_sec: 0, expired: true };
      return rem === null ? {} : { remaining_sec: rem };
    },
    async finish(_t, id) {
      return finishRec(rec(id));
    },
    async review(_t, id) {
      const r = rec(id);
      const items: PReviewItem[] = r.s.items.map((it, i) => {
        const st = r.s.answers[String(i)] ?? {};
        const res = r.results[i];
        return { ...it, answer: (st.answer ?? st.draft ?? null) as string | null, correct: res?.correct ?? null, correct_answer: r.keys[i].correct, explanation: r.keys[i].explanation, statement_results: res?.statement_results ?? null };
      });
      return { items };
    },
  };
}
