/**
 * Learner-facing cleanup of what the agent writes into the workspace: source refs, skill ids and file paths
 * stay in the files, but the learner reads plain sentences. Pure functions, no I/O.
 */

/** Words that open a source ref in parentheses: "(chat 27/10)", "(events 6/11)", "(nguồn: ...)", "(learning/math/...)". */
const REF_HEAD = "(?:chat|events?|nguồn|ảnh|onboarding|learning|goals|me|research|inbox|reports|sessions|xem)";
const REF = new RegExp(`\\s*[\\(（]\\s*${REF_HEAD}\\b[^)）]*[\\)）]`, "giu");
const SKILL_ID = /\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b\.?/g;
const FILE_PATH = /(?:`[^`\s]*\/[^`\s]*`|\b(?:[\w-]+\/)+[\w.-]+\.(?:md|jsonl?|ya?ml|txt|png|jpe?g|pdf)\b)/g;

/** A "d/m" date inside the first source ref, e.g. "(chat 1/11)" -> "1/11". */
export function refDate(text: string): { day: number; month: number } | null {
  for (const m of text.matchAll(REF)) {
    const d = m[0].match(/(\d{1,2})\/(\d{1,2})/);
    if (d) return { day: Number(d[1]), month: Number(d[2]) };
  }
  return null;
}

/** "hôm nay", "hôm qua", "3 ngày trước", "2 tuần trước", else "d/m". `now` is injectable for tests. */
export function relativeDay(d: { day: number; month: number }, now: Date = new Date()): string {
  let year = now.getFullYear();
  const at = (y: number) => new Date(y, d.month - 1, d.day).getTime();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (at(year) > today + 86_400_000) year -= 1;
  const days = Math.round((today - at(year)) / 86_400_000);
  if (days <= 0) return "hôm nay";
  if (days === 1) return "hôm qua";
  if (days < 7) return `${days} ngày trước`;
  if (days < 30) return `${Math.floor(days / 7)} tuần trước`;
  return `${d.day}/${d.month}`;
}

/** Workspace files the mentor names in learner-visible text, said the way the learner knows them. */
const FRIENDLY_FILES: [RegExp, string][] = [
  [/`?(?:[\w-]+\/)*mistakes\.md`?/g, "sổ lỗi"],
  [/`?(?:[\w-]+\/)*review-queue\.md`?/g, "lịch ôn"],
  [/`?(?:[\w-]+\/)*skills\.md`?/g, "bảng kỹ năng"],
  [/`?(?:[\w-]+\/)*practice-log\.md`?/g, "nhật ký luyện tập"],
];

/** Drops source refs and file paths from a line: "Thích học tối (chat 1/11)" -> "Thích học tối". */
export function stripRefs(text: string): string {
  let t = text;
  for (const [re, word] of FRIENDLY_FILES) t = t.replace(re, word);
  return t
    .replace(REF, "")
    .replace(FILE_PATH, "")
    .replace(/\(\s*\)/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

/** A mistakes.md bullet as one short sentence: no tag, skill id, source ref or repeat counter. */
export function mistakeSentence(line: string): string {
  let t = line
    .replace(/^\s*\[[^\]]*\]\s*/, "")
    .replace(REF, "")
    .replace(/chưa gắn kỹ năng\.?/gi, "")
    .replace(/\s*×\s*\d+.*$/u, "")
    .replace(SKILL_ID, "")
    .replace(/\*\*/g, "");
  t = stripRefs(t).replace(/[\s.,;:]+$/u, "");
  return t ? t.charAt(0).toUpperCase() + t.slice(1) + "." : "";
}

/** Current mistakes only: "Đang gặp" section if present, never "Đã khắc phục". At most `max` sentences. */
export function parseMistakes(content: string, max = 5): string[] {
  let section: string | null = null;
  const hasCurrent = /^#{2,6}\s*đang gặp/im.test(content);
  const out: string[] = [];
  for (const l of content.split(/\r?\n/)) {
    const h = l.match(/^#{1,6}\s+(.*)$/);
    if (h) {
      section = h[1].trim().toLowerCase();
      continue;
    }
    const m = l.match(/^\s*[-*]\s+(.*)$/);
    if (!m) continue;
    if (/khắc phục/.test(section ?? "")) continue;
    if (hasCurrent && !/đang gặp/.test(section ?? "")) continue;
    const s = mistakeSentence(m[1]);
    if (s) out.push(s);
  }
  return out.slice(0, max);
}

export interface DueSkill {
  title: string;
  /** ISO date (YYYY-MM-DD) */
  due: string;
}

function toIso(raw: string, now: Date): string | null {
  const iso = raw.match(/\d{4}-\d{2}-\d{2}/);
  if (iso) return iso[0];
  const d = raw.match(/(\d{1,2})\/(\d{1,2})(?:\/(\d{4}))?/);
  if (!d) return null;
  const y = d[3] ? Number(d[3]) : now.getFullYear();
  return `${y}-${d[2].padStart(2, "0")}-${d[1].padStart(2, "0")}`;
}

/** review-queue.md table (bkt_update: skill_id | Tên | Mastery | Đến hạn | Ghi chú; older: Kỹ năng | Đến hạn | Lý do). */
export function parseDueSkills(content: string, now: Date = new Date()): DueSkill[] {
  const rows = content
    .split(/\r?\n/)
    .filter((l) => l.trim().startsWith("|"))
    .map((l) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim()));
  if (rows.length < 3) return [];
  const head = rows[0].map((h) => h.toLowerCase());
  const iDue = head.findIndex((h) => /đến hạn|due/.test(h));
  let iTitle = head.findIndex((h) => /^(tên|kỹ năng|title|name)/.test(h));
  if (iDue < 0) return [];
  if (iTitle < 0) iTitle = head[0] === "skill_id" ? 1 : 0;
  const out: DueSkill[] = [];
  for (const r of rows.slice(2)) {
    const due = toIso(r[iDue] ?? "", now);
    const title = (r[iTitle] ?? "").replace(/\*\*/g, "");
    if (due && title) out.push({ title, due });
  }
  return out.sort((a, b) => a.due.localeCompare(b.due));
}

/** "hôm nay", "ngày mai", "đã đến hạn", else "d/m" for an ISO date. */
export function dueLabel(iso: string, today: string): string {
  const diff = Math.round((Date.parse(`${iso}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000);
  if (diff < 0) return "đã đến hạn";
  if (diff === 0) return "hôm nay";
  if (diff === 1) return "ngày mai";
  const [, m, d] = iso.split("-");
  return `${Number(d)}/${Number(m)}`;
}

/** An inbound address on a real domain (not the dev-only `.local`). */
export function hasRealInboundDomain(addr: string | null | undefined): boolean {
  const domain = addr?.split("@")[1]?.toLowerCase();
  return !!domain && domain.includes(".") && !/\.(local|localhost|test|invalid|example)$/.test(domain);
}

/** A tool step's text without file paths ("Đã đọc me/now.md" -> "Đã đọc tệp"). */
export function plainStep(summary: string): string {
  return summary.replace(/(?:[\w-]+\/)+[\w.-]+/g, "tệp");
}

/** Does a tool summary describe a failure (the harness words them "Lỗi: …")? */
export function isToolFailure(summary: string): boolean {
  return /^\s*lỗi\b|công cụ không tồn tại|chưa khả dụng/i.test(summary);
}

/** One neutral line for the whole tool activity of a turn. */
export function toolHeadline(tools: { tool: string; status: "running" | "done" }[]): string {
  const running = tools.filter((t) => t.status === "running");
  const last = (running[running.length - 1] ?? tools[tools.length - 1])?.tool ?? "";
  const verb = /run_|sympy|check|script|python/.test(last)
    ? "kiểm tra"
    : /write|edit|move|delete|note|schedule|notify|card/.test(last)
      ? "ghi chép"
      : "tra cứu";
  return running.length > 0 ? `Mentor đang ${verb}…` : `Mentor đã ${verb} xong`;
}

export interface WeekPlan {
  /** the file has a "Việc của người học" heading, so checklist parsing can be limited to it */
  hasLearnerSection: boolean;
  /** learner-facing markdown: no title, comments, "Mentor sẽ làm" or "Điều chỉnh", refs stripped */
  text: string;
  /** bullets of the learner section that have no checkbox (cannot be ticked), cleaned */
  plain: string[];
}

/** goals/plans/this-week.md as the learner should see it: only their own tasks. */
export function weekPlan(content: string): WeekPlan {
  const body = content.replace(/<!--[\s\S]*?-->/g, "");
  const hasLearnerSection = /^#{2,6}\s*việc của người học/im.test(body);
  let skip = false;
  let inLearner = false;
  const keep: string[] = [];
  const plain: string[] = [];
  for (const l of body.split(/\r?\n/)) {
    const h = l.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const title = h[2].trim().toLowerCase();
      skip = /mentor sẽ làm|điều chỉnh/.test(title);
      inLearner = /việc của người học/.test(title);
      if (h[1].length === 1 || skip || (hasLearnerSection && inLearner)) continue;
    }
    if (skip) continue;
    if (hasLearnerSection && !inLearner) continue;
    keep.push(stripRefs(l));
    const b = l.match(/^\s*[-*]\s+(?!\[[ xX]\])(.*)$/);
    if (b && stripRefs(b[1])) plain.push(stripRefs(b[1]));
  }
  return { hasLearnerSection, text: keep.join("\n").trim(), plain };
}
