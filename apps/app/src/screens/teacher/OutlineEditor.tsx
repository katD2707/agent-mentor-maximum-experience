import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BuildState, Outline, OutlineOp, TeacherTest } from "../../api";
import { Icon } from "../../components/Icon";
import { buildStateInfo } from "../../lib/teacher/status";
import { STEP_ICON, type StepKind } from "../../lib/teacher/steps";
import { addLessonOp, deleteOp, dropIndex, locate, moveLessonOps, renameOp, stepLessonOps } from "../../lib/teacher/outline";

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

/** What the built pack says about the tree rows (absent before the lessons are composed). */
export interface TreeMeta {
  lessons: ReadonlyMap<string, { steps: number; minutes: number; kinds: StepKind[]; unsure: number }>;
  recapMinutes: ReadonlyMap<string, number>;
  /** quiz items per level 1..4 */
  levels: number[] | null;
  tests: TeacherTest[];
}

export interface OutlineEditorProps {
  /** step counts, step icons, practice levels and tests (gv-02) */
  meta?: TreeMeta | null;
  outline: Outline;
  /** false while Mentor is composing: shown, not editable */
  editable: boolean;
  /** while composing: each lesson's state, shown as an icon on its row */
  states?: ReadonlyMap<string, BuildState>;
  /** send these ops; the parent applies them to its copy at once and queues the PUT */
  onOps(ops: OutlineOp[]): void;
  /** like onOps for the ops that need the server's answer (new ids); resolves to the ids of lessons that are new */
  onAdd(ops: OutlineOp[]): Promise<string[]>;
}

const STATE_ICON = { done: "check", now: "refresh", wait: "clock", err: "flag" } as const;

/** The editable chapter/lesson tree (gv-02): chapters fold open to lessons, one line each. */
export function OutlineEditor({ outline, editable, states, onOps, onAdd, meta }: OutlineEditorProps) {
  const { t } = useTranslation();
  const [drag, setDrag] = useState<string | null>(null);
  const [mark, setMark] = useState<{ chapter: string; before: string | null } | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [live, setLive] = useState("");
  const number = new Map(outline.chapters.flatMap((c) => c.lessons).map((l, i) => [l.id, i + 1]));
  const total = number.size;
  const [folded, setFolded] = useState<ReadonlySet<string>>(new Set());
  const fold = (id: string) =>
    setFolded((f) => {
      const n = new Set(f);
      if (!n.delete(id)) n.add(id);
      return n;
    });

  const move = (id: string, ops: OutlineOp[] | null) => {
    if (!ops) return;
    onOps(ops);
    const next = outline; // announced against the old numbering, then the new one after the re-render
    setLive(t("gv.moved", { title: next.chapters.flatMap((c) => c.lessons).find((l) => l.id === id)?.title ?? "" }));
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-handle="${CSS.escape(id)}"]`)?.focus());
  };

  const addLesson = async (chapter: string, after?: string) => {
    setFolded((f) => {
      const n = new Set(f);
      n.delete(chapter);
      return n;
    });
    const ids = await onAdd([addLessonOp(chapter, t("gv.newLesson"), after)]);
    if (ids[0]) setFocusId(ids[0]);
  };
  const addChapter = async () => {
    await onAdd([{ op: "add_chapter", title: t("gv.newChapter") }]);
  };

  return (
    <div className="outline oli" id="outline" role="group" aria-label={t("gv.outlineTitle")} data-guide="gv-outline" data-guide-label={t("gv.outlineTitle")}>
      <p className="sr" role="status" aria-live="polite">
        {live}
      </p>
      <details className="tg" open>
        <summary>
          <Icon name="chev" />
          <span className="tname">{t("gv.treeLessons")}</span>
          <span className="tcnt">{total}</span>
        </summary>
      {outline.chapters.map((ch) => (
        <section className="grp" key={ch.id} data-fold={folded.has(ch.id) ? "1" : "0"}>
          <div className="ghead">
            <button type="button" className="fold" aria-expanded={!folded.has(ch.id)} aria-label={t("gv.foldChapter")} onClick={() => fold(ch.id)}>
              <Icon name="chev" />
            </button>
            <h2 className="ctitle">
              <TitleInput value={ch.title} label={t("gv.chapterName")} locked={!editable} onSave={(v) => onOps([renameOp(ch.id, v)])} />
            </h2>
            {editable ? (
              <button type="button" className="gadd" aria-label={t("gv.addLesson")} onClick={() => void addLesson(ch.id, ch.lessons[ch.lessons.length - 1]?.id)}>
                <Icon name="plus" />
              </button>
            ) : (
              <span />
            )}
          </div>
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
                className={`gv-lesson${states?.has(l.id) ? ` s-${buildStateInfo(states.get(l.id)!).tone}` : ""}${drag === l.id ? " dragging" : ""}${mark?.chapter === ch.id && mark.before === l.id ? " drop-before" : ""}`}
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
                <span className="no">{number.get(l.id)}</span>
                <TitleInput value={l.title} label={t("gv.lessonName", { n: number.get(l.id) })} locked={!editable} autoFocus={focusId === l.id} onSave={(v) => onOps([renameOp(l.id, v)])} />
                {meta?.lessons.get(l.id) &&
                  (() => {
                    const m = meta.lessons.get(l.id)!;
                    return (
                      <span className="fmt" title={t("gv.openLesson")}>
                        <span className="meta">{t("gv.stepsMeta", { n: m.steps, m: m.minutes })}</span>
                        <span className="kinds" aria-hidden="true">
                          {Array.from(new Set(m.kinds)).map((k) => (
                            <Icon key={k} name={STEP_ICON[k]} />
                          ))}
                        </span>
                        {m.unsure > 0 && <span className="warn" role="img" aria-label={t("gv.unsureN", { n: m.unsure })} title={t("gv.unsureN", { n: m.unsure })} />}
                      </span>
                    );
                  })()}
                {states?.has(l.id) &&
                  (() => {
                    const info = buildStateInfo(states.get(l.id)!);
                    return (
                      <span className={`st ${info.tone}`} role="img" aria-label={t(info.key)} title={t(info.key)}>
                        <Icon name={STATE_ICON[info.tone]} />
                      </span>
                    );
                  })()}
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
            {meta?.recapMinutes.has(ch.id) && (
              <li className="ext">
                <Icon name="volume" />
                <span>{t("gv.listenRow", { m: meta.recapMinutes.get(ch.id) })}</span>
              </li>
            )}
          </ol>
        </section>
      ))}
      </details>
      <details className="tg" open>
        <summary>
          <Icon name="chev" />
          <span className="tname">{t("gv.treePractice")}</span>
          <span className="tcnt">4</span>
        </summary>
        <div className="tbody">
          {[1, 2, 3, 4].map((lv) => (
            <div className="row" key={lv}>
              <span className="no">{lv}</span>
              <span className="nm">{t(`gv.levelName.${lv}`)}</span>
              <span className="ct">{meta?.levels ? t("gv.qCount", { n: meta.levels[lv - 1] ?? 0 }) : ""}</span>
            </div>
          ))}
        </div>
      </details>
      {meta && meta.tests.length > 0 && (
        <details className="tg" open>
          <summary>
            <Icon name="chev" />
            <span className="tname">{t("gv.treeTests")}</span>
            <span className="tcnt">{meta.tests.length}</span>
          </summary>
          <div className="tbody">
            {meta.tests.map((x) => (
              <div className="row" key={x.profile_id}>
                <Icon name="quiz" />
                <span className="nm">{x.title}</span>
                <span className="ct">{t("gv.testMeta", { n: x.items, m: x.minutes })}</span>
              </div>
            ))}
          </div>
        </details>
      )}
      {editable && (
        <button type="button" className="btn btn-quiet gv-add" onClick={() => void addChapter()}>
          <Icon name="plus" />
          <span>{t("gv.addChapter")}</span>
        </button>
      )}
    </div>
  );
}
