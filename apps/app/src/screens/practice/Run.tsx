import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, PracticeError, type PItem, type PReport, type PResult, type PReviewItem, type PSession } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { speak } from "../../lib/speak";
import { Md } from "../courses/blocks";
import { ItemView } from "./ItemView";
import { Dialog } from "./Dialog";
import {
  answerOf,
  canCheck,
  clockText,
  firstSentence,
  fmtNum,
  fmtScore10,
  handInStats,
  initialRemaining,
  isBlank,
  isLow,
  isOpen,
  resumePosition,
  shown,
  wrongStatements,
} from "../../lib/practice";

/** `/luyen-tap/:id` (the focus screen), `/ket-qua` (result), `/xem-lai` (review). Loaded on demand with Markdown and KaTeX. */
export default function PracticeRun() {
  return (
    <Routes>
      <Route index element={<SessionScreen />} />
      <Route path="ket-qua" element={<ResultScreen />} />
      <Route path="xem-lai" element={<ReviewScreen />} />
      <Route path="*" element={<Navigate to="/luyen-tap" replace />} />
    </Routes>
  );
}

const reportKey = (id: string) => `mentor.practice.report.${id}`;
function cacheReport(r: PReport) {
  try {
    sessionStorage.setItem(reportKey(r.session.id), JSON.stringify(r));
  } catch {
    /* never required */
  }
}
function cachedReport(id: string): PReport | null {
  try {
    const raw = sessionStorage.getItem(reportKey(id));
    return raw ? (JSON.parse(raw) as PReport) : null;
  } catch {
    return null;
  }
}

type Load = { s: "loading" } | { s: "error" } | { s: "ready"; session: PSession };

function useLang(): "vi" | "en" {
  const { i18n } = useTranslation();
  return i18n.language === "en" ? "en" : "vi";
}

// =============================================================== the session

function SessionScreen() {
  const { id = "" } = useParams();
  const { token } = useAuth();
  const [load, setLoad] = useState<Load>({ s: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    setLoad({ s: "loading" });
    practice.get(token, id).then(
      (session) => alive && setLoad({ s: "ready", session }),
      () => alive && setLoad({ s: "error" }),
    );
    return () => {
      alive = false;
    };
  }, [token, id, attempt]);
  const { t } = useTranslation();
  if (load.s === "loading") return <div className="boot" />;
  if (load.s === "error")
    return (
      <div className="app practice-run">
        <main className="main pr-msg">
          <p>{t("practice.loadFailed")}</p>
          <p className="pr-row">
            <button className="btn btn-primary" onClick={() => setAttempt((n) => n + 1)}>
              {t("practice.retry")}
            </button>
            <Link className="btn btn-ghost" to="/luyen-tap">
              {t("practice.backToPractice")}
            </Link>
          </p>
        </main>
      </div>
    );
  if (!isOpen(load.session)) return <Navigate replace to={`/luyen-tap/${encodeURIComponent(id)}/ket-qua`} />;
  return <Player session={load.session} />;
}

function Player({ session }: { session: PSession }) {
  const { t } = useTranslation();
  const lang = useLang();
  const nav = useNavigate();
  const { token, user } = useAuth();
  const tk = token ?? "";
  const kid = user?.age_band === "g1_5";
  const mock = session.kind !== "practice";
  const id = session.id;
  const items = session.items;
  const last = items.length - 1;

  const [pos, setPos] = useState(() => resumePosition(session));
  const [answers, setAnswers] = useState<Record<number, string>>(() => Object.fromEntries(items.map((it) => [it.position, answerOf(session.answers[String(it.position)])])));
  const [results, setResults] = useState<Record<number, PResult>>(() => {
    const r: Record<number, PResult> = {};
    for (const it of items) {
      const st = session.answers[String(it.position)];
      if (st?.checked && st.result && !mock) r[it.position] = st.result;
      else if (st?.checked && !mock) r[it.position] = { correct: st.correct ?? null };
    }
    return r;
  });
  const [hints, setHints] = useState<Record<number, string>>(() => Object.fromEntries(items.flatMap((it) => (session.answers[String(it.position)]?.hint ? [[it.position, session.answers[String(it.position)]!.hint!]] : []))));
  const [why, setWhy] = useState<Record<number, string>>({});
  const [flags, setFlags] = useState<Record<number, boolean>>(() => Object.fromEntries(items.map((it) => [it.position, !!session.answers[String(it.position)]?.flagged])));
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | "exit" | "submit" | "grid">(null);
  const [finishing, setFinishing] = useState(false);

  // ---- clocks: seconds on the item (cumulative) and, for a mock, the server's deadline
  const shownAt = useRef(Date.now());
  const spent = useRef<Record<number, number>>({});
  const seconds = useCallback((p: number) => (spent.current[p] ?? 0) + Math.round((Date.now() - shownAt.current) / 1000), []);
  const bank = useCallback(
    (p: number) => {
      spent.current[p] = seconds(p);
      shownAt.current = Date.now();
    },
    [seconds],
  );
  const endAt = useRef<number | null>(null);
  const [left, setLeft] = useState<number | null>(() => {
    const r = initialRemaining(session, Date.now());
    endAt.current = r === null ? null : Date.now() + r * 1000;
    return r;
  });

  const live = useRef({ pos, answers, finishing });
  live.current = { pos, answers, finishing };

  const finish = useCallback(
    async (auto = false) => {
      if (live.current.finishing) return;
      setFinishing(true);
      setDialog(null);
      try {
        await practice.tick(tk, id, live.current.pos, seconds(live.current.pos)).catch(() => undefined);
        const report = await practice.finish(tk, id);
        cacheReport(report);
        nav(`/luyen-tap/${encodeURIComponent(id)}/ket-qua${auto ? "?auto=1" : ""}`, { replace: true });
      } catch {
        setFinishing(false);
        setNote(t("practice.finishFailed"));
      }
    },
    [id, nav, seconds, t, tk],
  );

  // mock: count down every second; the server (tick, every 5 s) corrects the clock; zero hands the exam in
  useEffect(() => {
    if (!mock) return;
    let n = 0;
    const timer = window.setInterval(() => {
      if (live.current.finishing) return;
      if (endAt.current !== null) {
        const r = Math.max(0, Math.ceil((endAt.current - Date.now()) / 1000));
        setLeft(r);
        if (r === 0) return void finish(true);
      }
      n += 1;
      if (n % 5 === 0) {
        void practice.tick(tk, id, live.current.pos, seconds(live.current.pos)).then(
          (r) => {
            if (r.expired) return void finish(true);
            if (typeof r.remaining_sec === "number") endAt.current = Date.now() + r.remaining_sec * 1000;
          },
          () => undefined,
        );
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [mock, finish, id, seconds, tk]);

  // save the place when the app is hidden or closed
  useEffect(() => {
    const save = () => void practice.tick(tk, id, live.current.pos, seconds(live.current.pos)).catch(() => undefined);
    const hide = () => document.visibilityState === "hidden" && save();
    window.addEventListener("pagehide", save);
    document.addEventListener("visibilitychange", hide);
    return () => {
      window.removeEventListener("pagehide", save);
      document.removeEventListener("visibilitychange", hide);
    };
  }, [id, seconds, tk]);

  const item: PItem | undefined = items[pos];
  const result = results[pos] ?? null;
  const value = answers[pos] ?? "";

  // ---- mock: answers are saved as drafts, editable until hand-in
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveDraft = useCallback(
    (p: number, v: string) => {
      practice.answer(tk, id, { position: p, answer: v, time_spent_sec: seconds(p) }).catch((e: unknown) => {
        if (e instanceof PracticeError && e.code === "expired") void finish(true);
        else setNote(t("practice.saveFailed"));
      });
    },
    [finish, id, seconds, t, tk],
  );
  const flushDraft = useCallback(() => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
      saveDraft(live.current.pos, live.current.answers[live.current.pos] ?? "");
    }
  }, [saveDraft]);

  // ---- practice: check the answer with the server
  const check = useCallback(
    async (p: number, v: string) => {
      const it = items[p];
      if (!it || busy || results[p]) return;
      setBusy(true);
      setNote(null);
      try {
        const r = await practice.answer(tk, id, { position: p, answer: v, time_spent_sec: seconds(p) });
        setResults((m) => ({ ...m, [p]: r }));
        // No quiz_answer event here: the planner derives it from PracticeAnswer (planner/events.derived), so logging would double-count FSRS reps.
        if (r.correct === false) {
          if (kid) speak(t("practice.kidWrong"), lang);
          const fb = typeof r.option_feedback === "string" ? r.option_feedback : r.option_feedback?.[v];
          if (fb) setWhy((m) => ({ ...m, [p]: firstSentence(fb) }));
          else
            practice.reveal(tk, id, p).then(
              (x) => setWhy((m) => ({ ...m, [p]: firstSentence(x.explanation) })),
              () => undefined,
            );
        }
      } catch (e) {
        if (e instanceof PracticeError && e.status === 409) {
          // already checked (another tab) or finished: reload shows the truth
          nav(0);
        } else setNote(t("practice.saveFailed"));
      } finally {
        setBusy(false);
      }
    },
    [busy, id, items, kid, lang, nav, results, seconds, t, tk],
  );

  const change = (v: string) => {
    if (!item) return;
    if (mock) {
      setAnswers((a) => ({ ...a, [pos]: v }));
      if (saveTimer.current) clearTimeout(saveTimer.current);
      if (item.type === "SHORT_ANSWER") saveTimer.current = setTimeout(() => flushDraft(), 600);
      else saveDraft(pos, v);
      return;
    }
    if (result) return;
    setAnswers((a) => ({ ...a, [pos]: v }));
    // one tap on a choice is the answer; the other types have a "Kiểm tra" button
    if (item.type === "SINGLE_CHOICE" || item.type === "PICTURE_CHOICE") void check(pos, v);
  };

  const goTo = (p: number) => {
    if (p < 0 || p > last || p === pos) return;
    flushDraft();
    bank(pos);
    setPos(p);
    setDialog(null);
    void practice.tick(tk, id, p, spent.current[p] ?? 0).catch(() => undefined);
  };

  const next = () => {
    if (pos < last) goTo(pos + 1);
    else if (mock) {
      flushDraft();
      setDialog("submit");
    } else void finish();
  };

  const skip = async () => {
    if (!item || busy) return;
    setBusy(true);
    try {
      await practice.answer(tk, id, { position: pos, answer: "", time_spent_sec: seconds(pos) });
      setResults((m) => ({ ...m, [pos]: { correct: null } }));
      next();
    } catch {
      setNote(t("practice.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const hint = async () => {
    if (!item || hints[pos] || result) return;
    try {
      const h = await practice.hint(tk, id, pos);
      setHints((m) => ({ ...m, [pos]: h.hint }));
      if (kid) speak(h.hint, lang);
    } catch {
      setNote(t("practice.hintFailed"));
    }
  };

  const flag = () => {
    const v = !flags[pos];
    setFlags((f) => ({ ...f, [pos]: v }));
    practice.flag(tk, id, pos, v).catch(() => {
      setFlags((f) => ({ ...f, [pos]: !v }));
      setNote(t("practice.saveFailed"));
    });
  };

  const leave = () => {
    flushDraft();
    void practice.tick(tk, id, pos, seconds(pos)).catch(() => undefined);
    nav("/luyen-tap");
  };

  const stats = useMemo(() => handInStats(session, answers, flags), [session, answers, flags]);

  if (!item) return <Navigate replace to="/luyen-tap" />;
  const done = Object.keys(results).length;
  const progress = mock ? stats.answered : done;
  const out = result ? shown(item, result) : null;

  return (
    <div className={`app practice-run ${kid ? "kid-run" : ""}`} data-age={user?.age_band ?? undefined}>
      <div className="player pr">
        <div className="ptop" data-guide="practice-progress" data-guide-label={t("practice.progressLabel")}>
          <button className="icon-btn" type="button" aria-label={t("practice.saveExit")} onClick={() => (mock ? setDialog("exit") : leave())}>
            <Icon name="x" />
          </button>
          <div className="bar" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={items.length}>
            <i style={{ width: `${(progress / Math.max(1, items.length)) * 100}%` }} />
          </div>
          <span className="muted small pr-count">{t("practice.count", { n: pos + 1, total: items.length })}</span>
          {mock && left !== null && (
            <span className={`pr-clock ${isLow(left) ? "low" : ""}`} role="timer" aria-label={t("practice.timeLeft")} data-guide="practice-clock" data-guide-label={t("practice.timeLeft")}>
              {clockText(left)}
            </span>
          )}
        </div>

        {mock && session.parts && (
          <p className="muted small pr-part">{session.parts.find((p) => p.positions.includes(item.position))?.label}</p>
        )}
        <p className="muted small pr-topic">{item.source ? `${item.source.lesson_title}` : item.topic_title}</p>

        <ItemView item={item} token={tk} lang={lang} kid={kid} value={value} onChange={change} locked={!mock && !!result} result={mock ? null : result} />

        {!mock && hints[pos] && !result && (
          <p className="hint pr-hint" role="status">
            <b>{t("courses.player.hint")}:</b> {hints[pos]}
          </p>
        )}

        {!mock && result && out && (
          <div className={`feedback pr-fb ${out.outcome}`} role="status" data-guide="practice-feedback" data-guide-label={t("practice.feedbackLabel")}>
            <b>{t(`practice.outcome.${out.outcome}${kid && out.outcome !== "right" ? "Kid" : ""}`)}</b>
            {out.tally && out.outcome !== "right" && <span>{t("practice.tally", { right: out.tally.right, total: out.tally.total })}</span>}
            {out.outcome !== "right" && out.outcome !== "blank" && item.type === "SHORT_ANSWER" && result.correct_answer && (
              <span>
                {t("practice.correctAnswer")}: <b className="ok">{result.correct_answer}</b>
              </span>
            )}
            {out.outcome !== "right" && item.type === "TAP_COUNT" && result.correct_answer && (
              <span>
                {t("practice.correctCount")}: <b className="ok">{result.correct_answer}</b>
              </span>
            )}
            {out.outcome !== "right" && why[pos] && <p className="why">{why[pos]}</p>}
            {out.outcome !== "right" && item.type === "TRUE_FALSE_GROUP" && !why[pos] && wrongStatements(result).some((s) => s.explanation) && <p className="why">{firstSentence(wrongStatements(result).find((s) => s.explanation)?.explanation)}</p>}
            {out.outcome === "blank" && <span>{t("practice.skipped")}</span>}
          </div>
        )}

        {note && (
          <p className="note muted" role="alert">
            {note}
          </p>
        )}

        <div className="pfoot">
          {!mock && !result && (
            <span className="pr-row">
              {!hints[pos] && (
                <button className="btn btn-quiet" type="button" onClick={() => void hint()} data-guide="practice-hint" data-guide-label={t("practice.hint")}>
                  {t("practice.hint")}
                </button>
              )}
              <button className="btn btn-quiet" type="button" onClick={() => void skip()} disabled={busy}>
                {t("practice.skip")}
              </button>
            </span>
          )}
          {mock && (
            <span className="pr-row">
              <button className="btn btn-quiet" type="button" aria-pressed={!!flags[pos]} onClick={flag} data-guide="practice-flag" data-guide-label={t("practice.flag")}>
                <Icon name="flag" /> {flags[pos] ? t("practice.unflag") : t("practice.flag")}
              </button>
              <button className="btn btn-quiet" type="button" onClick={() => setDialog("grid")}>
                {t("practice.allQuestions")}
              </button>
            </span>
          )}
          <span className="pr-row">
            {mock && pos > 0 && (
              <button className="btn btn-ghost" type="button" onClick={() => goTo(pos - 1)}>
                {t("practice.prev")}
              </button>
            )}
            {!mock && !result && item.type !== "SINGLE_CHOICE" && item.type !== "PICTURE_CHOICE" && (
              <button className="btn btn-primary" type="button" disabled={busy || !canCheck(item, value)} onClick={() => void check(pos, value)}>
                {t("practice.check")}
              </button>
            )}
            {!mock && result && (
              <button className="btn btn-primary" type="button" onClick={next} autoFocus>
                {pos < last ? t("practice.next") : t("practice.seeResult")}
              </button>
            )}
            {mock && (
              <button className="btn btn-primary" type="button" onClick={next}>
                {pos < last ? t("practice.next") : t("practice.handIn")}
              </button>
            )}
          </span>
        </div>
      </div>

      {dialog === "exit" && (
        <Dialog title={t("practice.exitTitle")} onClose={() => setDialog(null)}>
          <p>{t("practice.exitMock")}</p>
          <p className="pr-row">
            <button className="btn btn-primary" onClick={() => setDialog(null)}>
              {t("practice.keepGoing")}
            </button>
            <button className="btn btn-ghost" onClick={leave}>
              {t("practice.saveExit")}
            </button>
          </p>
        </Dialog>
      )}
      {dialog === "submit" && (
        <Dialog title={t("practice.handInTitle")} onClose={() => setDialog(null)}>
          <p>{t("practice.handInBody", { answered: stats.answered, total: stats.total })}</p>
          {stats.blank > 0 && <p className="why">{t("practice.blankLeft", { n: stats.blank })}</p>}
          {stats.flagged > 0 && <p className="why">{t("practice.flaggedLeft", { n: stats.flagged })}</p>}
          <p className="pr-row">
            <button className="btn btn-primary" onClick={() => void finish()} disabled={finishing}>
              {t("practice.handInYes")}
            </button>
            <button className="btn btn-ghost" onClick={() => setDialog(null)}>
              {t("practice.keepGoing")}
            </button>
          </p>
        </Dialog>
      )}
      {dialog === "grid" && (
        <Dialog title={t("practice.allQuestions")} onClose={() => setDialog(null)}>
          <div className="pr-grid" role="group">
            {items.map((it) => (
              <button
                key={it.position}
                type="button"
                className={`pr-cell ${it.position === pos ? "now" : ""} ${isBlank(answers[it.position]) ? "" : "has"} ${flags[it.position] ? "flag" : ""}`}
                aria-label={`${t("courses.player.questionN", { n: it.position + 1 })}${flags[it.position] ? `, ${t("practice.flag")}` : ""}${isBlank(answers[it.position]) ? "" : `, ${t("practice.answeredCell")}`}`}
                onClick={() => goTo(it.position)}
              >
                {it.position + 1}
              </button>
            ))}
          </div>
          <p className="pr-row">
            <button className="btn btn-primary" onClick={() => setDialog("submit")}>
              {t("practice.handIn")}
            </button>
          </p>
        </Dialog>
      )}
      {finishing && <div className="pr-busy" role="status" aria-label={t("practice.finishing")} />}
    </div>
  );
}

// =============================================================== the result

function ResultScreen() {
  const { id = "" } = useParams();
  const { token } = useAuth();
  const { t } = useTranslation();
  const lang = useLang();
  const [rep, setRep] = useState<PReport | null>(() => cachedReport(id));
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (rep || !token) return;
    let alive = true;
    practice.finish(token, id).then(
      (r) => {
        cacheReport(r);
        if (alive) setRep(r);
      },
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [rep, token, id]);

  if (failed)
    return (
      <div className="app practice-run">
        <main className="main pr-msg">
          <p>{t("practice.loadFailed")}</p>
          <Link className="btn btn-primary" to="/luyen-tap">
            {t("practice.backToPractice")}
          </Link>
        </main>
      </div>
    );
  if (!rep) return <div className="boot" />;

  const mock = rep.session.kind === "mock";
  const ratio = rep.total ? rep.correct / rep.total : 0;
  const generic = ratio >= 0.8 ? t("practice.line.good") : ratio >= 0.5 ? t("practice.line.ok") : t("practice.line.more");
  const takeaway = rep.takeaway ? (lang === "en" ? rep.takeaway.line_en : rep.takeaway.line_vi) : generic;
  const redo = rep.redo ? (lang === "en" ? rep.redo.line_en : rep.redo.line_vi) : null;
  return (
    <div className="app practice-run">
      <main className="main">
        <div className="result" data-guide="practice-result" data-guide-label={t("practice.resultLabel")}>
          <p className="score" aria-label={mock && rep.score_10 != null ? t("practice.scoreAria10", { n: fmtScore10(rep.score_10, lang) }) : t("practice.scoreAria", { right: rep.correct, total: rep.total })}>
            {mock && rep.score_10 != null ? fmtScore10(rep.score_10, lang) : rep.correct}
            <small>/{mock && rep.score_10 != null ? 10 : rep.total}</small>
          </p>
          <h1>{takeaway}</h1>
          {mock && <p className="muted">{t("practice.mockCounts", { right: rep.correct, total: rep.total, answered: rep.answered })}</p>}
          {redo && (
            <p className="plan">
              <Icon name="clock" />
              <span>{redo}</span>
            </p>
          )}
          {mock && rep.per_part && rep.per_part.length > 0 && (
            <ul className="pr-parts">
              {rep.per_part.map((p) => (
                <li key={p.label}>
                  <span>{p.label}</span>
                  <b>
                    {fmtNum(p.points, lang)}/{fmtNum(p.max_points, lang)}
                  </b>
                </li>
              ))}
            </ul>
          )}
          {rep.per_topic.length > 0 && (
            <ul className="pr-parts">
              {rep.per_topic.map((p) => (
                <li key={p.topic}>
                  <span>{p.title}</span>
                  <b>
                    {p.right}/{p.total}
                  </b>
                </li>
              ))}
            </ul>
          )}
          {rep.disclaimer && <p className="muted small">{rep.disclaimer}</p>}
          <p className="pr-row">
            <Link className="btn btn-primary" to="/">
              {t("practice.done")}
            </Link>
            <Link className="btn btn-ghost" to={`/luyen-tap/${encodeURIComponent(id)}/xem-lai`}>
              {t("practice.reviewAnswers")}
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}

// =============================================================== the review

function ReviewScreen() {
  const { id = "" } = useParams();
  const { token } = useAuth();
  const { t } = useTranslation();
  const lang = useLang();
  const [items, setItems] = useState<PReviewItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    practice.review(token, id).then(
      (r) => alive && setItems(Array.isArray(r) ? r : r.items),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [token, id]);
  return (
    <div className="app practice-run">
      <header className="topbar">
        <Link className="icon-btn" to={`/luyen-tap/${encodeURIComponent(id)}/ket-qua`} aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="x" />
        </Link>
        <h1 className="page-title">{t("practice.reviewTitle")}</h1>
      </header>
      <main className="main pr-review" data-guide="practice-review" data-guide-label={t("practice.reviewTitle")}>
        {failed && <p className="muted">{t("practice.loadFailed")}</p>}
        {!items && !failed && <p className="muted">{t("practice.loading")}</p>}
        {items?.map((it) => {
          const res: PResult = { correct: it.correct ?? null, points: it.points ?? undefined, max_points: it.max_points ?? undefined, correct_answer: it.correct_answer, option_feedback: it.option_feedback, statement_results: it.statement_results };
          const out = shown(it, res);
          const mine = it.answer ?? "";
          return (
            <article key={it.position} className={`pr-rev ${out.outcome}`}>
              <ItemView item={it} token={token ?? ""} lang={lang} value={mine} onChange={() => undefined} locked result={res} n={it.position + 1} />
              <div className={`feedback pr-fb ${out.outcome}`}>
                <b>{t(`practice.outcome.${out.outcome}`)}</b>
                {out.tally && out.outcome !== "right" && <span>{t("practice.tally", { right: out.tally.right, total: out.tally.total })}</span>}
                {out.outcome !== "right" && it.correct_answer && (it.type === "SHORT_ANSWER" || it.type === "TAP_COUNT") && (
                  <span>
                    {t("practice.correctAnswer")}: <b className="ok">{it.correct_answer}</b>
                  </span>
                )}
                {it.explanation && <Md md={it.explanation} />}
                {it.tip && <p className="muted small">{it.tip}</p>}
              </div>
            </article>
          );
        })}
        <p className="pr-row">
          <Link className="btn btn-primary" to="/">
            {t("practice.done")}
          </Link>
        </p>
      </main>
    </div>
  );
}
