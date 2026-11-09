import type { MascotTourStep } from "@mentor/mentor-mascot/mascot";
import type { Role } from "../api/types";
import { GUIDES } from "./guides";

/**
 * Mực's first-visit tours: the first time someone opens a screen, Mực walks them through its main parts (3 at most),
 * once. Texts come from GUIDES (lib/guides.ts) by data-guide key; titles live here. Approved in mockups/mascot.js.
 */

type Text = { vi: string; en: string };
const T = (vi: string, en: string): Text => ({ vi, en });

/** The most steps one screen gets, so a tour stays short. */
export const MAX_STEPS = 3;
/** Window event that asks Mực to show the tours again (Settings > "Xem lại từ đầu"). */
export const REPLAY_EVENT = "mentor:tour-replay";
const HELLO = "hello";

/** Areas each screen walks through, in order. Areas not on screen right now are skipped. */
const TOURS: Record<string, string[]> = {
  login: ["login-role"],
  hub: [HELLO, "courses", "settings"],
  courses: ["my-courses", "course-search", "more-courses"],
  "course-search": ["course-search"],
  course: ["course-tree"],
  player: ["player-progress"],
  practice: ["practice-resume", "practice-quick", "practice-mock", "practice-courses"],
  "practice-run": ["practice-progress", "practice-clock", "practice-hint", "practice-flag"],
  ask: ["ask-composer"],
  progress: ["progress-goals", "progress-week", "progress-courses"],
  research: ["research-tabs", "research-search", "research-hero", "research-reading"],
  "research-paper": ["research-summary", "research-ask", "research-related"],
  "gv-home": [HELLO, "drop", "teacher-courses"],
  "gv-course": ["gv-thread", "gv-outline", "gv-compose"],
  "gv-review": ["gv-review", "gv-comments", "gv-publish"],
};

const TITLES: Record<string, Text> = {
  "login-role": T("Chọn vai trò", "Pick your role"),
  courses: T("Khóa học", "Courses"),
  settings: T("Cài đặt", "Settings"),
  "my-courses": T("Khóa của em", "Your courses"),
  "course-search": T("Tìm khóa học", "Find courses"),
  "more-courses": T("Khóa học khác", "Other courses"),
  "course-tree": T("Nội dung khóa", "What's inside"),
  "player-progress": T("Tiến độ bài", "Lesson progress"),
  "practice-resume": T("Bài làm dở", "Left half done"),
  "practice-quick": T("Luyện nhanh", "Quick practice"),
  "practice-mock": T("Thi thử", "Mock exam"),
  "practice-courses": T("Luyện theo khóa", "By course"),
  "practice-progress": T("Số câu đã làm", "Questions done"),
  "practice-clock": T("Đồng hồ", "Clock"),
  "practice-hint": T("Gợi ý", "Hint"),
  "practice-flag": T("Đánh dấu", "Flag"),
  "ask-composer": T("Hỏi Mentor", "Ask Mentor"),
  "progress-goals": T("Mục tiêu", "Goals"),
  "progress-week": T("Lịch tuần", "This week"),
  "progress-courses": T("Từng khóa", "Each course"),
  "research-tabs": T("Bốn chương", "Four chapters"),
  "research-search": T("Tìm paper", "Find papers"),
  "research-hero": T("Đọc tiếp", "Read next"),
  "research-reading": T("Cần đọc", "To read"),
  "research-summary": T("Tóm tắt của bạn", "Your summary"),
  "research-ask": T("Hỏi về paper", "Ask about the paper"),
  "research-related": T("Bài liên quan", "Related papers"),
  drop: T("Gửi bài giảng", "Send a lesson"),
  "teacher-courses": T("Khóa của bạn", "Your courses"),
  "gv-thread": T("Trao đổi với Mentor", "Talk with Mentor"),
  "gv-outline": T("Cấu trúc khóa", "Course outline"),
  "gv-compose": T("Soạn bài", "Compose"),
  "gv-review": T("Bài như học sinh thấy", "As students see it"),
  "gv-comments": T("Nhận xét của bạn", "Your comments"),
  "gv-publish": T("Xuất bản", "Publish"),
};

const hello = (adult: boolean): MascotTourStep => ({
  title: adult ? T("Chào bạn, mình là Mực!", "Hi, I'm Mực!") : T("Chào em, mình là Mực!", "Hi, I'm Mực!"),
  text: adult
    ? T(
        "Lần đầu bạn mở một trang, mình sẽ chỉ nhanh vài chỗ chính. Sau đó cần gì cứ bấm vào mình.",
        "The first time you open a page I'll point out its main parts. After that, tap me whenever you need help.",
      )
    : T(
        "Lần đầu em mở một trang, mình sẽ chỉ nhanh vài chỗ chính. Sau đó cần gì cứ bấm vào mình.",
        "The first time you open a page I'll point out its main parts. After that, tap me whenever you need help.",
      ),
});

/** "Khóa học: bài hôm nay…" under the title "Khóa học" reads "Bài hôm nay…": the bubble already shows the name. */
function untitled(text: Text, title: Text): Text {
  const cut = (s: string, name: string) => {
    if (!s.toLowerCase().startsWith(name.toLowerCase() + ": ")) return s;
    const rest = s.slice(name.length + 2);
    return rest.charAt(0).toLocaleUpperCase() + rest.slice(1);
  };
  return { vi: cut(text.vi, title.vi), en: cut(text.en, title.en) };
}

/** Which tour belongs to the screen at `pathname`; undefined when that screen has none. */
export function tourScreen(pathname: string, role: Role | null): string | undefined {
  if (!role) return "login";
  if (role === "teacher") {
    if (/^\/khoa\/[^/]+\/duyet/.test(pathname)) return "gv-review";
    if (/^\/khoa\/[^/]+/.test(pathname)) return "gv-course";
    return pathname === "/" ? "gv-home" : undefined;
  }
  if (pathname === "/") return "hub";
  if (pathname.startsWith("/khoa-hoc/tim-kiem")) return "course-search";
  if (/^\/khoa-hoc\/[^/]+\/hoc/.test(pathname)) return "player";
  if (/^\/khoa-hoc\/[^/]+/.test(pathname)) return "course";
  if (pathname.startsWith("/khoa-hoc")) return "courses";
  if (/^\/luyen-tap\/.+/.test(pathname)) return "practice-run";
  if (pathname.startsWith("/luyen-tap")) return "practice";
  if (pathname.startsWith("/hoi-dap")) return "ask";
  if (pathname.startsWith("/tien-do")) return "progress";
  if (pathname.startsWith("/nghien-cuu/paper/")) return "research-paper";
  if (pathname.startsWith("/nghien-cuu")) return "research";
  return undefined;
}

/** The first area with this data-guide key that takes up room on the page now. */
function present(key: string): boolean {
  for (const el of document.querySelectorAll<HTMLElement>("[data-guide]")) {
    if (el.dataset.guide !== key || el.closest("[hidden]")) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return true;
  }
  return false;
}

/**
 * Steps for `screen` with the areas on the page now, at most MAX_STEPS. Empty when none of its areas is there yet
 * (the hello alone is not a tour: it waits until the screen has something to show).
 */
export function tourSteps(screen: string, adult: boolean, has: (key: string) => boolean = present): MascotTourStep[] {
  const out: MascotTourStep[] = [];
  for (const k of TOURS[screen] ?? []) {
    if (out.length >= MAX_STEPS) break;
    if (k === HELLO) out.push(hello(adult));
    else if (has(k)) out.push({ key: k, title: TITLES[k], text: GUIDES[k] && TITLES[k] ? untitled(GUIDES[k], TITLES[k]) : undefined });
  }
  return out.some((s) => s.key) ? out : [];
}

/** Every screen that has a tour (for tests). */
export const TOUR_SCREENS = Object.keys(TOURS);
/** Every data-guide key a tour points at (for tests: each needs a GUIDES text). */
export const TOUR_KEYS = [...new Set(Object.values(TOURS).flat().filter((k) => k !== HELLO))];

// ---- which screens this person has already been walked through (per account, on this device)
const storeKey = (uid: string | null) => `mentor.tour.seen.${uid ?? "guest"}`;
function seenList(uid: string | null): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(storeKey(uid)) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}
function saveSeen(uid: string | null, list: string[]) {
  try {
    if (list.length) localStorage.setItem(storeKey(uid), JSON.stringify(list));
    else localStorage.removeItem(storeKey(uid));
  } catch {
    /* private mode: tours just show again next time */
  }
}
export const hasSeen = (uid: string | null, screen: string) => seenList(uid).includes(screen);
export function markSeen(uid: string | null, screen: string, seen = true) {
  const list = seenList(uid).filter((s) => s !== screen);
  saveSeen(uid, seen ? [...list, screen] : list);
}
/** Forget every screen seen, so each tour shows again the next time its screen opens. */
export const resetSeen = (uid: string | null) => saveSeen(uid, []);
