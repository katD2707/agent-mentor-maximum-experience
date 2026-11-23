import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, type Goal, type PlanItem, type WeekPlan } from "../../../api";
import type { Milestone } from "../../../api/research-types";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { CourseCover } from "../../kit/common";
import { useMyCourses, type MyCourse } from "../../kit/useMyCourses";
import { buildGoal, toYmd, type DeadlinePick } from "../../../lib/goalForm";
import { pickLang } from "../../../lib/today";
import { resolveDeepLink } from "../../../lib/deeplink";
import { refreshReminders } from "../../../lib/behaviour";
import { lg, type XpWeek, type XpWeekChicken, type Village } from "../../api";
import { chickenName, stageOf, STAGE_AT, subjectOf, XP_PER_LEVEL } from "../../subjects";
import { Crown } from "../../components/Crown";
import { ChickenImg, FlameIcon } from "../study/icons";
import "../../styles/fonts";
import "../../styles/lang.css";
import "../../styles/progress.css";


type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

/** lg-09 Tiến độ: the chickens' week, the plan, goals, courses, streak and the rules of growth. */
export function TienDo() {
  const { t } = useTranslation();
  return (
    <div className="lg lg-back lg-pg" data-age="g10_12">
      <header className="lg-pg-top">
        <Link className="lg-pg-round" to="/" replace aria-label={t("lg.prog.back")}>
          <Icon name="back" />
        </Link>
        <h1 className="lg-pg-ribbon">{t("lg.prog.title")}</h1>
        <span className="lg-pg-grow" />
      </header>
      <main className="lg-pg-page">
        <ProgressBoards />
      </main>
    </div>
  );
}

/** The boards of the page (also what the village week sheet can reuse). `back` is where an opened session returns to. */
export function ProgressBoards({ back = "/tien-do" }: { back?: string }) {
  const { token, user } = useAuth();
  const [week, setWeek] = useState<Load<XpWeek>>({ status: "loading" });
  const [vil, setVil] = useState<Village | null>(null);
  const [goals, setGoals] = useState<Load<Goal[]>>({ status: "loading" });
  const [plan, setPlan] = useState<Load<WeekPlan>>({ status: "loading" });
  const my = useMyCourses();

  const load = useCallback(() => {
    if (!token) return;
    setWeek({ status: "loading" });
    setGoals({ status: "loading" });
    setPlan({ status: "loading" });
    lg.xpWeek(token).then(
      (data) => setWeek({ status: "ready", data }),
      () => setWeek({ status: "error" }),
    );
    lg.getVillage(token).then(setVil, () => undefined);
    api.listGoals(token).then(
      (data) => setGoals({ status: "ready", data }),
      () => setGoals({ status: "error" }),
    );
    api.getWeekPlan(token).then(
      (data) => setPlan({ status: "ready", data }),
      () => setPlan({ status: "error" }),
    );
  }, [token]);
  useEffect(load, [load]);

  /** A goal changes the plan: read the plan and the reminders again. */
  const replan = useCallback(() => {
    if (!token) return;
    void api.getWeekPlan(token).then(
      (data) => setPlan({ status: "ready", data }),
      () => undefined,
    );
    void refreshReminders();
  }, [token]);

  const dayHas = week.status === "ready" ? week.data.days.map((_, i) => week.data.chickens.some((c) => (c.week[i] ?? 0) > 0)) : [];

  return (
    <div className="lg-pg-stack">
      <GrowBoard state={week} onRetry={load} />
      <div className="lg-pg-cols">
        <div className="lg-pg-col">
          <WeekBoard state={plan} onRetry={load} back={back} />
          <GoalsBoard state={goals} setGoals={setGoals} onChanged={replan} onRetry={load} uni={user?.age_band === "uni"} />
          <CoursesBoard my={my} />
        </div>
        <div className="lg-pg-col">
          <StreakBoard vil={vil} dayHas={dayHas} days={week.status === "ready" ? week.data.days : []} />
          <RulesBoard />
        </div>
      </div>
    </div>
  );
}

function Retry({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <p className="lg-pg-muted" role="alert">
      {t("lg.prog.loadFailed")}{" "}
      <button className="lg-pg-linkbtn" type="button" onClick={onRetry}>
        {t("lg.prog.retry")}
      </button>
    </p>
  );
}

function Board({ id, title, children, head }: { id: string; title: string; children: React.ReactNode; head?: React.ReactNode }) {
  return (
    <section className="lg-pg-board" aria-labelledby={id}>
      {head ? (
        <div className="lg-pg-head">
          <h2 id={id}>{title}</h2>
          {head}
        </div>
      ) : (
        <h2 id={id}>{title}</h2>
      )}
      {children}
    </section>
  );
}

// ---------------------------------------------------------------- the chickens this week
/** The level where a chicken grows into its next stage (stages change at levels 2, 5 and 10). */
const nextStageLevel = (level: number): number | null => STAGE_AT.find((l) => l > level) ?? null;

/** The XP sources of a week as the six rows of lg-09, worked out from what each source pays. */
export function sourceRows(by: Record<string, number>, t: (k: string, o?: Record<string, unknown>) => string): { key: string; label: string; sub: string; amount: number }[] {
  const n = (k: string) => by[k] ?? 0;
  const join = (parts: string[]) => parts.filter(Boolean).join(", ").replace(/, ,/g, ",");
  const rows: { key: string; label: string; sub: string; amount: number }[] = [];
  const add = (key: string, amount: number, sub: string) => amount > 0 && rows.push({ key, label: t(`lg.prog.src.${key}`), sub, amount });
  const lessons = Math.round(n("lesson_done") / 20);
  const perfect = Math.round(n("lesson_perfect") / 5);
  add("lesson", n("lesson_done") + n("lesson_perfect"), t("lg.prog.src.lessonSub", { n: lessons }) + (perfect > 0 ? t("lg.prog.src.lessonPerfect", { p: perfect }) : ""));
  const right = Math.round(n("practice_right") / 2);
  const fixed = Math.round(n("fix_right") / 3);
  add("practice", n("practice_right") + n("fix_right"), join([right > 0 ? t("lg.prog.src.practiceRight", { n: right }) : "", fixed > 0 ? t("lg.prog.src.practiceFix", { n: fixed }) : ""]));
  const papers = Math.round(n("paper_submit") / 40);
  const bosses = Math.round(n("boss_beaten") / 50);
  add("arena", n("paper_submit") + n("boss_beaten"), join([papers > 0 ? t("lg.prog.src.arenaSub", { n: papers }) : "", bosses > 0 ? t("lg.prog.src.arenaBoss", { n: bosses }) : ""]));
  add("mock", n("mock_submit"), t("lg.prog.src.mockSub", { n: Math.round(n("mock_submit") / 40) }));
  add("room", n("focus") + n("focus_full"), t("lg.prog.src.roomSub", { n: n("focus") }) + (n("focus_full") > 0 ? t("lg.prog.src.roomFull") : ""));
  add("cards", n("notes_review"), t("lg.prog.src.cardsSub", { n: Math.round(n("notes_review") / 2) }));
  return rows;
}

function GrowBoard({ state, onRetry }: { state: Load<XpWeek>; onRetry: () => void }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "en" ? "en" : "vi";
  const list = state.status === "ready" ? state.data.chickens.filter((c) => c.owned) : [];
  return (
    <Board id="lg-pg-h-ga" title={t("lg.prog.mine")}>
      {state.status === "loading" && <p className="lg-pg-muted">{t("lg.loading")}</p>}
      {state.status === "error" && <Retry onRetry={onRetry} />}
      {state.status === "ready" && list.length === 0 && <p className="lg-pg-muted">{t("lg.prog.noChicken")}</p>}
      <div className="lg-pg-gas">
        {list.map((c) => (
          <ChickenCard key={c.chicken} c={c} lang={lang} />
        ))}
      </div>
    </Board>
  );
}

function ChickenCard({ c, lang }: { c: XpWeekChicken; lang: "vi" | "en" }) {
  const { t } = useTranslation();
  const name = chickenName(c.chicken, lang);
  const stage = stageOf(c.level);
  const nx = nextStageLevel(c.level);
  const rows = sourceRows(c.by_source, t);
  const art = subjectOf(c.chicken)?.art ?? c.chicken;
  const left = XP_PER_LEVEL - c.xp_in_level;
  return (
    <article className="lg-pg-ga" data-chicken={c.chicken}>
      <div className="who">
        <span className="pic" role="img" aria-label={name}>
          <ChickenImg art={art} stage={stage} />
        </span>
        <div>
          <h3>
            <Link className="cname" to={`/chuong/${encodeURIComponent(c.chicken)}`}>
              {name}
            </Link>{" "}
            <span className="lv">{c.level}</span>
          </h3>
          <span className="stg">{t(`lg.prog.stage${stage}`)} <Crown stage={stage} /></span>
        </div>
      </div>
      <div className="xp">
        <div className="row">
          <span>
            {c.xp_in_level}/{XP_PER_LEVEL} {lang === "en" ? "XP" : "kinh nghiệm"}
          </span>
          <span className="lg-pg-muted">{t("lg.prog.toLevel", { n: left, l: c.level + 1 })}</span>
        </div>
        <div className="bar" role="progressbar" aria-valuenow={c.xp_in_level} aria-valuemin={0} aria-valuemax={XP_PER_LEVEL} aria-label={t("lg.prog.xpAria", { name })}>
          <i style={{ width: `${c.xp_in_level}%` }} />
        </div>
        {nx && <p className="lg-pg-muted">{t("lg.prog.nextStage", { l: nx, name: t(`lg.prog.stage${stageOf(nx)}`) })}</p>}
      </div>
      <div className="week-xp">
        <span>{t("lg.prog.gained")}</span>
        <b>{t("lg.prog.kn", { n: c.week_total })}</b>
      </div>
      {rows.length > 0 ? (
        <ul className="src">
          {rows.map((r) => (
            <li key={r.key}>
              <span>
                <span>{r.label}</span>
                <small>{r.sub}</small>
              </span>
              <b>+{r.amount}</b>
            </li>
          ))}
        </ul>
      ) : (
        <p className="lg-pg-muted">{t("lg.prog.weekZero")}</p>
      )}
      {c.week_total > 0 && <p className="say">{t("lg.prog.sayWeek", { n: c.week_total, r: left, l: c.level + 1 })}</p>}
    </article>
  );
}

// ---------------------------------------------------------------- this week: the plan
/** Monday of the week a YYYY-MM-DD day belongs to. */
function weekStart(ymd: string): string {
  const d = new Date(`${ymd}T00:00:00`);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return toYmd(d);
}

function WeekBoard({ state, onRetry, back }: { state: Load<WeekPlan>; onRetry: () => void; back: string }) {
  const { t, i18n } = useTranslation();
  const plan = state.status === "ready" ? state.data : null;
  const byDay = useMemo(() => {
    const m = new Map<string, PlanItem[]>();
    for (const it of plan?.items ?? []) m.set(it.date, [...(m.get(it.date) ?? []), it]);
    return m;
  }, [plan]);
  // a reason shown on every row says nothing; keep only the ones that differ from the rest
  const why = useMemo(() => {
    const count = new Map<string, number>();
    const items = plan?.items ?? [];
    for (const it of items) {
      const r = pickLang(it, "reason", i18n.language).trim();
      if (r) count.set(r, (count.get(r) ?? 0) + 1);
    }
    return items.filter((it) => {
      const r = pickLang(it, "reason", i18n.language).trim();
      return r && count.get(r) === 1 && it.kind !== "break";
    });
  }, [plan, i18n.language]);
  const weekdays = t("lg.prog.weekdays", { returnObjects: true }) as unknown as string[];
  // the 7 cells are the Monday-to-Sunday week the plan is in (the plan also holds the days after it)
  const days = useMemo(() => {
    if (!plan) return [];
    const start = weekStart(plan.today);
    const wk = plan.days.filter((d) => weekStart(d) === start);
    return wk.length > 0 ? wk : plan.days.slice(0, 7);
  }, [plan]);
  const note = plan ? pickLang(plan, "note", i18n.language) : "";

  return (
    <Board id="lg-pg-h-week" title={t("lg.prog.week")}>
      {state.status === "loading" && <p className="lg-pg-muted">{t("lg.loading")}</p>}
      {state.status === "error" && <Retry onRetry={onRetry} />}
      {plan && plan.items.length === 0 && <p className="lg-pg-muted">{t("lg.prog.weekEmpty")}</p>}
      {plan && plan.items.length > 0 && (
        <>
          <div className="lg-pg-week" aria-label={t("lg.prog.weekAria")}>
            {days.map((d) => {
              const items = byDay.get(d) ?? [];
              const wd = (new Date(`${d}T00:00:00`).getDay() + 6) % 7;
              const isToday = d === plan.today;
              const study = items.filter((i) => i.kind !== "break");
              const done = study.length > 0 && study.every((i) => i.done);
              const miss = !done && study.length > 0 && d < plan.today && !study.some((i) => i.done);
              const next = study.find((i) => !i.done);
              const cls = "day" + (isToday ? " today" : "") + (done ? " done" : "") + (miss ? " miss" : "") + (study.length === 0 ? " rest" : "");
              const inner = (
                <>
                  <b>
                    <span>{weekdays[wd]}</span>
                    {done && <Icon name="check" />}
                    {miss && <Icon name="x" />}
                  </b>
                  {done ? (
                    <span className="lg-vh">{t("lg.prog.done")}</span>
                  ) : miss ? (
                    <>
                      <span className="plan">{t("lg.prog.minShort", { n: next?.minutes ?? 0 })}</span>
                      <span className="lg-vh">{t("lg.prog.missed")}</span>
                    </>
                  ) : study.length === 0 ? (
                    <span className="plan">{t("lg.prog.rest")}</span>
                  ) : (
                    <span className="plan">{t("lg.prog.minShort", { n: study.reduce((n, i) => n + i.minutes, 0) })}</span>
                  )}
                  {study[0] && !miss && <span className="sub">{study[0].course_title || study[0].label}</span>}
                </>
              );
              const aria = isToday ? "date" : undefined;
              // a day with a session still to do opens that session
              return next && !miss ? (
                <Link key={d} className={cls} to={resolveDeepLink(next.deep_link).to} state={{ back }} aria-current={aria} aria-label={`${weekdays[wd]}: ${next.label}`}>
                  {inner}
                </Link>
              ) : (
                <div key={d} className={cls} aria-current={aria}>
                  {inner}
                </div>
              );
            })}
          </div>
          <p className="lg-pg-say">{t("lg.prog.planSay")}</p>
          {(note || why.length > 0) && (
            <details className="lg-pg-why">
              <summary>{t("lg.prog.why")}</summary>
              {note && <p>{note}</p>}
              {why.length > 0 && (
                <ul>
                  {why.map((it, i) => (
                    <li key={i}>
                      <b>{weekdays[(new Date(`${it.date}T00:00:00`).getDay() + 6) % 7]}</b> {pickLang(it, "reason", i18n.language).trim()}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          )}
        </>
      )}
    </Board>
  );
}

// ---------------------------------------------------------------- goals
const TAG: Record<Goal["status"], string> = { on_track: "tag ok", slightly_behind: "tag wait", behind: "tag err", new: "tag" };

function niceDate(iso: string, lang: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(lang === "en" ? "en-GB" : "vi-VN", { day: "numeric", month: "numeric", year: "numeric" });
}

function GoalsBoard({ state, setGoals, onChanged, onRetry, uni }: { state: Load<Goal[]>; setGoals: (l: Load<Goal[]>) => void; onChanged: () => void; onRetry: () => void; uni: boolean }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [adding, setAdding] = useState(false);
  const goals = state.status === "ready" ? state.data : [];
  const add = (g: Goal) => {
    setGoals({ status: "ready", data: [...goals, g] });
    setAdding(false);
    onChanged();
  };
  const remove = async (g: Goal) => {
    if (!token) return;
    try {
      await api.deleteGoal(token, g.id);
      setGoals({ status: "ready", data: goals.filter((x) => x.id !== g.id) });
      onChanged();
    } catch {
      /* the goal stays; the list is still right */
    }
  };
  // university: the next thesis deadlines ("Full paper · còn 9 ngày"), one line each
  const soon: Milestone[] = uni
    ? goals
        .filter((g) => g.source === "research")
        .flatMap((g) => g.milestones ?? [])
        .filter((m) => !m.done && m.days_left >= 0)
        .sort((a, b) => a.due_date.localeCompare(b.due_date))
        .slice(0, 2)
    : [];
  return (
    <Board
      id="lg-pg-h-goals"
      title={t("lg.prog.goals")}
      head={
        <button className="lg-pg-btn wood sm" type="button" aria-expanded={adding} onClick={() => setAdding((a) => !a)}>
          <Icon name="plus" />
          <span>{t("lg.prog.add")}</span>
        </button>
      }
    >
      {adding && <AddGoal onAdded={add} />}
      {soon.length > 0 && (
        <div className="lg-pg-soon">
          {soon.map((m) => (
            <p key={m.id}>
              <Icon name="flag" />
              <span>{t("lg.prog.daysLeft", { title: m.title, n: m.days_left })}</span>
            </p>
          ))}
        </div>
      )}
      {state.status === "loading" && <p className="lg-pg-muted">{t("lg.loading")}</p>}
      {state.status === "error" && <Retry onRetry={onRetry} />}
      {state.status === "ready" && goals.length === 0 && !adding && <p className="lg-pg-muted">{t("lg.prog.noGoals")}</p>}
      <ul className="lg-pg-goals">
        {goals.map((g) => (
          <GoalRow key={g.id} g={g} onRemove={() => remove(g)} />
        ))}
      </ul>
    </Board>
  );
}

function AddGoal({ onAdded }: { onAdded: (g: Goal) => void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<DeadlinePick["kind"]>("none");
  const [date, setDate] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || busy) return;
    const pick: DeadlinePick = kind === "date" ? { kind: "date", value: date } : { kind };
    const r = buildGoal({ title, pick });
    if (!r.ok) return setErr(r.error === "title" ? t("lg.prog.errTitle") : t("lg.prog.errDeadline"));
    setErr(null);
    setBusy(true);
    try {
      onAdded(await api.createGoal(token, r.body));
    } catch {
      setErr(t("lg.prog.saveFailed"));
      setBusy(false);
    }
  };
  return (
    <form className="lg-pg-add" onSubmit={submit} noValidate>
      <div className="row">
        <input className="lg-pg-field" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder={t("lg.prog.titlePlaceholder")} aria-label={t("lg.prog.titleLabel")} />
        <div className="deadline" role="group" aria-label={t("lg.prog.deadlineLabel")}>
          {(["none", "month", "date"] as const).map((k) => (
            <button key={k} type="button" className="pick" aria-pressed={kind === k} onClick={() => setKind(k)}>
              {t(k === "none" ? "lg.prog.deadlineNone" : k === "month" ? "lg.prog.deadlineMonth" : "lg.prog.deadlineDate")}
            </button>
          ))}
        </div>
        <button className="lg-pg-btn" type="submit" disabled={busy}>
          {t("lg.prog.save")}
        </button>
      </div>
      {kind === "date" && <input className="lg-pg-field" type="date" min={toYmd(new Date())} value={date} onChange={(e) => setDate(e.target.value)} aria-label={t("lg.prog.deadlineDateLabel")} />}
      <p className="lg-pg-muted">
        {err ? (
          <span role="alert" className="lg-pg-err">
            {err}
          </span>
        ) : (
          t("lg.prog.hint")
        )}
      </p>
    </form>
  );
}

/** One goal: title, status tag, percentage, a thin bar, and the way to open or remove it. */
function GoalRow({ g, onRemove }: { g: Goal; onRemove: () => void }) {
  const { t, i18n } = useTranslation();
  const [ask, setAsk] = useState(false);
  const research = g.source === "research";
  const title = g.deadline && g.kind === "student" ? `${g.title} ${t("lg.prog.byDate", { date: niceDate(g.deadline, i18n.language) })}` : g.title;
  const pct = Math.round(g.progress_pct);
  const course = g.courses[0];
  return (
    <li className={"goal" + (research ? " main" : "")}>
      <div className="t">
        <h3>{title}</h3>
        <span className={TAG[g.status]}>{t(`lg.prog.status.${g.status}`)}</span>
        {course && (
          <Link className="tag ga" to={`/khoa-hoc/${encodeURIComponent(course.id)}`}>
            {course.title}
          </Link>
        )}
      </div>
      <span className="pct">{pct}%</span>
      <div className="bar slim" role="progressbar" aria-label={g.title} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${pct}%` }} />
      </div>
      <div className="acts">
        {research ? (
          <Link className="lg-pg-linkbtn" to="/thu-vien">
            {t("lg.prog.openLibrary")}
          </Link>
        ) : ask ? (
          <span role="group" aria-label={t("lg.prog.removeAsk")}>
            <span className="lg-pg-muted">{t("lg.prog.removeAsk")} </span>
            <button className="lg-pg-linkbtn" type="button" onClick={onRemove}>
              {t("lg.prog.removeYes")}
            </button>{" "}
            <button className="lg-pg-linkbtn" type="button" onClick={() => setAsk(false)}>
              {t("lg.prog.removeNo")}
            </button>
          </span>
        ) : (
          <button className="lg-pg-linkbtn" type="button" onClick={() => setAsk(true)}>
            {t("lg.prog.remove")}
          </button>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- courses
function CoursesBoard({ my }: { my: ReturnType<typeof useMyCourses> }) {
  const { t } = useTranslation();
  return (
    <Board id="lg-pg-h-courses" title={t("lg.prog.courses")}>
      {my.status === "ready" && my.courses.length === 0 && <p className="lg-pg-muted">{t("lg.prog.noCourses")}</p>}
      <ul className="lg-pg-courses">
        {my.courses.map((c) => (
          <CourseLine key={c.enrollment.course_id} c={c} />
        ))}
      </ul>
    </Board>
  );
}

function CourseLine({ c }: { c: MyCourse }) {
  return (
    <li>
      <CourseCover courseId={c.info.id} className="lg-pg-thumb" />
      <Link className="cname" to={`/khoa-hoc/${encodeURIComponent(c.info.id)}`}>
        {c.info.title}
      </Link>
      <span className="bar slim" role="progressbar" aria-label={c.info.title} aria-valuenow={c.percent} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${c.percent}%` }} />
      </span>
      <span className="pct">{c.percent}%</span>
    </li>
  );
}

// ---------------------------------------------------------------- streak and rules
/**
 * The week's dots agree with the streak the village shows (the planner's count, CONTRACTS-LANGGA: `streak` comes from the planner):
 * the days of the run are marked even when the chickens earned nothing on them. The run ends today, or yesterday while today is open.
 */
export function markStreak(dayHas: boolean[], streak: { days: number; today_done: boolean } | null | undefined): boolean[] {
  if (!streak || !dayHas.length) return dayHas;
  const last = dayHas.length - 1 - (streak.today_done ? 0 : 1);
  return dayHas.map((on, i) => on || (i <= last && i > last - streak.days));
}

function StreakBoard({ vil, dayHas: earned, days }: { vil: Village | null; dayHas: boolean[]; days: string[] }) {
  const { t } = useTranslation();
  const wd = t("lg.prog.weekdays", { returnObjects: true }) as unknown as string[];
  const dayHas = markStreak(earned, vil?.streak);
  // not loaded yet: a dash, never a "0 ngày liền" that is only the lack of an answer
  const n = vil ? vil.streak.days : null;
  const todayIdx = days.length - 1;
  return (
    <Board id="lg-pg-h-streak" title={t("lg.prog.streak")}>
      <div className="lg-pg-streak">
        <span className="flame">
          <FlameIcon />
        </span>
        <div>
          <b>{n ?? "–"}</b> {n !== null && <span>{t("lg.prog.streakDays")}</span>}
          {vil && <p className="lg-pg-muted">{vil.streak.today_done ? t("lg.prog.streakTodayDone") : t("lg.prog.streakTodayLeft")}</p>}
        </div>
      </div>
      {days.length > 0 && (
        <div className="lg-pg-dots" role="img" aria-label={t("lg.prog.streakDots")}>
          {days.map((d, i) => {
            const dow = (new Date(`${d}T00:00:00`).getDay() + 6) % 7;
            return (
              <span key={d} className={(dayHas[i] ? "on" : "") + (i === todayIdx ? " today" : "")}>
                <i>{dayHas[i] && <Icon name="check" />}</i>
                {wd[dow]}
              </span>
            );
          })}
        </div>
      )}
      <p className="lg-pg-rule">{t("lg.prog.streakRule")}</p>
    </Board>
  );
}

const RULES: [string, string][] = [
  ["rLesson", "+20 kinh nghiệm"],
  ["rPractice", "+2"],
  ["rFix", "+3"],
  ["rBoss", "+50 kinh nghiệm"],
  ["rMock", "+40 kinh nghiệm"],
  ["rPaper", "+40 kinh nghiệm"],
  ["rFocus", "+1"],
  ["rCard", "+2"],
];

function RulesBoard() {
  const { t } = useTranslation();
  return (
    <Board id="lg-pg-h-rules" title={t("lg.prog.rules")}>
      <ul className="lg-pg-rules">
        {RULES.map(([k, v]) => (
          <li key={k}>
            <span>{t(`lg.prog.${k}`)}</span>
            <b>{v}</b>
          </li>
        ))}
      </ul>
      <div className="lg-pg-lvls" role="group" aria-label={t("lg.prog.levelsAria")}>
        <span>
          <b>100</b>
          {t("lg.prog.perLevel")}
        </span>
        {STAGE_AT.map((from, i) => (
          <span key={from}>
            <b>{i === STAGE_AT.length - 1 ? `${from}+` : STAGE_AT[i + 1] - 1 > from ? `${from}–${STAGE_AT[i + 1] - 1}` : `${from}`}</b>
            {t(`lg.prog.stage${i + 1}`)}
          </span>
        ))}
      </div>
    </Board>
  );
}
