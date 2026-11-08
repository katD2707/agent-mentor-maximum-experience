import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { teacherApi, type BuildLesson, type ChatMessage, type Outline, type OutlineOp, type RetakeItem, type TeacherCourseDetail } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { applyOutlineOps } from "../../lib/teacher/outline";
import { onMediaError } from "../../lib/mediaRetry";
import { buildStateInfo } from "../../lib/teacher/status";
import { CameraButton, TeacherTop, useLangText } from "./common";
import { OutlineEditor } from "./OutlineEditor";
import { useTeacherCourses } from "./live";

const EDITABLE = new Set(["needs_retake", "outline_ready"]);

/** The course as a conversation (gv-02): outline to edit in place, unreadable pages, then per-lesson progress. */
export function CourseChat() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const { token } = useAuth();
  const nav = useNavigate();
  const { refresh: refreshList } = useTeacherCourses();
  const [detail, setDetail] = useState<TeacherCourseDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [extra, setExtra] = useState<ChatMessage[]>([]);
  const lang = useLangText();
  const lt = (vi?: string | null, en?: string | null) => (vi == null ? vi : lang(vi, en || vi));
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const inflight = useRef(0);
  const end = useRef<HTMLDivElement>(null);

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

  // the thread follows new messages and the build
  const n = (detail?.chat.length ?? 0) + extra.length;
  const building = detail?.status === "building";
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [n, building]);

  const editable = !!detail && EDITABLE.has(detail.status);

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
      const msgs = await teacherApi.chat(token, id, v);
      setExtra((x) => [...x, ...msgs]);
      await load();
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

  if (missing)
    return (
      <div className="app">
        <TeacherTop back />
        <main className="main chat-main">
          <p role="alert">{t("gv.notFound")}</p>
        </main>
      </div>
    );
  if (!detail || !outline)
    return (
      <div className="app">
        <TeacherTop back />
        <main className="main chat-main">
          <p className="muted" role="status">
            {detail && !detail.outline ? t("gv.readingNow") : t("gv.loading")}
          </p>
          {detail && !detail.outline && <ReadingNote title={detail.course.title} />}
        </main>
      </div>
    );

  const seen = new Set(detail.chat.map((m) => m.id));
  const messages = [...detail.chat, ...extra.filter((m) => !seen.has(m.id))];
  const hasKind = (k: ChatMessage["kind"]) => messages.some((m) => m.kind === k);
  // the gateway lists every lesson as "waiting" as soon as there is an outline: that is not a build yet
  const showBuild = detail.build.lessons.length > 0 && (!editable || detail.build.lessons.some((l) => l.state !== "waiting"));
  const done = detail.build.lessons.filter((l) => l.state === "done").length;

  const outlineNode = <OutlineEditor outline={outline} editable={editable} onOps={onOps} onAdd={onAdd} />;
  const retakeNode = detail.retake.length > 0 ? <RetakeCards id={id} items={detail.retake} onDone={() => void load()} onError={setError} /> : null;
  const thread: { key: string; node: React.ReactNode }[] = [];
  // every outline/retake message of the thread would show the same live editor: only the latest one does
  const lastOf = (k: ChatMessage["kind"]) => messages.reduce((at, m, i) => (m.kind === k ? i : at), -1);
  const lastOutline = lastOf("outline");
  const lastRetake = lastOf("retake");
  for (const [i, m] of messages.entries()) {
    if (m.kind === "outline")
      thread.push({ key: m.id, node: i === lastOutline ? <AgentBubble bare>{outlineNode}</AgentBubble> : <AgentBubble text={lt(m.text, m.text_en)} /> });
    else if (m.kind === "retake") {
      if (retakeNode) thread.push({ key: m.id, node: i === lastRetake ? <AgentBubble>{retakeNode}</AgentBubble> : <AgentBubble text={lt(m.text, m.text_en)} /> });
    } else if (m.kind === "build")
      thread.push({
        key: m.id,
        node: (
          <AgentBubble text={lt(m.text, m.text_en)}>
            <BuildProgress lessons={detail.build.lessons} />
          </AgentBubble>
        ),
      });
    else if (m.role === "teacher") thread.push({ key: m.id, node: <TeacherBubble text={m.text ?? ""} /> });
    else thread.push({ key: m.id, node: <AgentBubble text={lt(m.text, m.text_en)} /> });
  }
  // an outline or retake list the server did not put in the thread still shows, after the messages
  if (!hasKind("retake") && retakeNode) thread.push({ key: "retake*", node: <AgentBubble>{retakeNode}</AgentBubble> });
  if (!hasKind("outline")) thread.push({ key: "outline*", node: <AgentBubble bare>{outlineNode}</AgentBubble> });
  if (showBuild && !hasKind("build")) {
    thread.push({ key: "me-build", node: <TeacherBubble text={t("gv.composeThis")} /> });
    thread.push({ key: "build*", node: <AgentBubble text={t("gv.composing", { lessons: detail.build.lessons.length })}><BuildProgress lessons={detail.build.lessons} /></AgentBubble> });
  }

  return (
    <div className="app">
      <TeacherTop back />
      <main className="main chat-main">
        <div className="course-head">
          <h1>{outline.title || detail.course.title}</h1>
          <p className="muted small">{statusLine(detail)}</p>
        </div>

        <section className="thread" aria-label={t("gv.threadLabel")} data-guide="gv-thread" data-guide-label={t("gv.threadLabel")}>
          {thread.map((i) => (
            <div key={i.key} className="thread-item">
              {i.node}
            </div>
          ))}
          {detail.status === "review" || detail.status === "published" || detail.status === "revising" ? (
            <div className="msg">
              <div className="who">
                <span className="logo-mark">M</span>Mentor
              </div>
              <div className="bubble ready">
                <p>{t("gv.readyToReview")}</p>
                <Link className="btn btn-primary" to={`/khoa/${encodeURIComponent(id)}/duyet?v=${detail.course.latest_version || 1}`}>
                  <span>{t("gv.openReview")}</span>
                  <Icon name="next" />
                </Link>
              </div>
            </div>
          ) : null}
          {building && done < detail.build.lessons.length ? <p className="muted small thread-note">{t("gv.buildTime")}</p> : null}
          <div ref={end} />
        </section>

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
              <textarea
                rows={1}
                value={text}
                aria-label={t("gv.composerLabel")}
                placeholder={t("gv.composerPlaceholder")}
                onChange={(e) => {
                  setText(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${e.target.scrollHeight}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void say();
                  }
                }}
              />
              <button className="send" type="submit" aria-label={t("gv.send")} disabled={busy || !text.trim()}>
                <Icon name="send" />
              </button>
            </div>
            <div className="row">
              <span className="muted small">{t("gv.notPublished")}</span>
              <button type="button" className="btn btn-primary" onClick={() => void compose()} disabled={starting}>
                <span>{t("gv.composeBtn")}</span>
              </button>
            </div>
          </form>
        )}
        {!editable && !detail.outline && (
          <button className="btn btn-ghost" type="button" onClick={() => nav("/")}>
            {t("gv.back")}
          </button>
        )}
      </main>
    </div>
  );

  function statusLine(d: TeacherCourseDetail) {
    return t(`gv.line.${d.status}`);
  }
}

function ReadingNote({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <div className="msg">
      <div className="who">
        <span className="logo-mark">M</span>Mentor
      </div>
      <div className="bubble">
        <b>{title}</b>
        <p>{t("gv.readingLong")}</p>
      </div>
    </div>
  );
}

function TeacherBubble({ text }: { text: string }) {
  return (
    <div className="msg me">
      <div className="bubble">{text}</div>
    </div>
  );
}

function AgentBubble({ text, children, bare }: { text?: string | null; children?: React.ReactNode; bare?: boolean }) {
  return (
    <div className="msg">
      <div className="who">
        <span className="logo-mark">M</span>Mentor
      </div>
      {bare ? (
        children
      ) : (
        <div className="bubble">
          {text && <p>{text}</p>}
          {children}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- unreadable pages
function RetakeCards({ id, items, onDone, onError }: { id: string; items: RetakeItem[]; onDone(): void; onError(m: string): void }) {
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
    <div className="bad-pages" data-guide="gv-retake" data-guide-label={t("gv.retakeTitle")}>
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
          {r.thumb_url ? <img src={teacherApi.thumbSrc(token ?? "", r.thumb_url)} alt="" onError={onMediaError} /> : <span className="bad-ph" aria-hidden="true" />}
          <div>
            <b>{t("gv.pageN", { n: r.page })}</b>
            <p className="reason">{lt(r.message_vi, r.message_en)}</p>
            <div className="bad-acts">
              {busy === r.ref ? (
                <span className="muted small" role="status">
                  {t("gv.sendingPage")}
                </span>
              ) : (
                <>
                  <CameraButton single label={t("gv.retakePage", { n: r.page })} onFiles={(f) => void send(r, f)} className="btn retake-btn" />
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
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- build progress
export function BuildProgress({ lessons }: { lessons: BuildLesson[] }) {
  const { t } = useTranslation();
  return (
    <ul className="prog" data-guide="gv-build" data-guide-label={t("gv.buildTitle")}>
      {lessons.map((l, i) => {
        const s = buildStateInfo(l.state);
        return (
          <li key={l.id}>
            <span className={`dot ${s.tone}`} aria-hidden="true" />
            <span>
              {t("gv.lessonN", { n: i + 1 })}. {l.title}
              {l.note && <span className="muted small"> {l.note}</span>}
            </span>
            <span className={`st ${s.tone}`}>{t(s.key)}</span>
          </li>
        );
      })}
    </ul>
  );
}
