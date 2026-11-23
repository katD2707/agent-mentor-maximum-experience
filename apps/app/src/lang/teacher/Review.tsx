import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "katex/dist/katex.min.css";
import { assetUrl, teacherApi, type AssetRef, type Block, type CommentAnchor, type CoursePack, type TeacherComment, type TeacherCourseDetail, type TeacherTest, type UnsureStep } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { allLessons } from "../../lib/courseProgress";
import { numberComments, type Numbered } from "../../lib/teacher/comments";
import { versionLevel } from "../../lib/teacher/level";
import { canPublish } from "./labels";
import { commentPending, latestPublished } from "../../lib/teacher/status";
import type { BlockCtx } from "../kit/blocks";
import { Opening, TeacherTop, labelsRoute, useToast, withTimeout } from "./common";
import { useTeacherCourses } from "./live";
import { LevelTag } from "./LevelTag";
import { Notes } from "./ReviewParts";
import { LessonTab, PracticeTab, RecapTab, TestsTab } from "./ReviewTabs";

const OPEN_TIMEOUT_MS = 60000;

/** gv-03: the lesson exactly as students see it (same player components), with one-line comments in a red-pen margin; Publish is the one action. */
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
  const [busy, setBusy] = useState<"publish" | "edit" | null>(null);
  const toast = useToast(3200);
  const [error, setError] = useState<string | null>(null);
  const [nudged, setNudged] = useState(false);
  /** the course or its content did not open (a timeout counts): the screen says so and offers a retry */
  const [openFailed, setOpenFailed] = useState(false);

  const loadDetail = useCallback(async () => {
    if (!token) return null;
    try {
      const d = await withTimeout(teacherApi.getCourse(token, id), OPEN_TIMEOUT_MS);
      setDetail(d);
      setOpenFailed(false);
      return d;
    } catch (e) {
      if ((e as { status?: number }).status === 404) setMissing(true);
      else setOpenFailed(true);
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
  // the difficulty is confirmed in the Nhãn step; publishing waits for it
  const levelConfirmed = detail ? canPublish(detail.course, version) : false;

  const loadPack = useCallback(async () => {
    if (!token || !detail) return;
    try {
      setPack(await withTimeout(teacherApi.getPack(token, id, version), OPEN_TIMEOUT_MS));
      setOpenFailed(false);
    } catch {
      setOpenFailed(true);
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

  const [tab, setTab] = useState<"bai" | "luyen" | "kiem" | "nghe">("bai");
  const [unsure, setUnsure] = useState<UnsureStep[]>([]);
  const [tests, setTests] = useState<TeacherTest[]>([]);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!token || !detail) return;
    void teacherApi.getReview(token, id, version).then(setUnsure, () => setUnsure([]));
    void teacherApi.listTests(token, id).then(setTests, () => setTests([]));
  }, [token, id, version, detail?.course.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const unsureMap = useMemo(() => new Map(unsure.map((u) => [u.block_id, u])), [unsure]);
  const commented = useMemo(() => new Set(comments.map((c) => c.block_id)), [comments]);
  const locked = !!published;

  const replaceBlock = (blk: Block) =>
    setPack((p) => (p ? { ...p, chapters: p.chapters.map((c) => ({ ...c, lessons: c.lessons.map((l) => ({ ...l, blocks: l.blocks.map((x) => (x.id === blk.id ? blk : x)) })) })) } : p));
  const saveBlock = async (blockId: string, patch: Record<string, unknown>) => {
    if (!token) return;
    setSaving(true);
    try {
      replaceBlock(await teacherApi.patchBlock(token, id, version, blockId, patch));
      toast.show(t("gv.saved"));
    } catch {
      setError(t("gv.saveFailed"));
    } finally {
      setSaving(false);
    }
  };
  const seen = async (blockId: string) => {
    if (!token) return;
    setUnsure((u) => u.filter((x) => x.block_id !== blockId));
    try {
      await teacherApi.markSeen(token, id, version, blockId);
    } catch {
      setError(t("gv.saveFailed"));
    }
  };
  const sendNote = async (blockId: string, body: string) => {
    if (!token) return;
    const anchor: CommentAnchor = { kind: "text", start: 0, end: 0, quote: body.slice(0, 40) };
    try {
      const r = await teacherApi.postComment(token, id, version, { block_id: blockId, anchor, body });
      setComments((c) => [...c, { id: r.id, block_id: blockId, anchor, body, status: r.status }]);
      prev.current.set(r.id, r.status);
    } catch {
      setError(t("gv.commentFailed"));
      throw new Error("comment");
    }
  };
  const saveTest = async (profileId: string, body: { items: number; minutes: number }) => {
    if (!token) return;
    setTests((x) => x.map((r) => (r.profile_id === profileId ? { ...r, ...body } : r)));
    try {
      await teacherApi.putTest(token, id, profileId, body);
      toast.show(t("gv.saved"));
    } catch {
      setError(t("gv.saveFailed"));
    }
  };
  const saveRecap = async (chapterId: string, script: string[]) => {
    if (!token) return;
    try {
      await teacherApi.putRecap(token, id, version, chapterId, script);
      setPack(await teacherApi.getPack(token, id, version));
      toast.show(t("gv.saved"));
    } catch {
      setError(t("gv.saveFailed"));
    }
  };
  const saveGloss = async (n: number) => {
    if (!token) return;
    setPack((p) => (p ? { ...p, gloss_start: n } : p));
    try {
      await teacherApi.putGloss(token, id, version, n);
    } catch {
      setError(t("gv.saveFailed"));
    }
  };

  const pick = (n: Numbered) => {
    setActive(n.id);
    setTab("bai");
  };

  /** Publishing without confirmed labels: say so, and the Nhãn step is one tap away. */
  const needLevel = () => setNudged(true);

  const publish = async () => {
    if (!token) return;
    setBusy("publish");
    try {
      await teacherApi.publish(token, id, version);
      await loadDetail();
      refreshList();
      toast.show(version > 1 ? t("gv.publishedOkN", { version }) : t("gv.publishedOk"));
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
    } catch {
      setError(t("gv.newVersionFailed"));
    } finally {
      setBusy(null);
    }
  };

  const levelShown = lv.confirmed ?? lv.suggested;
  const prevPub = detail ? latestPublished({ versions: detail.course.versions.filter((v) => v.version < version) }) : null;

  const back = labelsRoute(id, version);
  if (missing)
    return (
      <div className="app">
        <TeacherTop step={4} courseId={id} backTo={back} />
        <main className="main">
          <p role="alert">{t("gv.notFound")}</p>
        </main>
      </div>
    );

  const blocked = anyPending;
  const publishLabel = version > 1 ? t("gv.publishN", { version }) : t("gv.publish");

  return (
    <div className="app review">
      <TeacherTop step={4} courseId={id} backTo={back}>
        {detail && pack &&
          (published ? (
            <button className="btn btn-primary act pub" type="button" onClick={() => void edit()} disabled={busy !== null} data-guide="gv-publish" data-guide-label={t("gv.editPublished")}>
              <span>{t("gv.editPublished")}</span>
            </button>
          ) : (
            <button className="btn btn-primary act pub" type="button" onClick={() => (levelConfirmed ? void publish() : needLevel())} disabled={busy !== null || blocked} aria-disabled={!levelConfirmed || undefined} aria-describedby={blocked ? "pub-why" : undefined} data-guide="gv-publish" data-guide-label={publishLabel}>
              <span>{publishLabel}</span>
            </button>
          ))}
      </TeacherTop>

      <main className="main review-main">
        {blocked && (
          <p id="pub-why" className="sr">
            {t("gv.publishWait")}
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

        {!pack || !lesson ? (
          <Opening failed={openFailed} message={detail && !pack ? t("gv.packFailed") : t("lg.gvl.openFailed")} onRetry={() => {
            setOpenFailed(false);
            void (detail ? loadPack() : loadDetail());
          }} />
        ) : (
          <>
            <div className="crumbs">
              <h1>{pack.title}</h1>
              <span className="grow" />
              {tab === "bai" && (
                <span className="pager">
                  <button className="icon-btn" type="button" aria-label={t("gv.prevLesson")} disabled={idx === 0} onClick={() => goto(idx - 1)}>
                    <Icon name="back" />
                  </button>
                  <span>{t("courses.lessonOf", { n: idx + 1, total: lessons.length })}</span>
                  <button className="icon-btn" type="button" aria-label={t("gv.nextLesson")} disabled={idx === lessons.length - 1} onClick={() => goto(idx + 1)}>
                    <Icon name="next" />
                  </button>
                </span>
              )}
            </div>
            {detail && version > 1 && !published && <VerNote>{prevPub && prevPub.students > 0 ? t("gv.versionNote", { students: prevPub.students, prev: prevPub.version, version }) : t("gv.versionNoteNone", { version })}</VerNote>}
            {detail && published && <VerNote>{t("gv.publishedNote", { version, students: vinfo?.students ?? 0 })}</VerNote>}
            <div className={`lvx-row${nudged && !levelConfirmed ? " need" : ""}`} id="levelrow" data-guide="gv-level" data-guide-label={t("lg.gvl.level.label")}>
              <span className="lvx-label">{t("lg.gvl.level.label")}</span>
              {levelShown ? <LevelTag level={levelShown} /> : <span className="muted">{t("lg.gvl.level.unset")}</span>}
              {nudged && !levelConfirmed && (
                <span className="lvx-note" role="status">
                  {t("lg.gvl.level.confirmFirst")}
                </span>
              )}
            </div>

            <div className="tabs" role="tablist" aria-label={t("gv.tabsAria")}>
              {(["bai", "luyen", "kiem", "nghe"] as const).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
                  {t(k === "bai" ? "gv.tabLesson" : k === "luyen" ? "gv.tabPractice" : k === "kiem" ? "gv.tabTests" : "gv.tabListen")}
                </button>
              ))}
            </div>
            {tab === "bai" && (
              <LessonTab lesson={lesson} no={idx + 1} ctx={ctx} unsure={unsureMap} commented={commented} locked={locked} english={pack.language === "en"} saving={saving} onSave={(b, p) => void saveBlock(b, p)} onSeen={(b) => void seen(b)} onComment={sendNote} />
            )}
            {tab === "luyen" && <PracticeTab pack={pack} locked={locked} saving={saving} onSave={(b, p) => void saveBlock(b, p)} />}
            {tab === "kiem" && <TestsTab tests={tests} locked={locked} onSave={(p, b) => void saveTest(p, b)} />}
            {tab === "nghe" && <RecapTab chapters={pack.chapters} locked={locked} english={pack.language === "en"} glossStart={pack.gloss_start ?? 30} urlOf={ctx.url} onSave={(c, sc) => void saveRecap(c, sc)} onGloss={(n) => void saveGloss(n)} />}
            <Notes notes={notes} active={active} onPick={pick} others={others} />
          </>
        )}
      </main>

      {toast.node}

    </div>
  );
}

function VerNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="vernote" role="note">
      <Icon name="layers" />
      <span>{children}</span>
    </p>
  );
}
