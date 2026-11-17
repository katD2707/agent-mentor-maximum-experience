import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "katex/dist/katex.min.css";
import "../../styles/lesson.css";
import { api, type AssetRef, type Block, type Enrollment, type Lesson, type QuizResult, type Today } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { getCourseInfo } from "../../lib/courseInfo";
import { loadEnrollments, saveProgress } from "../../lib/enrollments";
import { courseStore, loadPack, PackIntegrityError, PackTooNewError, type LoadedPack } from "../../lib/offline";
import { packShaFor, startDownload } from "../../lib/sync";
import { allLessons, blockIds, lessonPercent, resumePosition, stepsOf, type Pos, type Step } from "../../lib/courseProgress";
import { speak } from "../../lib/speak";
import { logEvent } from "../../lib/events";
import { GlossChip, StaticBlock, type BlockCtx } from "./blocks";
import { InteractiveView, Muc, RecallView, type RecallFoot } from "./StepBlocks";
import { QuizItemView, verdictDetail, type Stage } from "./QuizItemView";

type Load = { status: "loading" } | { status: "error"; reason: "integrity" | "tooNew" | "load"; minVersion?: string } | { status: "ready"; loaded: LoadedPack; enrollment: Enrollment };

/** The lesson player: Duolingo-style steps, one per screen; only the exit button and the progress bar stay on top. Lazy-loaded (Markdown + KaTeX). */
export default function Player() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token || !user) return;
    let alive = true;
    let loaded: LoadedPack | null = null;
    (async () => {
      try {
        const { list } = await loadEnrollments(token, user.id);
        const enrollment = list.find((e) => e.course_id === id);
        if (!enrollment) {
          nav(`/khoa-hoc/${id}`, { replace: true });
          return;
        }
        const info = await getCourseInfo(token, id).catch(() => null);
        loaded = await loadPack({ api, token, store: courseStore() }, id, enrollment.pinned_version, packShaFor(info, enrollment.pinned_version));
        if (!alive) return loaded.dispose();
        if (loaded.source === "network") void startDownload(token, id, enrollment.pinned_version, packShaFor(info, enrollment.pinned_version));
        setLoad({ status: "ready", loaded, enrollment });
      } catch (e) {
        if (alive) setLoad(e instanceof PackTooNewError ? { status: "error", reason: "tooNew", minVersion: e.minVersion } : { status: "error", reason: e instanceof PackIntegrityError ? "integrity" : "load" });
      }
    })();
    return () => {
      alive = false;
      loaded?.dispose();
    };
  }, [token, user, id, nav, attempt]);

  if (load.status === "ready") return <Runner key={id} loaded={load.loaded} enrollment={load.enrollment} />;
  return (
    <div className="app player lesson">
      <header className="ls-top">
        <button className="ls-x" type="button" onClick={() => (location.state?.back ? nav(-1) : nav("/"))} aria-label={t("lesson.exit")}>
          <Icon name="x" />
        </button>
      </header>
      <main className="ls-msg">
        {load.status === "loading" ? (
          <p className="muted" role="status">
            {t("courses.player.loading")}
          </p>
        ) : (
          <>
            <p role="alert">{load.reason === "tooNew" ? t("courses.player.tooNew", { v: load.minVersion }) : load.reason === "integrity" ? t("courses.player.integrity") : t("courses.player.loadFailed")}</p>
            <button className="btn btn-primary" type="button" onClick={() => (setLoad({ status: "loading" }), setAttempt((n) => n + 1))}>
              {t("courses.player.retry")}
            </button>
          </>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------- runner: progress state + saving
function Runner({ loaded, enrollment }: { loaded: LoadedPack; enrollment: Enrollment }) {
  const { pack } = loaded;
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const [params] = useSearchParams();
  const lessons = useMemo(() => allLessons(pack), [pack]);

  const start = useMemo<Pos>(() => {
    const want = params.get("lesson");
    const lesson = lessons.find((l) => l.id === want);
    return lesson ? { lessonId: lesson.id, blockId: lesson.blocks[0].id } : resumePosition(pack, enrollment.progress);
  }, [pack, lessons, enrollment.progress, params]);

  const [pos, setPos] = useState<Pos>(start);
  // English courses: the share offered in Vietnamese goes down with every right answer (5 points each)
  const [gloss, setGloss] = useState<number | null>(pack.gloss_start ?? null);
  const lessRight = useCallback(() => setGloss((g) => (g === null ? g : Math.max(0, g - 5))), []);
  const [completed, setCompleted] = useState<Set<string>>(() => new Set(enrollment.progress?.completed_block_ids ?? []));

  // ---- debounced save (saves position + every completed block; quiz answers ride along one PUT each)
  const latest = useRef({ pos, completed });
  latest.current = { pos, completed };
  const pending = useRef<QuizResult[]>([]);
  const loggedPct = useRef("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flush = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (!token || !user) return;
    const { pos: p, completed: c } = latest.current;
    const body = { lesson_id: p.lessonId, block_id: p.blockId, completed_block_ids: [...c] };
    const cur = lessons.find((l) => l.id === p.lessonId);
    if (cur) {
      const pct = lessonPercent(cur, c);
      if (loggedPct.current !== `${cur.id}:${pct}`) {
        loggedPct.current = `${cur.id}:${pct}`;
        logEvent("lesson_progress", { course_id: pack.course_id, lesson_id: cur.id, pct });
      }
    }
    const quizzes = pending.current.splice(0);
    if (quizzes.length === 0) void saveProgress(token, user.id, pack.course_id, body);
    else for (const quiz of quizzes) void saveProgress(token, user.id, pack.course_id, { ...body, quiz });
  }, [token, user, pack.course_id, lessons]);
  const schedule = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, 700);
  }, [flush]);
  useEffect(() => {
    const onHide = () => flush();
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      flush();
    };
  }, [flush]);

  const visit = useCallback(
    (lessonId: string, blockId: string) => {
      setPos((p) => (p.lessonId === lessonId && p.blockId === blockId ? p : { lessonId, blockId }));
      schedule();
    },
    [schedule],
  );
  const complete = useCallback(
    (ids: string[]) => {
      setCompleted((c) => {
        if (ids.every((i) => c.has(i))) return c;
        return new Set([...c, ...ids]);
      });
      schedule();
    },
    [schedule],
  );
  const quiz = useCallback(
    (r: QuizResult) => {
      logEvent("quiz_answer", { item: r.item_id, course_id: pack.course_id, correct: r.correct, seconds: r.seconds });
      pending.current.push(r);
      schedule();
    },
    [schedule, pack.course_id],
  );

  const lesson = lessons.find((l) => l.id === pos.lessonId) ?? lessons[0];
  const idx = lessons.indexOf(lesson);
  const next = lessons[idx + 1] ?? null;

  const goNext = () => {
    if (next) {
      setPos({ lessonId: next.id, blockId: next.blocks[0].id });
      schedule();
      window.scrollTo({ top: 0 });
    }
  };

  const ctx: BlockCtx = useMemo(
    () => ({
      lang: pack.language,
      url: (r: AssetRef | null | undefined) => (r ? loaded.url(r.path) : ""),
      watch: (blockId: string, pct: number) => logEvent("video_watch", { course_id: pack.course_id, lesson_id: latest.current.pos.lessonId, block_id: blockId, pct }),
      glossPct: gloss ?? undefined,
    }),
    [pack.language, pack.course_id, loaded, gloss],
  );

  return (
    <LessonView
      key={lesson.id}
      title={pack.title}
      lesson={lesson}
      index={idx}
      total={lessons.length}
      resumeBlock={lesson.id === start.lessonId ? start.blockId : lesson.blocks[0].id}
      completed={completed}
      ctx={ctx}
      next={next}
      cached={loaded.source === "cache"}
      onVisit={(b) => visit(lesson.id, b)}
      onComplete={complete}
      onQuiz={quiz}
      onRight={lessRight}
      onNext={goNext}
      flush={flush}
      doneLabel={t("lesson.doneTitle", { n: idx + 1 })}
    />
  );
}

// ---------------------------------------------------------------- one lesson
interface LessonProps {
  title: string;
  lesson: Lesson;
  index: number;
  total: number;
  resumeBlock: string;
  completed: ReadonlySet<string>;
  ctx: BlockCtx;
  next: Lesson | null;
  cached: boolean;
  onVisit(blockId: string): void;
  onComplete(ids: string[]): void;
  onQuiz(r: QuizResult): void;
  /** a question answered right on the first try */
  onRight(): void;
  onNext(): void;
  flush(): void;
  doneLabel: string;
}

interface QStep {
  key: string;
  step: Step;
  /** a missed item coming back once at the end of the lesson */
  retry: boolean;
}

type Phase = "steps" | "end" | "streak";
type Streak = NonNullable<Today["streak"]>;

function LessonView(p: LessonProps) {
  const { t, i18n } = useTranslation();
  const { user, token } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const kid = user?.age_band === "g1_5";
  const { lesson } = p;

  const base = useMemo(() => stepsOf(lesson), [lesson]);
  const [queue, setQueue] = useState<QStep[]>(() => base.map((step, n) => ({ key: String(n), step, retry: false })));
  const [i, setI] = useState(() => Math.max(0, base.findIndex((s) => s.blockId === p.resumeBlock)));
  const [phase, setPhase] = useState<Phase>("steps");
  const [stage, setStage] = useState<Stage | null>(null);
  const [combo, setCombo] = useState(0);
  const [streak, setStreak] = useState<Streak | null>(null);
  const results = useRef(new Map<string, boolean>()); // item id -> right on the first try
  const itemsDone = useRef(new Set<string>());
  const [reached, setReached] = useState<string | null>(null); // key of the "Kéo sơ đồ" step whose target was hit
  const [rfoot, setRfoot] = useState<RecallFoot | null>(null);
  const recalled = useRef({ seen: 0, forgot: 0 }); // "Nhớ lại" ideas marked, and those not remembered
  const t0 = useRef(Date.now());
  const mainRef = useRef<HTMLElement>(null);

  const leave = () => {
    p.flush();
    if (location.state?.back) nav(-1);
    else nav("/");
  };

  const cur = queue[i];
  const step = cur.step;
  const quiz = step.block.kind === "quiz" && step.itemIndex !== undefined;
  const verdict = quiz ? (stage?.verdict ?? null) : null;

  useEffect(() => {
    if (phase === "steps") p.onVisit(step.blockId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, step.blockId]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
    mainRef.current?.focus({ preventScroll: true });
  }, [i, phase]);

  const reachedKey = cur.key;
  const onReached = useCallback(() => setReached(reachedKey), [reachedKey]);
  const onResult = (r: QuizResult) => {
    if (!results.current.has(r.item_id)) results.current.set(r.item_id, r.correct);
    p.onQuiz(r);
  };
  const onItemDone = (block: Extract<Block, { kind: "quiz" }>, itemId: string, correct: boolean) => {
    itemsDone.current.add(itemId);
    if (block.items.every((it) => itemsDone.current.has(it.id))) p.onComplete([block.id]);
    if (correct) {
      setCombo((c) => c + 1);
      if (!cur.retry) p.onRight();
    } else {
      setCombo(0);
      // a missed item comes back once at the end of the lesson
      if (!cur.retry) setQueue((q) => [...q, { key: `r${q.length}`, step, retry: true }]);
    }
  };

  const finish = () => {
    p.onComplete(blockIds(lesson));
    setPhase("end");
    if (token) {
      api
        .getToday(token)
        .then((td) => td.streak && td.streak.days >= 1 && setStreak(td.streak))
        .catch(() => {});
    }
  };
  const advance = () => {
    if (!quiz) p.onComplete([step.blockId]);
    if (i >= queue.length - 1) return finish();
    setStage(null);
    setRfoot(null);
    setI(i + 1);
  };

  // what the bottom button does right now
  let label = t("lesson.continue");
  let run: (() => void) | null = advance;
  let enabled = true;
  if (phase === "end") {
    label = streak ? t("lesson.continue") : p.next ? t("courses.player.nextLesson") : t("lesson.leave");
    run = streak ? () => setPhase("streak") : p.next ? p.onNext : leave;
  } else if (phase === "streak") {
    label = t("lesson.keepStreak");
    run = leave;
  } else if (quiz && !verdict) {
    label = t("lesson.check");
    run = stage?.check ?? null;
    enabled = !!stage?.can;
    if (stage?.immediate) run = null;
  } else if (step.block.kind === "interactive") {
    enabled = reached === cur.key;
  } else if (step.block.kind === "recall") {
    if (rfoot?.kind === "show") {
      label = t("lesson.recall.show");
      run = rfoot.run;
    } else if (rfoot?.kind !== "done") run = null;
  }

  // Enter: continue / check, unless it would press a focused button or submit the answer field
  const optCheck = !!(quiz && !verdict && stage?.can && !stage.immediate);
  const act = useRef({ run, enabled, optCheck });
  act.current = { run, enabled, optCheck };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter" || e.repeat || e.isComposing) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      const onOpt = !!el?.closest?.(".opt") && act.current.optCheck;
      if (!onOpt && (tag === "BUTTON" || tag === "A" || tag === "INPUT" || tag === "SUMMARY" || tag === "TEXTAREA" || tag === "SELECT")) return;
      if (act.current.run && act.current.enabled) {
        e.preventDefault();
        act.current.run();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const total = results.current.size;
  const right = [...results.current.values()].filter(Boolean).length;
  const redo = total - right + recalled.current.forgot;
  const anyItems = total + recalled.current.seen > 0;
  const pct = phase !== "steps" ? 100 : Math.max(4, Math.round(((i + (verdict ? 1 : 0)) / queue.length) * 100));
  const minutes = Math.max(1, Math.round((Date.now() - t0.current) / 60000));

  const topbar = (
    <header className="ls-top">
      <button className="ls-x" type="button" onClick={leave} aria-label={t("lesson.exit")}>
        <Icon name="x" />
      </button>
      <span className="ls-bar" role="progressbar" aria-label={t("lesson.progress")} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} data-guide="player-progress" data-guide-label={t("lesson.progress")}>
        <i style={{ width: `${pct}%` }} />
      </span>
      <span className="ls-combo" hidden={phase !== "steps" || combo < 3}>
        {t("lesson.combo", { n: combo })}
      </span>
    </header>
  );

  // ---- the stage: one task per screen
  let stageBody: React.ReactNode = null;
  if (phase === "end") {
    const heading = p.doneLabel;
    stageBody = (
      <div className="ls-sum">
        <Muc happy />
        <div className="ls-h">
          <h1>{heading}</h1>
          {kid && (
            <button className="ls-speak" type="button" aria-label={t("courses.player.speak")} onClick={() => speak(heading, p.ctx.lang || i18n.language)}>
              <Icon name="volume" />
            </button>
          )}
        </div>
        <div className="ls-stats">
          {total > 0 && (
            <div className="ls-stat g">
              <b>{t("lesson.right")}</b>
              <span>
                {right}/{total}
              </span>
            </div>
          )}
          <div className="ls-stat">
            <b>{t("lesson.time")}</b>
            <span>{t("lesson.minutes", { n: minutes })}</span>
          </div>
          {anyItems && (
            <div className="ls-stat o">
              <b>{t("lesson.review")}</b>
              <span>{t("lesson.items", { n: redo })}</span>
            </div>
          )}
        </div>
        {redo > 0 && <p className="ls-why">{t("lesson.reviewLine")}</p>}
      </div>
    );
  } else if (phase === "streak" && streak) {
    stageBody = <StreakView days={streak.today_done ? streak.days : streak.days + 1} />;
  } else if (step.block.kind === "quiz" && step.itemIndex !== undefined) {
    const block = step.block;
    const qi = block.items[step.itemIndex];
    stageBody = <QuizItemView key={cur.key} item={qi} ctx={p.ctx} kid={kid} stepped onStage={setStage} onResult={onResult} onDone={(correct) => onItemDone(block, qi.id, correct)} />;
  } else if (step.block.kind === "text") {
    const say = (
      <div className="ls-say">
        <Muc />
        <div className="ls-bub">
          <StaticBlock b={step.block} ctx={p.ctx} />
        </div>
      </div>
    );
    stageBody =
      step.block.gloss && p.ctx.glossPct !== undefined ? (
        <div className="ls-gl" key={cur.key}>
          <GlossChip pct={p.ctx.glossPct} />
          {say}
        </div>
      ) : (
        <div key={cur.key} className="ls-one">
          {say}
        </div>
      );
  } else if (step.block.kind === "interactive") {
    stageBody = (
      <div className="ls-int" key={cur.key}>
        <InteractiveView b={step.block} muc={<Muc happy={reached === cur.key} />} onReached={onReached} />
      </div>
    );
  } else if (step.block.kind === "recall") {
    stageBody = (
      <div className="ls-rc" key={cur.key}>
        <RecallView
          b={step.block}
          ctx={p.ctx}
          muc={<Muc />}
          onMark={(ok) => {
            recalled.current.seen += 1;
            if (!ok) recalled.current.forgot += 1;
          }}
          onFoot={setRfoot}
        />
      </div>
    );
  } else {
    stageBody = (
      <div className="ls-media" key={cur.key}>
        <StaticBlock b={step.block as Exclude<Block, { kind: "quiz" | "interactive" | "recall" }>} ctx={p.ctx} />
      </div>
    );
  }

  // ---- the bottom: feedback band + the one big button
  const item = quiz ? (step.block as Extract<Block, { kind: "quiz" }>).items[step.itemIndex!] : null;
  const fbState = phase === "steps" && verdict ? (verdict.correct ? "ok" : "no") : "";
  const showFoot = !(phase === "steps" && quiz && !verdict && stage?.immediate) && !(phase === "steps" && step.block.kind === "recall" && !run);

  return (
    <div className={`app player lesson ${kid ? "kid" : ""}`} data-lang={p.ctx.lang}>
      {topbar}
      <main className="ls-stage" ref={mainRef} tabIndex={-1}>
        {stageBody}
      </main>
      <footer className={`ls-foot ${fbState}`} hidden={!showFoot}>
        {quiz && phase === "steps" && (
          <div className="ls-fb" role="status" aria-live="polite">
            {verdict && item && (
              <>
                <h3>
                  <Icon name={verdict.correct ? "check" : "x"} />
                  {verdict.correct ? (combo >= 3 ? t("lesson.great") : t("lesson.ok")) : t("lesson.no")}
                </h3>
                <p>{verdictDetail(item, verdict, stage?.chosen ?? null, t("lesson.answer"))}</p>
              </>
            )}
          </div>
        )}
        {run && (
          <button className="ls-go" type="button" disabled={!enabled} onClick={run}>
            {label}
          </button>
        )}
        {p.cached && <span className="sr">{t("courses.player.offlineBadge")}</span>}
      </footer>
    </div>
  );
}

function StreakView({ days }: { days: number }) {
  const { t } = useTranslation();
  const names = t("lesson.weekdays", { returnObjects: true }) as unknown as string[];
  const today = (new Date().getDay() + 6) % 7; // Monday first
  const on = new Set<number>();
  for (let k = 0; k < days && today - k >= 0; k++) on.add(today - k);
  return (
    <div className="ls-streak">
      <p className="ls-speech">{t("lesson.streakBubble", { n: days })}</p>
      <svg className="ls-flame" viewBox="0 0 120 120" aria-hidden="true">
        <path d="M60 8 C72 34 98 46 98 76 A38 38 0 0 1 22 76 C22 56 34 46 40 30 C46 44 52 48 56 48 C54 32 56 20 60 8 Z" fill="var(--lua)" />
        <path d="M60 54 C66 66 78 72 78 86 A18 18 0 0 1 42 86 C42 76 50 70 52 62 C55 68 58 70 60 70 Z" fill="var(--vang)" />
      </svg>
      <div className="ls-big">{days}</div>
      <p className="ls-days">{t("lesson.streakDays")}</p>
      <div className="ls-wk" role="img" aria-label={`${t("lesson.weekAria")}: ${days}`}>
        {names.map((d, n) => (
          <span key={d} className={on.has(n) ? "on" : ""}>
            {d}
            <i>{on.has(n) && <Icon name="check" />}</i>
          </span>
        ))}
      </div>
      <p className="ls-why">{t("lesson.streakNote")}</p>
    </div>
  );
}
