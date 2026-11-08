import { api, ApiError, type CourseDetail } from "../api";

/** GET /courses/{id} with a localStorage copy, so titles and the tree still show when offline. */
const key = (id: string) => `mentor.course.${id}`;

function readLocal(id: string): CourseDetail | null {
  try {
    const raw = localStorage.getItem(key(id));
    return raw ? (JSON.parse(raw) as CourseDetail) : null;
  } catch {
    return null;
  }
}

export async function getCourseInfo(token: string, id: string): Promise<CourseDetail> {
  try {
    const info = await api.getCourse(token, id);
    try {
      localStorage.setItem(key(id), JSON.stringify(info));
    } catch {
      /* ignore */
    }
    return info;
  } catch (e) {
    if (e instanceof ApiError && (e.code === "unauthorized" || e.code === "not_found")) throw e;
    const local = readLocal(id);
    if (local) return local;
    throw e;
  }
}
