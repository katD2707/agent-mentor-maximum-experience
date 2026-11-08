import { api, type Enrollment } from "../api";
import { getCourseInfo } from "./courseInfo";
import { readMirror, writeMirror } from "./enrollments";
import { packShaFor, startDownload } from "./sync";

/**
 * "+ Thêm": enroll in a course and start its background download (pack, assets, cover), the same as the course intro
 * does. Resolves with the enrollment; rejects when the enrollment itself failed (the download never rejects).
 */
export async function enrollCourse(token: string, userId: string, courseId: string): Promise<Enrollment> {
  const e = await api.enroll(token, courseId);
  writeMirror(userId, [...readMirror(userId).filter((x) => x.course_id !== courseId), e]);
  // course info (cached for offline) carries the pack hash the download verifies
  void getCourseInfo(token, courseId)
    .then((info) => packShaFor(info, e.pinned_version))
    .catch(() => null)
    .then((sha) => startDownload(token, courseId, e.pinned_version, sha));
  return e;
}
