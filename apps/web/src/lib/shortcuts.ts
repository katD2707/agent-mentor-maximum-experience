"use client";

import { useEffect } from "react";

export interface Shortcut {
  keys: string;
  description: string;
}

/** Shortcuts that work on every screen. */
export const GLOBAL_SHORTCUTS: Shortcut[] = [
  { keys: "F1 hoặc ?", description: "Mở bảng phím tắt này" },
  { keys: "Ctrl + K", description: "Tìm trong các cuộc trò chuyện" },
  { keys: "Esc", description: "Đóng hộp thoại đang mở" },
];

export const CHAT_SHORTCUTS: Shortcut[] = [
  { keys: "Enter", description: "Gửi tin nhắn" },
  { keys: "Shift + Enter", description: "Xuống dòng" },
  { keys: "Ctrl + N", description: "Cuộc trò chuyện mới" },
  { keys: "/", description: "Gõ để xem các lệnh: /luyen, /thithu, /tienbo, /nhac, /nho" },
  { keys: "Tab hoặc ↓ ↑", description: "Chọn lệnh gợi ý khi gõ /" },
];

const PAGE_SHORTCUTS: [prefix: string, title: string, list: Shortcut[]][] = [
  ["/chat", "Trò chuyện", CHAT_SHORTCUTS],
  ["/popup", "Trò chuyện (cửa sổ nhỏ)", CHAT_SHORTCUTS],
  [
    "/progress",
    "Tiến bộ",
    [
      { keys: "Tab", description: "Đi qua từng môn, chủ đề và nút gợi ý" },
      { keys: "← →", description: "Đổi môn khi đang ở thanh chọn môn" },
    ],
  ],
];

const extra = new Map<string, { title: string; list: Shortcut[] }>();
const listeners = new Set<() => void>();

/** Lets a page (e.g. the practice player) add its own shortcuts to the F1 overlay while it is mounted. */
export function usePageShortcuts(id: string, title: string, list: Shortcut[]): void {
  useEffect(() => {
    extra.set(id, { title, list });
    listeners.forEach((l) => l());
    return () => {
      extra.delete(id);
      listeners.forEach((l) => l());
    };
  }, [id, title, list]);
}

export function subscribeShortcuts(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Sections for the overlay: the current page's own, any registered extras, then the global ones. */
export function shortcutSections(pathname: string): { title: string; list: Shortcut[] }[] {
  const out: { title: string; list: Shortcut[] }[] = [];
  const page = PAGE_SHORTCUTS.find(([p]) => pathname === p || pathname.startsWith(p + "/"));
  if (page) out.push({ title: page[1], list: page[2] });
  for (const e of extra.values()) out.push(e);
  out.push({ title: "Mọi màn hình", list: GLOBAL_SHORTCUTS });
  return out;
}

/** True when the key event comes from a field where typing "?" must stay text. */
export function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return el.isContentEditable || el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT";
}
