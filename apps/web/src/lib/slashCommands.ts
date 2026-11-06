/** Slash commands of the chat composer (CONTRACTS 10.5): parsed by the web client. */
import { practiceRoute, mockRoute, progressRoute } from "./practice/routes";
import { fold } from "./text";

export type SubjectId = "math" | "physics" | "english";

const SUBJECT_ALIASES: Record<SubjectId, string[]> = {
  math: ["toan", "math", "maths", "mathematics", "toan hoc"],
  physics: ["ly", "vat ly", "vatly", "physics", "vat li", "li"],
  english: ["anh", "tieng anh", "tienganh", "english", "eng"],
};

/** "Toán", "toan", "math" -> "math"; null when unknown. */
export function parseSubject(raw: string): SubjectId | null {
  const f = fold(raw);
  if (!f) return null;
  for (const [id, names] of Object.entries(SUBJECT_ALIASES) as [SubjectId, string[]][]) {
    if (names.includes(f)) return id;
  }
  return null;
}

export const PRACTICE_MINUTES = [10, 20, 30, 45] as const;

export function snapMinutes(n: number): number {
  return PRACTICE_MINUTES.reduce((best, m) => (Math.abs(m - n) < Math.abs(best - n) ? m : best), PRACTICE_MINUTES[0]);
}

export interface SlashHint {
  command: string;
  usage: string;
  description: string;
}

export const SLASH_HINTS: SlashHint[] = [
  { command: "/luyen", usage: "/luyen [môn] [phút]", description: "Luyện tập, ví dụ /luyen toan 20" },
  { command: "/thithu", usage: "/thithu [môn]", description: "Thi thử có tính giờ" },
  { command: "/tienbo", usage: "/tienbo [môn]", description: "Xem tiến bộ của bạn" },
  { command: "/nhac", usage: "/nhac …", description: "Nhờ mentor nhắc việc, ví dụ /nhac ôn bài lúc 20h" },
  { command: "/nho", usage: "/nho …", description: "Nhờ mentor ghi nhớ điều gì đó" },
];

export type SlashResult =
  | { kind: "none" }
  | { kind: "route"; href: string; label: string }
  | { kind: "send"; text: string }
  | { kind: "error"; message: string };

const SUBJECT_LABEL: Record<SubjectId, string> = { math: "Toán", physics: "Vật lý", english: "Tiếng Anh" };

/** Splits "toan 20", "vat ly 30", "20 anh" into a subject (maybe null) and minutes (maybe undefined). */
function splitArgs(rest: string): { subject: SubjectId | null; unknown: string; minutes?: number } {
  const tokens = rest.trim().split(/\s+/).filter(Boolean);
  let minutes: number | undefined;
  const words: string[] = [];
  for (const t of tokens) {
    const m = /^(\d{1,3})(p|ph|phut|phút)?$/i.exec(t);
    if (m && minutes === undefined) minutes = Number(m[1]);
    else words.push(t);
  }
  const joined = words.join(" ");
  return { subject: joined ? parseSubject(joined) : null, unknown: joined, minutes };
}

/** Parses composer text. Anything not starting with a known command is `{kind: "none"}` (sent as a normal message). */
export function parseSlash(input: string): SlashResult {
  const text = input.trim();
  if (!text.startsWith("/")) return { kind: "none" };
  const m = /^\/(\S*)\s*([\s\S]*)$/.exec(text);
  if (!m) return { kind: "none" };
  const cmd = fold(m[1]);
  const rest = m[2];
  switch (cmd) {
    case "nhac":
    case "nho":
      // Sent to the mentor as a normal message (the leading slash stays, the mentor reads it as intent).
      return rest.trim() ? { kind: "send", text } : { kind: "error", message: `Hãy viết nội dung sau /${cmd}, ví dụ “/${cmd} ôn bài lúc 20h”.` };
    case "luyen": {
      const a = splitArgs(rest);
      if (a.unknown && !a.subject) return { kind: "error", message: `Chưa biết môn “${a.unknown}”. Thử: toán, lý, anh.` };
      const minutes = a.minutes !== undefined ? snapMinutes(a.minutes) : undefined;
      return {
        kind: "route",
        href: practiceRoute({ subject: a.subject ?? undefined, minutes }),
        label: `Mở luyện tập${a.subject ? ` ${SUBJECT_LABEL[a.subject]}` : ""}${minutes ? ` ${minutes} phút` : ""}`,
      };
    }
    case "thithu": {
      const a = splitArgs(rest);
      if (a.unknown && !a.subject) return { kind: "error", message: `Chưa biết môn “${a.unknown}”. Thử: toán, lý, anh.` };
      return {
        kind: "route",
        href: mockRoute({ subject: a.subject ?? undefined }),
        label: `Mở thi thử${a.subject ? ` ${SUBJECT_LABEL[a.subject]}` : ""}`,
      };
    }
    case "tienbo": {
      const a = splitArgs(rest);
      if (a.unknown && !a.subject) return { kind: "error", message: `Chưa biết môn “${a.unknown}”. Thử: toán, lý, anh.` };
      return { kind: "route", href: progressRoute(a.subject ?? undefined), label: "Mở tiến bộ" };
    }
    default:
      return { kind: "none" };
  }
}

/** Hints to show while the learner types "/…" (first word only). Empty when the text is not a slash start. */
export function slashHintsFor(input: string): SlashHint[] {
  if (!/^\/\S*$/.test(input)) return [];
  const typed = fold(input.slice(1));
  return SLASH_HINTS.filter((h) => h.command.slice(1).startsWith(typed));
}
