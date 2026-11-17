import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, type Goal, type PlanItem, type WeekPlan } from "../api";
import type { Milestone } from "../api/research-types";
import { useAuth } from "../state/auth";
import { Icon } from "../components/Icon";
import { CourseCover } from "./courses/common";
import { useMyCourses, type MyCourse } from "./courses/useMyCourses";
import { buildGoal, toYmd, type DeadlinePick } from "../lib/goalForm";
import { pickLang } from "../lib/today";
import { resolveDeepLink } from "../lib/deeplink";
import { refreshReminders } from "../lib/behaviour";

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

/** hs-12: goals (inferred + the student's), the week the agent planned, and the courses with their progress. */
export function Progress() {
  const { t } = useTranslation();
  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to="/" aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="grid" />
        </Link>
        <h1 className="page-title">{t("hub.progress")}</h1>
      </header>
      <main className="main pg-main">
        <ProgressBody />
      </main>
    </div>
  );
}

/**
 * The Tiến độ page (goals, week, courses), or with `compact` the sheet Today opens from its ring (the week as 7 cells, uni
 * deadlines, goals as one-line rows). Sessions opened from here come back here (`back`).
 */
export function ProgressBody({ compact = false, back = "/tien-do" }: { compact?: boolean; back?: string }) {
  const { token, user } = useAuth();
  const [goals, setGoals] = useState<Load<Goal[]>>({ status: "loading" });
  const [plan, setPlan] = useState<Load<WeekPlan>>({ status: "loading" });
  const my = useMyCourses();

  const load = useCallback(() => {
    if (!token) return;
    setGoals({ status: "loading" });
    setPlan({ status: "loading" });
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

  if (compact)
    return (
      <>
        <WeekSection state={plan} onRetry={load} back={back} compact />
        {user?.age_band === "uni" && <Soon goals={goals} />}
        <GoalsSection state={goals} setGoals={setGoals} onChanged={replan} onRetry={load} compact />
      </>
    );
  return (
    <>
      <GoalsSection state={goals} setGoals={setGoals} onChanged={replan} onRetry={load} />
      <WeekSection state={plan} onRetry={load} back={back} />
      <CoursesSection my={my} />
    </>
  );
}

function Retry({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <p className="muted" role="alert">
      {t("progress.loadFailed")}{" "}
      <button className="btn-link" type="button" onClick={onRetry}>
        {t("progress.retry")}
      </button>
    </p>
  );
}

// ---------------------------------------------------------------- university: what is coming up
/** The next deadlines of the thesis goal ("Full paper · còn 9 ngày"), one line each. */
function Soon({ goals }: { goals: Load<Goal[]> }) {
  const { t } = useTranslation();
  const list: Milestone[] =
    goals.status === "ready"
      ? goals.data
          .filter((g) => g.source === "research")
          .flatMap((g) => g.milestones ?? [])
          .filter((m) => !m.done && m.days_left >= 0)
          .sort((a, b) => a.due_date.localeCompare(b.due_date))
          .slice(0, 2)
      : [];
  if (list.length === 0) return null;
  return (
    <div className="pg-soon">
      {list.map((m) => (
        <p key={m.id}>
          <Icon name="flag" />
          <span>{t("progress.daysLeft", { title: m.title, n: m.days_left })}</span>
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- goals
function GoalsSection({ state, setGoals, onChanged, onRetry, compact = false }: { state: Load<Goal[]>; setGoals: (l: Load<Goal[]>) => void; onChanged: () => void; onRetry: () => void; compact?: boolean }) {
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
  const list = (
    <>
      {state.status === "loading" && <p className="muted">…</p>}
      {state.status === "error" && <Retry onRetry={onRetry} />}
      {state.status === "ready" && goals.length === 0 && !adding && !compact && <p className="muted">{t("progress.noGoals")}</p>}
      <ul className="pg-goals">
        {goals.map((g) => (
          <GoalRow key={g.id} g={g} compact={compact} onRemove={() => remove(g)} />
        ))}
      </ul>
    </>
  );
  // the sheet keeps to what is there: no heading, no adding (that lives on the page and in the box on Today)
  if (compact) return <section aria-label={t("progress.goals")}>{list}</section>;
  return (
    <section className="pg-sec" data-guide="progress-goals" data-guide-label={t("progress.goals")}>
      <div className="pg-head">
        <h2>{t("progress.goals")}</h2>
        <button className="btn btn-ghost" type="button" aria-expanded={adding} onClick={() => setAdding((a) => !a)}>
          <Icon name="plus" />
          <span>{t("progress.add")}</span>
        </button>
      </div>
      {adding && <AddGoal onAdded={add} />}
      {list}
    </section>
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
    if (!r.ok) return setErr(r.error === "title" ? t("progress.errTitle") : t("progress.errDeadline"));
    setErr(null);
    setBusy(true);
    try {
      onAdded(await api.createGoal(token, r.body));
    } catch {
      setErr(t("progress.saveFailed"));
      setBusy(false);
    }
  };
  return (
    <form className="pg-add" onSubmit={submit} noValidate>
      <div className="pg-add-row">
        <input className="pg-field" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder={t("progress.titlePlaceholder")} aria-label={t("progress.titleLabel")} />
        <div className="pg-deadline" role="group" aria-label={t("progress.deadlineLabel")}>
          {(["none", "month", "date"] as const).map((k) => (
            <button key={k} type="button" className="pg-pick" aria-pressed={kind === k} onClick={() => setKind(k)}>
              {t(k === "none" ? "progress.deadlineNone" : k === "month" ? "progress.deadlineMonth" : "progress.deadlineDate")}
            </button>
          ))}
        </div>
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {t("progress.save")}
        </button>
      </div>
      {kind === "date" && <input className="pg-field pg-date" type="date" min={toYmd(new Date())} value={date} onChange={(e) => setDate(e.target.value)} aria-label={t("progress.deadlineDateLabel")} />}
      <p className="small muted">
        {err ? (
          <span role="alert" className="pg-err">
            {err}
          </span>
        ) : (
          t("progress.hint")
        )}
      </p>
    </form>
  );
}

const TAG: Record<Goal["status"], string> = { on_track: "tag ok", slightly_behind: "tag wait", behind: "tag err", new: "tag" };

function niceDate(iso: string, lang: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(lang === "en" ? "en-GB" : "vi-VN", { day: "numeric", month: "numeric", year: "numeric" });
}

/** One goal on one line: title, tag (and the percentage on the page), a thin bar under it. */
function GoalRow({ g, compact, onRemove }: { g: Goal; compact: boolean; onRemove: () => void }) {
  const { t, i18n } = useTranslation();
  const [ask, setAsk] = useState(false);
  const research = g.source === "research";
  const title = g.deadline && g.kind === "student" ? `${g.title} ${t("progress.byDate", { date: niceDate(g.deadline, i18n.language) })}` : g.title;
  const pct = Math.round(g.progress_pct);
  return (
    <li className="pg-goal">
      <div className="pg-top">
        <h3>{title}</h3>
        <span className={TAG[g.status]}>{t(`progress.status.${g.status}`)}</span>
        {!compact && <span className="pg-pct">{pct}%</span>}
      </div>
      <div className="bar" role="progressbar" aria-label={g.title} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${pct}%` }} />
      </div>
      {!compact && (
        <div className="pg-actions">
          {research ? (
            <Link className="btn-link small" to="/nghien-cuu">
              {t("research.milestones.open")}
            </Link>
          ) : ask ? (
            <span role="group" aria-label={t("progress.removeAsk")}>
              <span className="small muted">{t("progress.removeAsk")} </span>
              <button className="btn-link" type="button" onClick={onRemove}>
                {t("progress.removeYes")}
              </button>{" "}
              <button className="btn-link" type="button" onClick={() => setAsk(false)}>
                {t("progress.removeNo")}
              </button>
            </span>
          ) : (
            <button className="btn-link small" type="button" onClick={() => setAsk(true)}>
              {t("progress.remove")}
            </button>
          )}
        </div>
      )}
    </li>
  );
}

// ---------------------------------------------------------------- week
/** Monday of the week a YYYY-MM-DD day belongs to. */
function weekStart(ymd: string): string {
  const d = new Date(`${ymd}T00:00:00`);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return toYmd(d);
}

function WeekSection({ state, onRetry, back, compact = false }: { state: Load<WeekPlan>; onRetry: () => void; back: string; compact?: boolean }) {
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
  const weekdays = t("progress.weekdays", { returnObjects: true }) as unknown as string[];
  // the 7 cells are the Monday-to-Sunday week the plan is in (the plan also holds the days after it)
  const days = useMemo(() => {
    if (!plan) return [];
    const start = weekStart(plan.today);
    const wk = plan.days.filter((d) => weekStart(d) === start);
    return wk.length > 0 ? wk : plan.days.slice(0, 7);
  }, [plan]);
  const note = plan ? pickLang(plan, "note", i18n.language) : "";

  const head = <h2>{t("progress.week")}</h2>;
  const body = (
    <>
      {state.status === "loading" && <p className="muted">…</p>}
      {state.status === "error" && <Retry onRetry={onRetry} />}
      {plan && plan.items.length === 0 && <p className="muted">{t("progress.weekEmpty")}</p>}
      {plan && plan.items.length > 0 && (
        <>
          <div className="pg-week" aria-label={t("progress.weekAria")}>
            {days.map((d) => {
              const items = byDay.get(d) ?? [];
              const wd = (new Date(`${d}T00:00:00`).getDay() + 6) % 7;
              const isToday = d === plan.today;
              const study = items.filter((i) => i.kind !== "break");
              const done = study.length > 0 && study.every((i) => i.done);
              const miss = !done && study.length > 0 && d < plan.today && !study.some((i) => i.done);
              const next = study.find((i) => !i.done);
              const cls = "pg-day" + (isToday ? " today" : "") + (done ? " done" : "") + (miss ? " miss" : "") + (study.length === 0 ? " rest" : "");
              const inner = (
                <>
                  <b>{weekdays[wd]}</b>
                  {done ? (
                    <>
                      <Icon name="check" />
                      <span className="sr">{t("progress.done")}</span>
                    </>
                  ) : miss ? (
                    <>
                      <Icon name="x" />
                      <span className="pg-plan">{t("progress.minShort", { n: next?.minutes ?? 0 })}</span>
                    </>
                  ) : study.length === 0 ? (
                    <span className="pg-plan">{t("progress.rest")}</span>
                  ) : (
                    <span className="pg-plan">{t("progress.minShort", { n: study.reduce((n, i) => n + i.minutes, 0) })}</span>
                  )}
                </>
              );
              const aria = isToday ? "date" : undefined;
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
          {!compact && (note || why.length > 0) && (
            <details className="pg-why-fold">
              <summary>{t("progress.why")}</summary>
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
    </>
  );
  if (compact) return <section aria-label={t("progress.week")}>{body}</section>;
  return (
    <section className="pg-sec" data-guide="progress-week" data-guide-label={t("progress.week")}>
      {head}
      {body}
    </section>
  );
}

// ---------------------------------------------------------------- courses
function CoursesSection({ my }: { my: ReturnType<typeof useMyCourses> }) {
  const { t } = useTranslation();
  return (
    <section className="pg-sec" data-guide="progress-courses" data-guide-label={t("progress.courses")}>
      <h2>{t("progress.courses")}</h2>
      {my.status === "ready" && my.courses.length === 0 && <p className="muted">{t("progress.noCourses")}</p>}
      <ul className="pg-courses">
        {my.courses.map((c) => (
          <CourseLine key={c.enrollment.course_id} c={c} />
        ))}
      </ul>
    </section>
  );
}

/** A course on one line: cover, name (a link to the course), bar, percentage. */
function CourseLine({ c }: { c: MyCourse }) {
  return (
    <li className="pg-course">
      <CourseCover courseId={c.info.id} className="pg-thumb" />
      <Link className="pg-cname" to={`/khoa-hoc/${encodeURIComponent(c.info.id)}`}>
        {c.info.title}
      </Link>
      <span className="bar" role="progressbar" aria-label={c.info.title} aria-valuenow={c.percent} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${c.percent}%` }} />
      </span>
      <span className="pg-pct">{c.percent}%</span>
    </li>
  );
}
