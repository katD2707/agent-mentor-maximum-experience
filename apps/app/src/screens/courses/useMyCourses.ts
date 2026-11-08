import { useCallback, useEffect, useState } from "react";
import type { CourseDetail, CoursePack, Enrollment } from "../../api";
import { useAuth } from "../../state/auth";
import { loadEnrollments } from "../../lib/enrollments";
import { getCourseInfo } from "../../lib/courseInfo";
import { courseStore } from "../../lib/offline";
import { packShaFor, startDownload } from "../../lib/sync";
import { isFinished, lessonOrdinal, progressPercent } from "../../lib/courseProgress";

export interface MyCourse {
  enrollment: Enrollment;
  info: CourseDetail;
  pack: CoursePack | null;
  percent: number;
  finished: boolean;
  lessonIds: string[];
  ordinal: { n: number; total: number };
}

export interface MyCourses {
  status: "loading" | "ready" | "error";
  courses: MyCourse[];
  offline: boolean;
  reload(): void;
}

async function cachedPack(id: string, v: number): Promise<CoursePack | null> {
  try {
    const bytes = await courseStore().getPack(id, v);
    return bytes ? (JSON.parse(new TextDecoder().decode(bytes)) as CoursePack) : null;
  } catch {
    return null;
  }
}

/** The learner's enrolled courses with titles, progress and the next lesson. Also starts missing downloads. */
export function useMyCourses(): MyCourses {
  const { token, user } = useAuth();
  const [state, setState] = useState<Omit<MyCourses, "reload">>({ status: "loading", courses: [], offline: false });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!token || !user) return;
    let alive = true;
    (async () => {
      try {
        const { list, offline } = await loadEnrollments(token, user.id);
        const rows = await Promise.all(
          list.map(async (enrollment): Promise<MyCourse | null> => {
            try {
              const info = await getCourseInfo(token, enrollment.course_id);
              const pack = await cachedPack(enrollment.course_id, enrollment.pinned_version);
              const lessonIds = info.tree.flatMap((c) => c.lessons.map((l) => l.id));
              if (!offline) void startDownload(token, enrollment.course_id, enrollment.pinned_version, packShaFor(info, enrollment.pinned_version));
              return {
                enrollment,
                info,
                pack,
                percent: progressPercent(pack, enrollment.progress, info.lessons_count, lessonIds),
                finished: pack ? isFinished(pack, enrollment.progress) : false,
                lessonIds,
                ordinal: lessonOrdinal(lessonIds, enrollment.progress),
              };
            } catch {
              return null;
            }
          }),
        );
        if (alive) setState({ status: "ready", courses: rows.filter((r): r is MyCourse => r !== null), offline });
      } catch {
        if (alive) setState({ status: "error", courses: [], offline: false });
      }
    })();
    return () => {
      alive = false;
    };
  }, [token, user, tick]);

  return { ...state, reload };
}
