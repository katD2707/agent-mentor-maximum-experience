import type { CourseDetail, CourseMeta } from "./course";
import data from "./mock-soon-data.json";

/**
 * Coming-soon placeholders for the mock API (VITE_API_MOCK=1): all 107 of them, generated from mentor-content
 * (`mentor-content/tools/make_placeholders.py` output), same shape as the real ones, covers included.
 */
export const SOON = data as unknown as { meta: CourseMeta; tree: CourseDetail["tree"] }[];

const files = import.meta.glob("../assets/courses/soon/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

export const SOON_COVERS: Record<string, string> = Object.fromEntries(
  Object.entries(files).map(([path, url]) => [path.split("/").pop()!.replace(/\.webp$/, ""), url]),
);
