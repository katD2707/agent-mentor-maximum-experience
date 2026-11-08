/** The catalog screen keeps its whole state in the URL, so the back arrow from a course page restores it. */
import type { AgeBand, CatalogQuery, CatalogSort, FacetKey } from "../api";

export const FACETS: FacetKey[] = ["subject", "band", "language", "level", "duration", "media", "status", "teacher"];

export interface CatState {
  q: string;
  sort: CatalogSort;
  dir: "asc" | "desc";
  page: number;
  view: "grid" | "list";
  f: Record<FacetKey, string[]>;
}

export const emptyFilters = (): Record<FacetKey, string[]> => ({ band: [], subject: [], language: [], level: [], duration: [], media: [], status: [], teacher: [] });

/**
 * `band` absent means "the student's own band"; `band=all` means every band (the chip was removed).
 * A kid (g1_5) is always in the primary band.
 */
export function parseState(p: URLSearchParams, own: AgeBand | null): CatState {
  const f = emptyFilters();
  for (const k of FACETS) f[k] = p.getAll(k).filter((v) => v && v !== "all");
  if (own === "g1_5") f.band = ["g1_5"];
  else if (!p.has("band") && own) f.band = [own];
  const sort = p.get("sort");
  const page = Number(p.get("page"));
  return {
    q: (p.get("q") ?? "").trim(),
    sort: sort === "new" || sort === "pop" || sort === "dur" ? sort : "rel",
    dir: p.get("dir") === "desc" ? "desc" : "asc",
    page: Number.isInteger(page) && page > 1 ? page : 1,
    view: p.get("view") === "list" ? "list" : "grid",
    f,
  };
}

export function toParams(s: CatState, own: AgeBand | null): URLSearchParams {
  const p = new URLSearchParams();
  if (s.q) p.set("q", s.q);
  for (const k of FACETS) {
    if (k === "band") {
      if (own === "g1_5") continue;
      if (s.f.band.length === 0) {
        if (own) p.set("band", "all");
      } else if (!(s.f.band.length === 1 && s.f.band[0] === own)) for (const v of s.f.band) p.append("band", v);
      continue;
    }
    for (const v of s.f[k]) p.append(k, v);
  }
  if (s.sort !== "rel") p.set("sort", s.sort);
  if (s.sort === "dur" && s.dir === "desc") p.set("dir", "desc");
  if (s.page > 1) p.set("page", String(s.page));
  if (s.view === "list") p.set("view", "list");
  return p;
}

export const toQuery = (s: CatState): CatalogQuery => ({ q: s.q, filters: s.f, sort: s.sort, dir: s.dir, page: s.page, page_size: 10 });

/** How many filters the student set, not counting their own band that is on by default. */
export function activeCount(s: CatState, own: AgeBand | null): number {
  let n = 0;
  for (const k of FACETS) n += s.f[k].length;
  if (own && s.f.band.length === 1 && s.f.band[0] === own) n -= 1;
  return n;
}
