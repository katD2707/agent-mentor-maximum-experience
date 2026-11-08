import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { researchApi, type Meeting, type Milestone, type UpcomingItem } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { dateBlock, errCode, pk, shortDate } from "./util";

type AddKind = "deadline" | "meeting";

/** "Sắp tới": meetings and deadlines as cards with a date block, "Xem agenda", and adding either by one line of text. */
export function Upcoming({ items, onChanged }: { items: UpcomingItem[]; onChanged: () => void }) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState<string | null>(null);
  const [add, setAdd] = useState<AddKind | null>(null);

  return (
    <>
      <section className="rs-upcoming full" data-guide="research-upcoming" data-guide-label={t("research.upcoming.title")}>
        <div className="rs-sec-head">
          <h2 className="rs-s">{t("research.upcoming.title")}</h2>
          <span className="rs-grow" />
          <button className="btn btn-quiet rs-mini" type="button" aria-expanded={add === "deadline"} onClick={() => setAdd(add === "deadline" ? null : "deadline")}>
            <Icon name="plus" />
            <span>{t("research.upcoming.addDeadline")}</span>
          </button>
          <button className="btn btn-quiet rs-mini" type="button" aria-expanded={add === "meeting"} onClick={() => setAdd(add === "meeting" ? null : "meeting")}>
            <Icon name="plus" />
            <span>{t("research.upcoming.addMeeting")}</span>
          </button>
        </div>
        {add && (
          <AddByText
            kind={add}
            onDone={() => {
              setAdd(null);
              onChanged();
            }}
          />
        )}
        {items.length === 0 && !add && <p className="muted">{t("research.upcoming.empty")}</p>}
        {items.length > 0 && (
          <div className="rs-events rs-scroller">
            {items.map((it) => {
              const b = dateBlock(it.date, i18n.language);
              const hot = it.kind === "deadline" && it.confirmed && it.days_left >= 0 && it.days_left <= 14 && it.planned_sessions > 0;
              return (
                <article key={`${it.kind}-${it.id}`} className={"rs-card rs-ev" + (hot ? " hot" : "")}>
                  <span className="rs-date">
                    <small>{b.weekday}</small>
                    <b>{b.day}</b>
                    <small>{b.month}</small>
                  </span>
                  <h3>{it.kind === "meeting" && it.time ? `${it.title}, ${it.time}` : it.title}</h3>
                  <span className="rs-sub">{sub(it, t)}</span>
                  <div className="rs-foot">
                    {it.kind === "meeting" ? (
                      <button className="btn btn-ghost rs-mini" type="button" aria-expanded={open === it.id} aria-controls="rs-agenda" onClick={() => setOpen(open === it.id ? null : it.id)}>
                        {t("research.upcoming.seeAgenda")}
                      </button>
                    ) : it.confirmed ? (
                      <span className="tag wait">{daysLeft(it.days_left, t)}</span>
                    ) : (
                      <span className="tag">{t("research.upcoming.unconfirmed")}</span>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
      {open && <AgendaPanel id={open} onChanged={onChanged} />}
    </>
  );
}

type T = (k: string, o?: Record<string, unknown>) => string;
const daysLeft = (n: number, t: T) => (n <= 0 ? t("research.upcoming.today") : n === 1 ? t("research.upcoming.tomorrow") : t("research.upcoming.daysLeft", { count: n }));

function sub(it: UpcomingItem, t: T): string {
  if (it.kind === "meeting") return it.agenda_ready ? t("research.upcoming.agendaReady") : t("research.upcoming.agendaNot");
  if (!it.confirmed) return t("research.upcoming.noTime");
  const parts: string[] = [];
  if (it.time) parts.push(it.original_text ? t("research.upcoming.timeAoE", { time: it.time, original: it.original_text }) : t("research.upcoming.time", { time: it.time }));
  if (it.planned_sessions > 0) parts.push(t(pk("research.upcoming.sessions", it.planned_sessions), { count: it.planned_sessions }));
  return parts.join(". ");
}

function AddByText({ kind, onDone }: { kind: AddKind; onDone: () => void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || busy || !text.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      if (kind === "deadline") await researchApi.createDeadline(token, { text: text.trim() });
      else await researchApi.createMeeting(token, { text: text.trim() });
      onDone();
    } catch (er) {
      const c = errCode(er);
      setErr(c === "deadline_unparsed" || c === "meeting_unparsed" ? t(`research.upcoming.${c}`) : t(`research.err.${c}`, { defaultValue: t("research.err.unknown") }));
      setBusy(false);
    }
  };
  return (
    <form className="rs-add-text" onSubmit={submit}>
      <label className="rs-search">
        <Icon name="clock" />
        <input autoFocus type="text" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" aria-label={t(`research.upcoming.${kind}Label`)} placeholder={t(`research.upcoming.${kind}Placeholder`)} maxLength={200} />
      </label>
      <button className="btn btn-primary rs-mini" type="submit" disabled={busy || !text.trim()}>
        {t("research.upcoming.addGo")}
      </button>
      {err && (
        <p className="rs-alert" role="alert">
          {err}
        </p>
      )}
    </form>
  );
}

/** The agenda Mentor drafted, the two boxes for you (saved when you leave a box), and the notes after the meeting. */
function AgendaPanel({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [m, setM] = useState<Meeting | null>(null);
  const [results, setResults] = useState("");
  const [questions, setQuestions] = useState("");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    researchApi.meetings(token, "all").then(
      (list) => {
        const x = list.find((y) => y.id === id);
        if (!alive || !x) return;
        setM(x);
        setResults(x.agenda?.new_results ?? "");
        setQuestions(x.agenda?.open_questions ?? "");
        setNotes(x.notes_md ?? "");
      },
      () => alive && setErr(t("research.err.unknown")),
    );
    return () => {
      alive = false;
    };
  }, [token, id, t]);

  const run = async (fn: () => Promise<Meeting>, done: string) => {
    setErr(null);
    try {
      setM(await fn());
      setSaved(done);
      return true;
    } catch (e) {
      setErr(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
      return false;
    }
  };
  const saveBoxes = () => {
    if (!token || !m) return;
    if ((m.agenda?.new_results ?? "") === results && (m.agenda?.open_questions ?? "") === questions) return;
    void run(() => researchApi.putAgenda(token, id, { new_results: results, open_questions: questions }), t("research.agenda.saved"));
  };

  if (!m) return <section className="rs-card rs-agenda full" id="rs-agenda">{err ? <p className="rs-alert" role="alert">{err}</p> : <p className="muted">…</p>}</section>;
  const promised = m.agenda?.promised ?? [];
  return (
    <section className="rs-card rs-agenda full" id="rs-agenda" aria-label={t("research.agenda.title")} data-guide="research-agenda" data-guide-label={t("research.agenda.title")}>
      <div className="rs-cols">
        <div>
          <h3>{t("research.agenda.promised")}</h3>
          {promised.length > 0 ? (
            <ul>
              {promised.map((p, i) => (
                <li key={i} className={p.done ? undefined : "half"}>
                  <Icon name={p.done ? "check" : "clock"} />
                  <span>{p.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small rs-mt">
              {t("research.agenda.noDraft")}{" "}
              <button className="btn-link" type="button" onClick={() => token && void run(() => researchApi.draftAgenda(token, id), t("research.agenda.drafted"))}>
                {t("research.agenda.draft")}
              </button>
            </p>
          )}
        </div>
        <div>
          <h3>{t("research.agenda.newResults")}</h3>
          <textarea className="rs-box" aria-label={t("research.agenda.newResults")} placeholder={t("research.agenda.newResultsPh")} value={results} onChange={(e) => setResults(e.target.value)} onBlur={saveBoxes} />
        </div>
        <div>
          <h3>{t("research.agenda.openQuestions")}</h3>
          <textarea className="rs-box" aria-label={t("research.agenda.openQuestions")} placeholder={t("research.agenda.openQuestionsPh")} value={questions} onChange={(e) => setQuestions(e.target.value)} onBlur={saveBoxes} />
        </div>
      </div>
      <div className="rs-notes">
        <h3>{t("research.agenda.notes")}</h3>
        <textarea className="rs-box" aria-label={t("research.agenda.notes")} placeholder={t("research.agenda.notesPh")} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <div className="rs-act">
          <button
            className="btn btn-ghost rs-mini"
            type="button"
            disabled={!notes.trim()}
            onClick={() => token && void run(() => researchApi.putNotes(token, id, notes.trim()), t("research.agenda.notesSaved")).then((ok) => ok && onChanged())}
          >
            {t("research.agenda.saveNotes")}
          </button>
          {saved && (
            <span className="muted small" role="status">
              {saved}
            </span>
          )}
        </div>
        {m.action_items.length > 0 && (
          <ul className="rs-actions">
            {m.action_items.map((a) => (
              <li key={a.id}>
                <label>
                  <input type="checkbox" checked={a.done} onChange={(e) => token && void run(() => researchApi.patchAction(token, id, a.id, { done: e.target.checked }), "")} />
                  <span>{a.text}</span>
                </label>
                {a.due_date && <span className="tag">{shortDate(a.due_date)}</span>}
                {a.in_plan && <span className="muted small">{t("research.agenda.inPlan")}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      {err && (
        <p className="rs-alert" role="alert">
          {err}
        </p>
      )}
    </section>
  );
}

/** "Mốc luận văn": the thesis milestones as a timeline; the first one not done is next. */
export function Milestones({ items, goalId }: { items: Milestone[]; goalId: string | null }) {
  const { t } = useTranslation();
  const nextId = items.find((m) => !m.done)?.id;
  return (
    <section className="rs-card rs-mswrap full" data-guide="research-milestones" data-guide-label={t("research.milestones.title")}>
      <div className="rs-sec-head">
        <h2 className="rs-s">{t("research.milestones.title")}</h2>
        <span className="rs-grow" />
        {goalId && (
          <Link className="rs-link" to="/tien-do">
            {t("research.milestones.seeProgress")}
          </Link>
        )}
      </div>
      <ul className="rs-ms">
        {items.map((m) => (
          <li key={m.id} className={m.done ? "done" : m.id === nextId ? "next" : undefined} aria-current={m.id === nextId ? "step" : undefined}>
            <span className="rs-dot">{m.done && <Icon name="check" />}</span>
            <span className="rs-d">
              {shortDate(m.due_date)}
              {m.done && <span className="sr"> {t("research.milestones.done")}</span>}
            </span>
            <span className="rs-what">{m.title}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
