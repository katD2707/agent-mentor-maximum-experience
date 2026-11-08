import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Outline, OutlineOp } from "../../api";
import { Icon } from "../../components/Icon";
import { addLessonOp, deleteOp, dropIndex, lessonCount, locate, moveLessonOps, renameOp, stepLessonOps, totalMinutes } from "../../lib/teacher/outline";

/** A title you click to rename: Enter saves, Escape puts the old one back, leaving the field saves. */
function TitleInput({ value, label, onSave, locked, autoFocus, className }: { value: string; label: string; onSave(v: string): void; locked: boolean; autoFocus?: boolean; className?: string }) {
  const [draft, setDraft] = useState(value);
  const focused = useRef(false);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!focused.current) setDraft(value);
  }, [value]);
  useEffect(() => {
    if (autoFocus) {
      ref.current?.focus();
      ref.current?.select();
    }
  }, [autoFocus]);
  const commit = () => {
    focused.current = false;
    const v = draft.trim();
    if (!v) setDraft(value);
    else if (v !== value) onSave(v);
  };
  return (
    <input
      ref={ref}
      className={`inline-edit ${className ?? ""}`}
      value={draft}
      aria-label={label}
      readOnly={locked}
      spellCheck={false}
      maxLength={160}
      onFocus={() => (focused.current = true)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          e.currentTarget.blur();
        } else if (e.key === "Escape") {
          setDraft(value);
          e.currentTarget.blur();
        }
      }}
    />
  );
}

export interface OutlineEditorProps {
  outline: Outline;
  /** false while Mentor is composing: shown, not editable */
  editable: boolean;
  /** send these ops; the parent applies them to its copy at once and queues the PUT */
  onOps(ops: OutlineOp[]): void;
  /** like onOps for the ops that need the server's answer (new ids); resolves to the ids of lessons that are new */
  onAdd(ops: OutlineOp[]): Promise<string[]>;
}

/** The editable chapter/lesson tree inside the chat (gv-02). */
export function OutlineEditor({ outline, editable, onOps, onAdd }: OutlineEditorProps) {
  const { t } = useTranslation();
  const [drag, setDrag] = useState<string | null>(null);
  const [mark, setMark] = useState<{ chapter: string; before: string | null } | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [live, setLive] = useState("");
  const number = new Map(outline.chapters.flatMap((c) => c.lessons).map((l, i) => [l.id, i + 1]));
  const total = lessonCount(outline);

  const move = (id: string, ops: OutlineOp[] | null) => {
    if (!ops) return;
    onOps(ops);
    const next = outline; // announced against the old numbering, then the new one after the re-render
    setLive(t("gv.moved", { title: next.chapters.flatMap((c) => c.lessons).find((l) => l.id === id)?.title ?? "" }));
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-handle="${CSS.escape(id)}"]`)?.focus());
  };

  const addLesson = async (chapter: string, after?: string) => {
    const ids = await onAdd([addLessonOp(chapter, t("gv.newLesson"), after)]);
    if (ids[0]) setFocusId(ids[0]);
  };
  const addChapter = async () => {
    await onAdd([{ op: "add_chapter", title: t("gv.newChapter") }]);
  };

  return (
    <div className="outline oli" data-guide="gv-outline" data-guide-label={t("gv.outlineTitle")}>
      {editable && <p className="hint">{t("gv.outlineHint")}</p>}
      <p className="sr" role="status" aria-live="polite">
        {live}
      </p>
      {outline.chapters.map((ch) => (
        <div className="chapter" key={ch.id}>
          <h2>
            <TitleInput value={ch.title} label={t("gv.chapterName")} locked={!editable} onSave={(v) => onOps([renameOp(ch.id, v)])} />
          </h2>
          <ol
            className="gv-lessons"
            onDragOver={(e) => {
              if (!drag || e.target !== e.currentTarget) return;
              e.preventDefault();
              setMark({ chapter: ch.id, before: null });
            }}
            onDrop={(e) => {
              if (!drag || e.target !== e.currentTarget) return;
              e.preventDefault();
              move(drag, moveLessonOps(outline, drag, ch.id, dropIndex(outline, drag, ch.id, null)));
              setDrag(null);
              setMark(null);
            }}
          >
            {ch.lessons.map((l, i) => (
              <li
                key={l.id}
                className={`gv-lesson${drag === l.id ? " dragging" : ""}${mark?.chapter === ch.id && mark.before === l.id ? " drop-before" : ""}`}
                onDragStart={(e) => {
                  setDrag(l.id);
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData("text/plain", l.id);
                }}
                onDragEnd={(e) => {
                  e.currentTarget.draggable = false;
                  setDrag(null);
                  setMark(null);
                }}
                onDragOver={(e) => {
                  if (!drag || drag === l.id) return;
                  e.preventDefault();
                  const r = e.currentTarget.getBoundingClientRect();
                  const lower = e.clientY > r.top + r.height / 2;
                  setMark({ chapter: ch.id, before: lower ? (ch.lessons[i + 1]?.id ?? null) : l.id });
                }}
                onDrop={(e) => {
                  if (!drag) return;
                  e.preventDefault();
                  const before = mark?.chapter === ch.id ? mark.before : l.id;
                  move(drag, moveLessonOps(outline, drag, ch.id, dropIndex(outline, drag, ch.id, before === drag ? l.id : before)));
                  setDrag(null);
                  setMark(null);
                }}
              >
                {editable && (
                  <button
                    type="button"
                    className="handle"
                    data-handle={l.id}
                    aria-label={t("gv.dragHandle", { n: number.get(l.id) })}
                    title={t("gv.dragHandleTip")}
                    onPointerDown={(e) => {
                      if (e.pointerType !== "touch") (e.currentTarget.closest("li") as HTMLElement).draggable = true;
                    }}
                    onPointerUp={(e) => ((e.currentTarget.closest("li") as HTMLElement).draggable = false)}
                    onKeyDown={(e) => {
                      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
                      e.preventDefault();
                      move(l.id, stepLessonOps(outline, l.id, e.key === "ArrowUp" ? -1 : 1));
                    }}
                  >
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
                      <circle cx="9" cy="6" r="1.6" />
                      <circle cx="15" cy="6" r="1.6" />
                      <circle cx="9" cy="12" r="1.6" />
                      <circle cx="15" cy="12" r="1.6" />
                      <circle cx="9" cy="18" r="1.6" />
                      <circle cx="15" cy="18" r="1.6" />
                    </svg>
                  </button>
                )}
                <span className="num">{t("gv.lessonN", { n: number.get(l.id) })}</span>
                <TitleInput value={l.title} label={t("gv.lessonName", { n: number.get(l.id) })} locked={!editable} autoFocus={focusId === l.id} onSave={(v) => onOps([renameOp(l.id, v)])} />
                <span className="meta">
                  {!l.grounded && <span className="tag wait">{t("gv.addedByYou")}</span>}
                  <span className="mins">{t("courses.minutes", { count: l.est_minutes })}</span>
                </span>
                {editable && (
                  <button
                    type="button"
                    className="del"
                    aria-label={t("gv.deleteLesson", { n: number.get(l.id) })}
                    disabled={total <= 1}
                    onClick={() => {
                      const at = locate(outline, l.id);
                      if (at) onOps([deleteOp(l.id)]);
                    }}
                  >
                    <Icon name="trash" />
                  </button>
                )}
              </li>
            ))}
          </ol>
          {editable && (
            <button type="button" className="btn btn-quiet gv-add" onClick={() => void addLesson(ch.id, ch.lessons[ch.lessons.length - 1]?.id)}>
              <Icon name="plus" />
              <span>{t("gv.addLesson")}</span>
            </button>
          )}
        </div>
      ))}
      <div className="outline-foot">
        <span className="muted small">{t("gv.outlineSummary", { chapters: outline.chapters.length, lessons: total, minutes: totalMinutes(outline) })}</span>
        {editable && (
          <button type="button" className="btn btn-quiet gv-add" onClick={() => void addChapter()}>
            <Icon name="plus" />
            <span>{t("gv.addChapter")}</span>
          </button>
        )}
      </div>
    </div>
  );
}
