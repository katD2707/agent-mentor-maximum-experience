import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "katex/dist/katex.min.css";
import { api, type AssetRef, type Block, type Enrollment, type Lesson, type QuizResult } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { getCourseInfo } from "../../lib/courseInfo";
import { loadEnrollments, saveProgress } from "../../lib/enrollments";
import { courseStore, loadPack, PackIntegrityError, PackTooNewError, type LoadedPack } from "../../lib/offline";
import { packShaFor, startDownload } from "../../lib/sync";
import { allLessons, blockIds, lessonPercent, resumePosition, stepsOf, type Pos } from "../../lib/courseProgress";
import { speak } from "../../lib/speak";
import { logEvent } from "../../lib/events";
import { StaticBlock, type BlockCtx } from "./blocks";
import { QuizItemView } from "./QuizItemView";

type Load = { status: "loading" } | { status: "error"; reason: "integrity" | "tooNew" | "load"; minVersion?: string } | { status: "ready"; loaded: LoadedPack; enrollment: Enrollment };

/** The lesson player: a focus screen with only a close button and a progress bar. Lazy-loaded (Markdown + KaTeX). */
export default function Player() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
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
    <div className="app player">
      <header className="lesson-top">
        <Link className="icon-btn" to="/khoa-hoc" aria-label={t("courses.player.close")}>
          <Icon name="x" />
        </Link>
      </header>
      <main className="player-msg">
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
    }),
    [pack.language, pack.course_id, loaded],
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
      onNext={goNext}
      flush={flush}
      doneLabel={t("courses.player.doneTitle", { n: idx + 1 })}
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
  onNext(): void;
  flush(): void;
  doneLabel: string;
}

function LessonView(p: LessonProps) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const nav = useNavigate();
  const kid = user?.age_band === "g1_5";
  const { lesson } = p;
  const results = useRef(new Map<string, boolean>()); // item id -> right on first try
  const itemsDone = useRef(new Set<string>());
  const [finished, setFinished] = useState(false);
  const steps = useMemo(() => stepsOf(lesson), [lesson]);
  const [step, setStep] = useState(() => Math.max(0, steps.findIndex((s) => s.blockId === p.resumeBlock)));

  const close = () => {
    p.flush();
    nav("/khoa-hoc");
  };

  const onResult = (r: QuizResult) => {
    if (!results.current.has(r.item_id)) results.current.set(r.item_id, r.correct);
    p.onQuiz(r);
  };
  const [, rerender] = useState(0);
  const onItemDone = (block: Extract<Block, { kind: "quiz" }>, itemId: string) => {
    itemsDone.current.add(itemId);
    rerender((n) => n + 1); // kid mode shows "Tiếp" once the item is done; a ref alone would not redraw
    if (block.items.every((i) => itemsDone.current.has(i.id))) p.onComplete([block.id]);
  };

  const finish = () => {
    p.onComplete(blockIds(lesson));
    setFinished(true);
    window.scrollTo({ top: 0 });
  };

  // kid mode: walk the steps
  useEffect(() => {
    if (kid && !finished) p.onVisit(steps[step].blockId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kid, step, finished]);

  const pct = finished ? 100 : kid ? Math.round((step / steps.length) * 100) : lessonPercent(lesson, p.completed);
  const total = results.current.size;
  const right = [...results.current.values()].filter(Boolean).length;

  const topbar = (
    <header className="lesson-top">
      <button className="icon-btn" type="button" onClick={close} aria-label={t("courses.player.close")}>
        <Icon name="x" />
      </button>
      <div className="t" data-guide="player-progress" data-guide-label={t("courses.player.progress")}>
        {kid ? (
          <div className="steps" role="progressbar" aria-label={t("courses.player.progress")} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            {steps.map((_, i) => (
              <i key={i} className={finished || i < step ? "done" : i === step ? "now" : ""} />
            ))}
          </div>
        ) : (
          <>
            <b>{p.title}</b>
            <span className="meta">
              <span className="bar" role="progressbar" aria-label={t("courses.player.progress")} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                <i style={{ width: `${pct}%` }} />
              </span>
              <span>{t("courses.lessonOf", { n: p.index + 1, total: p.total })}</span>
            </span>
          </>
        )}
      </div>
    </header>
  );

  // ---- done card
  if (finished) {
    return (
      <div className="app player" data-lang={p.ctx.lang}>
        {topbar}
        <main className="done-wrap">
          <section className="finish oli">
            {kid ? (
              <div className="win-stars" aria-hidden="true">
                {[0, 1, 2].map((i) => (
                  <svg key={i} viewBox="0 0 24 24" className="s">
                    <path d="M12 2.5l2.9 6 6.6.8-4.9 4.5 1.3 6.5L12 17l-5.9 3.3 1.3-6.5L2.5 9.3l6.6-.8z" fill="#FFC21A" stroke="#9A5200" strokeWidth="1" />
                  </svg>
                ))}
              </div>
            ) : (
              total > 0 && <span className="score">{right}/{total}</span>
            )}
            <div className="say">
              <h2>{kid ? t("courses.player.doneKid") : p.doneLabel}</h2>
              {kid && <button className="speak" type="button" aria-label={t("courses.player.speak")} onClick={() => speak(t("courses.player.doneKid"), p.ctx.lang || i18n.language)}><Icon name="volume" /></button>}
            </div>
            <p className="muted">{p.next ? t("courses.player.nextUp", { lesson: p.next.title }) : t("courses.player.courseDone")}</p>
            <div className="row">
              {p.next ? (
                <button className="btn btn-primary btn-big" type="button" onClick={p.onNext}>
                  <span>{t("courses.player.nextLesson")}</span>
                  <Icon name="next" />
                </button>
              ) : (
                <button className="btn btn-primary btn-big" type="button" onClick={close}>
                  {t("courses.player.backToCourse")}
                </button>
              )}
              {p.next && (
                <button className="btn btn-ghost" type="button" onClick={close}>
                  {t("courses.player.stop")}
                </button>
              )}
            </div>
          </section>
        </main>
      </div>
    );
  }

  // ---- little ones: one step per screen
  if (kid) {
    const s = steps[step];
    const last = step === steps.length - 1;
    const advance = () => {
      if (s.block.kind !== "quiz") p.onComplete([s.blockId]);
      if (last) finish();
      else setStep(step + 1);
    };
    const quizDone = s.block.kind === "quiz" && s.itemIndex !== undefined && itemsDone.current.has(s.block.items[s.itemIndex].id);
    return (
      <div className="app player kid-player" data-lang={p.ctx.lang}>
        {topbar}
        <main className="stage" key={`${s.blockId}-${s.itemIndex ?? 0}`}>
          {s.block.kind === "quiz" && s.itemIndex !== undefined ? (
            <>
              <QuizItemView
                item={s.block.items[s.itemIndex]}
                ctx={p.ctx}
                kid
                onResult={onResult}
                onDone={() => onItemDone(s.block as Extract<Block, { kind: "quiz" }>, (s.block as Extract<Block, { kind: "quiz" }>).items[s.itemIndex!].id)}
              />
              {quizDone && <NextButton onClick={advance} />}
            </>
          ) : (
            <>
              <StaticBlock b={s.block as Exclude<Block, { kind: "quiz" }>} ctx={p.ctx} />
              <NextButton onClick={advance} />
            </>
          )}
        </main>
        {p.cached && <span className="sr">{t("courses.player.offlineBadge")}</span>}
      </div>
    );
  }

  // ---- everyone else: the whole lesson as one column
  return (
    <div className="app player" data-lang={p.ctx.lang}>
      {topbar}
      <main className="lesson-col">
        <h1 className="lesson-h">{lesson.title}</h1>
        {lesson.blocks.map((b) => (
          <BlockSlot key={b.id} block={b} onSeen={() => (b.kind !== "quiz" && p.onComplete([b.id]), p.onVisit(b.id))} resume={b.id === p.resumeBlock && b.id !== lesson.blocks[0].id}>
            {b.kind === "quiz" ? (
              <div className="quiz-block">
                <h2 className="quiz-h">{b.title || t("courses.player.quizTitle")}</h2>
                {b.items.map((item, i) => (
                  <QuizItemView key={item.id} item={item} ctx={p.ctx} kid={false} n={b.items.length > 1 ? i + 1 : undefined} onResult={onResult} onDone={() => onItemDone(b, item.id)} />
                ))}
              </div>
            ) : (
              <StaticBlock b={b} ctx={p.ctx} />
            )}
          </BlockSlot>
        ))}
        <div className="lesson-end">
          <button className="btn btn-primary btn-big" type="button" onClick={finish}>
            {t("courses.player.finishLesson")}
          </button>
          {p.cached && <span className="muted small">{t("courses.player.offlineBadge")}</span>}
        </div>
      </main>
    </div>
  );
}

function NextButton({ onClick }: { onClick(): void }) {
  const { t } = useTranslation();
  return (
    <button className="btn btn-primary btn-big next" type="button" onClick={onClick}>
      <span>{t("courses.player.next")}</span>
      <Icon name="next" />
    </button>
  );
}

/** Wrapper that reports when a block has been on screen and, once, scrolls the saved block into view. */
function BlockSlot({ block, onSeen, resume, children }: { block: Block; onSeen(): void; resume: boolean; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useRef(onSeen);
  seen.current = onSeen;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (resume) el.scrollIntoView({ block: "start" });
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) seen.current();
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [resume]);
  return (
    <div ref={ref} id={`b-${block.id}`} className={`slot slot-${block.kind}`}>
      {children}
    </div>
  );
}

