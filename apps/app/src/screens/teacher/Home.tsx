import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { coverUrl, teacherApi, type TeacherCourseSummary } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { onMediaError } from "../../lib/mediaRetry";
import { shownLevel } from "../../lib/teacher/level";
import { courseRoute, statusTag } from "../../lib/teacher/status";
import { LevelTag } from "./LevelPicker";
import { CameraButton, TeacherTop, useLangText } from "./common";
import { useTeacherCourses } from "./live";

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
  const { token } = useAuth();
  const { courses, failed, refresh } = useTeacherCourses();
  const [over, setOver] = useState(false);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState<Sending | null>(null);
  const noteRef = useRef(note);
  noteRef.current = note;
  const lastFiles = useRef<File[]>([]);
  const pick = useRef<HTMLInputElement>(null);

  const send = useCallback(
    async (files: File[]) => {
      if (!token || !files.length) return;
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
    [token, refresh],
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
      <TeacherTop />
      <main className="main teacher-main">
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
            <label htmlFor="gv-note">{t("gv.noteLabel")}</label>
            <input id="gv-note" type="text" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder={t("gv.notePlaceholder")} autoComplete="off" />
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
          <p className="promise">{t("teacher.promise")}</p>
        </section>

        {sending && (
          <section className="sending" aria-live="polite" data-guide="gv-sending" data-guide-label={t("gv.sending")}>
            <div className="sending-top">
              <h2>{t("gv.received", { files: sending.files })}</h2>
              <span className="muted small">
                {sending.phase === "sent" ? t("gv.uploadedAll", { files: sending.files }) : sending.phase === "error" ? t("gv.uploadFailed") : t("gv.uploading", { done: sent, total: sending.files })}
              </span>
            </div>
            <div className="gv-bar" role="progressbar" aria-label={t("gv.sending")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(sending.frac * 100)}>
              <i style={{ width: `${Math.round(sending.frac * 100)}%` }} />
            </div>
            <div className="thumbs" aria-hidden="true">
              {Array.from({ length: Math.min(sending.files, 40) }, (_, i) => (
                <span key={i} className={`th${i < (sending.files <= 40 ? sent : Math.floor((sent / sending.files) * 40)) ? "" : " up"}`}>
                  <span className="ok">
                    <Icon name="check" />
                  </span>
                </span>
              ))}
            </div>
            {sending.phase === "error" ? (
              <div className="alert">
                <span>{t("gv.uploadFailedLong")}</span>
                <button className="btn btn-ghost" type="button" onClick={() => void send(lastFiles.current)}>
                  {t("gv.retry")}
                </button>
              </div>
            ) : (
              <div className="close-ok">
                <Icon name="check" />
                <span>{t("gv.closeOk")}</span>
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
              {courses.map((c) => (
                <CourseRow key={c.id} c={c} />
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  );
}

function CourseRow({ c }: { c: TeacherCourseSummary }) {
  const { t } = useTranslation();
  const lt = useLangText();
  const { token } = useAuth();
  const tag = statusTag(c);
  const to = courseRoute(c);
  const tagText = t(tag.key, tag.params);
  const line = lt(c.status_line_vi, c.status_line_en);
  const level = c.versions.length ? shownLevel(c) : null; // a level exists once the course has been composed
  const cover = c.cover_url || (c.cover_sha256 && token ? coverUrl(token, c.id) : "");
  const inner = (
    <>
      <span className={`media${cover ? "" : " pending"}`} aria-hidden="true">
        {cover ? <img src={cover} alt="" loading="lazy" onError={onMediaError} /> : <Icon name="clock" />}
      </span>
      <span>
        <h3>{c.title}</h3>
        <span className="sub">
          {level && <LevelTag level={level} />}
          {line !== tagText && line}
        </span>
      </span>
      <span className={`tag ${tag.tone}`}>{tagText}</span>
      {to ? <Icon name="next" className="go" /> : <span />}
    </>
  );
  return <li>{to ? <Link className="row" to={to}>{inner}</Link> : <div className="row">{inner}</div>}</li>;
}
