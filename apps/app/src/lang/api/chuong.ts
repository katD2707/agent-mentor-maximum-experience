import { api, isMock, type AgeBand, type CatalogItem, type CatalogPage, type CatalogSort, type FacetKey } from "../../api";
import { request } from "../../api/http";
import { chickenOfCourse } from "../chickenOf";
import { levelOf, stageOf, subjectOf, xpInLevel } from "../subjects";
import { lg } from "./index";
import type { Chicken } from "./types";

/** What the chicken's page (lg-03) needs from `GET /chickens/{id}` (CONTRACTS-LANGGA.md section 2 and 5). */
export interface ChuongTest {
  course_id: string | null;
  profile_or_mock: string;
  title: string;
  minutes: number;
  items: number;
  last_score: number | null;
}
export interface ChuongData {
  chicken: Chicken;
  /** the ids the server lists for this chicken; null = not known (offline, mock): the app groups its own enrollments */
  courseIds: string[] | null;
  weekXp: number[];
  tests: ChuongTest[];
}

interface Wire {
  chicken: Chicken;
  courses?: { course_id: string }[];
  week_xp?: number[];
  tests?: ChuongTest[];
}

function unowned(id: string): Chicken {
  const s = subjectOf(id);
  return { id, name_vi: `Gà ${s?.vi ?? id}`, name_en: `${s?.en ?? id} chicken`, art: s?.art ?? id, level: levelOf(0), xp: 0, xp_in_level: xpInLevel(0), stage: stageOf(1), courses: 0, active_course: null, done_today: false, taken_at: "" };
}

export async function getChuong(token: string, id: string): Promise<ChuongData> {
  if (isMock) {
    try {
      const r = await lg.getChicken(token, id);
      return { chicken: r.chicken, courseIds: null, weekXp: r.week_xp, tests: [] };
    } catch {
      if (!subjectOf(id)) throw new Error("unknown_chicken");
      return { chicken: unowned(id), courseIds: null, weekXp: [0, 0, 0, 0, 0, 0, 0], tests: [] };
    }
  }
  const r = await request<Wire>("GET", `/chickens/${encodeURIComponent(id)}`, { token });
  return { chicken: r.chicken, courseIds: r.courses ? r.courses.map((c) => c.course_id) : null, weekXp: r.week_xp ?? [], tests: r.tests ?? [] };
}

export const FIND_PER_PAGE = 12;
export type FindFacet = "level" | "language" | "duration" | "media";
export const FIND_FACETS: FindFacet[] = ["level", "language", "duration", "media"];

export interface FindQuery {
  q: string;
  sort: CatalogSort;
  page: number;
  f: Record<FindFacet, string[]>;
}

/** The catalog scoped to one chicken (`chicken` facet), 12 a page. In the mock layer the scoping is done here. */
export async function queryChicken(token: string, chicken: string, band: AgeBand, query: FindQuery): Promise<CatalogPage> {
  const filters: Partial<Record<FacetKey, string[]>> = { band: [band] };
  for (const k of FIND_FACETS) if (query.f[k].length) filters[k] = query.f[k];
  const base = { q: query.q, sort: query.sort };
  if (!isMock) return api.queryCatalog(token, { ...base, page: query.page, page_size: FIND_PER_PAGE, filters: { ...filters, chicken: [chicken] } as Partial<Record<FacetKey, string[]>> });
  const all = await api.queryCatalog(token, { ...base, page: 1, page_size: 200, filters });
  const mine = all.items.filter((c: CatalogItem) => chickenOfCourse(c) === chicken);
  const pages = Math.max(1, Math.ceil(mine.length / FIND_PER_PAGE));
  const page = Math.min(query.page, pages);
  return { ...all, total: mine.length, page, pages, page_size: FIND_PER_PAGE, items: mine.slice((page - 1) * FIND_PER_PAGE, page * FIND_PER_PAGE) };
}
