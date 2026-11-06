/** Diacritic-insensitive helpers shared by slash commands and search highlighting. */

/** Lowercase, strip Vietnamese diacritics (đ -> d), collapse spaces. */
export function fold(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** Folds while keeping a map from folded index to original index (so a match can be cut out of the original). */
function foldWithMap(s: string): { folded: string; map: number[] } {
  let folded = "";
  const map: number[] = [];
  let i = 0;
  for (const ch of s) {
    const f = ch
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[đĐ]/g, "d")
      .toLowerCase();
    for (let k = 0; k < f.length; k++) map.push(i);
    folded += f;
    i += ch.length;
  }
  map.push(s.length);
  return { folded, map };
}

export interface Segment {
  text: string;
  match: boolean;
}

/**
 * Splits `text` into segments, marking every occurrence of any word of `query` (accent- and case-insensitive).
 * Returns one unmarked segment when nothing matches.
 */
export function highlightSegments(text: string, query: string): Segment[] {
  const words = fold(query)
    .split(" ")
    .filter((w) => w.length > 0);
  if (words.length === 0 || !text) return [{ text, match: false }];
  const { folded, map } = foldWithMap(text);
  const ranges: [number, number][] = [];
  for (const w of words) {
    let from = 0;
    for (;;) {
      const at = folded.indexOf(w, from);
      if (at < 0) break;
      ranges.push([map[at], map[at + w.length]]);
      from = at + w.length;
    }
  }
  if (ranges.length === 0) return [{ text, match: false }];
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([r[0], r[1]]);
  }
  const out: Segment[] = [];
  let pos = 0;
  for (const [a, b] of merged) {
    if (a > pos) out.push({ text: text.slice(pos, a), match: false });
    out.push({ text: text.slice(a, b), match: true });
    pos = b;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), match: false });
  return out;
}

/** A window of `text` around the first match, with ellipses. */
export function snippetAround(text: string, query: string, radius = 60): string {
  const flat = text.replace(/\s+/g, " ").trim();
  const segs = highlightSegments(flat, query);
  let at = 0;
  for (const s of segs) {
    if (s.match) break;
    at += s.text.length;
  }
  if (flat.length <= radius * 2) return flat;
  const start = Math.max(0, at - radius);
  const end = Math.min(flat.length, at + radius);
  return `${start > 0 ? "…" : ""}${flat.slice(start, end)}${end < flat.length ? "…" : ""}`;
}
