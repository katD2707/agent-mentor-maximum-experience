import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "katex/dist/katex.min.css";
import { api, isMock, type AssetRef, type Block, type Enrollment, type Lesson as LessonT, type ProgressXp, type QuizResult, type Today } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { getCourseInfo } from "../../../lib/courseInfo";
import { loadEnrollments, saveProgress } from "../../../lib/enrollments";
import { emitXp, onXp } from "../../xp";
import { courseStore, loadPack, PackIntegrityError, PackTooNewError, type LoadedPack } from "../../../lib/offline";
import { packShaFor, startDownload } from "../../../lib/sync";
import { allLessons, blockIds, lessonPercent, resumePosition, stepsOf, type Pos, type Step } from "../../../lib/courseProgress";
import { speak } from "../../../lib/speak";
import { logEvent } from "../../../lib/events";
import { GlossChip, Md, StaticBlock, type BlockCtx } from "../../kit/blocks";
import { InteractiveView, RecallView, type RecallFoot } from "../../kit/StepBlocks";
import { QuizItemView, verdictDetail, type Stage } from "../../kit/QuizItemView";
import { lg, mockGiveXp, type Chicken } from "../../api";
import { chickenOfCourse } from "../../chickenOf";
import { mockAge, type Pose } from "../../chickenArt";
import { Sprite } from "./StepPreview";
import { chickenName, levelOf, stageOf, subjectOf, xpInLevel } from "../../subjects";
import { stageIndex } from "../chuong/logic";
import "../../styles/fonts";
import "../../styles/lesson-lg.css";

type Load = { status: "loading" } | { status: "error"; reason: "integrity" | "tooNew" | "load"; minVersion?: string } | { status: "ready"; loaded: LoadedPack; enrollment: Enrollment; chicken: string | null };

interface Coach {
  id: string | null;
  art: string;
  name: string;
  level: number;
  xpIn: number;
  stage: number;
}
const FALLBACK: Coach = { id: null, art: "toan", name: "", level: 1, xpIn: 0, stage: 3 };

/** Who is teaching: the chicken of the course (its picture, name, level). Falls back to a plain one when it cannot be read. */
function useCoach(chickenId: string | null, lang: "vi" | "en"): [Coach, () => Promise<Coach>] {
  const { token } = useAuth();
  const [coach, setCoach] = useState<Coach>(() => ({ ...FALLBACK, id: chickenId, art: subjectOf(chickenId ?? "")?.art ?? "toan", name: chickenId ? chickenName(chickenId, lang) : "" }));
  const read = useCallback(async (): Promise<Coach> => {
    const s = chickenId ? subjectOf(chickenId) : undefined;
    const base: Coach = { id: chickenId, art: s?.art ?? "toan", name: chickenId ? chickenName(chickenId, lang) : "", level: 1, xpIn: 0, stage: 1 };
    if (!token || !chickenId) return base;
    try {
      const { chicken: c }: { chicken: Chicken } = await lg.getChicken(token, chickenId);
      return { ...base, art: c.art, level: c.level, xpIn: c.xp_in_level, stage: c.stage };
    } catch {
      return { ...base, level: levelOf(0), xpIn: xpInLevel(0), stage: stageOf(1) };
    }
  }, [token, chickenId, lang]);
  useEffect(() => {
    let alive = true;
    void read().then((c) => alive && setCoach(c));
    return () => {
      alive = false;
    };
  }, [read]);
  return [coach, read];
}

/** The lesson player, restyled as lg-04: the chicken explains step by step. Lazy-loaded (Markdown + KaTeX). */
export default function Lesson() {
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
          nav(`/khoa-hoc/${encodeURIComponent(id)}`, { replace: true });
          return;
        }
        const info = await getCourseInfo(token, id).catch(() => null);
        loaded = await loadPack({ api, token, store: courseStore() }, id, enrollment.pinned_version, packShaFor(info, enrollment.pinned_version));
        if (!alive) return loaded.dispose();
        if (loaded.source === "network") void startDownload(token, id, enrollment.pinned_version, packShaFor(info, enrollment.pinned_version));
        setLoad({ status: "ready", loaded, enrollment, chicken: info ? chickenOfCourse(info) : null });
      } catch (e) {
        if (alive) setLoad(e instanceof PackTooNewError ? { status: "error", reason: "tooNew", minVersion: e.minVersion } : { status: "error", reason: e instanceof PackIntegrityError ? "integrity" : "load" });
      }
    })();
    return () => {
      alive = false;
      loaded?.dispose();
    };
  }, [token, user, id, nav, attempt]);

  const age = mockAge(user?.age_band);
  if (load.status === "ready") return <Runner key={id} loaded={load.loaded} enrollment={load.enrollment} chicken={load.chicken} />;
  const leave = () => {
    const back = (location.state as { back?: string } | null)?.back;
    nav(back ?? "/"); // the pack is not here yet, so the chicken of the course is not known either: back, or the village
  };
  return (
    <div className="lp" data-age={age}>
      <div className="lp-lesson">
        <header className="lp-ltop">
          <button className="lp-x" type="button" onClick={leave} aria-label={t("lesson.exit")}>
            <Icon name="x" />
          </button>
        </header>
        <main className="lp-stage">
          <div className="lp-msgbox">
            {load.status === "loading" ? (
              <p role="status">{t("courses.player.loading")}</p>
            ) : (
              <>
                <p role="alert">{load.reason === "tooNew" ? t("courses.player.tooNew", { v: load.minVersion }) : load.reason === "integrity" ? t("courses.player.integrity") : t("courses.player.loadFailed")}</p>
                <button className="lp-go" type="button" onClick={() => (setLoad({ status: "loading" }), setAttempt((n) => n + 1))}>
                  {t("courses.player.retry")}
                </button>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- runner: progress state + saving
function Runner({ loaded, enrollment, chicken }: { loaded: LoadedPack; enrollment: Enrollment; chicken: string | null }) {
  const { pack } = loaded;
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const [params] = useSearchParams();
  const lessons = useMemo(() => allLessons(pack), [pack]);

  const start = useMemo<Pos>(() => {
    const want = params.get("lesson");
    const lesson = lessons.find((l) => l.id === want);
    // a link to the lesson the student left in the middle (coop row, village speaker) picks up where they stopped; any other lesson starts at its first block
    if (lesson) {
      const saved = enrollment.progress;
      const done = new Set(saved?.completed_block_ids ?? []);
      const unfinished = lesson.blocks.some((b) => !done.has(b.id));
      return saved?.lesson_id === lesson.id && unfinished ? resumePosition(pack, saved) : { lessonId: lesson.id, blockId: lesson.blocks[0].id };
    }
    return resumePosition(pack, enrollment.progress);
  }, [pack, lessons, enrollment.progress, params]);

  const [pos, setPos] = useState<Pos>(start);
  // English courses: the share offered in Vietnamese goes down with every right answer (5 points each)
  const [gloss, setGloss] = useState<number | null>(pack.gloss_start ?? null);
  const lessRight = useCallback(() => setGloss((g) => (g === null ? g : Math.max(0, g - 5))), []);
  const [completed, setCompleted] = useState<Set<string>>(() => new Set(enrollment.progress?.completed_block_ids ?? []));

  // ---- debounced save through the enrollment outbox (position + every completed block; quiz answers ride along one PUT each)
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
      courseId={pack.course_id}
      chicken={chicken}
      lesson={lesson}
      index={idx}
      resumeBlock={lesson.id === start.lessonId ? start.blockId : lesson.blocks[0].id}
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
  courseId: string;
  chicken: string | null;
  lesson: LessonT;
  index: number;
  resumeBlock: string;
  ctx: BlockCtx;
  next: LessonT | null;
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

/** One screen of the lesson: a block/question, the chicken explaining a missed one again, or the missed question once more. */
interface QStep {
  key: string;
  step: Step;
  kind: "q" | "reteach" | "twin";
  /** a missed question coming back (right after its explanation, or once more at the end): no second chance after it */
  retry: boolean;
  /** reteach: what the chicken says */
  detail?: string;
}

type Phase = "steps" | "end" | "streak";
type Streak = NonNullable<Today["streak"]>;

function LessonView(p: LessonProps) {
  const { t, i18n } = useTranslation();
  const { user, token } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const lang: "vi" | "en" = i18n.language === "en" ? "en" : "vi";
  const kid = user?.age_band === "g1_5";
  const { lesson } = p;
  // the XP the server paid for this lesson (the progress PUT's `xp`); it also names the chicken that was credited
  const [xp, setXp] = useState<ProgressXp[]>([]);
  useEffect(() => onXp((list, cid) => cid === p.courseId && setXp((x) => [...x, ...list])), [p.courseId]);
  // the server's answer wins over the course's own label (and over the client mirror used when offline)
  const chicken = xp.find((x) => x.chicken)?.chicken ?? p.chicken;
  const [coach, readCoach] = useCoach(chicken, lang);
  const root = useRef<HTMLDivElement>(null);

  const base = useMemo(() => stepsOf(lesson), [lesson]);
  const [queue, setQueue] = useState<QStep[]>(() => base.map((step, n) => ({ key: String(n), step, kind: "q", retry: false })));
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

  // ---- XP, shown on the end screen
  const [after, setAfter] = useState<Coach | null>(null);
  const [counted, setCounted] = useState(false); // the wait for the server is over
  const before = useRef<Coach | null>(null);
  if (before.current && coach.id && before.current.id !== coach.id) before.current = null; // the server credited another chicken than the guess
  if (!before.current && coach.id) before.current = coach;
  useEffect(() => {
    if (!xp.length) return;
    let alive = true;
    void readCoach().then((c) => alive && setAfter(c));
    return () => {
      alive = false;
    };
  }, [xp, readCoach]);

  const leave = () => {
    p.flush();
    const back = (location.state as { back?: string } | null)?.back;
    if (params.get("from") === "khoa" && chicken) nav(`/chuong/${encodeURIComponent(chicken)}?khoa=${encodeURIComponent(p.courseId)}`);
    else if (back) nav(back);
    else nav("/");
  };

  const cur = queue[i];
  const step = cur.step;
  const reteach = cur.kind === "reteach";
  const quiz = !reteach && step.block.kind === "quiz" && step.itemIndex !== undefined;
  const verdict = quiz ? (stage?.verdict ?? null) : null;

  useEffect(() => {
    if (phase === "steps") p.onVisit(step.blockId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, step.blockId]);
  useEffect(() => {
    root.current?.scrollTo?.({ top: 0 });
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
      // the explanation and one more try come right after this question (see `advance`); a miss on that try comes back once at the end
      if (cur.kind === "twin") setQueue((q) => [...q, { key: `r${q.length}`, step, kind: "q", retry: true }]);
    }
  };

  const finish = () => {
    p.onComplete(blockIds(lesson));
    setPhase("end");
    // the mock server pays like the real one: +20 for the lesson, +5 when every question was right on the first try
    if (isMock && token && p.chicken) {
      const perfect = results.current.size > 0 && [...results.current.values()].every(Boolean);
      const up = mockGiveXp(token, p.chicken, 20 + (perfect ? 5 : 0));
      setTimeout(() => emitXp([{ chicken: p.chicken as string, source: "lesson_done", amount: 20, level_up: up && !perfect }, ...(perfect ? [{ chicken: p.chicken as string, source: "lesson_perfect", amount: 5, level_up: up }] : [])], p.courseId), 400);
    }
    setTimeout(() => setCounted(true), 3500);
    if (token) {
      api
        .getToday(token)
        .then((td) => td.streak && td.streak.days >= 1 && setStreak(td.streak))
        .catch(() => {});
    }
  };
  const advance = () => {
    if (!quiz && !reteach) p.onComplete([step.blockId]);
    // a first miss: the chicken explains it again, then the same question once more
    if (quiz && verdict && !verdict.correct && !cur.retry) {
      const item = (step.block as Extract<Block, { kind: "quiz" }>).items[step.itemIndex!];
      // the feedback band already showed the answer and the explanation: the chicken only explains again when it has something new (the hint)
      const shown = verdictDetail(item, verdict, stage?.chosen ?? null, t("lesson.answer"));
      const hint = (item.hint ?? "").trim();
      const fresh = hint && !shown.includes(hint) ? hint : "";
      const again: QStep[] = [...(fresh ? [{ key: `t${queue.length}`, step, kind: "reteach" as const, retry: true, detail: fresh }] : []), { key: `w${queue.length}`, step, kind: "twin" as const, retry: true }];
      setQueue((q) => [...q.slice(0, i + 1), ...again, ...q.slice(i + 1)]);
      setStage(null);
      setRfoot(null);
      setI(i + 1);
      return;
    }
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
  } else if (step.block.kind === "interactive" && !reteach) {
    enabled = reached === cur.key;
  } else if (step.block.kind === "recall" && !reteach) {
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

  const sprite = (pose: Pose = "stand", small = false) => <Sprite art={coach.art} stage={coach.stage} pose={pose} small={small} />;
  const say = (body: ReactNode) => (
    <div className="lp-say">
      {sprite()}
      <div className="lp-bub">{body}</div>
    </div>
  );

  // ---- the stage: one task per screen
  let stageBody: ReactNode = null;
  if (phase === "end") {
    stageBody = <EndView coach={coach} before={before.current} after={after} xp={xp} counted={counted} heading={p.doneLabel} kid={kid} lang={ctxLang(p.ctx, i18n.language)} total={total} right={right} minutes={minutes} redo={redo} anyItems={anyItems} />;
  } else if (phase === "streak" && streak) {
    stageBody = <StreakView days={streak.today_done ? streak.days : streak.days + 1} sprite={sprite("jump")} />;
  } else if (reteach) {
    stageBody = (
      <div className="lp-twinbox" key={cur.key}>
        <span className="lp-tag lp-wait lp-rlabel">{t("lg.lp.reteach")}</span>
        {say(
          <>
            <p className="lp-rt-line">{t("lg.lp.reteachSay")}</p>
            <Md className="lp-rt-line" md={cur.detail || t("lg.lp.reteachNone")} />
          </>,
        )}
      </div>
    );
  } else if (step.block.kind === "quiz" && step.itemIndex !== undefined) {
    const block = step.block;
    const qi = block.items[step.itemIndex];
    stageBody = (
      <div className="lp-twinbox" key={cur.key}>
        {cur.kind === "twin" && <span className="lp-tag lp-rlabel">{t("lg.lp.twin")}</span>}
        <QuizItemView item={qi} ctx={p.ctx} kid={kid} stepped onStage={setStage} onResult={onResult} onDone={(correct) => onItemDone(block, qi.id, correct)} />
      </div>
    );
  } else if (step.block.kind === "text") {
    const bubble = say(<StaticBlock b={step.block} ctx={p.ctx} />);
    stageBody =
      step.block.gloss && p.ctx.glossPct !== undefined ? (
        <div className="ls-gl" key={cur.key}>
          <GlossChip pct={p.ctx.glossPct} />
          {bubble}
        </div>
      ) : (
        <div key={cur.key} className="ls-one">
          {bubble}
        </div>
      );
  } else if (step.block.kind === "interactive") {
    stageBody = (
      <div className="ls-int" key={cur.key}>
        <InteractiveView b={step.block} muc={sprite(reached === cur.key ? "jump" : "stand", true)} onReached={onReached} />
      </div>
    );
  } else if (step.block.kind === "recall") {
    stageBody = (
      <div className="ls-rc" key={cur.key}>
        <RecallView
          b={step.block}
          ctx={p.ctx}
          muc={sprite("stand", true)}
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

  // ---- the bottom: the chicken's feedback band + the one big button
  const item = quiz ? (step.block as Extract<Block, { kind: "quiz" }>).items[step.itemIndex!] : null;
  const fbState = phase === "steps" && verdict ? (verdict.correct ? "ok" : "no") : "";
  const showFoot = !(phase === "steps" && quiz && !verdict && stage?.immediate) && !(phase === "steps" && step.block.kind === "recall" && !reteach && !run);

  return (
    <div className="lp" ref={root} data-age={mockAge(user?.age_band)} data-lang={p.ctx.lang}>
      <div className={`lp-lesson${kid ? " kid" : ""}`}>
        <h1 className="lp-ribbon">{t("lg.lp.ribbon", { n: p.index + 1 })}</h1>
        <header className="lp-ltop">
          <button className="lp-x" type="button" onClick={leave} aria-label={t("lg.lp.exit")}>
            <Icon name="x" />
          </button>
          <span className="lp-lbar" role="progressbar" aria-label={t("lg.lp.progress")} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <i style={{ width: `${pct}%` }} />
          </span>
          <span className="lp-combo" hidden={phase !== "steps" || combo < 3}>
            {t("lesson.combo", { n: combo })}
          </span>
        </header>
        <main className="lp-stage" ref={mainRef} tabIndex={-1}>
          <div className={`lp-in lesson${kid ? " kid" : ""}`}>{stageBody}</div>
        </main>
        <footer className={`lp-lfoot${fbState ? ` lp-${fbState}` : ""}`} hidden={!showFoot}>
          {quiz && phase === "steps" && (
            <div className="lp-fb" role="status" aria-live="polite">
              {verdict && item && (
                <>
                  <span className="lp-fbga">{sprite(verdict.correct ? "jump" : "stand", true)}</span>
                  <div className="lp-fbt">
                    <h3>
                      <Icon name={verdict.correct ? "check" : "x"} />
                      {verdict.correct ? (combo >= 3 ? t("lesson.great") : t("lesson.ok")) : t("lesson.no")}
                    </h3>
                    <Md className="lp-fbmd" md={verdictDetail(item, verdict, stage?.chosen ?? null, t("lesson.answer"))} />
                  </div>
                </>
              )}
            </div>
          )}
          {run && (
            <button className="lp-go" type="button" disabled={!enabled} onClick={run}>
              {label}
            </button>
          )}
          {p.cached && <span className="lp-sr">{t("courses.player.offlineBadge")}</span>}
        </footer>
      </div>
    </div>
  );
}

const ctxLang = (ctx: BlockCtx, fallback: string) => ctx.lang || fallback;

/** The end of a lesson: what was done and how much the chicken grew (the XP the server paid, +20 / +5 / level up). */
function EndView({ coach, before, after, xp, counted, heading, kid, lang, total, right, minutes, redo, anyItems }: { coach: Coach; before: Coach | null; after: Coach | null; xp: ProgressXp[]; counted: boolean; heading: string; kid: boolean; lang: string; total: number; right: number; minutes: number; redo: number; anyItems: boolean }) {
  const { t } = useTranslation();
  const gained = xp.reduce((n, x) => n + x.amount, 0);
  const bonus = xp.filter((x) => x.source === "lesson_perfect").reduce((n, x) => n + x.amount, 0);
  const up = xp.some((x) => x.level_up);
  const shown = after ?? before ?? coach;
  const level = shown.level;
  const stageNames = t("lg.cg.stage", { returnObjects: true }) as unknown as string[];
  const left = Math.max(0, 100 - shown.xpIn);
  const width = after ? after.xpIn : before?.xpIn ?? 0;
  return (
    <div className="lp-done-sum">
      <Sprite art={coach.art} stage={coach.stage} pose="jump" />
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <h2>{heading}</h2>
        {kid && (
          <button className="lp-speakb" type="button" aria-label={t("courses.player.speak")} onClick={() => speak(heading, lang)}>
            <Icon name="volume" />
          </button>
        )}
      </div>
      {coach.id && (
        <div className="lp-xp" aria-label={t("lg.lp.xpAria")}>
          <div className="lp-xp-h">
            <span className="lp-lvb">{level}</span>
            <span>
              <span className="lp-gname">{coach.name}</span> <small>{stageNames[stageIndex(level) - 1]}</small>
            </span>
            {gained > 0 && <span className="lp-xp-gain">{t("lg.lp.xpGain", { n: gained - bonus })}</span>}
            {bonus > 0 && <span className="lp-xp-bonus">{t("lg.lp.xpBonus", { n: bonus })}</span>}
            {up && <span className="lp-xp-up">{t("lg.lp.xpUp")}</span>}
          </div>
          <div className="lp-xp-track" role="progressbar" aria-label={t("lg.lp.xpTrack")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={width}>
            <i style={{ width: `${width}%` }} />
          </div>
          <div className="lp-xp-n">{!gained && !counted ? t("lg.lp.xpWait") : t("lg.lp.xpLine", { xp: shown.xpIn, left, next: level + 1 })}</div>
        </div>
      )}
      <div className="lp-stats">
        {total > 0 && (
          <div className="lp-stat lp-g">
            <b>{t("lesson.right")}</b>
            <span>
              {right}/{total}
            </span>
          </div>
        )}
        <div className="lp-stat">
          <b>{t("lesson.time")}</b>
          <span>{t("lesson.minutes", { n: minutes })}</span>
        </div>
        {anyItems && (
          <div className="lp-stat lp-o">
            <b>{t("lesson.review")}</b>
            <span>{t("lesson.items", { n: redo })}</span>
          </div>
        )}
      </div>
      {redo > 0 && <p className="lp-why">{t("lg.lp.reviewLine")}</p>}
    </div>
  );
}

function StreakView({ days, sprite }: { days: number; sprite: ReactNode }) {
  const { t } = useTranslation();
  const names = t("lesson.weekdays", { returnObjects: true }) as unknown as string[];
  const today = (new Date().getDay() + 6) % 7; // Monday first
  const on = new Set<number>();
  for (let k = 0; k < days && today - k >= 0; k++) on.add(today - k);
  return (
    <div className="lp-streak">
      <p className="lp-bubble">{t("lg.lp.streakBubble", { n: days })}</p>
      {sprite}
      <div className="lp-flamerow">
        <svg className="lp-flame" viewBox="0 0 120 120" aria-hidden="true">
          <path d="M60 8 C72 34 98 46 98 76 A38 38 0 0 1 22 76 C22 56 34 46 40 30 C46 44 52 48 56 48 C54 32 56 20 60 8 Z" fill="var(--lua)" />
          <path d="M60 54 C66 66 78 72 78 86 A18 18 0 0 1 42 86 C42 76 50 70 52 62 C55 68 58 70 60 70 Z" fill="var(--vang)" />
        </svg>
        <div className="lp-bignum">{days}</div>
      </div>
      <p className="lp-days">{t("lesson.streakDays")}</p>
      <div className="lp-wk" role="img" aria-label={`${t("lesson.weekAria")}: ${days}`}>
        {names.map((d, n) => (
          <span key={d} className={on.has(n) ? "lp-on" : ""}>
            {d}
            <i>{on.has(n) && <Icon name="check" />}</i>
          </span>
        ))}
      </div>
      <p className="lp-why">{t("lg.lp.streakNote")}</p>
    </div>
  );
}
