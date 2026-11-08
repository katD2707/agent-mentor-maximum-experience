import { lazy, Suspense, useEffect, useRef, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./state/auth";
import { needsFirstRun } from "./lib/gate";
import { Login } from "./screens/Login";
import { FirstRun } from "./screens/FirstRun";
import { Hub } from "./screens/Hub";
import { Progress } from "./screens/Progress";
import { resolveDeepLink } from "./lib/deeplink";
import { startBackground, type Background } from "./lib/behaviour";
import { Courses } from "./screens/courses/Courses";
import { CourseSearch } from "./screens/courses/CourseSearch";
import { CourseIntro } from "./screens/courses/CourseIntro";

// the player pulls in Markdown + KaTeX, so it loads on demand
const Player = lazy(() => import("./screens/courses/Player"));
const Ask = lazy(() => import("./screens/ask/Ask"));
import { Practice } from "./screens/practice/Practice";
const PracticeRun = lazy(() => import("./screens/practice/Run"));
const TeacherApp = lazy(() => import("./screens/teacher/TeacherApp"));
const Research = lazy(() => import("./screens/research/Research"));
const ResearchPaper = lazy(() => import("./screens/research/Paper"));
import { SourceKeysProvider } from "./screens/research/Sources";
import { Guide } from "./components/Guide";
import { UpdateNotice } from "./components/UpdateNotice";

/** `/khoa-hoc/<id>?lesson=<lesson>` (what the planner and reminders link to) opens the player at that lesson. */
function CourseRoute() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const lesson = params.get("lesson");
  if (lesson) return <Navigate replace to={`/khoa-hoc/${encodeURIComponent(id)}/hoc?lesson=${encodeURIComponent(lesson)}`} />;
  return <CourseIntro />;
}

/** The research screens are for the university band only; anyone else lands on the hub. */
function UniOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user?.age_band === "uni" ? <>{children}</> : <Navigate to="/" replace />;
}

/**
 * Runs while a student is signed in: behaviour events, focus accounting and reminders (fetch, schedule, show). Also
 * handles a tapped reminder: opens its deep link and reports `opened`.
 */
function BackgroundWork() {
  const { token, user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const { i18n } = useTranslation();
  const bg = useRef<Background | null>(null);
  const lang = useRef(i18n.language);
  lang.current = i18n.language;
  const me = useRef(user);
  me.current = user;
  const userId = user?.id;

  useEffect(() => {
    if (!token || !me.current) return;
    const b = startBackground({
      token,
      user: me.current,
      lang: () => (lang.current === "en" ? "en" : "vi"),
      open: ({ id, deepLink }) => {
        if (id) bg.current?.opened(id);
        nav(resolveDeepLink(deepLink).to);
      },
    });
    bg.current = b;
    return () => {
      b.stop();
      bg.current = null;
    };
  }, [token, userId, nav]);

  const quiet = user?.quiet_until ?? null;
  useEffect(() => bg.current?.setQuiet(quiet), [quiet]);

  // a browser tab opened by a notification arrives with ?reminder=<id> in its address
  useEffect(() => {
    const id = new URLSearchParams(loc.search).get("reminder");
    if (!id) return;
    const t = resolveDeepLink(loc.pathname + loc.search);
    bg.current?.opened(t.reminderId ?? id);
    nav(t.to, { replace: true });
  }, [loc.pathname, loc.search, nav]);
  return null;
}

/** The source-key dialog and status exist only for the university band (Settings shows its row from them). */
function SourceKeysGate({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user?.age_band === "uni" ? <SourceKeysProvider>{children}</SourceKeysProvider> : <>{children}</>;
}

export function App() {
  const { status, user } = useAuth();

  let body;
  if (status === "loading") body = <div className="boot" />;
  else if (!user) body = <Login />;
  else if (user.role === "teacher") body = (
      <Suspense fallback={<div className="boot" />}>
        <TeacherApp />
      </Suspense>
    );
  else if (needsFirstRun(user)) body = <FirstRun />;
  else
    body = (
      <SourceKeysGate>
      <BackgroundWork />
      <Routes>
        <Route path="/" element={<Hub />} />
        <Route path="/khoa-hoc" element={<Courses />} />
        <Route path="/khoa-hoc/tim-kiem" element={<CourseSearch />} />
        <Route path="/khoa-hoc/:id" element={<CourseRoute />} />
        <Route
          path="/khoa-hoc/:id/hoc"
          element={
            <Suspense fallback={<div className="boot" />}>
              <Player />
            </Suspense>
          }
        />
        <Route path="/luyen-tap" element={<Practice />} />
        <Route
          path="/luyen-tap/:id/*"
          element={
            <Suspense fallback={<div className="boot" />}>
              <PracticeRun />
            </Suspense>
          }
        />
        <Route
          path="/hoi-dap"
          element={
            <Suspense fallback={<div className="boot" />}>
              <Ask />
            </Suspense>
          }
        />
        <Route path="/tien-do" element={<Progress />} />
        <Route
          path="/nghien-cuu"
          element={
            <UniOnly>
              <Suspense fallback={<div className="boot" />}>
                <Research />
              </Suspense>
            </UniOnly>
          }
        />
        <Route
          path="/nghien-cuu/paper/:id"
          element={
            <UniOnly>
              <Suspense fallback={<div className="boot" />}>
                <ResearchPaper />
              </Suspense>
            </UniOnly>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </SourceKeysGate>
    );

  return (
    <>
      {body}
      <Guide />
      <UpdateNotice />
    </>
  );
}
