import { fold } from "../../../lib/text";

/** Pure helpers of the village's chat tray (kept apart from the screen so they can be tested). */

export type TextRoute = "help" | "notes" | "mock" | "practice" | "goal" | "chat";

/** A "how do I use the app" question needs an app word; a bare "thế nào" or "làm sao" is a subject question (chicken chat). */
const APP_WORD = /(\bapp\b|ứng dụng|\blàng\b|\bgà\b|chuồng|đấu trường|phòng tự học|chợ gà|cài đặt|điểm kinh nghiệm|kinh nghiệm|lên cấp|cấp độ|\bnút\b|màn hình|trang này|giao diện|chụp vở|nhắc|thông báo|lịch tuần|\bvillage\b|\bcoop\b|\bchicken\b|\barena\b|study room|settings|\bbutton\b|\bscreen\b|level up|\bxp\b)/i;
const HOW = /(ở đâu|nút nào|chỗ nào|cách dùng|dùng .*(app|ứng dụng)|làm sao|thế nào|như thế nào|sao để|where is|where do|how do i|how do you|how to use|how can i)/i;
const HELP_ALWAYS = /(cách dùng|dùng app|dùng ứng dụng|how to use)/i;
/** "… ở đâu?" about one of the village's places is a way-finding question even without an app word. */
const WHERE = /(ở đâu|chỗ nào|nút nào|where is|where are|where do|where can)/i;
const PLACE = /(thi thử|đề thật|đề thi|thư viện|tiến độ|bảng tin|mục tiêu|vở ghi|mock exam|real exam|library|progress)/i;
const MOCK = /(thi thử|đề thật|đề thi|mock exam|real exam)/i;
const PRACTICE = /^(cho (em|mình|tôi) )?(luyện|ôn)|^practi[cs]e|^review/i;
const NOTES = /(chụp vở|vở ghi|ảnh vở|photo (of )?my notes|my notes|\bnotes?\b)/i;
const GOAL = /(mục tiêu|muốn (được|đạt)|\bgoal\b|i want an? \d)/i;

/**
 * What a line typed in the box means. Anything that is not one of the app's own errands goes to the chicken (chat).
 * The little ones (grade 1-5) have no notes and no mock exams.
 */
export function routeText(text: string, kid = false): TextRoute {
  const s = text.trim();
  if (HELP_ALWAYS.test(s) || (HOW.test(s) && APP_WORD.test(s)) || (WHERE.test(s) && PLACE.test(s))) return "help";
  if (!kid && NOTES.test(s)) return "notes";
  if (!kid && MOCK.test(s)) return "mock";
  if (PRACTICE.test(s)) return "practice";
  if (GOAL.test(s)) return "goal";
  return "chat";
}

/**
 * Streamed Markdown with a formula still being typed: an unclosed `$...`, `$$...` or `\(...` at the end is held back until
 * it closes, so the bubble never flashes raw TeX (`$O(n`) between two deltas.
 */
export function streamSafeMd(md: string): string {
  let s = md;
  const cut = (i: number) => (s = s.slice(0, i).trimEnd());
  const dd = [...s.matchAll(/\$\$/g)];
  if (dd.length % 2 === 1) cut(dd[dd.length - 1].index!);
  else {
    const rest = s.replace(/\$\$[\s\S]*?\$\$/g, (m) => " ".repeat(m.length));
    const one = [...rest.matchAll(/(?<!\\)\$/g)];
    if (one.length % 2 === 1) cut(one[one.length - 1].index!);
  }
  const open = s.lastIndexOf("\\(");
  if (open >= 0 && s.indexOf("\\)", open) < 0) cut(open);
  const sq = s.lastIndexOf("\\[");
  if (sq >= 0 && s.indexOf("\\]", sq) < 0) cut(sq);
  return s.replace(/\\[a-zA-Z]*$/, "");
}

/** Local answers about the village itself (the guide map of the chicken): topic key and its keywords (without accents). */
const TOPICS: [string, string[]][] = [
  ["arena", ["dau truong", "de that", "de thi", "arena", "real exam", "paper"]],
  ["study", ["phong tu hoc", "tu hoc", "dong ho", "study room", "focus", "timer"]],
  ["market", ["cho ga", "nhan ga", "them ga", "market", "take a chicken", "new chicken"]],
  ["notes", ["chup vo", "vo ghi", "notes", "notebook"]],
  ["week", ["tuan", "lich", "tien do", "muc tieu", "week", "plan", "goal", "progress"]],
  ["remind", ["nhac", "thong bao", "remind", "notification"]],
  ["settings", ["cai dat", "ngon ngu", "nen toi", "settings", "language", "dark"]],
  ["photo", ["chup bai", "giai bai", "bai tap", "homework", "snap", "solve"]],
];
export function helpTopic(question: string): string | null {
  const q = fold(question);
  let best: string | null = null;
  let score = 0;
  for (const [key, words] of TOPICS) {
    const s = words.filter((w) => q.includes(w)).length;
    if (s > score) {
      best = key;
      score = s;
    }
  }
  return best;
}

/** An instant `dayOffset` days from `now` at "HH:MM". */
export function at(now: Date, dayOffset: number, time: string): Date {
  const [h, m] = time.split(":").map(Number);
  const d = new Date(now);
  d.setDate(d.getDate() + dayOffset);
  d.setHours(h, m, 0, 0);
  return d;
}

export interface LaterOption {
  key: "in1h" | "tonight" | "tomorrow";
  /** "HH:MM" for tonight and tomorrow */
  time?: string;
  when: Date;
}
/**
 * The three "Để sau" choices: in an hour, this evening (the session's own slot when it is still ahead, else 20:00 until
 * 19:00), and tomorrow at the usual slot. `sessionStart` is the planned start ("19:30") when the session is today.
 */
export function laterOptions(now: Date, opts: { sessionStart?: string | null; sessionToday?: boolean; kid?: boolean }): LaterOption[] {
  const slot = opts.sessionStart && opts.sessionStart >= "06:30" ? opts.sessionStart : opts.kid ? "18:00" : "19:30";
  const out: LaterOption[] = [{ key: "in1h", when: new Date(now.getTime() + 3600000) }];
  const tonight = opts.sessionToday && at(now, 0, slot).getTime() > now.getTime() + 30 * 60000 ? slot : now.getHours() < 19 ? "20:00" : null;
  if (tonight) out.push({ key: "tonight", time: tonight, when: at(now, 0, tonight) });
  out.push({ key: "tomorrow", time: slot, when: at(now, 1, slot) });
  return out;
}

/** Which week day (0 = Monday) of the plan's `days` list is `today`. */
export function todayIndex(days: string[], today: string): number {
  return Math.max(0, days.indexOf(today));
}

export const pad2 = (n: number) => String(n).padStart(2, "0");
export const hhmm = (d: Date) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;

/** A slow server call: after `slowMs` a soft "taking a while" line (with Cancel), at `limitMs` the call is dropped. */
export interface SlowWatch {
  cancelled: boolean;
  timedOut: boolean;
  cancel(): void;
  stop(): void;
}
export function watchSlow(c: AbortController, onSlow: () => void, slowMs = 15000, limitMs = 50000): SlowWatch {
  const w: SlowWatch = {
    cancelled: false,
    timedOut: false,
    cancel: () => {
      w.cancelled = true;
      c.abort();
    },
    stop: () => {
      clearTimeout(a);
      clearTimeout(b);
    },
  };
  const a = setTimeout(onSlow, slowMs);
  const b = setTimeout(() => {
    w.timedOut = true;
    c.abort();
  }, limitMs);
  return w;
}
