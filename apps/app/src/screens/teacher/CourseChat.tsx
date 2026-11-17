import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { teacherApi, type CoursePack, type TeacherTest, type UnsureStep, type BuildState, type Outline, type OutlineOp, type RetakeItem, type TeacherCourseDetail } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { applyOutlineOps, lessonCount } from "../../lib/teacher/outline";
import { courseRoute } from "../../lib/teacher/status";
import { CameraButton, TeacherTop, useLangText, useToast } from "./common";
import { OutlineEditor, type TreeMeta } from "./OutlineEditor";
import { questionsByLevel, stepKind } from "../../lib/teacher/steps";
import { useTeacherCourses } from "./live";

const EDITABLE = new Set(["needs_retake", "outline_ready"]);

/** gv-02: the outline tree is the page. Unreadable pages above it, a one-line box to tell Mentor what to change, per-lesson progress on the rows while composing. */
export function CourseChat() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const { token } = useAuth();
  const { refresh: refreshList } = useTeacherCourses();
  const [detail, setDetail] = useState<TeacherCourseDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const inflight = useRef(0);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const d = await teacherApi.getCourse(token, id);
      setDetail(d);
      if (inflight.current === 0) setOutline(d.outline);
      setMissing(false);
    } catch (e) {
      if ((e as { status?: number }).status === 404) setMissing(true);
    }
  }, [token, id]);

  useEffect(() => {
    void load();
    const h = setInterval(() => void load(), 3000);
    return () => clearInterval(h);
  }, [load]);

  const editable = !!detail && EDITABLE.has(detail.status);

  // what the built lessons look like (steps, icons, unsure dots), the practice levels and the tests
  const [pack, setPack] = useState<CoursePack | null>(null);
  const [unsure, setUnsure] = useState<UnsureStep[]>([]);
  const [tests, setTests] = useState<TeacherTest[]>([]);
  const ver = detail?.course.latest_version ?? 0;
  const built = ver > 0 && !!detail && !EDITABLE.has(detail.status) && detail.status !== "building";
  useEffect(() => {
    if (!token || !built) return;
    void teacherApi.getPack(token, id, ver).then(setPack, () => setPack(null));
    void teacherApi.getReview(token, id, ver).then(setUnsure, () => setUnsure([]));
    void teacherApi.listTests(token, id).then(setTests, () => setTests([]));
  }, [token, id, ver, built]);
  const meta: TreeMeta | null = useMemo(() => {
    if (!pack) return built ? { lessons: new Map(), recapMinutes: new Map(), levels: null, tests } : null;
    const bad = new Set(unsure.map((u) => u.block_id));
    return {
      lessons: new Map(pack.chapters.flatMap((c) => c.lessons).map((l) => [l.id, { steps: l.blocks.length, minutes: l.est_minutes, kinds: l.blocks.map(stepKind), unsure: l.blocks.filter((b) => bad.has(b.id)).length }])),
      recapMinutes: new Map(pack.chapters.filter((c) => c.recap).map((c) => [c.id, Math.max(1, Math.round(c.recap!.duration_s / 60))])),
      levels: questionsByLevel(pack).map((x) => x.items.length),
      tests,
    };
  }, [pack, unsure, tests, built]);

  /** Apply to our copy at once, send in order; on failure show the server's version again. */
  const onOps = (ops: OutlineOp[]) => {
    if (!token || !outline) return;
    try {
      setOutline(applyOutlineOps(outline, ops));
    } catch {
      return;
    }
    inflight.current++;
    queue.current = queue.current
      .then(() => teacherApi.putOutline(token, id, ops))
      .then((o) => {
        if (inflight.current === 1) setOutline(o);
      })
      .catch(() => setError(t("gv.editFailed")))
      .finally(() => {
        inflight.current--;
        if (inflight.current === 0) void load();
      });
  };

  /** Adds need the server (it makes the id): wait for the answer. Returns the ids that did not exist before. */
  const onAdd = async (ops: OutlineOp[]): Promise<string[]> => {
    if (!token || !outline) return [];
    const before = new Set([...outline.chapters.map((c) => c.id), ...outline.chapters.flatMap((c) => c.lessons.map((l) => l.id))]);
    inflight.current++;
    try {
      await queue.current;
      const o = await teacherApi.putOutline(token, id, ops);
      if (inflight.current === 1) setOutline(o);
      return [...o.chapters.flatMap((c) => [c.id, ...c.lessons.map((l) => l.id)])].filter((x) => !before.has(x)).reverse();
    } catch {
      setError(t("gv.editFailed"));
      return [];
    } finally {
      inflight.current--;
      if (inflight.current === 0) void load();
    }
  };

  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const say = async () => {
    const v = text.trim();
    if (!v || !token || busy) return;
    setBusy(true);
    setText("");
    try {
      await queue.current;
      await teacherApi.chat(token, id, v);
      await load();
      toast.show(t("gv.fixed"));
    } catch {
      setError(t("gv.chatFailed"));
      setText(v);
    } finally {
      setBusy(false);
    }
  };

  const [starting, setStarting] = useState(false);
  const compose = async () => {
    if (!token || starting) return;
    setStarting(true);
    try {
      await queue.current;
      await teacherApi.build(token, id);
      await load();
      refreshList();
    } catch {
      setError(t("gv.buildFailed"));
    } finally {
      setStarting(false);
    }
  };

  const building = detail?.status === "building";
  const header = (action?: React.ReactNode) => (
    <TeacherTop step={2} courseId={id} backTo="/">
      {action}
    </TeacherTop>
  );

  if (missing)
    return (
      <div className="app">
        {header()}
        <main className="main chat-main">
          <p role="alert">{t("gv.notFound")}</p>
        </main>
      </div>
    );
  if (!detail || !outline)
    return (
      <div className="app">
        {header()}
        <main className="main chat-main">
          <p className="muted" role="status">
            {detail && !detail.outline ? t("gv.readingNow") : t("gv.loading")}
          </p>
        </main>
      </div>
    );

  // the gateway lists every lesson as "waiting" as soon as there is an outline: that is not a build yet
  const showBuild = detail.build.lessons.length > 0 && (!editable || detail.build.lessons.some((l) => l.state !== "waiting"));
  const states = new Map<string, BuildState>(detail.build.lessons.map((l) => [l.id, l.state]));
  const done = detail.build.lessons.filter((l) => l.state === "done").length;
  const reviewTo = courseRoute({ id, status: detail.status, latest_version: detail.course.latest_version || 1 });
  const action = editable ? (
    <button type="button" className="btn btn-primary act" id="go" onClick={() => void compose()} disabled={starting} data-guide="gv-go" data-guide-label={t("gv.composeBtn")}>
      {t("gv.composeBtn")}
    </button>
  ) : building ? (
    <button type="button" className="btn btn-primary act" id="go" aria-disabled="true" data-guide="gv-go" data-guide-label={t("gv.composingBtn")}>
      {t("gv.composingBtn")}
    </button>
  ) : reviewTo?.includes("/duyet") ? (
    <Link className="btn btn-primary act" to={reviewTo}>
      {t("teacher.step3")}
    </Link>
  ) : null;

  return (
    <div className="app">
      {header(action)}
      <main className="main chat-main">
        <div className="course-head">
          <h1>{outline.title || detail.course.title}</h1>
          <p className="meta">
            {t("gv.outlineSummary", { chapters: outline.chapters.length, lessons: lessonCount(outline) })}
            {showBuild && building && " · " + t("gv.composeProgress", { done, total: detail.build.lessons.length })}
          </p>
        </div>

        {detail.retake.length > 0 && <RetakeRows id={id} items={detail.retake} onDone={() => void load()} onError={setError} />}

        <OutlineEditor meta={meta} outline={outline} editable={editable} states={showBuild ? states : undefined} onOps={onOps} onAdd={onAdd} />

        {error && (
          <div className="alert" role="alert">
            <span>{error}</span>
            <button className="btn btn-ghost" type="button" onClick={() => setError(null)}>
              {t("gv.ok")}
            </button>
          </div>
        )}

        {editable && (
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              void say();
            }}
            data-guide="gv-compose"
            data-guide-label={t("gv.composerLabel")}
          >
            <div className="box">
              <input type="text" value={text} aria-label={t("gv.composerLabel")} placeholder={t("gv.composerPlaceholder")} autoComplete="off" onChange={(e) => setText(e.target.value)} />
              <button className="send" type="submit" aria-label={t("gv.send")} disabled={busy || !text.trim()}>
                <Icon name="send" />
              </button>
            </div>
          </form>
        )}
      </main>
      {toast.node}
    </div>
  );
}

// ---------------------------------------------------------------- unreadable pages
function RetakeRows({ id, items, onDone, onError }: { id: string; items: RetakeItem[]; onDone(): void; onError(m: string): void }) {
  const { t } = useTranslation();
  const lt = useLangText();
  const { token } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const pickRef = useRef<HTMLInputElement>(null);
  const target = useRef<RetakeItem | null>(null);

  const send = async (item: RetakeItem, files: File[]) => {
    if (!token || !files.length) return;
    setBusy(item.ref);
    try {
      await teacherApi.addMaterials(token, id, files.slice(0, 1), item.ref);
      onDone();
    } catch {
      onError(t("gv.retakeFailed"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="bads" data-guide="gv-retake" data-guide-label={t("gv.retakeTitle")}>
      <input
        ref={pickRef}
        className="sr"
        type="file"
        accept="image/*,application/pdf"
        tabIndex={-1}
        aria-label={t("gv.pickPage")}
        onChange={(e) => {
          const f = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (target.current) void send(target.current, f);
        }}
      />
      {items.map((r) => (
        <div className="bad" key={r.ref}>
          <Icon name="flag" />
          <span>
            <b>{t("gv.pageN", { n: r.page })}</b> <span className="reason">· {lt(r.message_vi, r.message_en)}</span>
          </span>
          <span className="bad-acts">
            {busy === r.ref ? (
              <span className="muted small" role="status">
                {t("gv.sendingPage")}
              </span>
            ) : (
              <>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => {
                    target.current = r;
                    pickRef.current?.click();
                  }}
                >
                  {t("gv.pickPage")}
                </button>
                <CameraButton single label={t("gv.retakeBtn")} ariaLabel={t("gv.retakePage", { n: r.page })} onFiles={(f) => void send(r, f)} className="btn retake-btn" />
              </>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
