import { lazy, Suspense, useEffect, useRef, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./state/auth";
import { needsFirstRun } from "./lib/gate";
import { LgLogin } from "./lang/screens/Login";
import { LgFirstRun } from "./lang/screens/FirstRun";
import { Village } from "./lang/screens/Village";
import { resolveDeepLink } from "./lib/deeplink";
import { startBackground, type Background } from "./lib/behaviour";
import { ToChuong, ToFind } from "./lang/screens/chuong/redirects";

// the player pulls in Markdown + KaTeX, so it loads on demand
const Lesson = lazy(() => import("./lang/screens/lesson/Lesson"));
import { PracticeEntry } from "./lang/screens/arena/Legacy";
const TienDo = lazy(() => import("./lang/screens/progress/Progress").then((m) => ({ default: m.TienDo })));
const StudyRoom = lazy(() => import("./lang/screens/study/StudyRoom").then((m) => ({ default: m.StudyRoom })));
const Chuong = lazy(() => import("./lang/screens/chuong/Chuong").then((m) => ({ default: m.Chuong })));
const Arena = lazy(() => import("./lang/screens/arena/Arena").then((m) => ({ default: m.Arena })));
const CourseTests = lazy(() => import("./lang/screens/arena/CourseTests").then((m) => ({ default: m.CourseTests })));
const PracticeRun = lazy(() => import("./lang/screens/practice/Run"));
const TeacherApp = lazy(() => import("./lang/teacher/TeacherApp"));
const Library = lazy(() => import("./lang/screens/library/Library").then((m) => ({ default: m.Library })));
const LibraryPaper = lazy(() => import("./lang/screens/library/Library").then((m) => ({ default: m.LibraryPaper })));
import { SourceKeysProvider } from "./lang/screens/library/research/Sources";
import { RouteGuide } from "./lang/guide/RouteGuide";
import { ScrollTop } from "./lang/kit/ScrollTop";
import { UpdateNotice } from "./components/UpdateNotice";

/** `/khoa-hoc/<id>?lesson=<lesson>` (what the planner and reminders link to) opens the player at that lesson. */
function CourseRoute() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const lesson = params.get("lesson");
  if (lesson) return <Navigate replace to={`/khoa-hoc/${encodeURIComponent(id)}/hoc?lesson=${encodeURIComponent(lesson)}`} />;
  return <ToChuong />;
}

/** The old research address of a paper lands on its Library page. */
function ToLibraryPaper() {
  const { id = "" } = useParams();
  return <Navigate to={`/thu-vien/paper/${encodeURIComponent(id)}`} replace />;
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
  else if (!user) body = <LgLogin />;
  else if (user.role === "teacher") body = (
      <Suspense fallback={<div className="boot" />}>
        <TeacherApp />
      </Suspense>
    );
  else if (needsFirstRun(user)) body = <LgFirstRun />;
  else
    body = (
      <SourceKeysGate>
      <BackgroundWork />
      <Suspense fallback={<div className="boot" />}>
      <Routes>
        <Route path="/" element={<Village />} />
        <Route path="/chon-ga" element={<LgFirstRun />} />
        <Route path="/hoi-dap" element={<Navigate to="/" replace />} />
        <Route path="/khoa-hoc" element={<Navigate to="/" replace />} />
        <Route path="/chuong/:chicken" element={<Chuong />} />
        <Route path="/khoa-hoc/tim-kiem" element={<ToFind />} />
        <Route path="/khoa-hoc/:id" element={<CourseRoute />} />
        <Route
          path="/khoa-hoc/:id/hoc"
          element={
            <Suspense fallback={<div className="boot" />}>
              <Lesson />
            </Suspense>
          }
        />
        <Route path="/dau-truong" element={<Arena />} />
        <Route path="/dau-truong/:paper" element={<Arena />} />
        <Route path="/kiem-tra/:courseId" element={<CourseTests />} />
        <Route path="/luyen-tap" element={<PracticeEntry />} />
        <Route
          path="/luyen-tap/:id/*"
          element={
            <Suspense fallback={<div className="boot" />}>
              <PracticeRun />
            </Suspense>
          }
        />
        <Route path="/tien-do" element={<TienDo />} />
        <Route path="/phong-tu-hoc" element={<StudyRoom />} />
        <Route
          path="/thu-vien"
          element={
            <Suspense fallback={<div className="boot" />}>
              <Library />
            </Suspense>
          }
        />
        <Route
          path="/thu-vien/paper/:id"
          element={
            <Suspense fallback={<div className="boot" />}>
              <LibraryPaper />
            </Suspense>
          }
        />
        <Route path="/nghien-cuu" element={<Navigate to="/thu-vien" replace />} />
        <Route path="/nghien-cuu/paper/:id" element={<ToLibraryPaper />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
      </SourceKeysGate>
    );

  return (
    <>
      {body}
      <ScrollTop />
      <RouteGuide />
      <UpdateNotice />
    </>
  );
}
