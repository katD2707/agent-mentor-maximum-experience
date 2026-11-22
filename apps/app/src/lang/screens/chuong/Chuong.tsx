import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { packShaFor } from "../../../lib/sync";
import { useMyCourses, type MyCourse } from "../../kit/useMyCourses";
import { DownloadNote, useDownload } from "../../kit/common";
import { getChuong, type ChuongData } from "../../api/chuong";
import { chickenOfCourse } from "../../chickenOf";
import { Crown } from "../../components/Crown";
import { chickenSrc, drawnStage, jumpSrc, mockAge, reducedMotion } from "../../chickenArt";
import { chickenName } from "../../subjects";
import { CourseTree, lessonTo } from "./CourseTree";
import { FindBoard } from "./Find";
import { MiniPlayer, useRecaps, type Playable } from "./Recap";
import { activeIndex, findIsOpen, rowOf, stageIndex, STAGE_AT, type Row } from "./logic";
import "../../styles/fonts";
import "../../styles/chuong.css";

type Page = { status: "loading" } | { status: "error"; missing: boolean } | { status: "ready"; data: ChuongData };

/** Chuồng gà (mockups/lg-03): one subject's home. The chicken and how far it has grown; its courses; "Tìm thêm khóa". */
export function Chuong() {
  const { chicken = "" } = useParams();
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const loc = useLocation();
  const [params, setParams] = useSearchParams();
  const lang: "vi" | "en" = i18n.language === "en" ? "en" : "vi";
  const [page, setPage] = useState<Page>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const mine = useMyCourses();
  const [listening, setListening] = useState<{ p: Playable; course: string } | null>(null);
  const [jump, setJump] = useState(false);
  const jumpTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const kid = user?.age_band === "g1_5";
  const open = params.get("khoa");

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setPage({ status: "loading" });
    getChuong(token, chicken).then(
      (data) => alive && setPage({ status: "ready", data }),
      (e: unknown) => alive && setPage({ status: "error", missing: e instanceof Error && /unknown_chicken|not_found/.test(`${e.message} ${(e as { code?: string }).code ?? ""}`) }),
    );
    return () => {
      alive = false;
    };
  }, [token, chicken, attempt]);

  // this chicken's courses: the server's list when it gave one, else the enrollments grouped by their subject
  const courses: MyCourse[] = useMemo(() => {
    if (page.status !== "ready") return [];
    const ids = page.data.courseIds ? new Set(page.data.courseIds) : null;
    return mine.courses.filter((c) => (ids ? ids.has(c.info.id) : chickenOfCourse(c.info) === chicken));
  }, [mine.courses, page, chicken]);
  const rows: Row[] = useMemo(() => courses.map((c) => rowOf(c.info, c.enrollment, c.finished, c.percent)), [courses]);
  const act = activeIndex(rows);
  const openId = open === "-" ? null : open && rows.some((r) => r.id === open) ? open : rows[act]?.id ?? null;

  // the board of more courses opens at once when the address asks for it
  useEffect(() => {
    if (page.status !== "ready" || !findIsOpen(params)) return;
    const id = setTimeout(() => document.getElementById("tim-khoa")?.scrollIntoView?.({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" }), 50);
    return () => clearTimeout(id);
    // only when the page arrives
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page.status]);

  const goBack = () => {
    const b = (loc.state as { back?: string } | null)?.back;
    nav(b && !b.startsWith(`/chuong/${chicken}`) ? b : "/");
  };
  const toggle = (id: string) => {
    const p = new URLSearchParams(params);
    if (openId === id) p.set("khoa", "-");
    else p.set("khoa", id);
    setParams(p, { replace: true });
  };
  const see = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params);
      p.set("khoa", id);
      p.delete("c");
      setParams(p, { replace: true });
      setTimeout(() => document.getElementById(`course-${id}`)?.scrollIntoView?.({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" }), 120);
    },
    [params, setParams],
  );
  const start = useCallback((id: string, lessonId?: string) => nav(lessonTo(id, lessonId), { state: { back: `/chuong/${chicken}` } }), [nav, chicken]);

  if (!token || !user) return null;
  if (page.status === "error" && page.missing) return <Navigate to="/" replace />;

  const data = page.status === "ready" ? page.data : null;
  const c = data?.chicken;
  const name = c ? chickenName(c.id, lang) : chickenName(chicken, lang);
  const art = c?.art ?? chicken;
  const stage = c?.stage ?? 1;
  const level = c?.level ?? 1;
  const sIdx = stageIndex(level);
  const xp = c?.xp_in_level ?? 0;
  const drawn = drawnStage(art, stage);
  const playerOn = !!listening;
  const stageNames = t("lg.cg.stage", { returnObjects: true }) as unknown as string[];
  const ranges = t("lg.cg.range", { returnObjects: true }) as unknown as string[];
  const mon = art === "van" || art === "anh" ? art : "toan";

  const hop = () => {
    if (reducedMotion()) return;
    setJump(true);
    if (jumpTimer.current) clearTimeout(jumpTimer.current);
    jumpTimer.current = setTimeout(() => setJump(false), 1950);
  };
  const imgSrc = jump && jumpSrc(art, stage) ? (jumpSrc(art, stage) as string) : chickenSrc(art, stage, "stand", reducedMotion());

  // what the chicken suggests today
  const cur = rows[act];
  const nextLesson = cur ? cur.lessons[Math.min(cur.at, cur.lessons.length - 1)] : null;
  let says: string;
  if (!cur) says = t("lg.cg.saysNone");
  else if (cur.finished) says = t("lg.cg.saysDone");
  else if (cur.state === "new") says = t("lg.cg.saysNew", { name });
  else says = kid ? t("lg.cg.saysContinueKid") : t("lg.cg.saysContinue", { c: cur.title.replace(/^[^:]*: /, ""), n: Math.min(cur.at + 1, cur.lessons.length) });
  const goCur = () => (cur ? start(cur.id, cur.finished ? cur.lessons[0]?.id : nextLesson?.id) : document.getElementById("tim-khoa")?.scrollIntoView?.({ behavior: "auto", block: "start" }));

  return (
    <div className="ck" data-mon={mon} data-age={mockAge(user.age_band)} data-player={playerOn ? "on" : "off"}>
      <div className="ck-wrap">
        <div className="ck-top">
          <button className="ck-back" type="button" onClick={goBack} aria-label={t("lg.cg.backAria")}>
            <Icon name="back" />
            <span>{t("lg.cg.back")}</span>
          </button>
          <span className="ck-crumb">{t("lg.cg.crumb", { name })}</span>
        </div>

        {page.status === "loading" && (
          <p className="ck-msg" role="status" style={{ color: "#fff" }}>
            {t("lg.cg.loading")}
          </p>
        )}
        {page.status === "error" && (
          <p className="ck-msg" role="alert" style={{ color: "#fff" }}>
            {t("lg.cg.failed")}
            <button type="button" style={{ color: "#ffcf3d" }} onClick={() => setAttempt((n) => n + 1)}>
              {t("lg.cg.retry")}
            </button>
          </p>
        )}

        {c && (
          <div className="ck-cols">
            <section className="ck-board ck-me-col" aria-labelledby="gname">
              <h1 className="ck-ribbon" id="gname">
                {name}
              </h1>
              <div className="ck-stage" data-drawn={drawn}>
                <div className="ck-sky" />
                <button className="ck-chick" type="button" onClick={hop} aria-label={t("lg.cg.jumpAria")}>
                  <img className={jump ? "ck-jump" : undefined} src={imgSrc} alt="" onError={(e) => (e.currentTarget.src = chickenSrc(art, stage, "stand", true))} />
                </button>
                <span className="ck-tap">{t("lg.cg.jump")}</span>
              </div>
              <div className="ck-plate">
                <span className="ck-lv">{level}</span>
                <span>{name}</span>
                <span style={{ fontWeight: 500, fontSize: ".85em", color: "#ffe9a8" }}>· {stageNames[sIdx - 1]}</span>
                <Crown stage={sIdx} />
              </div>
              <div className="ck-grow">
                <ol className="ck-stages" aria-label={t("lg.cg.stagesAria")}>
                  {stageNames.map((s, i) => {
                    const st = i + 1 < sIdx ? "ck-done" : i + 1 === sIdx ? "ck-cur" : "";
                    return (
                      <li key={s} className={st} aria-current={st === "ck-cur" ? "step" : undefined}>
                        <i>{st === "ck-done" ? "✓" : i + 1}</i>
                        <span>{s}</span>
                        <small>{ranges[i]}</small>
                      </li>
                    );
                  })}
                </ol>
                <div className="ck-gbar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={xp} aria-label={t("lg.cg.xpAria")}>
                  <i style={{ width: `${xp}%` }} />
                </div>
                <p className="ck-gtxt">
                  <Trans i18nKey="lg.cg.xpLine" values={{ xp, left: 100 - xp, next: level + 1 }} components={{ b: <b /> }} />
                </p>
                <p className="ck-gnote">{sIdx === 4 ? t("lg.cg.noteMax") : t("lg.cg.noteNext", { lv: STAGE_AT[sIdx], stage: stageNames[sIdx] })}</p>
              </div>
              <div className="ck-says" role="note">
                <small>{t("lg.cg.saysWho", { name })}</small>
                <span>{says}</span>
                <button className="ck-gbtn" type="button" style={{ justifySelf: "start" }} onClick={goCur}>
                  <Icon name={cur ? "play" : "search"} />
                  <span>{cur ? t("lg.cg.studyNow") : t("lg.cg.saysFind")}</span>
                </button>
              </div>
            </section>

            <div className="ck-rcol">
              <section className="ck-board" aria-labelledby="ct">
                <h2 className="ck-ribbon" id="ct">
                  {t("lg.cg.coursesTitle", { name })}
                </h2>
                {cur && (
                  <div className="ck-cta-row">
                    <button className="ck-gbtn ck-cta" type="button" onClick={goCur} data-testid="cta">
                      <Icon name="play" />
                      <span>{cur.finished ? t("lg.cg.cta.review") : cur.state === "new" ? t("lg.cg.cta.start") : t("lg.cg.cta.continue")}</span>
                      <span className="ck-sub">
                        {t("lg.cg.ctaSub", { course: cur.title, lesson: nextLesson?.title ?? "" })}
                        {nextLesson && !cur.finished ? t("lg.cg.ctaMin", { count: nextLesson.est_minutes }) : ""}
                      </span>
                    </button>
                  </div>
                )}
                <div className="ck-courses">
                  {mine.status === "loading" && <p className="ck-msg">{t("lg.cg.loading")}</p>}
                  {mine.status !== "loading" && rows.length === 0 && <p className="ck-msg">{t("lg.cg.noCourses")}</p>}
                  {courses.map((mc, i) => (
                    <CourseItem key={mc.info.id} mc={mc} row={rows[i]} open={openId === mc.info.id} name={name} band={user.age_band} tests={data?.tests ?? []} onToggle={() => toggle(mc.info.id)} onListen={(p) => setListening({ p, course: mc.info.id })} />
                  ))}
                </div>
              </section>
              <FindBoard chicken={c.id} name={name} band={user.age_band} owned={new Set(mine.courses.map((m) => m.info.id))} onAdded={() => mine.reload()} onSee={see} onStart={start} />
            </div>
          </div>
        )}
      </div>
      {listening && <MiniPlayer key={listening.p.chapter.id} item={listening.p} kid={!!kid} name={name} face={chickenSrc(art, stage, "stand", true)} onClose={() => setListening(null)} />}
    </div>
  );
}

function CourseItem({ mc, row, open, name, band, tests, onToggle, onListen }: { mc: MyCourse; row: Row; open: boolean; name: string; band: string | null; tests: ChuongData["tests"]; onToggle(): void; onListen(p: Playable): void }) {
  const { t } = useTranslation();
  const v = mc.enrollment.pinned_version;
  const recaps = useRecaps(row.id, v, packShaFor(mc.info, v), open);
  const dl = useDownload(row.id, v);
  const tag = row.state === "now" ? <span className="ck-tag ck-now">{t("lg.cg.state.now")}</span> : row.state === "fin" ? <span className="ck-tag ck-fin">{t("lg.cg.state.fin")}</span> : <span className="ck-tag ck-new">{t("lg.cg.state.new")}</span>;
  const pct = row.lessons.length ? Math.round((Math.min(row.at, row.lessons.length) / row.lessons.length) * 100) : 0;
  return (
    <article className={`ck-course${open ? " ck-open" : ""}`} id={`course-${row.id}`}>
      <button className="ck-c-head" type="button" aria-expanded={open} aria-controls={`cb-${row.id}`} onClick={onToggle}>
        <span className="ck-c-ic">
          <Icon name="book" />
        </span>
        <span className="ck-c-t">
          <b>{row.title}</b>
          <span className="ck-c-m">
            <span className="ck-mbar" aria-hidden="true">
              <i style={{ width: `${pct}%` }} />
            </span>
            <span>{t("lg.cg.lessonsOf", { done: Math.min(row.at, row.lessons.length), total: row.lessons.length })}</span>
            {mc.enrollment.update_available && <span className="ck-upd">{t("lg.cg.update")}</span>}
            {open && <DownloadNote state={dl} />}
          </span>
        </span>
        {tag}
        <span className="ck-c-chev">
          <Icon name="chev" />
        </span>
      </button>
      {open && (
        <div className="ck-c-body" id={`cb-${row.id}`}>
          <CourseTree row={row} band={band} name={name} recaps={recaps} tests={tests} onListen={onListen} />
        </div>
      )}
    </article>
  );
}

export default Chuong;
