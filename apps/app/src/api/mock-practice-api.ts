import { PracticeError, type PXp, type PHome, type PItem, type PReport, type PResult, type PReviewItem, type PSession, type PracticeApi } from "./practice";
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

/** Three step items (tiles, pairs, order), appended to the bank with `createMockPractice({ steps: true })`. */
function stepEntries(say: Say): Entry[] {
  const topic = { topic: "t", topic_title: say("Điện trường", "Electric fields") };
  return [
    {
      item: {
        id: "s:1",
        type: "FILL_TILES",
        stem: "E = k · |q| / {{gap}}",
        parts: [{ id: "a", text: "r" }, { id: "b", text: "q" }, { id: "c", text: "r²" }, { id: "d", text: "k" }],
        ...topic,
      },
      key: { correct: JSON.stringify({ gaps: ["c"] }), explanation: say("E tỉ lệ nghịch với bình phương khoảng cách.", "E falls with the square of the distance.") },
    },
    {
      item: {
        id: "s:2",
        type: "MATCH_PAIRS",
        stem: say("Nối đại lượng với đơn vị", "Match each quantity with its unit"),
        parts: [
          { id: "l1", text: say("Cường độ E", "Field E"), side: "left" },
          { id: "l2", text: say("Lực điện F", "Force F"), side: "left" },
          { id: "r1", text: "V/m", side: "right" },
          { id: "r2", text: "N", side: "right" },
        ],
        ...topic,
      },
      key: { correct: JSON.stringify({ pairs: { l1: "r1", l2: "r2" } }), explanation: say("E đo bằng V/m, lực bằng N.", "E is in V/m, force in N.") },
    },
    {
      item: {
        id: "s:3",
        type: "ORDER_STEPS",
        stem: say("Xếp các bước giải bài", "Put the steps of a solution in order"),
        parts: [{ id: "a", text: say("Đọc đề", "Read the problem") }, { id: "b", text: say("Chọn công thức", "Pick the formula") }, { id: "c", text: say("Thay số", "Plug in numbers") }, { id: "d", text: say("Ra kết quả", "Get the result") }],
        ...topic,
      },
      key: { correct: JSON.stringify({ order: ["a", "b", "c", "d"] }), explanation: say("Đọc, chọn công thức, thay số, rồi tính.", "Read, pick the formula, plug in, then work it out.") },
    },
  ];
}

const norm = (v: unknown): unknown => (Array.isArray(v) ? v.map(norm) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)).map(([k, x]) => [k, norm(x)])) : v);
function sameJson(a: string, b: string): boolean {
  try {
    return JSON.stringify(norm(JSON.parse(a))) === JSON.stringify(norm(JSON.parse(b)));
  } catch {
    return false;
  }
}

/** Arena papers of the mock: id `thpt-<chicken>-...`; the boss follows the subject like the gateway's table. */
const BOSS: Record<string, { name_vi: string; name_en: string; art: string }> = {
  toan: { name_vi: "Quái Sai Số", name_en: "The Slip-Up Monster", art: "boss-toan" },
  van: { name_vi: "Bóng Lạc Đề", name_en: "The Off-Topic Phantom", art: "boss-van" },
  anh: { name_vi: "Quái Lỗi Ngữ Pháp", name_en: "The Grammar-Slip Monster", art: "boss-anh" },
};
function paperOf(id: string): NonNullable<PSession["paper"]> {
  const c = id.split("-")[1] ?? "toan";
  const chicken = c === "ly" ? "li" : c;
  const boss = BOSS[chicken === "anh" ? "anh" : chicken === "van" ? "van" : "toan"];
  return { id, kind: "thpt", chicken, title_vi: `Đề mẫu ${id}`, title_en: `Sample ${id}`, placeholder: true, boss };
}

interface Rec {
  s: PSession;
  bank: BankSet;
  keys: Key[];
  results: Record<number, PResult>;
  finished?: PReport;
  fixed: Set<string>;
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
  if (item.type === "FILL_TILES" || item.type === "MATCH_PAIRS" || item.type === "ORDER_STEPS") {
    const same = sameJson(v, key.correct);
    return { correct: same, points: same ? 1 : 0, max_points: 1, correct_answer: key.correct };
  }
  const ok = item.type === "SHORT_ANSWER" ? checkShortAnswer(v, [key.correct]) : v === key.correct;
  return { correct: ok, points: ok ? 1 : 0, max_points: 1, correct_answer: key.correct, option_feedback: key.feedback ?? null };
}

/** Who is practising: picks the bank (age band) and its language. Without it: the counting bank, in Vietnamese. */
export type Learner = (token: string) => { age_band: string | null; language: string | null };

export function createMockPractice(opts: { mockMinutes?: number; enough?: boolean; learner?: Learner; steps?: boolean } = {}): PracticeApi {
  const sessions = new Map<string, Rec>();
  let n = 0;
  const enough = opts.enough ?? true;
  const bankFor = (token: string): BankSet => {
    const u = opts.learner?.(token) ?? { age_band: "g1_5", language: "vi" };
    const say: Say = (vi, en) => (u.language === "en" ? en : vi);
    const bank = (BANKS[u.age_band ?? "g10_12"] ?? BANKS.g10_12)(say);
    return opts.steps ? { ...bank, entries: [...bank.entries, ...stepEntries(say)] } : bank;
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
    const score10 = mock ? Math.round((correct / r.s.items.length) * 1000) / 100 : null;
    const paper = r.s.paper;
    const xp: PXp[] = !mock || !answered ? [] : paper ? [{ chicken: paper.chicken, source: "paper_submit", amount: 40, level_up: false }, ...((score10 ?? 0) >= 5 ? [{ chicken: paper.chicken, source: "boss_beaten", amount: 50, level_up: false }] : [])] : [{ chicken: "toan", source: "mock_submit", amount: 40, level_up: false }];
    r.finished = {
      ...(paper ? { boss: { name: paper.boss.name_vi, ...paper.boss, hp: r.s.items.length, damage: correct, beaten: (score10 ?? 0) >= 5 } } : {}),
      xp,
      session: { id: r.s.id, kind: r.s.kind, subject: r.s.subject, status: "finished" },
      correct,
      total: mock ? r.s.items.length : answered,
      answered,
      score_10: score10,
      minutes: 1,
      hints: 0,
      per_topic: [{ topic: "t", title: r.s.items[0]?.topic_title ?? "", right: correct, total: mock ? r.s.items.length : answered, label: "Đang tiến bộ" }],
      takeaway: correct < answered ? { line_vi: r.bank.takeaway.vi, line_en: r.bank.takeaway.en } : null,
      wrong: r.s.items.flatMap((it, i) => (r.results[i]?.correct === false ? [{ position: i, item_id: it.id, type: it.type, chosen: (r.s.answers[String(i)]?.answer ?? null) as string | null }] : [])),
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
    async courseLevels(_token, courseId) {
      return {
        course_id: courseId,
        title: "",
        min_items: 3,
        levels: [
          { level: 1, items: 6, studied: 6, answered: 6, correct: 6, solid: true },
          { level: 2, items: 6, studied: 6, answered: 3, correct: 2, solid: false },
          { level: 3, items: 4, studied: 2, answered: 0, correct: 0, solid: false },
          { level: 4, items: 2, studied: 0, answered: 0, correct: 0, solid: false },
        ],
        suggested: 2,
        mocks: [{ profile_id: "demo", title: "Thi thử mẫu", subject: "toan", minutes: opts.mockMinutes ?? 20, items: 5, last_score: null }],
      };
    },
    async start(token, body) {
      if (body.source === "quick" && !enough) throw new PracticeError(422, "insufficient_content", "Chưa đủ câu hỏi.", {});
      const mock = body.source.startsWith("mock:") || body.source.startsWith("paper:") || body.source.startsWith("course-mock:");
      for (const r of sessions.values()) if (mock && r.s.kind === "mock" && r.s.status === "active") throw new PracticeError(409, "active_session", null, { session_id: r.s.id });
      n += 1;
      const id = `p-${n}`;
      const bank = bankFor(token);
      const items = bank.entries.map((x, i) => ({ ...x.item, position: i }) as PItem);
      const s: PSession = {
        id,
        kind: mock ? "mock" : "practice",
        subject: mock ? "toan" : "quick",
        source: body.source,
        ...(mock ? { minutes: opts.mockMinutes ?? 20 } : {}),
        ...(body.source.startsWith("paper:") ? { paper: paperOf(body.source.slice(6)) } : {}),
        status: "active",
        started_at: new Date().toISOString(),
        deadline: mock ? new Date(Date.now() + (opts.mockMinutes ?? 20) * 60000).toISOString() : null,
        position: 0,
        items,
        answers: {},
        disclaimer: mock ? "Đề thi thử để luyện, không phải đề thật." : null,
      };
      sessions.set(id, { s, bank, keys: bank.entries.map((x) => x.key), results: {}, fixed: new Set() });
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
      return res.correct ? { ...res, xp: [{ chicken: "toan", source: "practice_right", amount: 2, level_up: false }] } : res;
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
    async fix(_t, id, b) {
      const r = rec(id);
      if (r.s.status === "active") throw new PracticeError(409, "not_finished");
      const i = r.s.items.findIndex((it) => it.id === b.item_id);
      if (i < 0 || r.results[i]?.correct !== false) throw new PracticeError(422, "not_wrong");
      if (r.fixed.has(b.item_id)) throw new PracticeError(409, "already_fixed");
      r.fixed.add(b.item_id);
      const res = grade(r.s.items[i], r.keys[i], b.answer);
      if (res.correct) return { correct: true, xp: [{ chicken: "toan", source: "fix_right", amount: 3, level_up: false }] };
      return { correct: false, right: r.keys[i].correct, explanation: r.keys[i].explanation, ...(r.keys[i].feedback?.[b.answer] ? { note: r.keys[i].feedback![b.answer] } : {}) };
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
