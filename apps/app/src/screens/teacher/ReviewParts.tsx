import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { CommentAnchor, VideoBlock } from "../../api";
import { Icon } from "../../components/Icon";
import { commentStatusInfo } from "../../lib/teacher/status";
import { fmtTime, pointAnchor, timeAnchor } from "../../lib/teacher/anchors";
import type { Numbered } from "../../lib/teacher/comments";

export interface Draft {
  block_id: string;
  anchor: CommentAnchor;
  /** where the popover opens (viewport coordinates) */
  x: number;
  y: number;
}


// ---------------------------------------------------------------- the box where the comment is typed
export function CommentPop({ draft, onSend, onCancel, busy }: { draft: Draft; onSend(body: string): void; onCancel(): void; busy: boolean }) {
  const { t } = useTranslation();
  const [body, setBody] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const a = draft.anchor;
  const left = Math.max(8, Math.min(draft.x - 170, window.innerWidth - 348));
  const top = Math.min(draft.y + 8, Math.max(8, window.innerHeight - 260));
  return (
    <form
      className="pop"
      style={{ "--px": `${left}px`, "--py": `${top}px` } as React.CSSProperties}
      aria-label={t("gv.commentTitle")}
      data-guide="gv-comment-box"
      data-guide-label={t("gv.commentTitle")}
      onSubmit={(e) => {
        e.preventDefault();
        if (body.trim() && !busy) onSend(body.trim());
      }}
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
    >
      {a.kind === "text" && <q>{a.quote}</q>}
      {a.kind === "time" && (
        <p className="pop-m">
          <Icon name="video" />
          {t("gv.atTime", { time: fmtTime(a.t) })}
        </p>
      )}
      {a.kind === "point" && (
        <p className="pop-m">
          <Icon name="image" />
          {t("gv.atPoint")}
        </p>
      )}
      <textarea ref={ref} value={body} onChange={(e) => setBody(e.target.value)} placeholder={t("gv.commentPlaceholder")} aria-label={t("gv.commentTitle")} />
      <div className="acts">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          {t("gv.cancel")}
        </button>
        <button className="btn btn-primary" type="submit" disabled={!body.trim() || busy}>
          {t("gv.send")}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- video: pause, comment at that second
export function VideoBar({ block, slot, notes, active, onComment, onPick }: { block: VideoBlock; slot: React.RefObject<HTMLDivElement | null>; notes: Numbered[]; active: string | null; onComment(a: CommentAnchor, rect: DOMRect): void; onPick(id: string): void }) {
  const { t } = useTranslation();
  const [vid, setVid] = useState<HTMLVideoElement | null>(null);
  const [time, setTime] = useState(0);
  const btn = useRef<HTMLButtonElement>(null);
  const len = Math.max(1, block.duration_s);

  // the <video> comes and goes (the student player shows a placeholder when the file is missing)
  useEffect(() => {
    const el = slot.current;
    if (!el) return;
    const find = () => setVid(el.querySelector("video"));
    find();
    const mo = new MutationObserver(find);
    mo.observe(el, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [slot]);
  useEffect(() => {
    if (!vid) return;
    const on = () => setTime(vid.currentTime);
    const evs = ["timeupdate", "seeked", "pause", "loadedmetadata"] as const;
    evs.forEach((e) => vid.addEventListener(e, on));
    return () => evs.forEach((e) => vid.removeEventListener(e, on));
  }, [vid]);

  const at = time;
  return (
    <div className="vreview" data-guide="gv-video-comment" data-guide-label={t("gv.videoBar")}>
      <div className="vtrack">
        {!vid ? (
          <input type="range" min={0} max={Math.round(len)} step={1} value={Math.round(time)} onChange={(e) => setTime(Number(e.target.value))} aria-label={t("gv.videoPos")} />
        ) : (
          <span className="vline" aria-hidden="true">
            <i style={{ width: `${Math.min(100, (time / len) * 100)}%` }} />
          </span>
        )}
        {notes.map((n) => (
          <button key={n.id} type="button" className={`vmark${n.status === "applied" ? " fixed" : ""}${active === n.id ? " active" : ""}`} style={{ left: `${Math.min(100, ((n.anchor.kind === "time" ? n.anchor.t : 0) / len) * 100)}%` }} aria-label={t("gv.noteAria", { n: n.n })} onClick={() => onPick(n.id)}>
            {n.n}
          </button>
        ))}
      </div>
      <span className="vtime" aria-live="off">
        {fmtTime(at)} / {fmtTime(len)}
      </span>
      <button
        ref={btn}
        className="btn btn-ghost vcmt"
        type="button"
        onClick={() => {
          vid?.pause();
          onComment(timeAnchor(vid ? vid.currentTime : time), btn.current!.getBoundingClientRect());
        }}
      >
        <Icon name="comment" />
        <span>{t("gv.commentAt", { time: fmtTime(at) })}</span>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- image: tap a spot to pin a comment
export function PinLayer({ slot, notes, active, pending, onComment, onPick }: { slot: React.RefObject<HTMLDivElement | null>; notes: Numbered[]; active: string | null; pending: CommentAnchor | null; onComment(a: CommentAnchor, rect: DOMRect): void; onPick(id: string): void }) {
  const { t } = useTranslation();
  const [box, setBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const layer = useRef<HTMLDivElement>(null);

  // follow the picture: it loads late and resizes with the window
  useEffect(() => {
    const s = slot.current;
    if (!s) return;
    const measure = () => {
      const target = s.querySelector<HTMLElement>(".blk-image img, .blk-image .ph");
      if (!target) return setBox(null);
      const a = s.getBoundingClientRect();
      const b = target.getBoundingClientRect();
      setBox((o) => (o && o.left === b.left - a.left && o.top === b.top - a.top && o.width === b.width && o.height === b.height ? o : { left: b.left - a.left, top: b.top - a.top, width: b.width, height: b.height }));
    };
    measure();
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    ro?.observe(s);
    s.addEventListener("load", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      ro?.disconnect();
      s.removeEventListener("load", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [slot]);

  if (!box) return null;
  const pin = (a: CommentAnchor | undefined) => (a && a.kind === "point" ? { left: `${a.x * 100}%`, top: `${a.y * 100}%` } : undefined);
  return (
    <div
      ref={layer}
      className="pin-layer"
      style={box}
      role="button"
      tabIndex={0}
      aria-label={t("gv.pinHint")}
      data-guide="gv-image-pin"
      data-guide-label={t("gv.pinHint")}
      onClick={(e) => {
        if (e.target !== e.currentTarget) return;
        onComment(pointAnchor(e.currentTarget.getBoundingClientRect(), e.clientX, e.clientY), new DOMRect(e.clientX, e.clientY, 0, 0));
      }}
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        const r = e.currentTarget.getBoundingClientRect();
        onComment(pointAnchor(r, r.left + r.width / 2, r.top + r.height / 2), new DOMRect(r.left + r.width / 2, r.top + r.height / 2, 0, 0));
      }}
    >
      {notes.map((n) => (
        <button key={n.id} type="button" className={`ipin${n.status === "applied" ? " fixed" : ""}${active === n.id ? " active" : ""}`} style={pin(n.anchor)} aria-label={t("gv.noteAria", { n: n.n })} onClick={() => onPick(n.id)}>
          {n.n}
        </button>
      ))}
      {pending?.kind === "point" && <span className="ipin pending" style={pin(pending)} aria-hidden="true" />}
    </div>
  );
}

// ---------------------------------------------------------------- the red-pen margin
export function Notes({ notes, active, onPick, others }: { notes: Numbered[]; active: string | null; onPick(n: Numbered): void; others: number }) {
  const { t } = useTranslation();
  return (
    <aside className="panel" aria-labelledby="notes-h" data-guide="gv-comments" data-guide-label={t("gv.yourComments")}>
      <h2 id="notes-h">{t("gv.yourComments")}</h2>
      {notes.length === 0 && <p className="muted small">{t("gv.noComments")}</p>}
      <ul className="notes">
        {notes.map((n) => {
          const s = commentStatusInfo(n.status);
          return (
            <li key={n.id} id={`note-${n.id}`} className={`gv-notecard${s.fixed ? " fixed" : ""}${s.failed ? " failed" : ""}${active === n.id ? " active" : ""}`}>
              <button type="button" className="note-btn" onClick={() => onPick(n)}>
                <span className="top">
                  <span className="n">{n.n}</span>
                  <span className="where">{n.anchor.kind === "text" ? t("gv.whereText") : n.anchor.kind === "time" ? t("gv.whereVideo", { time: fmtTime(n.anchor.t) }) : t("gv.wherePoint")}</span>
                  <span className={`tag ${s.fixed ? "ok" : s.failed ? "err" : "wait"}`}>{t(s.key)}</span>
                </span>
                {n.anchor.kind === "text" && <q>{n.anchor.quote}</q>}
                <span className="said">{n.body}</span>
                {n.note && <span className="done-txt">{n.note}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      {others > 0 && <p className="muted small">{t("gv.otherLessons", { notes: others })}</p>}
    </aside>
  );
}
