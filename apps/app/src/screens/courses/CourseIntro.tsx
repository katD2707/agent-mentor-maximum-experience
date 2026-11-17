import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError, type CourseDetail, type Enrollment, type TreeLesson } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { getCourseInfo } from "../../lib/courseInfo";
import { loadEnrollments, readMirror, writeMirror } from "../../lib/enrollments";
import { packShaFor, startDownload } from "../../lib/sync";
import { CourseCover, DownloadNote, formatMinutes, MediaIcons, useDownload } from "./common";
import { CoursePractice } from "./CoursePractice";
import { RecapRows } from "./Recap";

/**
 * The course page as a fold-open tree (hs-04; the not-yet-enrolled intro and the coming-soon preview use the same look,
 * hs-07 and hs-08): the cover, one primary button, then "Bài học" / "Luyện tập" / "Kiểm tra".
 */
export function CourseIntro() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [info, setInfo] = useState<CourseDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !user) return;
    let alive = true;
    (async () => {
      try {
        const [i, { list }] = await Promise.all([getCourseInfo(token, id), loadEnrollments(token, user.id)]);
        if (!alive) return;
        setInfo(i);
        setEnrollment(list.find((e) => e.course_id === id) ?? null);
        setStatus("ready");
      } catch (e) {
        if (alive) setStatus(e instanceof ApiError && e.code === "not_found" ? "missing" : "error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [token, user, id]);

  const dl = useDownload(id, enrollment?.pinned_version ?? 0);
  const here = `/khoa-hoc/${id}`;
  const lessons: TreeLesson[] = info?.tree.flatMap((c) => c.lessons) ?? [];
  const soon = info?.status === "coming_soon";
  const playerTo = (lessonId: string) => `${here}/hoc?lesson=${encodeURIComponent(lessonId)}`;

  // where the learner is: lessons before this one are done
  const at = enrollment?.progress ? Math.max(0, lessons.findIndex((l) => l.id === enrollment.progress?.lesson_id)) : 0;
  const next = lessons[at];

  const enroll = async () => {
    if (!token || !user || !info || busy) return;
    setErr(null);
    setBusy(true);
    try {
      const e = await api.enroll(token, id);
      writeMirror(user.id, [...readMirror(user.id).filter((x) => x.course_id !== id), e]);
      setEnrollment(e);
      void startDownload(token, id, e.pinned_version, packShaFor(info, e.pinned_version));
      nav(lessons[0] ? playerTo(lessons[0].id) : `${here}/hoc`, { state: { back: here } });
    } catch {
      setErr(t("courses.intro.enrollFailed"));
    } finally {
      setBusy(false);
    }
  };

  const back = from ?? (soon ? "/khoa-hoc/tim-kiem" : "/");
  const meta = info ? [info.teacher_name, t("courses.lessons", { count: info.lessons_count }), formatMinutes(t, info.est_minutes)].join(" · ") : "";
  const lessonKey = (i: number) => (enrollment ? (i < at ? "done" : i === at ? "now" : "later") : "plain");

  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to={back} state={from ? { restore: true } : undefined} aria-label={from ? t("courses.intro.backToResults") : soon ? t("courses.search.title") : t("back")}>
          <Icon name="back" />
        </Link>
        <h1 className="page-title">{from || soon ? t("courses.search.title") : t("hub.courses")}</h1>
      </header>
      <main className="main courses-main ct-main">
        {status === "loading" && <p className="muted" role="status">{t("courses.search.searching")}</p>}
        {status === "missing" && <p className="muted" role="alert">{t("courses.intro.notFound")}</p>}
        {status === "error" && <p className="muted" role="alert">{t("courses.intro.failed")}</p>}
        {status === "ready" && info && (
          <>
            <section className="ct-hero">
              <CourseCover courseId={info.id} />
              <div>
                <h2>{info.title}</h2>
                <div className="meta">
                  {enrollment && !soon ? (
                    <>
                      <span className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={lessons.length} aria-valuenow={at}>
                        <i style={{ width: `${lessons.length ? (at / lessons.length) * 100 : 0}%` }} />
                      </span>
                      <span>{at}/{lessons.length}</span>
                      <DownloadNote state={dl} />
                    </>
                  ) : (
                    <>
                      <span>{meta}</span>
                      {soon && (
                        <span className="ct-soon">
                          <Icon name="clock" />
                          {t("courses.soon")}
                        </span>
                      )}
                    </>
                  )}
                </div>
              </div>
            </section>

            {!soon &&
              (enrollment && next ? (
                <Link className="btn btn-primary btn-big ct-next" to={playerTo(next.id)} state={{ back: here }} data-guide="course-next" data-guide-label={t("courses.intro.continue")}>
                  <Icon name="play" />
                  <span>{enrollment.progress ? t("courses.intro.continue") : t("courses.intro.start")}</span>
                  <small>{t("courses.intro.min", { count: next.est_minutes })}</small>
                </Link>
              ) : (
                <button className="btn btn-primary btn-big ct-next" type="button" onClick={() => void enroll()} disabled={busy} data-guide="course-next" data-guide-label={t("courses.intro.start")}>
                  <Icon name="play" />
                  <span>{busy ? t("courses.intro.starting") : t("courses.intro.start")}</span>
                </button>
              ))}
            {err && (
              <p className="cp-err" role="alert">
                {err}
              </p>
            )}

            <nav className="ct-tree" aria-label={t("courses.intro.treeAria")}>
              {soon ? (
                // coming soon: chapters fold open, one line per lesson
                info.tree.map((ch, ci) => {
                  const first = info.tree.slice(0, ci).reduce((n, c) => n + c.lessons.length, 0);
                  return (
                    <details key={ch.id} className="ct-grp" open={ci === 0 || info.tree.length <= 3}>
                      <Summary icon="book" title={ch.title} end={String(ch.lessons.length)} />
                      <div className="ct-kids">
                        {ch.lessons.map((l, i) => (
                          <div className="ct-node" key={l.id}>
                            <span className="no">{first + i + 1}</span>
                            <span className="t">{l.title}</span>
                            <span className="end">
                              <MediaIcons media={info.media} />
                            </span>
                          </div>
                        ))}
                      </div>
                    </details>
                  );
                })
              ) : (
                <details className="ct-grp lessons" open data-guide="course-tree" data-guide-label={t("courses.intro.lessons")}>
                  <Summary icon="book" title={t("courses.intro.lessons")} end={enrollment ? "" : String(lessons.length)} />
                  <div className="ct-kids">
                    {lessons.map((l, i) => {
                      const state = lessonKey(i);
                      const body = (
                        <>
                          <span className="no">{i + 1}</span>
                          <span className="t">{l.title}</span>
                          <span className="end">{state === "done" ? <Icon name="check" /> : state === "now" ? <Icon name="play" /> : state === "plain" ? <MediaIcons media={l.media} /> : null}</span>
                        </>
                      );
                      return state === "done" || state === "now" ? (
                        <Link key={l.id} className={`ct-node ${state}`} to={playerTo(l.id)} state={{ back: here }} aria-current={state === "now" ? "step" : undefined}>
                          {body}
                        </Link>
                      ) : (
                        <span key={l.id} className={`ct-node ${state}`}>
                          {body}
                        </span>
                      );
                    })}
                    {enrollment && <RecapRows courseId={id} version={enrollment.pinned_version} sha={packShaFor(info, enrollment.pinned_version)} kid={user?.age_band === "g1_5"} />}
                  </div>
                </details>
              )}

              {enrollment && !soon && <CoursePractice courseId={id} />}

              {!enrollment && info.outcomes.length > 0 && (
                <details className="ct-grp">
                  <Summary icon="target" title={t("courses.intro.learnTitle")} end="" />
                  <div className="ct-kids">
                    {info.outcomes.map((o) => (
                      <div className="ct-node out" key={o}>
                        <span className="t">{o}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </nav>
          </>
        )}
      </main>
    </div>
  );
}

function Summary({ icon, title, end }: { icon: "book" | "target"; title: string; end: string }) {
  return (
    <summary className="ct-node">
      <span className="chev">
        <Icon name="chev" />
      </span>
      <span className="ic">
        <Icon name={icon} />
      </span>
      <span className="t">{title}</span>
      <span className="end">{end}</span>
    </summary>
  );
}
