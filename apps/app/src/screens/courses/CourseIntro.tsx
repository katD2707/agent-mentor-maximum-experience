import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError, type CourseDetail, type Enrollment } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { getCourseInfo } from "../../lib/courseInfo";
import { loadEnrollments, readMirror, writeMirror } from "../../lib/enrollments";
import { packShaFor, startDownload } from "../../lib/sync";
import { CourseCover, DownloadNote, formatMinutes, LangTag, MediaIcons, useDownload } from "./common";
import { CourseTags } from "./catalogUi";

/** hs-03 detail: cover, short description with language tag, outcomes, the content tree, "Bắt đầu học". */
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

  const start = async () => {
    if (!token || !user || !info) return;
    setErr(null);
    try {
      let e = enrollment;
      if (!e) {
        setBusy(true);
        e = await api.enroll(token, id);
        writeMirror(user.id, [...readMirror(user.id).filter((x) => x.course_id !== id), e]);
        setEnrollment(e);
        void startDownload(token, id, e.pinned_version, packShaFor(info, e.pinned_version));
      }
      nav(`/khoa-hoc/${id}/hoc`);
    } catch {
      setErr(t("courses.intro.enrollFailed"));
    } finally {
      setBusy(false);
    }
  };

  const soon = info?.status === "coming_soon";
  const back = from ?? "/khoa-hoc";
  const lessonLink = (lessonId: string) => (enrollment ? `/khoa-hoc/${id}/hoc?lesson=${encodeURIComponent(lessonId)}` : null);

  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to={back} state={from ? { restore: true } : undefined} aria-label={from ? t("courses.intro.backToResults") : t("courses.intro.back")}>
          <Icon name="back" />
        </Link>
        <h1 className="page-title">{from ? t("courses.search.title") : t("hub.courses")}</h1>
      </header>
      <main className="main courses-main">
        {status === "loading" && <p className="muted" role="status">{t("courses.search.searching")}</p>}
        {status === "missing" && <p className="muted" role="alert">{t("courses.intro.notFound")}</p>}
        {status === "error" && <p className="muted" role="alert">{t("courses.intro.failed")}</p>}
        {status === "ready" && info && (
          <div className="detail">
            <div className="detail-main">
              <section className="cover">
                <figure className="cover-media">
                  <CourseCover courseId={info.id} />
                </figure>
                <h2 className="course-h">{info.title}</h2>
                <p className="muted">{t("courses.intro.by", { teacher: info.teacher_name })}</p>
                <CourseTags course={info} />
                <p className="desc">
                  {info.description_short} <LangTag lang={info.language} />
                </p>
              </section>

              {info.outcomes.length > 0 && (
                <section className="learn-box">
                  <h2 className="sub-h">{t("courses.intro.learnTitle")}</h2>
                  <ul className="learn">
                    {info.outcomes.map((o) => (
                      <li key={o}>{o}</li>
                    ))}
                  </ul>
                </section>
              )}

              <section data-guide="course-tree" data-guide-label={t("courses.intro.treeTitle")} aria-label={t("courses.intro.treeAria")}>
                <h2 className="sub-h">{t("courses.intro.treeTitle")}</h2>
                <div className="tree">
                  {info.tree.map((ch, ci) => (
                    <details key={ch.id} open={ci === 0 || info.tree.length <= 3}>
                      <summary>{ch.title}</summary>
                      <ol className="lessons">
                        {ch.lessons.map((l) => {
                          const to = lessonLink(l.id);
                          return (
                            <li key={l.id}>
                              <div className="lesson-main">
                                {to ? (
                                  <Link to={to} className="lesson-title">
                                    {l.title}
                                  </Link>
                                ) : (
                                  <span className="lesson-title">{l.title}</span>
                                )}
                                {l.key_ideas.length > 0 && (
                                  <ul className="ideas" aria-label={t("courses.intro.keyIdeas")}>
                                    {l.key_ideas.map((k) => (
                                      <li key={k}>{k}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                              <span className="kinds">
                                <MediaIcons media={l.media} />
                              </span>
                            </li>
                          );
                        })}
                      </ol>
                    </details>
                  ))}
                </div>
              </section>
            </div>

            <aside className="side">
              {soon ? (
                <p className="soon-label">{t("courses.soon")}</p>
              ) : (
                <button className="btn btn-primary btn-big" type="button" onClick={() => void start()} disabled={busy}>
                  <Icon name="play" />
                  <span>{busy ? t("courses.intro.starting") : enrollment?.progress ? t("courses.intro.continue") : t("courses.intro.start")}</span>
                </button>
              )}
              {err && (
                <p className="side-err" role="alert">
                  {err}
                </p>
              )}
              <div className="facts">
                <span>
                  <Icon name="clock" />
                  <span>
                    {t("courses.intro.factTime", { t: formatMinutes(t, info.est_minutes) })}, {t("courses.lessons", { count: info.lessons_count })}
                  </span>
                </span>
                <DownloadNote state={dl} />
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
