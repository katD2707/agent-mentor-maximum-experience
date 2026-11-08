import type { AskCard, AskEvent, AskRequest } from "./ask";
import { FIXTURES, treeOf } from "./mock-courses";
import { fold } from "../lib/text";

/**
 * Scripted POST /ask for VITE_API_MOCK=1: the same events, in the same order, as the gateway (CONTRACTS.md section 13).
 *   text about learning      -> answer + course cards
 *   text with a maths task   -> problem + solution (last step withheld)
 *   a photo                  -> two problems to choose from (set localStorage `mentor.mock.badphoto` = "1" for the retake flow)
 *   audio                    -> transcript of a learning question, then the cards
 *   anything else            -> one redirect sentence
 */

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("aborted", "AbortError"));
    const id = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => (clearTimeout(id), reject(new DOMException("aborted", "AbortError"))), { once: true });
  });

interface Thread {
  problem?: { id: string; label: string; text: string };
  steps: { title: string; md: string }[];
}
const threads = new Map<string, Thread>();

const PROBLEMS = [
  { id: "p3b", label: "Bài 3b", text: "Cho cấp số cộng có $u_1 = 3$, $d = 4$. Tính tổng 20 số hạng đầu." },
  { id: "p4", label: "Bài 4", text: "Tìm $x$ biết $2, x, 18$ lập thành cấp số nhân." },
];
const SOLUTIONS: Record<string, { steps: { title: string; md: string }[]; tip: string }> = {
  p3b: {
    steps: [
      { title: "Nhớ lại công thức tổng", md: "$$S_n = \\frac{n\\,(2u_1 + (n-1)d)}{2}$$" },
      { title: "Thay n = 20, u₁ = 3, d = 4", md: "$$S_{20} = \\frac{20\\,(2\\cdot 3 + 19\\cdot 4)}{2} = 10\\,(6 + 76)$$" },
      { title: "Tính kết quả", md: "$$S_{20} = 10 \\cdot 82 = 820$$" },
    ],
    tip: "Tính (n − 1)d = 19 · 4 = 76 trước, rồi mới cộng số hạng đầu.",
  },
  p4: {
    steps: [
      { title: "Dùng tính chất cấp số nhân", md: "$$x^2 = 2 \\cdot 18 = 36$$" },
      { title: "Lấy căn hai vế", md: "$$x = 6 \\quad\\text{hoặc}\\quad x = -6$$" },
    ],
    tip: "Hai nghiệm đều thỏa, nhớ viết cả hai.",
  },
};

function cards(): AskCard[] {
  return FIXTURES.slice(0, 3).map(({ meta, pack }) => {
    const tree = treeOf(pack);
    const first = tree[0]?.lessons[0];
    return {
      course_id: meta.id,
      title: meta.title,
      cover_sha256: "0".repeat(64),
      description_short: meta.description_short,
      language: meta.language,
      lessons_count: meta.lessons_count,
      est_minutes: meta.est_minutes,
      tree,
      age_band: meta.age_band,
      enrolled: false,
      first_lesson: first ? { lesson_id: first.id, title: first.title } : null,
    };
  });
}

type Emit = (e: AskEvent) => void;

async function solve(id: string, th: Thread, emit: Emit, signal?: AbortSignal, simpler = false) {
  const p = PROBLEMS.find((x) => x.id === id) ?? PROBLEMS[0];
  const sol = SOLUTIONS[p.id] ?? SOLUTIONS.p3b;
  th.problem = p;
  th.steps = sol.steps;
  emit({ event: "intent", data: { intent: "solve" } });
  emit({ event: "status", data: { stage: "solving" } });
  await sleep(700, signal);
  emit({ event: "problem", data: p });
  await sleep(250, signal);
  if (simpler) emit({ event: "answer", data: { text: "Mình giải lại từng bước nhỏ hơn nhé." } });
  const shown = sol.steps.slice(0, -1);
  emit({
    event: "solution",
    data: { problem_id: p.id, problem_md: p.text, steps: shown.length ? shown : sol.steps, last_step_withheld: shown.length > 0, tip: sol.tip },
  });
}

export async function mockAskStream(req: AskRequest, onEvent: Emit, signal?: AbortSignal): Promise<void> {
  const tid = req.thread_id || `t-${Math.random().toString(36).slice(2, 8)}`;
  const th = threads.get(tid) ?? { steps: [] };
  threads.set(tid, th);
  const emit: Emit = (e) => {
    if (signal?.aborted) throw new DOMException("aborted", "AbortError");
    onEvent(e);
  };
  emit({ event: "thread", data: { thread_id: tid } });
  try {
    await sleep(250, signal);
    let text = (req.text ?? "").trim();

    if (req.action === "last_step") {
      const last = th.steps[th.steps.length - 1];
      if (!last) emit({ event: "message", data: { kind: "no_last_step", text: "Chưa có lời giải nào để xem bước cuối." } });
      else emit({ event: "last_step", data: { problem_id: th.problem?.id, step: last } });
    } else if (req.action === "similar") {
      emit({ event: "intent", data: { intent: "solve" } });
      emit({ event: "status", data: { stage: "solving" } });
      await sleep(800, signal);
      emit({
        event: "similar",
        data: {
          items: [
            { problem_md: "Cấp số cộng có $u_1 = 2$, $d = 3$. Tính $S_{10}$.", answer_md: "$S_{10} = 5\\,(4 + 27) = 155$" },
            { problem_md: "Cấp số cộng có $u_1 = 5$, $d = 2$. Tính $S_{15}$.", answer_md: "$S_{15} = 15\\,(5 + 14) = 285$" },
            { problem_md: "Cấp số cộng có $u_1 = 1$, $d = 6$. Tính $S_{8}$.", answer_md: "$S_{8} = 4\\,(2 + 42) = 176$" },
          ],
        },
      });
    } else if (req.action === "simpler") {
      await solve(th.problem?.id ?? "p3b", th, emit, signal, true);
    } else if (req.action === "choose") {
      await solve(req.problem_id ?? "p3b", th, emit, signal);
    } else if (req.image) {
      emit({ event: "status", data: { stage: "reading" } });
      await sleep(1100, signal);
      let bad = false;
      try {
        bad = localStorage.getItem("mentor.mock.badphoto") === "1";
      } catch {
        /* no storage */
      }
      if (bad) {
        emit({ event: "quality", data: { ok: false, reasons: ["too_dark", "missing_area"] } });
        emit({
          event: "message",
          data: {
            kind: "retake",
            text: "Bài 3 đọc được. Bài 4 bị tối quá, chưa ra chữ.",
            where: "nửa dưới ảnh",
            reasons: ["too_dark"],
            tips: ["Bật đèn hoặc ra gần cửa sổ", "Giữ máy thật yên", "Giữ máy thẳng phía trên trang giấy"],
            offer_readable: true,
          },
        });
        emit({ event: "choices", data: { problems: [PROBLEMS[0]], reason: "partial" } });
      } else {
        emit({ event: "quality", data: { ok: true, reasons: [] } });
        emit({ event: "choices", data: { problems: PROBLEMS, reason: "multiple" } });
      }
    } else if (req.audio) {
      emit({ event: "status", data: { stage: "listening" } });
      await sleep(900, signal);
      text = "Em muốn học về điện trường";
      emit({ event: "transcript", data: { text } });
      await learn(emit, signal);
    } else if (!text) {
      emit({ event: "message", data: { kind: "empty", text: "Em gõ câu hỏi hoặc chụp bài nhé." } });
    } else if (/\d|giai|tinh|tim x|solve|bai tap|exercise/.test(fold(text)) && !/muon hoc|hoc ve|learn/.test(fold(text))) {
      await solve("p3b", th, emit, signal);
    } else if (/hoc|dien|on thi|khoa|course|learn|study|field|la gi|what/.test(fold(text))) {
      await learn(emit, signal);
    } else {
      emit({ event: "intent", data: { intent: "other" } });
      await sleep(300, signal);
      emit({ event: "answer", data: { text: "Mình giúp em học và giải bài thôi nhé. Em muốn học gì hôm nay?" } });
    }
  } catch (e) {
    if ((e as DOMException)?.name === "AbortError") throw e;
    emit({ event: "error", data: { code: "internal", message: String(e) } });
  }
  emit({ event: "done", data: { thread_id: tid } });
}

async function learn(emit: Emit, signal?: AbortSignal) {
  emit({ event: "intent", data: { intent: "learn" } });
  await sleep(500, signal);
  const items = cards();
  emit({ event: "answer", data: { text: "Có 3 khóa hợp với em, nên bắt đầu từ " + items[0].title + "." } });
  await sleep(300, signal);
  emit({
    event: "courses",
    data: { items, suggested_all_ages: false, start_with: items[0].first_lesson ? { course_id: items[0].course_id, ...items[0].first_lesson } : null },
  });
}
