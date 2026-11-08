import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { isMock, teacherApi, type TeacherCourseSummary } from "../../api";
import { useAuth } from "../../state/auth";
import { startLive } from "../../lib/teacher/live";
import { finishedJobs, statusMap } from "../../lib/teacher/status";
import { isTauri, nativeOnOpen, nativeShow, webOnOpen, webShow } from "../../lib/platform";

interface Live {
  courses: TeacherCourseSummary[] | null;
  failed: boolean;
  refresh(): void;
}
const Ctx = createContext<Live>({ courses: null, failed: false, refresh() {} });
export const useTeacherCourses = () => useContext(Ctx);

/** A route inside the teacher app, from a tapped notification. Anything else is the home screen. */
export function teacherDeepLink(link: string | null | undefined): string {
  const m = /^\/khoa\/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})(\/duyet(\?v=\d{1,4})?)?$/.exec(link ?? "");
  return m ? link! : "/";
}

const appHidden = () => document.hidden || !document.hasFocus();

/**
 * The course list, kept fresh (SSE + polling), and the desktop notification when a job finishes while the app is
 * hidden or not focused. Reuses the reminder toast of the student side (Rust `show_reminder` / the service worker).
 */
export function TeacherLive({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const { t } = useTranslation();
  const nav = useNavigate();
  const [courses, setCourses] = useState<TeacherCourseSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const last = useRef<ReadonlyMap<string, TeacherCourseSummary["status"]> | null>(null);
  const tr = useRef(t);
  tr.current = t;

  const pull = useCallback(async () => {
    if (!token) return;
    try {
      const list = await teacherApi.listCourses(token);
      for (const j of finishedJobs(last.current, list)) {
        if (!appHidden()) continue;
        const link = j.status === "review" ? `/khoa/${encodeURIComponent(j.id)}/duyet` : `/khoa/${encodeURIComponent(j.id)}`;
        const n = { id: `gv-${j.id}-${j.status}`, title: "Mentor", body: tr.current(`gv.notify.${j.status}`, { title: j.title }), deepLink: link };
        void (isTauri() ? nativeShow(n) : webShow(n)).catch(() => undefined);
      }
      last.current = statusMap(list);
      setCourses(list);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    void pull();
    return startLive({ token, onTick: () => void pull(), sse: !isMock });
  }, [token, pull]);

  // a tapped notification opens its screen
  useEffect(() => {
    const open = (o: { deepLink: string }) => nav(teacherDeepLink(o.deepLink));
    if (isTauri()) {
      let off: (() => void) | undefined;
      let dead = false;
      void nativeOnOpen(open).then((f) => (dead ? f() : (off = f)));
      return () => {
        dead = true;
        off?.();
      };
    }
    return webOnOpen(open);
  }, [nav]);

  const value = useMemo(() => ({ courses, failed, refresh: () => void pull() }), [courses, failed, pull]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
