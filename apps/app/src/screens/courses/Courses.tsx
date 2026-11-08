import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, coverUrl, type CatalogEntry } from "../../api";
import { onMediaError } from "../../lib/mediaRetry";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { speak } from "../../lib/speak";
import { chapterOrdinal, pickToday, stars } from "../../lib/courseProgress";
import { CourseCover, DownloadNote, formatMinutes, useDownload } from "./common";
import { CourseTags } from "./catalogUi";
import { useMyCourses, type MyCourse } from "./useMyCourses";
import { resolveDeepLink } from "../../lib/deeplink";
import { pickLang, useToday } from "../../lib/today";
import type { TodaySession } from "../../api";

/** hs-02b: today block, the learner's courses, search. Only the back button on top (no tabs). */
export function Courses() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const kid = user?.age_band === "g1_5";
  const my = useMyCourses();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const plan = useToday().today?.today ?? null;

  const finished = new Set(my.courses.filter((c) => c.finished).map((c) => c.enrollment.course_id));
  const todayEnrollment = pickToday(
    my.courses.map((c) => c.enrollment),
    finished,
  );
  const today = my.courses.find((c) => c.enrollment.course_id === todayEnrollment?.course_id) ?? null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const s = q.trim();
    nav(`/khoa-hoc/tim-kiem${s ? `?q=${encodeURIComponent(s)}` : ""}`);
  };

  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to="/" aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="grid" />
        </Link>
        <h1 className="page-title">{t("hub.courses")}</h1>
      </header>
      <main className="main courses-main">
        <TodayBlock today={today} plan={plan} loading={my.status === "loading"} kid={kid} age={user?.age_band ?? null} />

        <div className="head">
          <h2>{t("courses.mine")}</h2>
        </div>

        <form className="search" role="search" onSubmit={submit} data-guide="course-search" data-guide-label={t("courses.search.title")}>
          <Icon name="search" />
          <input name="q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("courses.search.placeholder")} aria-label={t("courses.search.label")} />
        </form>

        {my.offline && (
          <p className="note muted small" role="status">
            {t("courses.offlineList")}
          </p>
        )}
        {my.status === "error" && (
          <p className="note muted" role="alert">
            {t("courses.loadFailed")}
          </p>
        )}

        <div data-guide="my-courses" data-guide-label={t("courses.mine")}>
          {my.status === "ready" && my.courses.length === 0 && <p className="muted none-yet">{t("courses.noneYet")}</p>}
          {kid ? (
            <div className="kid-shelf">
              {my.courses.map((c) => (
                <KidTile key={c.enrollment.course_id} c={c} />
              ))}
            </div>
          ) : (
            <ul className="courses">
              {my.courses.map((c) => (
                <li key={c.enrollment.course_id}>
                  <CourseRow c={c} uni={user?.age_band === "uni"} />
                </li>
              ))}
            </ul>
          )}
        </div>

        {my.status === "ready" && <MoreCourses mine={new Set(my.courses.map((c) => c.enrollment.course_id))} kid={kid} />}
      </main>
    </div>
  );
}

/** The rest of the catalog for the learner's age band: real courses first, then the ones that are coming soon. */
function MoreCourses({ mine, kid }: { mine: Set<string>; kid: boolean }) {
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const [list, setList] = useState<CatalogEntry[]>([]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    api
      .getCatalog(token, { age_band: user?.age_band ?? null })
      .then((c) => alive && setList(c.courses))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [token, user?.age_band]);
  // a preview of 4: real courses first, then the ones coming soon; "Xem tất cả" opens the full catalog
  const rows = list
    .filter((c) => !mine.has(c.id))
    .sort((a, b) => Number(a.status === "coming_soon") - Number(b.status === "coming_soon"))
    .slice(0, 4);
  if (!token || rows.length === 0) return null;
  const pic = (c: CatalogEntry, className: string) => {
    const url = coverUrl(token, c.id);
    return <img className={className} src={url ? `${url}${url.includes("?") ? "&" : "?"}v=${c.cover_sha256}` : undefined} alt="" loading="lazy" onError={onMediaError} />;
  };
  return (
    <section data-guide="more-courses" data-guide-label={t("courses.all")}>
      <div className="head">
        <h2>{t("courses.all")}</h2>
        <span className="grow" />
        <Link className="btn btn-quiet" id="more-all" to="/khoa-hoc/tim-kiem">
          <span>{t("courses.catalog.seeAll")}</span>
          <Icon name="next" />
        </Link>
      </div>
      {kid ? (
        <div className="kid-shelf kid-more">
          {rows.map((c) => (
            <Link key={c.id} className="kid-tile" to={`/khoa-hoc/${c.id}`}>
              {pic(c, "pic")}
              <span>{c.title}</span>
              <CourseTags course={c} kid />
              {c.status === "coming_soon" && <span className="tag">{t("courses.soon")}</span>}
            </Link>
          ))}
        </div>
      ) : (
        <ul className="courses">
          {rows.map((c) => (
            <li key={c.id}>
              <Link className="course" to={`/khoa-hoc/${c.id}`}>
                {pic(c, "thumb")}
                <span>
                  <h3>{c.title}</h3>
                  <span className="meta">
                    <span>
                      {c.teacher_name}, {t("courses.lessons", { count: c.lessons_count })}, {formatMinutes(t, c.est_minutes)}
                    </span>
                    {c.status === "coming_soon" && <span className="tag">{t("courses.soon")}</span>}
                  </span>
                  <CourseTags course={c} />
                </span>
                <Icon name="next" className="go" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The block for a session the planner chose: its title, minutes, the one-sentence reason and a link straight to it. */
function PlannedBlock({ plan, kid, guide }: { plan: TodaySession; kid: boolean; guide: Record<string, string> }) {
  const { t, i18n } = useTranslation();
  const title = pickLang(plan, "title", i18n.language);
  const why = pickLang(plan, "reason", i18n.language);
  const to = resolveDeepLink(plan.deep_link).to;
  const label = plan.kind === "practice" || plan.kind === "review" ? t("courses.today.practice") : t("courses.today.continue");
  const button = (
    <Link className="btn btn-primary btn-big" to={to}>
      <Icon name="play" />
      <span>{label}</span>
    </Link>
  );
  if (kid) {
    return (
      <section className="today oli" aria-labelledby="today-h" {...guide}>
        <div className="today-in kid-hero">
          <div className="today-text">
            <h2 id="today-h">{title}</h2>
            <div className="row">
              {button}
              <button className="speak" type="button" aria-label={t("courses.today.readAloud")} onClick={() => speak(`${title}. ${why}`, i18n.language)}>
                <Icon name="volume" />
              </button>
            </div>
          </div>
          {plan.course_id && (
            <div className="kid-pic">
              <CourseCover courseId={plan.course_id} />
            </div>
          )}
        </div>
      </section>
    );
  }
  return (
    <section className="today oli" aria-labelledby="today-h" {...guide}>
      <div className="today-in">
        <h2 id="today-h">{title}</h2>
        {why && <p className="why">{why}</p>}
        <div className="row">
          {button}
          <span className="muted small">{t("courses.today.minutes", { count: plan.minutes })}</span>
        </div>
      </div>
    </section>
  );
}

function TodayBlock({ today, plan, loading, kid, age }: { today: MyCourse | null; plan: TodaySession | null; loading: boolean; kid: boolean; age: string | null }) {
  const { t, i18n } = useTranslation();
  const guide = { "data-guide": "course-today", "data-guide-label": t("courses.today.aria") };
  if (plan && plan.kind !== "break") return <PlannedBlock plan={plan} kid={kid} guide={guide} />;
  if (loading) return <section className="today oli" aria-busy="true" {...guide}><div className="today-in today-skeleton" /></section>;

  if (!today) {
    return (
      <section className="today oli" aria-labelledby="today-h" {...guide}>
        <div className="today-in">
          <h2 id="today-h">{t("courses.today.emptyTitle")}</h2>
          <p className="why">{t("courses.today.emptyBody")}</p>
          <div className="row">
            <Link className="btn btn-primary btn-big" to="/khoa-hoc/tim-kiem">
              <Icon name="search" />
              <span>{t("courses.today.find")}</span>
            </Link>
          </div>
        </div>
      </section>
    );
  }

  const { info, enrollment, ordinal } = today;
  const lessons = info.tree.flatMap((c) => c.lessons);
  const lesson = lessons.find((l) => l.id === enrollment.progress?.lesson_id) ?? lessons[0];
  const started = !!enrollment.progress;
  const title = kid ? t("courses.today.titleKid", { course: info.title }) : started ? t("courses.today.titleContinue", { min: lesson.est_minutes, course: info.title }) : t("courses.today.titleStart", { course: info.title });
  const why = started ? t("courses.today.whyContinue", { n: ordinal.n, lesson: lesson.title }) : t("courses.today.whyStart", { lesson: lesson.title });
  const label = !started ? t("courses.today.start") : age === "uni" ? t("courses.today.read") : t("courses.today.continue");
  const to = `/khoa-hoc/${info.id}/hoc`;

  if (kid) {
    return (
      <section className="today oli" aria-labelledby="today-h" {...guide}>
        <div className="today-in kid-hero">
          <div className="today-text">
            <h2 id="today-h">{title}</h2>
            <div className="row">
              <Link className="btn btn-primary btn-big" to={to}>
                <Icon name="play" />
                <span>{label}</span>
              </Link>
              <button className="speak" type="button" aria-label={t("courses.today.readAloud")} onClick={() => speak(title, i18n.language)}>
                <Icon name="volume" />
              </button>
            </div>
          </div>
          <div className="kid-pic">
            <CourseCover courseId={info.id} />
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="today oli" aria-labelledby="today-h" {...guide}>
      <div className="today-in">
        <h2 id="today-h">{title}</h2>
        <p className="why">{why}</p>
        <div className="row">
          <Link className="btn btn-primary btn-big" to={to}>
            <Icon name="play" />
            <span>{label}</span>
          </Link>
        </div>
      </div>
    </section>
  );
}

function statusLine(t: ReturnType<typeof useTranslation>["t"], c: MyCourse, uni: boolean): string {
  if (c.finished) return t("courses.finished");
  if (!c.enrollment.progress) return t("courses.notStarted");
  if (c.percent === 0) return t("courses.justStarted");
  const o = uni ? chapterOrdinal(c.info.tree, c.enrollment.progress) : c.ordinal;
  return t(uni ? "courses.chapterOf" : "courses.lessonOf", o) + ", " + c.info.teacher_name;
}

function CourseRow({ c, uni }: { c: MyCourse; uni: boolean }) {
  const { t } = useTranslation();
  const dl = useDownload(c.enrollment.course_id, c.enrollment.pinned_version);
  return (
    <Link className="course" to={`/khoa-hoc/${c.info.id}`}>
      <CourseCover courseId={c.info.id} className="thumb" />
      <span>
        <h3>{c.info.title}</h3>
        <span className="meta">
          <span className="bar" role="progressbar" aria-valuenow={c.percent} aria-valuemin={0} aria-valuemax={100}>
            <i style={{ width: `${c.percent}%` }} />
          </span>
          <span>{statusLine(t, c, uni)}</span>
          <DownloadNote state={dl} />
        </span>
      </span>
      <Icon name="next" className="go" />
    </Link>
  );
}

function KidTile({ c }: { c: MyCourse }) {
  const { t, i18n } = useTranslation();
  const n = stars(c.percent);
  const state = c.finished ? t("courses.finished") : !c.enrollment.progress ? t("courses.notStarted") : n >= 4 ? t("courses.almost") : t("courses.learning");
  return (
    <div className="kid-cell">
      <Link className="kid-tile" to={`/khoa-hoc/${c.info.id}`}>
        <CourseCover courseId={c.info.id} className="pic" />
        <span>{c.info.title}</span>
        <span className="stars" role="img" aria-label={t("courses.starsLabel", { n })}>
          {"★".repeat(n)}
          {"☆".repeat(5 - n)} <small>{state}</small>
        </span>
      </Link>
      <button className="speak" type="button" aria-label={t("courses.readName", { name: c.info.title })} onClick={() => speak(c.info.title, c.info.language || i18n.language)}>
        <Icon name="volume" />
      </button>
    </div>
  );
}
