import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { coverUrl, teacherApi, type TeacherCourseSummary } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { onMediaError } from "../../lib/mediaRetry";
import { shownLevel } from "../../lib/teacher/level";
import { courseRoute, latestPublished, statusTag } from "../../lib/teacher/status";
import { hubRowView } from "../../lib/teacher/hubStatus";
import { LevelTag } from "./LevelTag";
import { CameraButton, TeacherTop, useToast } from "./common";
import { useTeacherCourses } from "./live";
import { AiKeyPrompt, useAiKey } from "../kit/aiKey";

interface Sending {
  files: number;
  /** 0..1 of the bytes sent */
  frac: number;
  phase: "sending" | "sent" | "error";
}

/** How many of `files` thumbnails show as uploaded at `frac` of the bytes. */
export const uploadedCount = (files: number, frac: number) => Math.min(files, Math.floor(files * frac + 1e-9));

/** gv-01: the whole page is a drop zone; below it, the courses and what Mentor is doing with each. */
export function TeacherHome() {
  const { t } = useTranslation();
  const { token, hub } = useAuth();
  const ai = useAiKey();
  const toast = useToast(3200);
  const { courses, failed, refresh } = useTeacherCourses();
  const [over, setOver] = useState(false);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState<Sending | null>(null);
  const [ask, setAsk] = useState<TeacherCourseSummary | null>(null);
  const [removing, setRemoving] = useState<TeacherCourseSummary | null>(null);
  const noteRef = useRef(note);
  noteRef.current = note;
  const lastFiles = useRef<File[]>([]);
  const pick = useRef<HTMLInputElement>(null);

  const send = useCallback(
    async (files: File[]) => {
      if (!token || !files.length || ai.configured === false) return; // Mentor reads the pages with the AI: the prompt above says so
      lastFiles.current = files;
      setSending({ files: files.length, frac: 0, phase: "sending" });
      try {
        await teacherApi.upload(token, files, noteRef.current.trim() || undefined, (done, total) => setSending({ files: files.length, frac: total ? done / total : 0, phase: "sending" }));
        setSending({ files: files.length, frac: 1, phase: "sent" });
        setNote("");
        refresh();
      } catch {
        setSending({ files: files.length, frac: 0, phase: "error" });
      }
    },
    [token, refresh, ai.configured],
  );
  const sendRef = useRef(send);
  sendRef.current = send;

  // the whole window takes a drop; a file dropped outside the zone must not open in the browser
  useEffect(() => {
    let depth = 0;
    const has = (e: DragEvent) => !!e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files");
    const enter = (e: DragEvent) => {
      if (!has(e)) return;
      e.preventDefault();
      depth++;
      setOver(true);
    };
    const overE = (e: DragEvent) => {
      if (!has(e)) return;
      e.preventDefault();
      setOver(true);
    };
    const leave = () => {
      depth = Math.max(0, depth - 1);
      if (!depth) setOver(false);
    };
    const drop = (e: DragEvent) => {
      if (!has(e)) return;
      e.preventDefault();
      depth = 0;
      setOver(false);
      void sendRef.current(Array.from(e.dataTransfer?.files ?? []));
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", overE);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", overE);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, []);

  // "sent" message goes away on its own
  useEffect(() => {
    if (sending?.phase !== "sent") return;
    const h = setTimeout(() => setSending(null), 45000);
    return () => clearTimeout(h);
  }, [sending]);

  const sent = sending ? uploadedCount(sending.files, sending.frac) : 0;

  return (
    <div className="app">
      <TeacherTop step={1} />
      <main className="main teacher-main">
        {ai.configured === false && <AiKeyPrompt className="aik-bar" />}
        <section className={`drop oli${over ? " is-over" : ""}`} aria-labelledby="drop-h" data-guide="drop" data-guide-label={t("teacher.dropTitle")}>
          <span className="drop-icon">
            <Icon name="upload" />
          </span>
          <h1 id="drop-h">{t("teacher.dropTitle")}</h1>
          <div className="kinds">
            <span>
              <Icon name="camera" />
              {t("teacher.photos")}
            </span>
            <span>
              <Icon name="file" />
              PDF, Word
            </span>
            <span>
              <Icon name="layers" />
              {t("teacher.slides")}
            </span>
            <span>
              <Icon name="video" />
              {t("teacher.video")}
            </span>
            <span>
              <Icon name="volume" />
              {t("teacher.recordings")}
            </span>
          </div>
          <div className="note-field" data-guide="gv-note" data-guide-label={t("gv.noteLabel")}>
            <input id="gv-note" type="text" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} aria-label={t("gv.noteLabel")} placeholder={t("gv.noteLabel")} autoComplete="off" />
          </div>
          <div className="actions">
            <label className="btn btn-primary">
              <Icon name="plus" />
              <span>{t("teacher.choose")}</span>
              <input
                ref={pick}
                className="sr"
                type="file"
                multiple
                accept="image/*,application/pdf,.pdf,.doc,.docx,.ppt,.pptx,video/*,audio/*"
                onChange={(e) => {
                  const f = Array.from(e.target.files ?? []);
                  e.target.value = "";
                  void send(f);
                }}
              />
            </label>
            <CameraButton label={t("gv.takePhotos")} onFiles={(f) => void send(f)} />
          </div>
        </section>

        {sending && (
          <section className="sending" aria-live="polite" data-guide="gv-sending" data-guide-label={t("gv.sending")}>
            <div className="sending-top">
              <h2>{t("gv.received", { files: sending.files })}</h2>
              <span className="muted small">
                {sending.phase === "sent" ? t("gv.uploadedAll", { files: sending.files }) : sending.phase === "error" ? t("gv.uploadFailed") : t("gv.uploading", { done: sent, total: sending.files })}
              </span>
              {sending.phase !== "error" && <span className="muted small">{t("gv.closeOk")}</span>}
            </div>
            <div className="thumbs" role="progressbar" aria-label={t("gv.sending")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(sending.frac * 100)}>
              {Array.from({ length: Math.min(sending.files, 40) }, (_, i) => (
                <span key={i} className={`th${i < (sending.files <= 40 ? sent : Math.floor((sent / sending.files) * 40)) ? "" : " up"}`}>
                  <span className="ok">
                    <Icon name="check" />
                  </span>
                </span>
              ))}
            </div>
            {sending.phase === "error" && (
              <div className="alert">
                <span>{t("gv.uploadFailedLong")}</span>
                <button className="btn btn-ghost" type="button" onClick={() => void send(lastFiles.current)}>
                  {t("gv.retry")}
                </button>
              </div>
            )}
          </section>
        )}

        {courses === null && failed && (
          <div className="alert" role="alert">
            <span>{t("gv.listFailed")}</span>
            <button className="btn btn-ghost" type="button" onClick={refresh}>
              {t("gv.retry")}
            </button>
          </div>
        )}
        {courses && courses.length > 0 && (
          <>
            <div className="head">
              <h2>{t("teacher.yourCourses")}</h2>
            </div>
            <ul className="list" data-guide="teacher-courses" data-guide-label={t("teacher.yourCourses")}>
              {courses.map((c) =>
                hub ? (
                  <HubRow key={c.id} c={c} onDelete={() => setAsk(c)} onRemove={() => setRemoving(c)} onChanged={(msg) => (toast.show(msg), refresh())} />
                ) : (
                  <CourseRow key={c.id} c={c} onDelete={() => setAsk(c)} />
                ),
              )}
            </ul>
          </>
        )}
        {ask && <DeleteAsk c={ask} onClose={() => setAsk(null)} onDone={() => (setAsk(null), refresh())} />}
        {removing && <RemoveAsk c={removing} onClose={() => setRemoving(null)} onDone={() => (setRemoving(null), toast.show(t("lg.hub.course.removedOk")), refresh())} />}
        {toast.node}
      </main>
    </div>
  );
}

/** A course that was never published can be deleted (a stuck or unwanted draft); a published one has students and stays. */
const canDelete = (c: TeacherCourseSummary) => !c.versions.some((v) => v.status === "published");

function DeleteAsk({ c, onClose, onDone }: { c: TeacherCourseSummary; onClose(): void; onDone(): void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  return (
    <Confirm
      name={c.title}
      title={t("lg.gvl.del.title")}
      body={t("lg.gvl.del.body")}
      ok={t("lg.gvl.del.ok")}
      keep={t("lg.gvl.del.keep")}
      failed={t("lg.gvl.del.failed")}
      onClose={onClose}
      onDone={onDone}
      run={() => teacherApi.deleteCourse(token!, c.id)}
    />
  );
}

/** Gỡ (hub on): the live course is unpublished at once; students who downloaded it keep studying. */
function RemoveAsk({ c, onClose, onDone }: { c: TeacherCourseSummary; onClose(): void; onDone(): void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  return (
    <Confirm
      name=""
      title={t("lg.hub.course.removeTitle", { title: c.title })}
      body={t("lg.hub.course.removeBody")}
      ok={t("lg.hub.course.removeOk")}
      keep={t("lg.hub.course.removeKeep")}
      failed={t("lg.hub.course.failed")}
      onClose={onClose}
      onDone={onDone}
      run={() => teacherApi.remove(token!, c.id)}
    />
  );
}

function Confirm({ name, title, body, ok, keep, failed, run, onClose, onDone }: { name: string; title: string; body: string; ok: string; keep: string; failed: string; run(): Promise<void>; onClose(): void; onDone(): void }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(false);
  const keepBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    keepBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const go = async () => {
    if (!token || busy) return;
    setBusy(true);
    setErr(false);
    try {
      await run();
      onDone();
    } catch {
      setErr(true);
      setBusy(false);
    }
  };
  return (
    <div className="gv-ask" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="gv-ask-box" role="alertdialog" aria-modal="true" aria-labelledby="ask-h" aria-describedby="ask-d">
        <h2 id="ask-h">{title}</h2>
        {name && <p className="ask-name">{name}</p>}
        <p id="ask-d" className="muted">
          {body}
        </p>
        {err && (
          <p className="ask-err" role="alert">
            {failed}
          </p>
        )}
        <div className="ask-acts">
          <button ref={keepBtn} type="button" className="btn btn-ghost" onClick={onClose}>
            {keep}
          </button>
          <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void go()}>
            {ok}
          </button>
        </div>
      </div>
    </div>
  );
}

function CourseRow({ c, onDelete }: { c: TeacherCourseSummary; onDelete(): void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const tag = statusTag(c);
  const to = courseRoute(c);
  const tagText = t(tag.key, tag.params);
  const level = c.versions.length ? shownLevel(c) : null; // a level exists once the course has been composed
  const pub = c.status === "published" ? latestPublished(c) : null;
  const cover = c.cover_url || (c.cover_sha256 && token ? coverUrl(token, c.id) : "");
  // a cover that is missing or does not load shows a placeholder, never an empty box
  const failures = useRef(0);
  const [broken, setBroken] = useState(false);
  const onCoverError = (e: SyntheticEvent<HTMLImageElement>) => {
    if (failures.current++ === 0) onMediaError(e); // one retry with a fresh media token
    else setBroken(true);
  };
  const showCover = !!cover && !broken;
  const inner = (
    <>
      <span className={`media${showCover ? "" : " pending"}`} aria-hidden="true">
        {showCover ? <img src={cover} alt="" loading="lazy" onError={onCoverError} /> : <Icon name={c.versions.length ? "layers" : "clock"} />}
      </span>
      <span>
        <h3>{c.title}</h3>
        <span className="sub">
          {level && <LevelTag level={level} />}
          {pub && <span>{t("gv.subPublished", { version: pub.version, students: pub.students })}</span>}
          {c.drive_unsynced && <span className="unsynced">{t("gv.unsynced", { defaultValue: "chưa đồng bộ" })}</span>}
        </span>
      </span>
      <span className={`tag ${tag.tone}`}>{tagText}</span>
    </>
  );
  return (
    <li className="crow">
      {to ? (
        <Link className="row" to={to}>
          {inner}
        </Link>
      ) : (
        <div className="row">{inner}</div>
      )}
      {canDelete(c) && (
        <button type="button" className="icon-btn crow-del" aria-label={t("lg.gvl.del.aria", { title: c.title })} title={t("lg.gvl.del.btn")} onClick={onDelete}>
          <Icon name="trash" />
        </button>
      )}
    </li>
  );
}

/** gv-01 with the hub on: a status chip from `hub.state` and the actions that fit it (Tiếp tục, Rút lại, Sửa, Gỡ). */
function HubRow({ c, onDelete, onRemove, onChanged }: { c: TeacherCourseSummary; onDelete(): void; onRemove(): void; onChanged(msg: string): void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const v = hubRowView(c);
  const to = courseRoute(c);
  const level = c.versions.length ? shownLevel(c) : null;
  const pub = c.status === "published" || c.hub?.live_version != null ? latestPublished(c) : null;
  const cover = c.cover_url || (c.cover_sha256 && token ? coverUrl(token, c.id) : "");
  const failures = useRef(0);
  const [broken, setBroken] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const onCoverError = (e: SyntheticEvent<HTMLImageElement>) => {
    if (failures.current++ === 0) onMediaError(e);
    else setBroken(true);
  };
  const showCover = !!cover && !broken;
  const withdraw = async () => {
    if (!token || busy) return;
    setBusy(true);
    setFailed(false);
    try {
      await teacherApi.withdraw(token, c.id);
      onChanged(t("lg.hub.course.withdrawn"));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  const canTrash = canDelete(c) && (!c.hub || c.hub.state === "rut_lai");
  return (
    <li className="crow hub-crow">
      <span className={`media${showCover ? "" : " pending"}`} aria-hidden="true">
        {showCover ? <img src={cover} alt="" loading="lazy" onError={onCoverError} /> : <Icon name={c.versions.length ? "layers" : "clock"} />}
      </span>
      <span className="hub-main">
        <h3>{to ? <Link to={to}>{c.title}</Link> : c.title}</h3>
        <span className="sub">
          {level && <LevelTag level={level} />}
          {pub && <span>{t("gv.subPublished", { version: pub.version, students: pub.students })}</span>}
          {c.drive_unsynced && <span className="unsynced">{t("gv.unsynced", { defaultValue: "chưa đồng bộ" })}</span>}
        </span>
      </span>
      <span className="hub-side">
        <span className="hub-chips">
          {v.chips.map((chip) => (
            <span key={chip.key} className={`tag ${chip.tone}`}>
              {t(chip.key, chip.params)}
            </span>
          ))}
        </span>
        {v.actions.map((a) => {
          if (a === "continue" || a === "edit")
            return to ? (
              <Link key={a} className={"hub-act" + (a === "continue" ? " go" : "")} to={to} aria-label={t(a === "continue" ? "lg.hub.course.continueAria" : "lg.hub.course.editAria", { title: c.title })}>
                {t(a === "continue" ? "lg.hub.course.continue" : "lg.hub.course.edit")}
              </Link>
            ) : null;
          if (a === "withdraw")
            return (
              <button key={a} type="button" className="hub-act" disabled={busy} aria-label={t("lg.hub.course.withdrawAria", { title: c.title })} onClick={() => void withdraw()}>
                {t("lg.hub.course.withdraw")}
              </button>
            );
          return (
            <button key={a} type="button" className="hub-act del" aria-label={t("lg.hub.course.removeAria", { title: c.title })} onClick={onRemove}>
              {t("lg.hub.course.remove")}
            </button>
          );
        })}
        {canTrash && (
          <button type="button" className="icon-btn crow-del" aria-label={t("lg.gvl.del.aria", { title: c.title })} title={t("lg.gvl.del.btn")} onClick={onDelete}>
            <Icon name="trash" />
          </button>
        )}
      </span>
      {v.why && <span className="hub-why">{v.why}</span>}
      {v.oldVersion && <span className="hub-warn">{t("lg.hub.course.oldVersion")}</span>}
      {failed && (
        <span className="hub-why" role="alert">
          {t("lg.hub.course.failed")}
        </span>
      )}
    </li>
  );
}
