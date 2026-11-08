/**
 * Scroll position of the catalog results, per URL (`/khoa-hoc/tim-kiem?q=...&page=2`). Saved when a card is opened, read
 * when the student comes back (browser back, or the back arrow of the course page), so the list is where they left it.
 */
const mem = new Map<string, number>();

export function saveScroll(key: string, y: number): void {
  mem.set(key, Math.max(0, Math.round(y)));
}

/** The remembered position for `key`, or null. */
export function peekScroll(key: string): number | null {
  return mem.get(key) ?? null;
}
