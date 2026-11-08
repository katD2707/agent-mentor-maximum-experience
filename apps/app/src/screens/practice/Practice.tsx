import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, PracticeError, type PHome, type PSession, type StartSource } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import quickArt from "../../assets/hub/luyen-tap.jpg";
import { speak } from "../../lib/speak";
import { answeredCount, clockText, fmtScore10, initialRemaining, unfinished } from "../../lib/practice";
import { CourseCover } from "../courses/common";
import { Dialog } from "./Dialog";

type State = { s: "loading" } | { s: "error" } | { s: "ready"; home: PHome; active: PSession | null };

/** hs-07: quick practice, mock exams, by course. Only the back button on top (sessions are focus screens). */
export function Practice() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "en" ? "en" : "vi";
  const { token, user } = useAuth();
  const kid = user?.age_band === "g1_5";
  const nav = useNavigate();
  const [st, setSt] = useState<State>({ s: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<PHome["mocks"][number] | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setSt({ s: "loading" });
    Promise.all([practice.home(token), practice.active(token).catch(() => null)]).then(
      ([home, active]) => alive && setSt({ s: "ready", home, active: unfinished(active) ? active : null }),
      () => alive && setSt({ s: "error" }),
    );
    return () => {
      alive = false;
    };
  }, [token, attempt]);

  const start = useCallback(
    async (source: StartSource, seed?: string | number) => {
      if (!token || starting) return;
      setStarting(source);
      setError(null);
      setConfirm(null);
      try {
        const s = await practice.start(token, { source, ...(seed !== undefined ? { seed } : {}) });
        nav(`/luyen-tap/${encodeURIComponent(s.id)}`);
      } catch (e) {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`);
        else if (e instanceof PracticeError && e.code === "insufficient_content") setError("insufficient");
        else setError("failed");
        setStarting(null);
      }
    },
    [nav, starting, token],
  );

  const home = st.s === "ready" ? st.home : null;
  const active = st.s === "ready" ? st.active : null;
  const quick = home?.quick;
  const empty = !!quick && (quick.count === 0 || quick.reason === "insufficient_content");

  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to="/" aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="grid" />
        </Link>
        <h1 className="page-title">{t("hub.practice")}</h1>
      </header>
      <main className="main practice-main">
        {st.s === "loading" && <p className="muted" role="status">{t("practice.loading")}</p>}
        {st.s === "error" && (
          <div className="pr-msg">
            <p role="alert">{t("practice.loadFailed")}</p>
            <button className="btn btn-primary" onClick={() => setAttempt((n) => n + 1)}>
              {t("practice.retry")}
            </button>
          </div>
        )}

        {active && (
          <section className="resume oli" data-guide="practice-resume" data-guide-label={t("practice.resumeTitle")}>
            <div>
              <h2>{t("practice.resumeTitle")}</h2>
              <p className="muted">
                {active.kind === "mock"
                  ? t("practice.resumeMock", { time: clockText(initialRemaining(active, Date.now()) ?? 0) })
                  : t("practice.resumeBody", { done: answeredCount(active), total: active.items.length })}
              </p>
            </div>
            <Link className="btn btn-primary" to={`/luyen-tap/${encodeURIComponent(active.id)}`}>
              {t("practice.resumeBtn")}
            </Link>
          </section>
        )}

        {quick && (
          <section className={`quick oli ${kid ? "quick-kid" : ""}`} data-guide="practice-quick" data-guide-label={t("practice.quickTitle", { n: quick.count, minutes: quick.minutes })}>
            {empty ? (
              <>
                {kid && <img className="quick-pic" src={quickArt} alt="" />}
                <p className="quick-empty" role="status">
                  {t(kid ? "practice.insufficientKid" : "practice.insufficient")}
                </p>
                <p>
                  <Link className={`btn btn-primary ${kid ? "btn-big" : ""}`} to="/khoa-hoc">
                    {t("practice.goCourses")}
                  </Link>
                </p>
              </>
            ) : (
              <>
                {kid && <img className="quick-pic" src={quickArt} alt="" />}
                <h2>{t(kid ? "practice.quickTitleKid" : "practice.quickTitle", { n: quick.count, minutes: quick.minutes })}</h2>
                <p className="muted">{t(kid ? "practice.quickBodyKid" : "practice.quickBody")}</p>
                {!kid && quick.from.length > 0 && (
                  <div className="mix">
                    {quick.from.map((f, i) => (
                      <span className="tag" key={`${f.course_id ?? f.subject}-${i}`}>
                        {f.label} {f.n}
                      </span>
                    ))}
                  </div>
                )}
                <p className="pr-row">
                  <button className="btn btn-primary btn-big" type="button" disabled={!!starting} onClick={() => void start("quick", quick.seed)}>
                    <Icon name="play" />
                    <span>{t(kid ? "practice.startKid" : "practice.start")}</span>
                  </button>
                  {kid && (
                    <button className="icon-btn" type="button" aria-label={t("practice.readQuick")} onClick={() => speak(t("practice.quickTitleKid", { n: quick.count }), lang)}>
                      <Icon name="volume" />
                    </button>
                  )}
                </p>
              </>
            )}
            {error === "insufficient" && !empty && (
              <p className="note" role="alert">
                {t(kid ? "practice.insufficientKid" : "practice.insufficient")} <Link to="/khoa-hoc">{t("practice.goCourses")}</Link>
              </p>
            )}
          </section>
        )}
        {error === "failed" && (
          <p className="note muted" role="alert">
            {t("practice.startFailed")}
          </p>
        )}

        {home && home.mocks.length > 0 && (
          <section data-guide="practice-mock" data-guide-label={t("practice.mocksTitle")}>
            <div className="head">
              <h2>{t("practice.mocksTitle")}</h2>
            </div>
            <ul className="rows">
              {home.mocks.map((m) => (
                <li key={m.profile_id}>
                  <div>
                    <h3>{m.title}</h3>
                    <p>
                      {t("practice.mockMeta", { minutes: m.minutes, items: m.items })}. {m.last_score != null ? t("practice.mockLast", { score: fmtScore10(m.last_score, lang) }) : t("practice.mockNew")}
                    </p>
                  </div>
                  <button className="btn btn-ghost" type="button" disabled={!!starting} onClick={() => setConfirm(m)}>
                    {t("practice.takeMock")}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {home && (
          <section data-guide="practice-courses" data-guide-label={t("practice.byCourse")}>
            <div className="head">
              <h2>{t("practice.byCourse")}</h2>
            </div>
            {home.by_course.length === 0 ? (
              <p className="muted none-yet">{t("practice.noCourses")}</p>
            ) : (
              <ul className="rows with-media">
                {home.by_course.map((c) => (
                  <li key={c.course_id}>
                    <span className="thumb">
                      <CourseCover courseId={c.course_id} />
                    </span>
                    <div>
                      <h3>{c.title}</h3>
                      <p>{t("practice.courseMeta", { range: c.lessons_range, n: c.items })}</p>
                    </div>
                    <button className="btn btn-quiet" type="button" disabled={!!starting} onClick={() => void start(`course:${c.course_id}`)}>
                      {t("practice.practiceBtn")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </main>

      {confirm && (
        <Dialog title={t("practice.mockConfirmTitle")} onClose={() => setConfirm(null)}>
          <p>
            <b>{confirm.title}</b>
          </p>
          <p>{t("practice.mockConfirmBody", { items: confirm.items, minutes: confirm.minutes })}</p>
          <p className="pr-row">
            <button className="btn btn-primary" onClick={() => void start(`mock:${confirm.profile_id}`)}>
              {t("practice.takeMock")}
            </button>
            <button className="btn btn-ghost" onClick={() => setConfirm(null)}>
              {t("practice.later")}
            </button>
          </p>
        </Dialog>
      )}
    </div>
  );
}
