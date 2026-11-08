/**
 * The mock API's catalog query (VITE_API_MOCK=1): the same rules as services/gateway content/catalog_query.py, so the
 * screen behaves the same with and without the gateway. Text matching is the plain name match only (no embeddings).
 */
import { fold } from "../lib/text";
import type { CatalogItem, CatalogPage, CatalogQuery, FacetKey, FacetOption, Suggestions } from "./course";

export const PAGE_SIZE = 10;
const MAX_PAGE_SIZE = 50;
const FIXED: Partial<Record<FacetKey, string[]>> = {
  band: ["g1_5", "g6_9", "g10_12", "uni"],
  language: ["vi", "en"],
  level: ["basic", "intermediate", "advanced"],
  duration: ["short", "medium", "long"],
  status: ["live", "coming_soon"],
  media: ["video", "reading", "quiz", "interactive", "audio"],
};
export const FACET_KEYS: FacetKey[] = ["band", "subject", "language", "level", "duration", "media", "status", "teacher"];

export const durationBucket = (m: number) => (m < 60 ? "short" : m <= 180 ? "medium" : "long");

export function valuesOf(e: CatalogItem, k: FacetKey): string[] {
  switch (k) {
    case "band":
      return [e.age_band];
    case "subject":
      return [e.subject];
    case "language":
      return [e.language];
    case "level":
      return e.level ? [e.level] : [];
    case "duration":
      return [durationBucket(e.est_minutes)];
    case "media":
      return e.media;
    case "status":
      return [e.status ?? "live"];
    default:
      return [e.teacher_name];
  }
}

type Filters = Partial<Record<FacetKey, string[]>>;

function passes(e: CatalogItem, filters: Filters, skip?: FacetKey): boolean {
  for (const k of FACET_KEYS) {
    const accepted = filters[k];
    if (k === skip || !accepted?.length) continue;
    if (!valuesOf(e, k).some((v) => accepted.includes(v))) return false;
  }
  return true;
}

export const tokensOf = (q: string) => fold(q).split(/\s+/).filter(Boolean);
const nameText = (e: CatalogItem) => fold(`${e.title} ${e.subject} ${e.teacher_name} ${e.language === "en" ? "english" : "tieng viet"}`);
const nameMatch = (e: CatalogItem, toks: string[]) => toks.length > 0 && toks.every((t) => nameText(e).includes(t));

function relevance(e: CatalogItem, toks: string[]): number {
  if (!nameMatch(e, toks)) return 0;
  const title = fold(e.title);
  return title.startsWith(toks[0]) ? 0.5 : toks.every((t) => title.includes(t)) ? 0.3 : 0.15;
}

function facets(entries: CatalogItem[], filters: Filters, matched: Set<string> | null): Record<FacetKey, FacetOption[]> {
  const out = {} as Record<FacetKey, FacetOption[]>;
  for (const k of FACET_KEYS) {
    const counts = new Map<string, number>();
    for (const e of entries) {
      if (matched && !matched.has(e.id)) continue;
      if (!passes(e, filters, k)) continue;
      for (const v of valuesOf(e, k)) counts.set(v, (counts.get(v) ?? 0) + 1);
    }
    const fixed = FIXED[k];
    if (fixed) out[k] = fixed.map((v) => ({ v, n: counts.get(v) ?? 0 }));
    else {
      const vals = new Set([...counts.keys(), ...(filters[k] ?? [])]);
      out[k] = [...vals].sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || a.localeCompare(b, "vi")).map((v) => ({ v, n: counts.get(v) ?? 0 }));
    }
  }
  return out;
}

// ---- did you mean
function dist(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...new Array<number>(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  return d[a.length][b.length];
}

function vocabulary(entries: CatalogItem[]): Map<string, string> {
  const v = new Map<string, string>();
  for (const e of entries)
    for (const raw of `${e.title} ${e.subject} ${e.teacher_name}`.split(/\s+/)) {
      const word = raw.replace(/^[:,.()]+|[:,.()]+$/g, "").toLowerCase();
      const k = fold(word);
      if (k.length > 1 && !v.has(k)) v.set(k, word);
    }
  return v;
}

export function didYouMean(q: string, entries: CatalogItem[]): string | null {
  const vocab = vocabulary(entries);
  const words = [...vocab.keys()];
  const out: string[] = [];
  let changed = false;
  for (const t of tokensOf(q)) {
    const pre = words.find((w) => w.startsWith(t));
    if (pre) {
      out.push(vocab.get(pre)!);
      continue;
    }
    changed = true;
    let best: string | null = null;
    let bd = t.length > 4 ? 2 : 1;
    for (const w of words) {
      const d = dist(t, w);
      if (d <= bd && (best === null || d < bd)) {
        best = w;
        bd = d;
      }
    }
    out.push(best ? vocab.get(best)! : t);
  }
  const s = out.join(" ");
  return changed && s && fold(s) !== fold(q) ? s : null;
}

export function suggestFrom(entries: CatalogItem[], q: string): Suggestions {
  const toks = tokensOf(q);
  if (!toks.length) return { courses: [], subjects: [], teachers: [], did_you_mean: null };
  const ok = (s: string) => toks.every((t) => fold(s).includes(t));
  const courses = entries.filter((e) => ok(e.title)).slice(0, 4).map((e) => ({ id: e.id, title: e.title }));
  const subjects: string[] = [];
  const teachers: string[] = [];
  for (const e of entries) {
    if (!subjects.includes(e.subject) && ok(e.subject)) subjects.push(e.subject);
    if (!teachers.includes(e.teacher_name) && ok(e.teacher_name)) teachers.push(e.teacher_name);
  }
  const none = !courses.length && !subjects.length && !teachers.length;
  return { courses, subjects: subjects.slice(0, 3), teachers: teachers.slice(0, 3), did_you_mean: none ? didYouMean(q, entries) : null };
}

export function queryEntries(entries: CatalogItem[], query: CatalogQuery): CatalogPage {
  const filters = query.filters ?? {};
  const q = (query.q ?? "").trim();
  const toks = tokensOf(q);
  const matched = toks.length ? new Set(entries.filter((e) => nameMatch(e, toks)).map((e) => e.id)) : null;
  const rows = entries.map((e, i) => ({ e, i })).filter(({ e }) => (!matched || matched.has(e.id)) && passes(e, filters));
  const soon = (e: CatalogItem) => (e.status === "coming_soon" ? 1 : 0);
  const sort = query.sort ?? "rel";
  const sign = query.dir === "desc" ? -1 : 1;
  const stamp = (e: CatalogItem) => (e.published_at ? Date.parse(e.published_at) || 0 : 0);
  rows.sort((a, b) => {
    let x = 0;
    if (sort === "new") x = soon(a.e) - soon(b.e) || (soon(a.e) ? 0 : stamp(b.e) - stamp(a.e));
    else if (sort === "pop") x = b.e.students - a.e.students;
    else if (sort === "dur") x = sign * (a.e.est_minutes - b.e.est_minutes);
    else x = relevance(b.e, toks) - relevance(a.e, toks) || soon(a.e) - soon(b.e);
    return x || a.i - b.i;
  });
  const size = Math.max(1, Math.min(query.page_size ?? PAGE_SIZE, MAX_PAGE_SIZE));
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const page = Math.min(Math.max(1, query.page ?? 1), pages);
  return {
    query: q,
    mode: "lexical",
    total: rows.length,
    page,
    pages,
    page_size: size,
    items: rows.slice((page - 1) * size, page * size).map(({ e }) => ({ ...e, score: relevance(e, toks) })),
    facets: facets(entries, filters, matched),
    did_you_mean: toks.length ? didYouMean(q, entries) : null,
  };
}
