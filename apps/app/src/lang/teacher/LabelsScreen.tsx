import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { coverUrl, teacherApi, type CourseLevel, type TeacherCourseDetail } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { LEVELS } from "../../lib/teacher/level";
import { chickenName, subjectsFor, UNI, type Subject } from "../subjects";
import { Opening, TeacherTop, useToast, withTimeout } from "./common";
import { useTeacherCourses } from "./live";
import { LevelBars } from "./LevelTag";
import { putLabels } from "./labelsApi";
import { gradeWarning, gradesFor, guessLabels, labelsBody, missingFields, type Bac, type LabelField, type Labels } from "./labels";
import "./teacher-lg.css";

const base = import.meta.env.BASE_URL;
const MAX_GOALS = 6;
const MAX_TOPICS = 8;
/** how long a save or an open may take before the screen says so */
const SAVE_TIMEOUT_MS = 20000;
const OPEN_TIMEOUT_MS = 60000;
/** The goal lines the way the gateway keeps them: blank lines dropped, spaces collapsed, at most 6 lines of 160 characters. */
export const goalLines = (text: string): string[] =>
  text
    .split(/\r?\n/)
    .map((x) => x.replace(/\s+/g, " ").trim().slice(0, 160))
    .filter(Boolean)
    .slice(0, MAX_GOALS);
const GROUPS: [string, number[]][] = [
  ["g1_5", [1, 2, 3, 4, 5]],
  ["g6_9", [6, 7, 8, 9]],
  ["g10_12", [10, 11, 12]],
];

/** The chicken list of the picked level: school lists depend on the grade (Khoa học below grade 10, Lí/Hóa/Sinh from it). */
export const chickensFor = (l: Labels): Subject[] => (l.bac === "dh" ? UNI : subjectsFor(l.grade && l.grade >= 10 ? "g10_12" : l.grade ? "g6_9" : "g10_12"));

function radioKeys(e: KeyboardEvent<HTMLElement>) {
  if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key)) return;
  const all = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]'));
  const i = all.indexOf(document.activeElement as HTMLElement);
  if (i < 0) return;
  e.preventDefault();
  all[(i + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length].click();
}

/** gv labels: Mentor pre-fills the course labels; the teacher checks them. Continue saves them (this confirms the difficulty). */
export default function Labels() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const { refresh: refreshList } = useTeacherCourses();
  const [detail, setDetail] = useState<TeacherCourseDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const toast = useToast(3000);
  const [cur, setCur] = useState<Labels | null>(null);
  /** fields Mentor could not decide: the one still open is explained in the note on top */
  const [open, setOpen] = useState<Set<LabelField>>(new Set());
  /** fields the teacher has set or confirmed by tapping */
  const [touched, setTouched] = useState<Set<LabelField>>(new Set());
  const [nudged, setNudged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guessed = useRef<Labels | null>(null);
  // Mục tiêu (one goal a line), Ngôn ngữ and Chủ đề: optional, prefilled from the saved labels else Mentor's suggestion
  const [goals, setGoals] = useState("");
  const [language, setLanguage] = useState<"vi" | "en">("vi");
  const [topics, setTopics] = useState<string[]>([]);
  const [topicIn, setTopicIn] = useState("");

  useEffect(() => {
    if (!token) return;
    let dead = false;
    setLoadFailed(false);
    withTimeout(teacherApi.getCourse(token, id), OPEN_TIMEOUT_MS).then(
      (d) => !dead && setDetail(d),
      (e) => {
        if (dead) return;
        if ((e as { status?: number }).status === 404) setMissing(true);
        else setLoadFailed(true);
      },
    );
    return () => {
      dead = true;
    };
  }, [token, id, attempt]);

  const version = Number(params.get("v")) || detail?.course.latest_version || 1;
  const vinfo = detail?.course.versions.find((v) => v.version === version);
  const published = vinfo?.status === "published";

  // Mentor's guess, once per course and version
  useEffect(() => {
    if (!detail) return;
    const g = guessLabels({ title: detail.course.title, subject: detail.course.subject, age_band: detail.course.age_band, level_suggested: detail.course.level_suggested, level: detail.course.level, saved: detail.course.labels, versions: detail.course.versions }, version);
    guessed.current = g;
    setCur(g);
    setOpen(new Set(missingFields(g)));
    setTouched(new Set());
    setNudged(false);
    const l = detail.course.labels;
    const pick = <T,>(now: T[] | undefined, sug: T[] | undefined): T[] => (now && now.length ? now : (sug ?? []));
    setGoals(pick(l?.goals, l?.suggested?.goals).join("\n"));
    setLanguage(l?.language ?? l?.suggested?.language ?? "vi");
    setTopics(pick(l?.topics, l?.suggested?.topics).slice(0, MAX_TOPICS));
    setTopicIn("");
  }, [detail?.course.id, version]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = useMemo(() => (cur ? chickensFor(cur) : []), [cur]);
  const lang = i18n.language === "en" ? "en" : "vi";

  const set = useCallback((f: LabelField, patch: Partial<Labels>) => {
    setCur((c) => (c ? { ...c, ...patch } : c));
    setTouched((x) => new Set(x).add(f));
    setOpen((x) => {
      const n = new Set(x);
      n.delete(f);
      return n;
    });
  }, []);

  const pickBac = (b: Bac) => {
    if (!cur || cur.bac === b) return;
    // the other level has other chickens and grades: those start over
    setCur({ ...cur, bac: b, chicken: null, grade: null });
    setTouched((x) => {
      const n = new Set(x).add("bac");
      n.delete("chicken");
      n.delete("grade");
      return n;
    });
    setOpen((x) => new Set([...x, "chicken", "grade"]));
  };

  if (missing)
    return (
      <div className="app">
        <TeacherTop step={3} courseId={id} backTo="/" />
        <main className="main">
          <p role="alert">{t("gv.notFound")}</p>
        </main>
      </div>
    );

  const need = cur ? missingFields(cur) : [];
  const complete = !!cur && need.length === 0;
  const warn = cur ? gradeWarning(cur) : null;

  const status = (f: LabelField): "need" | "ok" | "mentor" => {
    if (!cur) return "mentor";
    if (cur[f] === null) return "need";
    return touched.has(f) ? "ok" : "mentor";
  };
  const isNeed = (f: LabelField) => !!cur && cur[f] === null && (nudged || open.has(f));

  const go = async () => {
    if (!cur || !token || saving) return;
    const body = labelsBody(cur);
    if (!body) {
      setNudged(true);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await withTimeout(putLabels(token, id, version, { ...body, goals: goalLines(goals), language, topics }), SAVE_TIMEOUT_MS);
      refreshList();
      setTouched(new Set(["bac", "chicken", "grade", "difficulty"]));
      toast.show(t("lg.gvl.labels.saved"));
    } catch (e) {
      setError(t((e as { status?: number }).status === 422 ? "lg.gvl.labels.chickenRejected" : "lg.gvl.labels.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const title = detail?.course.title ?? "";
  const cover = detail?.course.cover_url || (detail?.course.cover_sha256 && token ? coverUrl(token, id) : "");
  const lessons = detail?.outline ? detail.outline.chapters.reduce((n, c) => n + c.lessons.length, 0) : 0;
  const sel = list.find((s) => s.id === cur?.chicken);
  const unsureField = guessed.current ? missingFields(guessed.current).find((f) => open.has(f)) : undefined;

  const head = (f: LabelField, label: string, hid: string) => {
    const s = status(f);
    return (
      <div className="fhead">
        <h2 id={hid}>{label}</h2>
        <span className={`tag${s === "ok" ? " ok" : s === "need" ? " wait" : ""}`}>
          {s === "ok" && <Icon name="check" />}
          {t(s === "ok" ? "lg.gvl.labels.tagOk" : s === "need" ? "lg.gvl.labels.tagNeed" : "lg.gvl.labels.tagMentor")}
        </span>
      </div>
    );
  };


  return (
    <div className="app lbl">
      <TeacherTop step={3} courseId={id} backTo={`/khoa/${encodeURIComponent(id)}`}>
        {cur && (
          <button type="button" className="btn btn-primary act" id="go" aria-disabled={!complete || undefined} disabled={saving} onClick={() => void go()}>
            {saving ? t("lg.gvl.labels.saving") : t("lg.gvl.labels.save")}
          </button>
        )}
      </TeacherTop>
      <main className="main lbl-main">
        <div className="course-head lbl-head">
          <span className="media" aria-hidden="true">
            {cover ? <img src={cover} alt="" /> : <Icon name="layers" />}
          </span>
          <div>
            <h1>{title}</h1>
            <div className="meta">{lessons ? t("lg.gvl.labels.meta", { lessons }) : ""}</div>
          </div>
        </div>
        {!cur ? (
          <Opening failed={loadFailed} message={t("lg.gvl.openFailed")} onRetry={() => setAttempt((n) => n + 1)} />
        ) : (
          <>
            <p className="lead">{t("lg.gvl.labels.lead")}</p>
            {unsureField && (
              <div className="unsure-note" role="status">
                <Icon name="flag" />
                <span>{t("lg.gvl.labels.unsure", { what: t(`lg.gvl.labels.unsureWhat.${unsureField === "bac" ? "band" : unsureField}`) })}</span>
              </div>
            )}
            <p className="need-msg" role="status">
              {nudged && !complete ? t("lg.gvl.labels.need") : ""}
            </p>
            {published && <p className="muted small">{t("lg.gvl.labels.published")}</p>}
            {error && (
              <div className="alert" role="alert">
                <span>{error}</span>
                <button className="btn btn-ghost" type="button" onClick={() => setError(null)}>
                  {t("gv.ok")}
                </button>
              </div>
            )}
            <div className="layout">
              <form className="fields" onSubmit={(e) => e.preventDefault()}>
                <section className={`field${isNeed("bac") ? " need" : ""}`} aria-labelledby="h-bac">
                  {head("bac", t("lg.gvl.labels.band"), "h-bac")}
                  <div className="opts" role="radiogroup" aria-labelledby="h-bac" onKeyDown={radioKeys}>
                    {(["pt", "dh"] as Bac[]).map((b) => (
                      <button key={b} type="button" className="opt-btn" role="radio" aria-checked={cur.bac === b} tabIndex={cur.bac === b || (cur.bac === null && b === "pt") ? 0 : -1} onClick={() => (cur.bac === b ? set("bac", {}) : pickBac(b))}>
                        <span>{t(b === "pt" ? "lg.gvl.labels.bandPt" : "lg.gvl.labels.bandDh")}</span>
                        <Icon name="check" />
                      </button>
                    ))}
                  </div>
                </section>

                <section className={`field gv-lab-chicken${isNeed("chicken") ? " need" : ""}`} aria-labelledby="h-mon">
                  {head("chicken", t("lg.gvl.labels.chicken"), "h-mon")}
                  <div className="opts" role="radiogroup" aria-labelledby="h-mon" onKeyDown={radioKeys}>
                    {list.map((s, i) => (
                      <button key={s.id} type="button" className="opt-btn sub-btn" role="radio" aria-checked={cur.chicken === s.id} tabIndex={cur.chicken === s.id || (cur.chicken === null && i === 0) ? 0 : -1} onClick={() => set("chicken", { chicken: s.id })}>
                        <span className="ico" aria-hidden="true">
                          <img alt="" src={`${base}ga/${s.art}.png`} />
                        </span>
                        <span>{lang === "en" ? s.en : s.vi}</span>
                        <Icon name="check" />
                      </button>
                    ))}
                  </div>
                  <p className="fhint">{t("lg.gvl.labels.chickenHint")}</p>
                </section>

                <section className={`field${isNeed("grade") ? " need" : ""}`} aria-labelledby="h-lop">
                  {head("grade", t(cur.bac === "dh" ? "lg.gvl.labels.year" : "lg.gvl.labels.grade"), "h-lop")}
                  <div role="radiogroup" aria-labelledby="h-lop" onKeyDown={radioKeys}>
                    {cur.bac === "dh" ? (
                      <div className="opts">
                        {gradesFor("dh").map((n) => (
                          <GradeBtn key={n} cur={cur.grade} n={n} first={n === 1} label={t("lg.gvl.labels.yearN", { n })} onPick={() => set("grade", { grade: n })} />
                        ))}
                      </div>
                    ) : (
                      GROUPS.map(([g, ls]) => (
                        <div key={g}>
                          <div className="grp-label">{t(`lg.gvl.labels.gradeGroups.${g}`)}</div>
                          <div className="opts">
                            {ls.map((n) => (
                              <GradeBtn key={n} cur={cur.grade} n={n} first={n === 1} label={String(n)} onPick={() => set("grade", { grade: n, ...(cur.bac === null ? { bac: "pt" as Bac } : {}) })} />
                            ))}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                  <p className={`fhint${warn ? " warn" : ""}`} aria-live="polite">
                    {warn === "low" ? t("lg.gvl.labels.warnLow", { grade: cur.grade }) : warn === "high" ? t("lg.gvl.labels.warnHigh") : ""}
                  </p>
                </section>

                <section className={`field${isNeed("difficulty") ? " need" : ""}`} aria-labelledby="h-kho">
                  {head("difficulty", t("lg.gvl.labels.difficulty"), "h-kho")}
                  <div className="opts" role="radiogroup" aria-labelledby="h-kho" onKeyDown={radioKeys}>
                    {LEVELS.map((l: CourseLevel, i) => (
                      <button key={l} type="button" className="opt-btn" role="radio" aria-checked={cur.difficulty === l} tabIndex={cur.difficulty === l || (cur.difficulty === null && i === 0) ? 0 : -1} onClick={() => set("difficulty", { difficulty: l })}>
                        <LevelBars level={l} />
                        <span>{t(`lg.gvl.levelOf.${l}`)}</span>
                        <Icon name="check" />
                      </button>
                    ))}
                  </div>
                </section>

                <section className="field gv-lab-goals" aria-labelledby="h-mt">
                  <div className="fhead">
                    <h2 id="h-mt">{t("lg.gvl.labels.goals")}</h2>
                  </div>
                  <textarea
                    className="gv-lab-area"
                    rows={4}
                    value={goals}
                    aria-labelledby="h-mt"
                    placeholder={t("lg.gvl.labels.goalsPlaceholder")}
                    maxLength={MAX_GOALS * 170}
                    onChange={(e) => setGoals(e.target.value)}
                  />
                  <p className="fhint" aria-live="polite">
                    {goals.split(/\r?\n/).filter((x) => x.trim()).length > MAX_GOALS ? t("lg.gvl.labels.goalsTooMany") : t("lg.gvl.labels.goalsHint")}
                  </p>
                </section>

                <section className="field gv-lab-lang" aria-labelledby="h-nn">
                  <div className="fhead">
                    <h2 id="h-nn">{t("lg.gvl.labels.language")}</h2>
                  </div>
                  <div className="opts" role="radiogroup" aria-labelledby="h-nn" onKeyDown={radioKeys}>
                    {(["vi", "en"] as const).map((l) => (
                      <button key={l} type="button" className="opt-btn" role="radio" aria-checked={language === l} tabIndex={language === l ? 0 : -1} onClick={() => setLanguage(l)}>
                        <span>{t(l === "vi" ? "lg.gvl.labels.langVi" : "lg.gvl.labels.langEn")}</span>
                        <Icon name="check" />
                      </button>
                    ))}
                  </div>
                </section>

                <section className="field gv-lab-topics" aria-labelledby="h-cd" style={{ borderBottom: 0 }}>
                  <div className="fhead">
                    <h2 id="h-cd">{t("lg.gvl.labels.topics")}</h2>
                    <span className="opt">{t("lg.gvl.labels.topicsMax")}</span>
                  </div>
                  <div className="topics">
                    {topics.map((tp) => (
                      <span className="topic" key={tp}>
                        {tp}
                        <button type="button" aria-label={t("lg.gvl.labels.topicRemove", { t: tp })} onClick={() => setTopics((l) => l.filter((x) => x !== tp))}>
                          <Icon name="x" />
                        </button>
                      </span>
                    ))}
                    <input
                      className="tinput"
                      type="text"
                      maxLength={40}
                      value={topicIn}
                      disabled={topics.length >= MAX_TOPICS}
                      placeholder={t(topics.length >= MAX_TOPICS ? "lg.gvl.labels.topicFull" : "lg.gvl.labels.topicAdd")}
                      aria-label={t("lg.gvl.labels.topics")}
                      onChange={(e) => setTopicIn(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key !== "Enter") return;
                        e.preventDefault();
                        const v = topicIn.replace(/\s+/g, " ").trim();
                        if (v && !topics.includes(v) && topics.length < MAX_TOPICS) setTopics((l) => [...l, v]);
                        setTopicIn("");
                      }}
                    />
                  </div>
                  {(() => {
                    const left = (detail?.course.labels?.suggested?.topics ?? []).filter((x) => !topics.includes(x));
                    return left.length > 0 && topics.length < MAX_TOPICS ? (
                      <div className="sugg">
                        <span>{t("lg.gvl.labels.topicSuggest")}</span>
                        {left.map((x) => (
                          <button key={x} type="button" className="sg" onClick={() => setTopics((l) => [...l, x])}>
                            <Icon name="plus" />
                            {x}
                          </button>
                        ))}
                      </div>
                    ) : null;
                  })()}
                  <p className="fhint">{t("lg.gvl.labels.topicsHint")}</p>
                </section>

              </form>

              <aside className="side" aria-live="polite">
                <h2>{t("lg.gvl.labels.previewTitle")}</h2>
                {sel && cur.chicken ? (
                  <div className="pvbox">
                    <Crop art={sel.art} />
                    <span className="shelf" />
                    <div className="cname">{chickenName(sel.id, lang)}</div>
                    <div className="csub">
                      {[cur.grade ? (cur.bac === "dh" ? t("lg.gvl.labels.yearN", { n: cur.grade }) : `${t("lg.gvl.labels.grade")} ${cur.grade}`) : "", cur.difficulty ? t(`lg.gvl.levelOf.${cur.difficulty}`) : ""].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                ) : (
                  <p className="empty">{t("lg.gvl.labels.previewEmpty")}</p>
                )}
              </aside>
            </div>
          </>
        )}
      </main>
      {toast.node}
    </div>
  );
}

function GradeBtn({ cur, n, label, first, onPick }: { cur: number | null; n: number; label: string; first?: boolean; onPick(): void }) {
  return (
    <button type="button" className="opt-btn sq" role="radio" aria-checked={cur === n} tabIndex={cur === n || (cur === null && first) ? 0 : -1} onClick={onPick}>
      <span>{label}</span>
    </button>
  );
}

/** The chicken's picture cropped to the drawing (the grown chicken spans top..85% of the 512 frame). */
function Crop({ art }: { art: string }) {
  const top = 0.33;
  const w = 112;
  const S = w / 0.35;
  return (
    <span className="crop" style={{ width: w, height: S * (0.85 - top) }}>
      <img alt="" src={`${base}ga/${art}.png`} style={{ width: S, left: -0.34 * S, top: -top * S }} />
    </span>
  );
}
