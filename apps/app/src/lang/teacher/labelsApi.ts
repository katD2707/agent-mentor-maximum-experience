import { isMock } from "../../api";
import { request } from "../../api/http";
import { get, load, save } from "../../api/mock-teacher-api";
import { ApiError } from "../../api/types";
import type { CourseLevel } from "../../api/teacher";
import type { Band } from "./labels";
import { bandOfGrade } from "./labels";
import { subjectsFor } from "../subjects";

export interface LabelsPut {
  chicken?: string;
  band?: Band;
  /** school grade 1-12 (university: the year) */
  level?: number;
  difficulty?: CourseLevel;
  /** Mục tiêu: up to 6 lines of at most 160 characters */
  goals?: string[];
  language?: "vi" | "en";
  /** Chủ đề: up to 8 tags of at most 40 characters */
  topics?: string[];
}
export interface LabelsRes {
  version: number;
  chicken: string;
  band: string;
  level: number | null;
  difficulty: CourseLevel | null;
  published: boolean;
}

/** PUT /teacher/courses/{id}/versions/{v}/labels. Rejects with status 422 `chicken_not_in_band` for a chicken outside the band. */
export const putLabels = (token: string, id: string, version: number, body: LabelsPut): Promise<LabelsRes> =>
  isMock ? mockPutLabels(id, version, body) : request<LabelsRes>("PUT", `/teacher/courses/${encodeURIComponent(id)}/versions/${version}/labels`, { token, body });

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** The mock follows the gateway: a draft keeps the labels; the latest published version takes them at once (no new version). */
async function mockPutLabels(id: string, version: number, body: LabelsPut): Promise<LabelsRes> {
  await wait(60);
  const db = load();
  const c = get(db, id);
  const v = c.versions.find((x) => x.version === version);
  if (!v) throw new ApiError(404, "not_found");
  const band = body.band ?? (v.labels?.band as Band | undefined) ?? (v.labels?.grade ? bandOfGrade(v.labels.grade) : "g10_12");
  if (body.chicken && !subjectsFor(band === "uni" ? "uni" : band).some((s) => s.id === body.chicken)) throw new ApiError(422, "bad_request");
  const labels = { ...(v.labels ?? {}) };
  if (body.chicken) labels.chicken = body.chicken;
  if (body.band) labels.band = body.band;
  if (body.level) labels.grade = body.level;
  if (body.goals) labels.goals = body.goals;
  if (body.language) labels.language = body.language;
  if (body.topics) labels.topics = body.topics;
  v.labels = labels;
  if (body.difficulty) {
    v.level_confirmed = body.difficulty;
    if (v.status === "published") c.level = body.difficulty;
  }
  c.updatedAt = Date.now();
  save(db);
  return { version, chicken: labels.chicken ?? "", band, level: labels.grade ?? null, difficulty: v.level_confirmed ?? null, published: v.status === "published" };
}
