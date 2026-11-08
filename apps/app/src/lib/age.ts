import type { AgeBand } from "../api/types";

export const BIRTH_YEAR_MIN = 1980;
export const BIRTH_YEAR_MAX = 2020;

/**
 * Age band from the birth year. The school year starts in September and grade 1 is the year a child turns 6:
 * grade = schoolYearStart - birthYear - 5. Grade 5 or less (including before grade 1) is g1_5, then g6_9,
 * g10_12, and uni after grade 12. Worked out in the background; age and grade are never shown.
 * Mirrors services/gateway/src/mentor_gateway/age.py.
 */
export function bandForBirthYear(birthYear: number | null, now: Date = new Date()): AgeBand | null {
  if (birthYear === null) return null;
  const schoolYear = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
  const grade = schoolYear - birthYear - 5;
  return grade <= 5 ? "g1_5" : grade <= 9 ? "g6_9" : grade <= 12 ? "g10_12" : "uni";
}
