import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, PracticeError, type PItem, type PReport, type PResult, type PReviewItem, type PSession, type PXp } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { speak } from "../../../lib/speak";
import { Md } from "../../kit/blocks";
import { ItemView } from "./ItemView";
import { FixFlow } from "./Fix";
import { chickenName } from "../../subjects";
import { BossArt, bossSvg } from "../arena/Bosses";
import { Shell, chickenPic, f1, useLang } from "../arena/common";
import { ArDialog } from "./Dialog";
import {
  answerOf,
  canCheck,
  clockText,
  firstSentence,
  fmtNum,
  handInStats,
  initialRemaining,
  isBlank,
  isOpen,
  isStepType,
  resumePosition,
  shown,
  stepText,
  wrongStatements,
} from "../../../lib/practice";

/**
 * `/luyen-tap/:id` (the exam or practice screen), `/ket-qua` (result, with the boss replay for an Arena paper) and `/xem-lai`
 * (the wrong ones), in the wood-board language of the village. Loaded on demand with Markdown and KaTeX.
 */
export default function PracticeRun() {
  return (
    <Routes>
      <Route index element={<SessionScreen />} />
      <Route path="ket-qua" element={<ResultScreen />} />
      <Route path="xem-lai" element={<ReviewScreen />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

type RunKind = "paper" | "course-mock" | "bank-mock" | "practice";
const kindOf = (s: Pick<PSession, "kind" | "source" | "paper">): RunKind => (s.paper || s.source?.startsWith("paper:") ? "paper" : s.source?.startsWith("course-mock:") ? "course-mock" : s.kind !== "practice" ? "bank-mock" : "practice");

const reportKey = (id: string) => `mentor.practice.report.${id}`;
const xpKey = (id: string) => `mentor.practice.xp.${id}`;
const seenKey = (id: string) => `mentor.boss.seen.${id}`;
function ssGet<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}
function ssSet(key: string, v: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* never required */
  }
}
const cachedReport = (id: string) => ssGet<PReport>(reportKey(id));
/** XP the answers of this session paid so far, kept for the result screen. */
function addXp(id: string, xp: PXp[] | undefined) {
  if (!xp?.length) return;
  ssSet(xpKey(id), [...(ssGet<PXp[]>(xpKey(id)) ?? []), ...xp]);
}
const reducedMotion = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Where "Xong" and "Lưu và thoát" go: the screen the run was opened from, else the village. */
function useBack() {
  const nav = useNavigate();
  const { state } = useLocation();
  const back = (state as { back?: string } | null)?.back;
  return { back, go: () => nav(back ?? "/", { replace: true }) };
}

type Load = { s: "loading" } | { s: "error" } | { s: "ready"; session: PSession };

// =============================================================== the session

function SessionScreen() {
  const { id = "" } = useParams();
  const { token } = useAuth();
  const { t } = useTranslation();
  const { state } = useLocation();
  const { go } = useBack();
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
  if (load.s === "loading") return <div className="boot" />;
  if (load.s === "error")
    return (
      <Shell title={t("practice.title")}>
        <div className="ar-stack">
          <p role="alert">{t("practice.loadFailed")}</p>
          <div className="ar-acts">
            <button className="ar-btn" type="button" onClick={() => setAttempt((n) => n + 1)}>
              {t("practice.retry")}
            </button>
            <button className="ar-btn quiet" type="button" onClick={go}>
              {t("lg.backHome")}
            </button>
          </div>
        </div>
      </Shell>
    );
  if (!isOpen(load.session)) return <Navigate replace to={`/luyen-tap/${encodeURIComponent(id)}/ket-qua`} state={state} />;
  return <Player session={load.session} />;
}

function Player({ session }: { session: PSession }) {
  const { t } = useTranslation();
  const lang = useLang();
  const nav = useNavigate();
  const { state } = useLocation();
  const { go } = useBack();
  const { token, user } = useAuth();
  const tk = token ?? "";
  const kid = user?.age_band === "g1_5";
  const kind = kindOf(session);
  const mock = session.kind !== "practice";
  const id = session.id;
  const items = session.items;
  const last = items.length - 1;
  const paper = session.paper ?? null;
  const notes = !!session.source?.startsWith("notes:");

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
  const [tips, setTips] = useState<Record<number, string>>({});
  const [tipOpen, setTipOpen] = useState(false);
  const [flags, setFlags] = useState<Record<number, boolean>>(() => Object.fromEntries(items.map((it) => [it.position, !!session.answers[String(it.position)]?.flagged])));
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | "exit" | "submit">(null);
  const [finishing, setFinishing] = useState(false);
  const [charge, setCharge] = useState(0);

  // ---- clocks: seconds on the item (cumulative) and, for an exam, the server's deadline
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
  const total = useRef<number | null>(null);
  const [left, setLeft] = useState<number | null>(() => {
    const r = initialRemaining(session, Date.now());
    endAt.current = r === null ? null : Date.now() + r * 1000;
    total.current = r === null ? null : Math.max(r, (session.minutes ?? 0) * 60);
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
        ssSet(reportKey(id), report);
        nav(`/luyen-tap/${encodeURIComponent(id)}/ket-qua${auto ? "?auto=1" : ""}`, { replace: true, state });
      } catch {
        setFinishing(false);
        setNote(t("practice.finishFailed"));
      }
    },
    [id, nav, seconds, state, t, tk],
  );

  // exam: count down every second; the server (tick, every 5 s) corrects the clock; zero hands the exam in
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

  // save the place when the app is hidden or closed; a tab that slept catches up when it wakes
  useEffect(() => {
    const save = () => void practice.tick(tk, id, live.current.pos, seconds(live.current.pos)).catch(() => undefined);
    const hide = () => {
      if (document.visibilityState === "hidden") save();
      else if (endAt.current !== null) {
        const r = Math.max(0, Math.ceil((endAt.current - Date.now()) / 1000));
        setLeft(r);
        if (r === 0 && mock) void finish(true);
      }
    };
    window.addEventListener("pagehide", save);
    document.addEventListener("visibilitychange", hide);
    return () => {
      window.removeEventListener("pagehide", save);
      document.removeEventListener("visibilitychange", hide);
    };
  }, [id, seconds, tk, mock, finish]);

  const item: PItem | undefined = items[pos];
  const result = results[pos] ?? null;
  const value = answers[pos] ?? "";
  useEffect(() => setTipOpen(false), [pos]);

  // ---- exam: answers are saved as drafts, editable until hand-in
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
        addXp(id, r.xp);
        // No quiz_answer event here: the planner derives it from PracticeAnswer (planner/events.derived), so logging would double-count FSRS reps.
        if (r.correct === false) {
          if (kid) speak(t("practice.kidWrong"), lang);
          const fb = typeof r.option_feedback === "string" ? r.option_feedback : r.option_feedback?.[v];
          if (fb) setWhy((m) => ({ ...m, [p]: firstSentence(fb) }));
          practice.reveal(tk, id, p).then(
            (x) => {
              if (!fb) setWhy((m) => ({ ...m, [p]: firstSentence(x.explanation) }));
              if (x.tip) setTips((m) => ({ ...m, [p]: x.tip as string }));
            },
            () => undefined,
          );
        }
        if (r.correct) setCharge((n) => n + 1);
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
    go();
  };

  const stats = useMemo(() => handInStats(session, answers, flags), [session, answers, flags]);

  if (!item) return <Navigate replace to="/" />;
  const done = Object.keys(results).length;
  const progress = mock ? stats.answered : done;
  const out = result ? shown(item, result) : null;
  const chicken = paper?.chicken ?? null;
  const heroName = chicken ? chickenName(chicken, lang) : "";
  const bossName = paper ? (lang === "en" ? paper.boss.name_en : paper.boss.name_vi) : "";
  const title = kind === "paper" ? t("lg.run.paper") : kind === "course-mock" ? t("lg.run.courseMock") : kind === "bank-mock" ? t("lg.run.bankMock") : notes ? t("lg.run.notes") : t("lg.run.practice", { count: items.length });
  const warn = mock && left !== null && left <= 300 && left > 60;
  const crit = mock && left !== null && left <= 60;
  const bannerSec = total.current ?? Infinity;
  const banner = crit && bannerSec > 60 ? { text: t("lg.run.left1"), crit: true } : warn && bannerSec > 300 ? { text: t("lg.run.left5"), crit: false } : null;
  const partLabel = session.parts?.find((p) => p.positions.includes(item.position))?.label;
  const clock = mock && left !== null && (
    <span className={`ar-timer${crit ? " crit" : warn ? " warn" : ""}`} role="timer" aria-label={t("practice.timeLeft")} data-guide="practice-clock">
      <Icon name="clock" />
      <span>{clockText(left)}</span>
    </span>
  );
  const typeName = !mock && item.topic_title ? item.topic_title : "";

  return (
    <Shell title={title} pr busy={finishing}>
      <div className={`ar-player${kid ? " kid-run" : ""}`} data-exam={mock ? "1" : undefined}>
        <div className={`ar-ptop${mock ? " stick" : ""}`} data-guide="practice-progress">
          <button className="ar-x" type="button" aria-label={t("practice.saveExit")} onClick={() => (mock ? setDialog("exit") : leave())}>
            <Icon name="x" />
          </button>
          {mock ? (
            <>
              <span className="ar-chip">{t("lg.run.qOf", { n: pos + 1, total: items.length })}</span>
              {partLabel && (session.parts?.length ?? 0) > 1 && <span className="ar-chip lv">{partLabel}</span>}
              <span style={{ flex: 1 }} />
              {clock}
            </>
          ) : (
            <>
              <div className="ar-bar" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={items.length}>
                <i style={{ width: `${(progress / Math.max(1, items.length)) * 100}%` }} />
              </div>
              <span className="ar-chip">{t("lg.run.qOf", { n: pos + 1, total: items.length })}</span>
            </>
          )}
        </div>

        {paper && chicken && (
          <Strip art={paper.boss.art} hero={chickenPic(chicken)} me={heroName} foe={bossName} done={stats.answered} total={items.length} charge={charge} flagKey={stats.answered} />
        )}
        {paper && <p className="ar-exname">{lang === "en" ? paper.title_en : paper.title_vi}</p>}
        {banner && (
          <p className={`ar-note${banner.crit ? " crit" : ""}`} role="status" aria-live="polite">
            {banner.text}
          </p>
        )}

        {!mock && (typeName || notes || tips[pos]) && (
          <div className="ar-qtype">
            {notes && <span className="ar-chip">{t("lg.run.fromNotes")}</span>}
            {typeName && <span className="ar-chip">{t("lg.run.type", { name: typeName })}</span>}
            {tips[pos] && (
              <button className="ar-btn wood" type="button" style={{ minHeight: 42, padding: "0 16px" }} aria-expanded={tipOpen} aria-controls="ar-tip" onClick={() => setTipOpen((o) => !o)}>
                <Icon name="bulb" />
                <span>{t("lg.run.tip")}</span>
              </button>
            )}
          </div>
        )}
        {!mock && tips[pos] && tipOpen && (
          <div className="ar-tip" id="ar-tip">
            <Md md={tips[pos]} />
            <small className="ar-muted">{t("lg.run.tipBy")}</small>
          </div>
        )}

        <div className="ar-qcard" data-guide="practice-answer">
          <ItemView item={item} token={tk} lang={lang} kid={kid} value={value} onChange={change} locked={!mock && !!result} result={mock ? null : result} />
        </div>

        {!mock && hints[pos] && !result && (
          <p className="hint pr-hint" role="status">
            <b>{t("courses.player.hint")}:</b> {hints[pos]}
          </p>
        )}

        {!mock && result && out && (
          <div className={`feedback pr-fb ${out.outcome}`} role="status" data-guide="practice-feedback">
            <b>{t(`practice.outcome.${out.outcome}${kid && out.outcome !== "right" ? "Kid" : ""}`)}</b>
            {out.outcome === "right" && result.xp && result.xp.length > 0 && <span className="ar-xp">{t("lg.run.rightXp", { n: result.xp.reduce((s, x) => s + x.amount, 0) })}</span>}
            {out.tally && out.outcome !== "right" && <span>{t("practice.tally", { right: out.tally.right, total: out.tally.total })}</span>}
            {out.outcome !== "right" && out.outcome !== "blank" && item.type === "SHORT_ANSWER" && result.correct_answer && (
              <span>
                {t("practice.correctAnswer")}: <b className="ok">{result.correct_answer}</b>
              </span>
            )}
            {out.outcome !== "right" && isStepType(item.type) && result.correct_answer && (
              <span>
                {t("practice.rightIs")}: <b className="ok">{stepText(item, result.correct_answer)}</b>
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
          <p className="ar-note crit" role="alert">
            {note}
          </p>
        )}

        <div className="ar-qmap" role="group" aria-label={t("practice.qmap")}>
          {items.map((it) => {
            const p = it.position;
            const isDone = mock ? !isBlank(answers[p]) : !!results[p];
            const label = `${t("courses.player.questionN", { n: p + 1 })}${flags[p] ? `, ${t("practice.flag")}` : ""}${isDone ? `, ${t("practice.answeredCell")}` : ""}`;
            const cls = `ar-qn ${isDone ? "done" : ""} ${flags[p] ? "flag" : ""}`;
            return mock ? (
              <button key={p} type="button" className={cls} aria-label={label} aria-current={p === pos ? "true" : undefined} onClick={() => goTo(p)}>
                {p + 1}
              </button>
            ) : (
              <span key={p} className={cls} role="img" aria-label={label} aria-current={p === pos ? "true" : undefined}>
                {p + 1}
              </span>
            );
          })}
        </div>

        <div className={`ar-pfoot${mock ? " sticky" : ""}`}>
          {!mock && (
            <span className="mid">
              {!result && !hints[pos] && (
                <button className="ar-btn quiet" type="button" onClick={() => void hint()} data-guide="practice-hint">
                  {t("practice.hint")}
                </button>
              )}
              {!result && (
                <button className="ar-btn quiet" type="button" onClick={() => void skip()} disabled={busy}>
                  {t("practice.skip")}
                </button>
              )}
            </span>
          )}
          {mock && (
            <span className="mid">
              <button className="ar-btn wood" type="button" disabled={pos === 0} onClick={() => goTo(pos - 1)}>
                {t("lg.run.prev")}
              </button>
              <button className="ar-btn wood" type="button" aria-pressed={!!flags[pos]} onClick={flag} data-guide="practice-flag">
                <Icon name="flag" /> {flags[pos] ? t("practice.unflag") : t("practice.flag")}
              </button>
            </span>
          )}
          <span className="mid">
            {mock && (
              <button className="ar-btn red" type="button" onClick={() => (flushDraft(), setDialog("submit"))}>
                {t("practice.handIn")}
              </button>
            )}
            {!mock && !result && item.type !== "SINGLE_CHOICE" && item.type !== "PICTURE_CHOICE" && (
              <button className="ar-btn" type="button" disabled={busy || !canCheck(item, value)} onClick={() => void check(pos, value)}>
                {t("practice.check")}
              </button>
            )}
            {!mock && result && (
              <button className="ar-btn" type="button" onClick={next} autoFocus>
                {pos < last ? t("practice.next") : t("practice.seeResult")}
              </button>
            )}
            {mock && pos < last && (
              <button className="ar-btn" type="button" onClick={next}>
                {t("practice.next")}
              </button>
            )}
          </span>
        </div>
      </div>

      {dialog === "exit" && (
        <ArDialog title={t("practice.exitTitle")} onClose={() => setDialog(null)}>
          <p>{t("practice.exitMock")}</p>
          <div className="ar-acts">
            <button className="ar-btn" type="button" onClick={() => setDialog(null)}>
              {t("practice.keepGoing")}
            </button>
            <button className="ar-btn wood" type="button" onClick={leave}>
              {t("practice.saveExit")}
            </button>
          </div>
        </ArDialog>
      )}
      {dialog === "submit" && (
        <ArDialog title={t("lg.run.submitTitle")} onClose={() => setDialog(null)}>
          <p>{t("practice.handInBody", { answered: stats.answered, total: stats.total })}</p>
          {stats.blank > 0 && <p>{t("practice.blankLeft", { n: stats.blank })}</p>}
          {stats.flagged > 0 && <p>{t("practice.flaggedLeft", { n: stats.flagged })}</p>}
          <div className="ar-acts">
            <button className="ar-btn wood" type="button" onClick={() => setDialog(null)}>
              {t("practice.keepGoing")}
            </button>
            <button className="ar-btn red" type="button" onClick={() => void finish()} disabled={finishing}>
              {t("practice.handInYes")}
            </button>
          </div>
        </ArDialog>
      )}
      {finishing && <div className="ar-busy" role="status" aria-label={t("practice.finishing")} />}
    </Shell>
  );
}

/** The battle strip while sitting an Arena paper: the chicken charges one notch per answered question, the boss HP stays hidden. */
function Strip({ art, hero, me, foe, done, total, charge, flagKey }: { art: string; hero: string; me: string; foe: string; done: number; total: number; charge: number; flagKey: number }) {
  const { t } = useTranslation();
  const [on, setOn] = useState(false);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setOn(false);
    const id = window.setTimeout(() => setOn(true), 16);
    const off = window.setTimeout(() => setOn(false), 600);
    return () => {
      window.clearTimeout(id);
      window.clearTimeout(off);
    };
  }, [flagKey, charge]);
  return (
    <div className="ar-stage strip" role="img" aria-label={t("lg.run.stripAria", { name: me, done, total })}>
      <StageBg fence={false} />
      <div className="ar-plate me">
        <b className="nm">{me}</b>
        <div className="row">
          <div className={`ar-lucbar${on ? " charge" : ""}`} style={{ ["--w" as string]: `${(done / Math.max(1, total)) * 100}%`, ["--step" as string]: `${total <= 60 ? 100 / total : 100}%` }}>
            <i />
          </div>
          <span className="ar-luclab">{`${t("lg.run.power")} ${done}/${total}`}</span>
        </div>
      </div>
      <div className="ar-plate foe">
        <b className="nm">{foe}</b>
        <div className="ar-hpbar hid" aria-label={t("lg.run.bossHp")}>
          <i />
          <em>???</em>
        </div>
      </div>
      <BossArt art={art} className="ar-boss" />
      <div className={`ar-hero${on ? " charge" : ""}`}>
        <img src={hero} alt="" />
      </div>
    </div>
  );
}

function StageBg({ fence }: { fence: boolean }) {
  return (
    <svg className="bg" viewBox="0 0 400 200" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 80 Q0 56 40 56 L360 56 Q400 56 400 80 L400 128 L0 128Z" fill="#c2402a" />
      <path d="M0 76 H400" stroke="#fff" strokeWidth="4" opacity=".8" />
      <path d="M0 98 H400" stroke="#8f2d1c" strokeWidth="3" />
      {fence && (
        <>
          <g stroke="#7d4c22" strokeWidth="3">
            <path d="M50 56V20M140 56V12M260 56V12M350 56V20" />
          </g>
          <path d="M50 20l22 6-22 6z" fill="#ffcf3d" />
          <path d="M140 12l22 6-22 6z" fill="#e2573a" />
          <path d="M260 12l22 6-22 6z" fill="#ffcf3d" />
          <path d="M350 20l22 6-22 6z" fill="#e2573a" />
        </>
      )}
      <rect y="124" width="400" height="76" fill="#e9cf98" />
      <ellipse cx="200" cy="170" rx="260" ry="42" fill="#f1dcaa" opacity=".85" />
      <rect y="124" width="400" height="6" fill="#9ccf78" />
    </svg>
  );
}

// =============================================================== the boss replay

/** Damage = right answers, boss HP = number of questions. One quick strike per step; skippable; still frame under reduced motion. */
function BossReplay({ boss, hero, me, onDone }: { boss: NonNullable<PReport["boss"]>; hero: string; me: string; onDone(): void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const n = Math.max(1, boss.hp);
  const d = Math.min(n, Math.max(0, boss.damage));
  const [hp, setHp] = useState(n);
  const [fx, setFx] = useState("");
  const [dmg, setDmg] = useState("");
  const [over, setOver] = useState(false);
  const timers = useRef<number[]>([]);
  const clear = () => {
    timers.current.forEach((x) => window.clearTimeout(x));
    timers.current = [];
  };
  const later = (fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms));
  };
  const finish = useCallback(() => {
    clear();
    setFx(boss.beaten ? "thang" : "thoat");
    setHp(boss.beaten ? 0 : n - d);
    setOver(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boss.beaten, n, d]);

  useEffect(() => {
    if (reducedMotion()) {
      finish();
      return clear;
    }
    const steps = Math.min(Math.max(d, 1), 8);
    const gap = Math.max(260, Math.floor(2200 / steps));
    let i = 0;
    let dealt = 0;
    const strike = () => {
      if (i >= steps || d === 0) return void later(finish, d === 0 ? 700 : 450);
      i += 1;
      const part = Math.round((d * i) / steps) - dealt;
      dealt += part;
      setFx("");
      later(() => {
        setFx("nhanh");
        setDmg(`-${part}`);
      }, 20);
      const now = dealt;
      later(() => setHp(n - now), 220);
      later(strike, gap);
    };
    later(strike, 500);
    return clear;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const name = lang === "en" ? boss.name_en : boss.name_vi;
  return (
    <div className="ar-battle">
      <div className="ar-stage" data-fx={fx} role="img" aria-label={t("lg.run.stageAria")}>
        <StageBg fence />
        <div className="ar-plate me">
          <b>{me}</b>
        </div>
        <div className="ar-plate foe">
          <b>{name}</b>
          <div className="ar-hpbar" role="progressbar" aria-label={t("lg.run.hpAria")} aria-valuemin={0} aria-valuemax={n} aria-valuenow={hp}>
            <i style={{ ["--w" as string]: `${(hp / n) * 100}%` }} />
          </div>
          <span className="ar-hpnum">{`HP ${hp}/${n}`}</span>
        </div>
        <span className="ar-boss" aria-hidden="true" dangerouslySetInnerHTML={{ __html: bossSvg(boss.art) }} />
        <div className="ar-hero">
          <img src={hero} alt="" />
        </div>
        <div className="ar-shot" aria-hidden="true" />
        <svg className="ar-boom" viewBox="0 0 100 100" aria-hidden="true">
          <path d="M50 4l9 28 28-12-14 26 27 10-27 11 14 26-28-12-9 28-9-28-28 12 14-26-27-11 27-10-14-26 28 12z" fill="#ffcf3d" stroke="#fff" strokeWidth="4" strokeLinejoin="round" />
        </svg>
        <div className="ar-dmg" aria-hidden="true">
          {dmg}
        </div>
      </div>
      <p className={`ar-verdict${over ? (boss.beaten ? " win" : " run") : ""}`} role="status" aria-live="polite">
        {over ? t(boss.beaten ? "lg.run.bossDown" : "lg.run.bossRun") : ""}
      </p>
      <div className="ar-acts" style={{ justifyContent: "center" }}>
        {!over && (
          <button className="ar-btn quiet" type="button" onClick={finish}>
            {t("lg.run.skip")}
          </button>
        )}
        {over && (
          <button className="ar-btn big" type="button" onClick={onDone} autoFocus>
            {t("lg.run.seeResult")}
          </button>
        )}
      </div>
    </div>
  );
}

// =============================================================== the result

function ResultScreen() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const { back, go } = useBack();
  const nav = useNavigate();
  const { state } = useLocation();
  const { token } = useAuth();
  const { t } = useTranslation();
  const lang = useLang();
  const [rep, setRep] = useState<PReport | null>(() => cachedReport(id));
  const [sess, setSess] = useState<PSession | null>(null);
  const [failed, setFailed] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fixed, setFixed] = useState<{ right: number; total: number } | null>(null);
  const auto = params.get("auto") === "1";
  const [timeup, setTimeup] = useState(auto);
  const [replayed, setReplayed] = useState(() => !!ssGet<boolean>(seenKey(id)));

  useEffect(() => {
    if (rep || !token) return;
    let alive = true;
    practice.finish(token, id).then(
      (r) => {
        ssSet(reportKey(id), r);
        if (alive) setRep(r);
      },
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [rep, token, id]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    practice.get(token, id).then((s) => alive && setSess(s), () => undefined);
    return () => {
      alive = false;
    };
  }, [token, id]);
  useEffect(() => {
    if (!timeup) return;
    const x = window.setTimeout(() => setTimeup(false), reducedMotion() ? 2200 : 1800);
    return () => window.clearTimeout(x);
  }, [timeup]);

  if (failed)
    return (
      <Shell title={t("lg.run.result")}>
        <div className="ar-stack">
          <p role="alert">{t("practice.loadFailed")}</p>
          <button className="ar-btn" type="button" onClick={go}>
            {t("lg.backHome")}
          </button>
        </div>
      </Shell>
    );
  if (!rep) return <div className="boot" />;

  const kind = sess ? kindOf(sess) : rep.boss ? "paper" : rep.session.kind === "mock" ? "bank-mock" : "practice";
  const mock = rep.session.kind === "mock";
  const chicken = sess?.paper?.chicken ?? rep.xp?.[0]?.chicken ?? (ssGet<PXp[]>(xpKey(id)) ?? [])[0]?.chicken ?? null;
  const gaName = chicken ? chickenName(chicken, lang) : "";
  const wrongN = rep.wrong?.length ?? 0;
  const ratio = rep.total ? rep.correct / rep.total : 0;
  const generic = ratio >= 0.8 ? t("practice.line.good") : ratio >= 0.5 ? t("practice.line.ok") : t("practice.line.more");
  const takeaway = rep.takeaway ? (lang === "en" ? rep.takeaway.line_en : rep.takeaway.line_vi) : generic;
  const redo = rep.redo ? (lang === "en" ? rep.redo.line_en : rep.redo.line_vi) : null;
  const score = mock && rep.score_10 != null ? rep.score_10 : null;
  const paperTitle = sess?.paper ? (lang === "en" ? sess.paper.title_en : sess.paper.title_vi) : null;

  const timeUp = timeup && mock && (
    <div className="ar-timeup" role="alert">
      <div>{t("lg.run.timeUp")}</div>
    </div>
  );

  // ---- the boss replay comes first for an Arena paper
  if (rep.boss && !replayed)
    return (
      <Shell title={t("lg.run.boss")}>
        <BossReplay
          boss={rep.boss}
          hero={chicken ? chickenPic(chicken) : ""}
          me={gaName}
          onDone={() => {
            ssSet(seenKey(id), true);
            setReplayed(true);
          }}
        />
        {timeUp}
      </Shell>
    );

  if (fixing)
    return (
      <Shell title={t("lg.run.fixTitle")} pr>
        <div className="ar-player">
          <FixFlow
            id={id}
            report={rep}
            onDone={(right, total) => {
              setFixed({ right, total });
              setFixing(false);
            }}
          />
        </div>
      </Shell>
    );

  const title = kind === "practice" ? t("lg.run.resultPractice", { count: rep.total }) : kind === "course-mock" ? t("lg.run.resultCourseMock") : kind === "paper" ? t("lg.run.resultPaper") : t("lg.run.resultMock");
  const xpMine = ssGet<PXp[]>(xpKey(id)) ?? [];
  const xpSum = xpMine.reduce((s, x) => s + x.amount, 0);
  const weakPart = (list: { right: number; total: number }[]) => {
    if (list.length < 2) return -1;
    const r = list.map((x) => (x.total ? x.right / x.total : 1));
    const w = Math.min(...r);
    return w < 0.6 ? r.indexOf(w) : -1;
  };
  const parts = (rep.per_part ?? []).map((p) => ({ label: p.label, right: p.points, total: p.max_points, text: `${fmtNum(p.points, lang)}/${fmtNum(p.max_points, lang)}` }));
  const topics = (rep.per_topic ?? []).map((p) => ({ label: p.title || p.topic, right: p.right, total: p.total, text: `${p.right}/${p.total}` }));
  const bars = kind === "paper" || kind === "bank-mock" ? (parts.length ? parts : topics) : topics;
  const weak = weakPart(bars);
  const usedMin = rep.minutes;
  const backLabel = back === "/dau-truong" || kind === "paper" ? t("lg.run.backArena") : back?.startsWith("/kiem-tra") ? t("lg.run.backCourse") : t("practice.done");

  return (
    <Shell title={title} pr>
      <div className="ar-res" data-guide="practice-result">
        {auto && mock && <p className="ar-auto" role="status">{t("lg.run.autoNote")}</p>}
        <div className="ar-res-top">
          {chicken && (
            <span className="ar-cro">
              <img src={chickenPic(chicken, "body")} alt="" />
            </span>
          )}
          <div className="ar-stack" style={{ gap: 4 }}>
            <p className="ar-score score" aria-label={score != null ? t("practice.scoreAria10", { n: f1(score, lang) }) : t("practice.scoreAria", { right: rep.correct, total: rep.total })}>
              {score != null ? f1(score, lang).replace(/[,.]0$/, "") : rep.correct}
              <small>/{score != null ? 10 : rep.total}</small>
            </p>
            {paperTitle && <p className="ar-muted">{paperTitle}</p>}
            {rep.boss && <p className={`ar-verdict sm ${rep.boss.beaten ? "win" : "run"}`}>{t(rep.boss.beaten ? "lg.run.beat" : "lg.run.gotAway", { name: lang === "en" ? rep.boss.name_en : rep.boss.name_vi })}</p>}
            {(rep.xp ?? []).map((x) => (
              <p className="ar-xp" key={x.source}>
                {x.source === "boss_beaten" ? t("lg.run.xpBoss", { n: x.amount }) : t("lg.run.xpSubmit", { name: chickenName(x.chicken, lang), n: x.amount })}
              </p>
            ))}
            {!mock && xpSum > 0 && (
              <>
                <p className="ar-xp">{t("lg.run.xpRight", { name: gaName, n: xpSum })}</p>
                <p className="ar-muted">{t("lg.run.xpRightSub", { count: xpMine.length })}</p>
              </>
            )}
          </div>
        </div>
        {!mock && <h1>{takeaway}</h1>}
        {redo && (
          <p className="ar-muted">
            <Icon name="clock" /> {redo}
          </p>
        )}
        {mock && (
          <ul className="ar-facts" style={{ justifyContent: "flex-start" }}>
            <li className="ar-chip">{t("lg.run.time", { used: Math.max(1, usedMin), total: sess?.minutes ?? Math.max(1, usedMin) })}</li>
            <li className="ar-chip">{t("lg.run.blank", { count: Math.max(0, rep.total - rep.answered) })}</li>
          </ul>
        )}
        {mock && bars.length > 0 && (
          <>
            <h2 className="ar-sub">{t(kind === "paper" || (kind === "bank-mock" && parts.length) ? "lg.run.byPart" : "lg.run.byTopic")}</h2>
            <ul className="ar-bytype pr-parts">
              {bars.map((b, i) => (
                <li key={b.label + i} className={i === weak ? "weak" : undefined}>
                  <span className="nm">{b.label}</span>
                  <span className="ct">{b.text}</span>
                  <span className="tr">
                    <i style={{ width: `${Math.round((b.total ? b.right / b.total : 0) * 100)}%` }} />
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
        {rep.disclaimer && <p className="ar-muted">{rep.disclaimer}</p>}
        {fixed && fixed.total > 0 && (
          <p className="ar-muted" role="status">
            <Icon name="clock" /> {fixed.right === fixed.total ? t("practice.fixAll") : `${t("practice.fixSummary", { right: fixed.right, total: fixed.total })} ${t("practice.fixLeft")}`}
          </p>
        )}
        {!fixed && wrongN > 0 && <p className="ar-muted">{t("practice.yourSummary", { count: wrongN })}</p>}
        <div className="ar-acts">
          {!fixed && wrongN > 0 && (
            <button className="ar-btn" type="button" onClick={() => setFixing(true)}>
              {t("practice.fixN", { count: wrongN })}
            </button>
          )}
          {mock && wrongN > 0 && (
            <button className="ar-btn wood" type="button" onClick={() => nav(`/luyen-tap/${encodeURIComponent(id)}/xem-lai`, { state })}>
              {t("lg.run.reviewN", { count: wrongN })}
            </button>
          )}
          <button className={`ar-btn ${!fixed && wrongN > 0 ? "quiet" : ""}`} type="button" onClick={go}>
            {back ? backLabel : t("practice.done")}
          </button>
        </div>
      </div>
      {timeUp}
    </Shell>
  );
}

// =============================================================== the review

function ReviewScreen() {
  const { id = "" } = useParams();
  const { state } = useLocation();
  const nav = useNavigate();
  const { go } = useBack();
  const { token } = useAuth();
  const { t } = useTranslation();
  const lang = useLang();
  const [items, setItems] = useState<PReviewItem[] | null>(null);
  const [parts, setParts] = useState<PSession["parts"]>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    practice.review(token, id).then(
      (r) => alive && setItems(Array.isArray(r) ? r : r.items),
      () => alive && setFailed(true),
    );
    practice.get(token, id).then((s) => alive && setParts(s.parts ?? null), () => undefined);
    return () => {
      alive = false;
    };
  }, [token, id]);
  const wrong = (items ?? []).filter((it) => it.correct === false);
  const shownList = wrong.slice(0, 20);
  return (
    <Shell title={t("lg.run.reviewTitle")} pr>
      <div className="ar-res" data-guide="practice-review">
        <button className="ar-btn wood" type="button" onClick={() => nav(`/luyen-tap/${encodeURIComponent(id)}/ket-qua`, { replace: true, state })}>
          <Icon name="back" />
          <span>{t("lg.run.reviewBack")}</span>
        </button>
        {failed && <p className="ar-muted">{t("practice.loadFailed")}</p>}
        {!items && !failed && <p className="ar-muted">{t("practice.loading")}</p>}
        {items && (
          <p className="ar-muted">
            {t("lg.run.reviewSum", { count: wrong.length })}
            {wrong.length > shownList.length ? t("lg.run.reviewShown", { count: shownList.length }) : ""}
          </p>
        )}
        <ul className="ar-rvs">
          {shownList.map((it) => {
            const res: PResult = { correct: it.correct ?? null, points: it.points ?? undefined, max_points: it.max_points ?? undefined, correct_answer: it.correct_answer, option_feedback: it.option_feedback, statement_results: it.statement_results };
            const out = shown(it, res);
            const part = parts?.find((p) => p.positions.includes(it.position))?.label;
            return (
              <li key={it.position} className={`ar-rv ${out.outcome}`}>
                {part && parts && parts.length > 1 && <span className="ar-chip">{part}</span>}
                <ItemView item={it} token={token ?? ""} lang={lang} value={it.answer ?? ""} onChange={() => undefined} locked result={res} n={it.position + 1} />
                <div className={`feedback pr-fb ${out.outcome}`}>
                  <b>{t(`practice.outcome.${out.outcome}`)}</b>
                  {out.tally && out.outcome !== "right" && <span>{t("practice.tally", { right: out.tally.right, total: out.tally.total })}</span>}
                  {out.outcome !== "right" && it.correct_answer && (it.type === "SHORT_ANSWER" || it.type === "TAP_COUNT") && (
                    <span>
                      {t("practice.correctAnswer")}: <b className="ok">{it.correct_answer}</b>
                    </span>
                  )}
                  {it.explanation && <Md md={it.explanation} />}
                  {it.tip && <p className="ar-muted">{it.tip}</p>}
                </div>
              </li>
            );
          })}
        </ul>
        <button className="ar-btn quiet" type="button" onClick={go}>
          {t("practice.done")}
        </button>
      </div>
    </Shell>
  );
}
