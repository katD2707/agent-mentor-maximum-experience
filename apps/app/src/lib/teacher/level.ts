import type { CourseLevel, TeacherCourseSummary, TeacherVersion } from "../../api/teacher";

export const LEVELS: readonly CourseLevel[] = ["basic", "intermediate", "advanced"];

/** 1-3 bars for a level, as in the gv-03 mockup. */
export const levelBars = (l: CourseLevel): number => LEVELS.indexOf(l) + 1;

type HasLevel = Pick<TeacherCourseSummary, "level" | "level_suggested" | "level_confirmed">;

/** What a row or header shows: the teacher's pick, else what students see, else the agent's suggestion. */
export function shownLevel(c: HasLevel): CourseLevel | null {
  return c.level_confirmed ?? c.level ?? c.level_suggested ?? null;
}

/** The level state of one version: confirmed (a published version always counts as confirmed by what students see). */
export function versionLevel(c: HasLevel, v: TeacherVersion | undefined): { suggested: CourseLevel | null; confirmed: CourseLevel | null } {
  const published = v?.status === "published";
  return { suggested: v?.level_suggested ?? null, confirmed: v?.level_confirmed ?? (published ? (c.level ?? null) : null) };
}
