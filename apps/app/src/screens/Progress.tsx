import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, type Goal, type PlanItem, type WeekPlan } from "../api";
import { useAuth } from "../state/auth";
import { Icon } from "../components/Icon";
import { CourseCover } from "./courses/common";
import { useMyCourses, type MyCourse } from "./courses/useMyCourses";
import { buildGoal, toYmd, type DeadlinePick } from "../lib/goalForm";
import { pickLang } from "../lib/today";
import { resolveDeepLink } from "../lib/deeplink";
import { courseInsight } from "../lib/insight";
import { refreshReminders } from "../lib/behaviour";

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

/** hs-10: goals (inferred + the student's), the week the agent planned, and where each course is strong or needs care. */
export function Progress() {
  const { t } = useTranslation();
  const { token } = useAuth();
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

  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to="/" aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="grid" />
        </Link>
        <h1 className="page-title">{t("hub.progress")}</h1>
      </header>
      <main className="main pg-main">
        <GoalsSection state={goals} setGoals={setGoals} onChanged={replan} onRetry={load} />
        <WeekSection state={plan} onRetry={load} />
        <CoursesSection my={my} />
      </main>
    </div>
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

// ---------------------------------------------------------------- goals
function GoalsSection({ state, setGoals, onChanged, onRetry }: { state: Load<Goal[]>; setGoals: (l: Load<Goal[]>) => void; onChanged: () => void; onRetry: () => void }) {
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
      {state.status === "loading" && <p className="muted">…</p>}
      {state.status === "error" && <Retry onRetry={onRetry} />}
      {state.status === "ready" && goals.length === 0 && !adding && <p className="muted">{t("progress.noGoals")}</p>}
      <ul className="pg-goals">
        {goals.map((g) => (
          <GoalCard key={g.id} g={g} onRemove={() => remove(g)} />
        ))}
      </ul>
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

function GoalCard({ g, onRemove }: { g: Goal; onRemove: () => void }) {
  const { t, i18n } = useTranslation();
  const [ask, setAsk] = useState(false);
  const research = g.source === "research";
  const title = g.deadline && g.kind === "student" ? `${g.title} ${t("progress.byDate", { date: niceDate(g.deadline, i18n.language) })}` : g.title;
  return (
    <li className="pg-goal">
      <div className="pg-top">
        <h3>{title}</h3>
        <span className={TAG[g.status]}>{t(`progress.status.${g.status}`)}</span>
      </div>
      <div className="bar" role="progressbar" aria-label={g.title} aria-valuenow={Math.round(g.progress_pct)} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${Math.round(g.progress_pct)}%` }} />
      </div>
      {g.courses.length > 0 && (
        <p className="pg-for">
          {g.courses.map((c) => (
            <Link key={c.id} className="pg-chip" to={`/khoa-hoc/${c.id}`}>
              <CourseCover courseId={c.id} />
              {c.title}
            </Link>
          ))}
        </p>
      )}
      {research && (g.milestones?.length ?? 0) > 0 && (
        <ul className="pg-ms" aria-label={t("research.milestones.title")}>
          {g.milestones!.map((m) => (
            <li key={m.id} className={m.done ? "done" : undefined}>
              <span className="pg-ms-d">{m.due_date.slice(8, 10)}/{m.due_date.slice(5, 7)}</span>
              <span>{m.title}</span>
              {m.done && <Icon name="check" />}
            </li>
          ))}
        </ul>
      )}
      <p className="pg-why">
        <span className="pg-pct">{Math.round(g.progress_pct)}%</span> {pickLang(g, "line", i18n.language)}
      </p>
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
    </li>
  );
}

// ---------------------------------------------------------------- week
function WeekSection({ state, onRetry }: { state: Load<WeekPlan>; onRetry: () => void }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const plan = state.status === "ready" ? state.data : null;
  const byDay = useMemo(() => {
    const m = new Map<string, PlanItem[]>();
    for (const it of plan?.items ?? []) m.set(it.date, [...(m.get(it.date) ?? []), it]);
    return m;
  }, [plan]);
  const reasonCount = useMemo(() => {
    const m = new Map<string, number>();
    for (const it of plan?.items ?? []) {
      const r = pickLang(it, "reason", i18n.language).trim();
      if (r) m.set(r, (m.get(r) ?? 0) + 1);
    }
    return m;
  }, [plan, i18n.language]);
  const weekdays = t("progress.weekdays", { returnObjects: true }) as unknown as string[];
  const [count, setCount] = useState<{ done: number; planned: number } | null>(null);
  useEffect(() => {
    if (token)
      void api.getToday(token).then(
        (x) => setCount(x.week),
        () => undefined,
      );
  }, [token]);

  return (
    <section className="pg-sec" data-guide="progress-week" data-guide-label={t("progress.week")}>
      <div className="pg-head">
        <h2>{t("progress.week")}</h2>
        {count && count.planned > 0 && <span className="muted small">{t("progress.weekCount", count)}</span>}
      </div>
      {state.status === "loading" && <p className="muted">…</p>}
      {state.status === "error" && <Retry onRetry={onRetry} />}
      {plan && plan.items.length === 0 && <p className="muted">{t("progress.weekEmpty")}</p>}
      {plan && plan.items.length > 0 && (
        <>
          <div className="pg-week">
            {/* a reason shown on every row says nothing; keep only the ones that differ from the rest */}
            {plan.days.map((d) => {
              const items = byDay.get(d) ?? [];
              const wd = (new Date(`${d}T00:00:00`).getDay() + 6) % 7;
              const isToday = d === plan.today;
              const nextWeek = wd === 0 && d !== plan.days[0];
              const study = items.filter((i) => i.kind !== "break");
              const done = study.length > 0 && study.every((i) => i.done);
              return (
                <div key={d} className={"pg-day" + (isToday ? " today" : "") + (done ? " done" : "") + (nextWeek ? " next-week" : "")} aria-current={isToday ? "date" : undefined}>
                  <b>{weekdays[wd]}</b>
                  {items.length === 0 ? (
                    <span className="pg-plan muted">{t("progress.rest")}</span>
                  ) : (
                    items.map((it, i) => (
                      <Link key={i} className={"pg-plan" + (it.done ? " done" : "")} to={resolveDeepLink(it.deep_link).to}>
                        <span>{it.label}</span>
                        {(() => {
                          const r = pickLang(it, "reason", i18n.language).trim();
                          return r && reasonCount.get(r) === 1 ? <small>{r}</small> : null;
                        })()}
                      </Link>
                    ))
                  )}
                </div>
              );
            })}
          </div>
          <p className="pg-note">{pickLang(plan, "note", i18n.language)}</p>
        </>
      )}
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

function CourseLine({ c }: { c: MyCourse }) {
  const { t } = useTranslation();
  const insight = courseInsight(c.pack, c.enrollment);
  const note = [insight.strong.length ? t("progress.strong", { what: insight.strong.join(", ") }) : "", insight.watch.length ? t("progress.watch", { what: insight.watch.join(", ") }) : ""].filter(Boolean);
  const fallback = c.finished ? t("progress.finished") : !c.enrollment.progress ? t("progress.notStarted") : c.percent === 0 ? t("progress.justStarted") : t("progress.keepGoing");
  return (
    <li>
      <Link className="pg-course" to={`/khoa-hoc/${c.info.id}`}>
        <CourseCover courseId={c.info.id} className="pg-thumb" />
        <span>
          <h3>{c.info.title}</h3>
          <p>{note.length ? note.join(". ") : fallback}</p>
        </span>
        <span className="bar" role="progressbar" aria-valuenow={c.percent} aria-valuemin={0} aria-valuemax={100}>
          <i style={{ width: `${c.percent}%` }} />
        </span>
        <span className="pg-pct">{c.percent}%</span>
      </Link>
    </li>
  );
}
