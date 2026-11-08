import type { User } from "../api/types";

/** The first-run screen shows for a student who has not yet picked a language or given a birth year. */
export function needsFirstRun(user: User): boolean {
  return user.role === "student" && (user.language === null || user.birth_year === null);
}
