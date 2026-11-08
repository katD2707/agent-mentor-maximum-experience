import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "katex/dist/katex.min.css";
import { assetUrl, teacherApi, type AssetRef, type Block, type CommentAnchor, type CourseLevel, type CoursePack, type TeacherComment, type TeacherCourseDetail } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { allLessons } from "../../lib/courseProgress";
import { markText, textAnchor } from "../../lib/teacher/anchors";
import { numberComments, textMarks, type Numbered } from "../../lib/teacher/comments";
import { versionLevel } from "../../lib/teacher/level";
import { needsNewerApp } from "../../lib/version";
import { commentPending, latestPublished } from "../../lib/teacher/status";
import { StaticBlock, type BlockCtx } from "../courses/blocks";
import { QuizItemView } from "../courses/QuizItemView";
import { TeacherTop } from "./common";
import { useTeacherCourses } from "./live";
import { LevelPicker, LevelTag } from "./LevelPicker";
import { CommentPop, Notes, PinLayer, VideoBar, type Draft } from "./ReviewParts";

const noop = () => undefined;

/** gv-03: the lesson exactly as students see it (same player components), with comments in a red-pen margin. */
export default function Review() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { t } = useTranslation();
  const { token } = useAuth();
  const { refresh: refreshList } = useTeacherCourses();

  const [detail, setDetail] = useState<TeacherCourseDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [pack, setPack] = useState<CoursePack | null>(null);
  const [comments, setComments] = useState<TeacherComment[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [float, setFloat] = useState<(Draft & { rectTop: number }) | null>(null);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState<"publish" | "edit" | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<CourseLevel | null>(null);
  const [nudged, setNudged] = useState(false);
  const [levelBusy, setLevelBusy] = useState(false);
  const levelRow = useRef<HTMLDivElement>(null);
  const paper = useRef<HTMLElement>(null);

  const loadDetail = useCallback(async () => {
    if (!token) return null;
    try {
      const d = await teacherApi.getCourse(token, id);
      setDetail(d);
      return d;
    } catch (e) {
      if ((e as { status?: number }).status === 404) setMissing(true);
      return null;
    }
  }, [token, id]);
  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const version = Number(params.get("v")) || detail?.course.latest_version || 1;
  const vinfo = detail?.course.versions.find((v) => v.version === version);
  const published = vinfo?.status === "published";
  const lv = detail ? versionLevel(detail.course, vinfo) : { suggested: null, confirmed: null };
  const levelShown = picked ?? lv.confirmed ?? lv.suggested;
  const levelConfirmed = lv.confirmed !== null;
  // the agent's suggestion is what the picker starts on; a pick of ours shows until the detail has caught up
  useEffect(() => setPicked(null), [version, lv.confirmed]);

  const loadPack = useCallback(async () => {
    if (!token || !detail) return;
    try {
      setPack(await teacherApi.getPack(token, id, version));
    } catch {
      setError(t("gv.packFailed"));
    }
  }, [token, id, version, detail?.course.id, t]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setPack(null);
    setComments([]);
    void loadPack();
  }, [loadPack]);

  // comments, and the agent's progress on them
  const prev = useRef<Map<string, TeacherComment["status"]>>(new Map());
  const loadComments = useCallback(async () => {
    if (!token) return;
    try {
      const list = await teacherApi.listComments(token, id, version);
      const fixed = list.some((c) => c.status === "applied" && prev.current.has(c.id) && prev.current.get(c.id) !== "applied");
      prev.current = new Map(list.map((c) => [c.id, c.status]));
      setComments(list);
      if (fixed) void loadPack();
    } catch {
      /* stays as it was */
    }
  }, [token, id, version, loadPack]);
  useEffect(() => {
    prev.current = new Map();
    void loadComments();
  }, [loadComments]);
  const anyPending = comments.some((c) => commentPending(c.status));
  useEffect(() => {
    if (!anyPending) return;
    const h = setInterval(() => void loadComments(), 2500);
    return () => clearInterval(h);
  }, [anyPending, loadComments]);

  const lessons = useMemo(() => (pack ? allLessons(pack) : []), [pack]);
  const lessonId = params.get("lesson");
  const idx = Math.max(0, lessons.findIndex((l) => l.id === lessonId));
  const lesson = lessons[idx];
  const goto = (i: number) => {
    const next = new URLSearchParams(params);
    next.set("lesson", lessons[i].id);
    setParams(next, { replace: true });
    setActive(null);
    window.scrollTo({ top: 0 });
  };

  const notes: Numbered[] = useMemo(() => (lesson ? numberComments(comments, lesson.blocks.map((b) => b.id)) : []), [comments, lesson]);
  const others = comments.length - notes.length;

  const ctx: BlockCtx = useMemo(
    () => ({ lang: pack?.language ?? "vi", url: (r: AssetRef | null | undefined) => (r && token ? assetUrl(token, id, version, r.path) : "") }),
    [pack?.language, token, id, version],
  );

  // red-pen highlights in the text
  useLayoutEffect(() => {
    const root = paper.current;
    if (!root || !lesson) return;
    root.querySelectorAll<HTMLElement>("[data-block]").forEach((slot) => {
      const b = slot.dataset.block!;
      const own = notes.filter((n) => n.block_id === b && n.anchor.kind === "text");
      if (!own.length && !slot.querySelector("mark[data-cmt]")) return;
      markText(slot, textMarks(notes, b, slot.textContent ?? "", active));
    });
  }, [notes, lesson, active, pack]);

  // selecting text offers "Nhận xét"
  useEffect(() => {
    let h: ReturnType<typeof setTimeout>;
    const on = () => {
      clearTimeout(h);
      h = setTimeout(() => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount) return setFloat(null);
        const r = sel.getRangeAt(0);
        const el = r.commonAncestorContainer.nodeType === 1 ? (r.commonAncestorContainer as Element) : r.commonAncestorContainer.parentElement;
        const slot = el?.closest<HTMLElement>("[data-block]");
        if (!slot || !paper.current?.contains(slot)) return setFloat(null);
        const anchor = textAnchor(slot, r);
        if (!anchor) return setFloat(null);
        const rect = r.getBoundingClientRect();
        setFloat({ block_id: slot.dataset.block!, anchor, x: rect.left + rect.width / 2, y: rect.bottom, rectTop: rect.top });
      }, 120);
    };
    document.addEventListener("selectionchange", on);
    return () => {
      clearTimeout(h);
      document.removeEventListener("selectionchange", on);
    };
  }, []);

  const open = (block_id: string, anchor: CommentAnchor, rect: DOMRect) => {
    setFloat(null);
    setDraft({ block_id, anchor, x: rect.left + rect.width / 2, y: rect.bottom });
  };

  const send = async (body: string) => {
    if (!token || !draft) return;
    setSending(true);
    try {
      const r = await teacherApi.postComment(token, id, version, { block_id: draft.block_id, anchor: draft.anchor, body });
      setComments((c) => [...c, { id: r.id, block_id: draft.block_id, anchor: draft.anchor, body, status: r.status }]);
      prev.current.set(r.id, r.status);
      setDraft(null);
      window.getSelection()?.removeAllRanges();
    } catch {
      setError(t("gv.commentFailed"));
    } finally {
      setSending(false);
    }
  };

  const pick = (n: Numbered) => {
    setActive(n.id);
    const slot = paper.current?.querySelector<HTMLElement>(`[data-block="${CSS.escape(n.block_id)}"]`);
    const target = n.anchor.kind === "text" ? (slot?.querySelector(`mark[data-cmt="${CSS.escape(n.id)}"]`) ?? slot) : slot;
    target?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  };

  const needLevel = () => {
    setNudged(true);
    levelRow.current?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  };
  const chooseLevel = async (level: CourseLevel) => {
    if (!token || levelBusy) return;
    setPicked(level);
    setLevelBusy(true);
    try {
      const r = await teacherApi.setLevel(token, id, version, level);
      await loadDetail();
      refreshList();
      setNudged(false);
      if (r.version !== version) setParams({ v: String(r.version) }, { replace: true }); // a published course: the pick goes to version N+1
    } catch {
      setPicked(null);
      setError(t("gv.levelFailed"));
    } finally {
      setLevelBusy(false);
    }
  };

  const publish = async () => {
    if (!token) return;
    setBusy("publish");
    setConfirm(false);
    try {
      await teacherApi.publish(token, id, version);
      await loadDetail();
      refreshList();
      setFlash(t("gv.publishedOk", { version }));
    } catch (e) {
      if ((e as { status?: number }).status === 409 && !levelConfirmed) needLevel();
      else setError(t("gv.publishFailed"));
    } finally {
      setBusy(null);
    }
  };
  const edit = async () => {
    if (!token) return;
    setBusy("edit");
    try {
      const v = await teacherApi.newVersion(token, id);
      await loadDetail();
      refreshList();
      setParams({ v: String(v) }, { replace: true });
      setFlash(null);
    } catch {
      setError(t("gv.newVersionFailed"));
    } finally {
      setBusy(null);
    }
  };

  const prevPub = detail ? latestPublished({ versions: detail.course.versions.filter((v) => v.version < version) }) : null;

  if (missing)
    return (
      <div className="app">
        <TeacherTop back />
        <main className="main">
          <p role="alert">{t("gv.notFound")}</p>
        </main>
      </div>
    );

  const blocked = anyPending;
  const publishLabel = version > 1 ? t("gv.publishN", { version }) : t("gv.publish");

  return (
    <div className="app review">
      <TeacherTop back>
        {detail && pack &&
          (published ? (
            <button className="btn btn-primary pub" type="button" onClick={() => void edit()} disabled={busy !== null} data-guide="gv-publish" data-guide-label={t("gv.editPublished")}>
              <span>{t("gv.editPublished")}</span>
            </button>
          ) : (
            <button className="btn btn-primary pub" type="button" onClick={() => (levelConfirmed ? setConfirm(true) : needLevel())} disabled={busy !== null || blocked} aria-disabled={!levelConfirmed || undefined} aria-describedby={blocked ? "pub-why" : undefined} data-guide="gv-publish" data-guide-label={publishLabel}>
              <span>{publishLabel}</span>
            </button>
          ))}
      </TeacherTop>

      <main className="main review-main">
        {blocked && (
          <p id="pub-why" className="muted small pub-why">
            {t("gv.publishWait")}
          </p>
        )}
        {flash && (
          <p className="close-ok" role="status">
            <Icon name="check" />
            <span>{flash}</span>
          </p>
        )}
        {error && (
          <div className="alert" role="alert">
            <span>{error}</span>
            <button className="btn btn-ghost" type="button" onClick={() => setError(null)}>
              {t("gv.ok")}
            </button>
          </div>
        )}
        {pack && !published && needsNewerApp(pack.min_app_version, detail?.released_app_version) && (
          <div className="version" role="note">
            <Icon name="layers" />
            <p>{t("gv.needsNewerApp", { v: pack.min_app_version })}</p>
          </div>
        )}
        {detail && version > 1 && !published && (
          <div className="version" role="note">
            <Icon name="layers" />
            <p>{prevPub && prevPub.students > 0 ? t("gv.versionNote", { students: prevPub.students, prev: prevPub.version, version }) : t("gv.versionNoteNone", { prev: prevPub?.version ?? version - 1, version })}</p>
          </div>
        )}
        {detail && published && (
          <div className="version" role="note">
            <Icon name="layers" />
            <p>{t("gv.publishedNote", { version, students: vinfo?.students ?? 0 })}</p>
          </div>
        )}

        {!pack || !lesson ? (
          <p className="muted" role="status">
            {t("gv.loading")}
          </p>
        ) : (
          <>
            <div className="crumbs">
              <h1>{pack.title}</h1>
              <span className="tag">{t("gv.versionTag", { version })}</span>
              {levelShown && <LevelTag level={levelShown} pill />}
              <span className="grow" />
              <span className="pager">
                <button className="icon-btn" type="button" aria-label={t("gv.prevLesson")} disabled={idx === 0} onClick={() => goto(idx - 1)}>
                  <Icon name="back" />
                </button>
                <span>{t("courses.lessonOf", { n: idx + 1, total: lessons.length })}</span>
                <button className="icon-btn" type="button" aria-label={t("gv.nextLesson")} disabled={idx === lessons.length - 1} onClick={() => goto(idx + 1)}>
                  <Icon name="next" />
                </button>
              </span>
            </div>
            <LevelPicker
              rowRef={levelRow}
              value={levelShown}
              suggested={lv.suggested}
              confirmed={levelConfirmed}
              nudged={nudged}
              nextVersion={!published && version > 1 && levelConfirmed && detail?.course.level && lv.confirmed !== detail.course.level ? version : null}
              busy={levelBusy}
              onPick={(l) => void chooseLevel(l)}
              onConfirm={() => levelShown && void chooseLevel(levelShown)}
            />
            {!published && <p className="hint">{t("gv.reviewHint")}</p>}

            <div className="layout">
              <article
                ref={paper}
                className="paper oli"
                lang={pack.language}
                data-lang={pack.language}
                data-guide="gv-review"
                data-guide-label={t("gv.reviewTitle")}
                onClick={(e) => {
                  const m = (e.target as Element).closest?.("mark[data-cmt]");
                  if (m) {
                    const n = notes.find((x) => x.id === (m as HTMLElement).dataset.cmt);
                    if (n) setActive(n.id);
                    document.getElementById(`note-${(m as HTMLElement).dataset.cmt}`)?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
                  }
                }}
              >
                <div className="lesson-body">
                  <h2>{lesson.title}</h2>
                  <p className="lesson-meta">{t("gv.lessonMeta", { n: idx + 1, minutes: lesson.est_minutes })}</p>
                  {lesson.blocks.map((b) => (
                    <ReviewBlock key={b.id} b={b} ctx={ctx} notes={notes} active={active} draft={draft} onComment={(a, r) => open(b.id, a, r)} onPick={(nid) => setActive(nid)} />
                  ))}
                </div>
              </article>
              <Notes notes={notes} active={active} onPick={pick} others={others} />
            </div>
          </>
        )}
      </main>

      {float && !draft && (
        <div className="float" style={{ left: float.x, top: float.rectTop }}>
          <button className="btn" type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => open(float.block_id, float.anchor, new DOMRect(float.x, float.y, 0, 0))} data-guide="gv-text-comment" data-guide-label={t("gv.comment")}>
            <Icon name="comment" />
            <span>{t("gv.comment")}</span>
          </button>
        </div>
      )}
      {draft && <CommentPop draft={draft} busy={sending} onSend={(b) => void send(b)} onCancel={() => setDraft(null)} />}

      {confirm && (
        <div className="scrim" role="presentation" onClick={() => setConfirm(false)}>
          <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="pub-h" onClick={(e) => e.stopPropagation()}>
            <h2 id="pub-h">{t("gv.confirmTitle", { version })}</h2>
            <p>{prevPub && prevPub.students > 0 ? t("gv.confirmUpdate", { students: prevPub.students, prev: prevPub.version, version }) : t("gv.confirmFirst")}</p>
            <div className="acts">
              <button className="btn btn-ghost" type="button" onClick={() => setConfirm(false)}>
                {t("gv.cancel")}
              </button>
              <button className="btn btn-primary" type="button" onClick={() => void publish()} autoFocus>
                {publishLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewBlock({ b, ctx, notes, active, draft, onComment, onPick }: { b: Block; ctx: BlockCtx; notes: Numbered[]; active: string | null; draft: Draft | null; onComment(a: CommentAnchor, rect: DOMRect): void; onPick(id: string): void }) {
  const { t } = useTranslation();
  const slot = useRef<HTMLDivElement>(null);
  const own = notes.filter((n) => n.block_id === b.id);
  return (
    <div ref={slot} className="slot" data-block={b.id} id={`b-${b.id}`}>
      {b.kind === "quiz" ? (
        <div className="quiz-block">
          <h2 className="quiz-h">{b.title || t("courses.player.quizTitle")}</h2>
          {b.items.map((item, i) => (
            <QuizItemView key={item.id} item={item} ctx={ctx} kid={false} n={b.items.length > 1 ? i + 1 : undefined} onResult={noop} onDone={noop} />
          ))}
        </div>
      ) : (
        <StaticBlock b={b} ctx={ctx} />
      )}
      {b.kind === "video" && <VideoBar block={b} slot={slot} notes={own.filter((n) => n.anchor.kind === "time")} active={active} onComment={onComment} onPick={onPick} />}
      {b.kind === "image" && <PinLayer slot={slot} notes={own.filter((n) => n.anchor.kind === "point")} active={active} pending={draft?.block_id === b.id ? draft.anchor : null} onComment={onComment} onPick={onPick} />}
    </div>
  );
}
