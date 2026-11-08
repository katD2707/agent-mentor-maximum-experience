import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AskCard, TreeChapter } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { enrollCourse } from "../../lib/enrollCourse";
import { CourseCover, formatMinutes, LangTag, MediaIcons } from "../courses/common";

export type AddState = "idle" | "adding" | "added";

export const treeOf = (c: AskCard): TreeChapter[] => (Array.isArray(c.tree) ? c.tree : (c.tree?.tree ?? []));

/** "+ Thêm" for the course cards: enroll (and start the download), remembering what was added in this thread. */
export function useAddCourse(onAdded: (card: AskCard) => void, onFailed: () => void) {
  const { token, user } = useAuth();
  const [added, setAdded] = useState<Record<string, AddState>>({});
  const live = useRef(true);
  useEffect(() => {
    live.current = true; // StrictMode runs the cleanup once before the real mount
    return () => void (live.current = false);
  }, []);

  const stateOf = (c: AskCard): AddState => added[c.course_id] ?? (c.enrolled ? "added" : "idle");

  const add = useCallback(
    async (c: AskCard): Promise<boolean> => {
      if (!token || !user) return false;
      setAdded((m) => ({ ...m, [c.course_id]: "adding" }));
      try {
        await enrollCourse(token, user.id, c.course_id);
        if (live.current) setAdded((m) => ({ ...m, [c.course_id]: "added" }));
        onAdded(c);
        return true;
      } catch {
        if (live.current) setAdded((m) => ({ ...m, [c.course_id]: "idle" }));
        onFailed();
        return false;
      }
    },
    [token, user, onAdded, onFailed],
  );
  return { stateOf, add };
}
export type AddCourse = ReturnType<typeof useAddCourse>;

export function AddButton({ card, adder }: { card: AskCard; adder: AddCourse }) {
  const { t } = useTranslation();
  const s = adder.stateOf(card);
  if (card.status === "coming_soon")
    return (
      <button className="add" type="button" disabled aria-label={`${t("courses.soon")}: ${card.title}`}>
        <Icon name="clock" />
        <span>{t("courses.soon")}</span>
      </button>
    );
  return (
    <button
      className="add"
      type="button"
      aria-pressed={s === "added"}
      disabled={s !== "idle"}
      aria-label={`${s === "added" ? t("ask.courses.added") : t("ask.courses.add")}: ${card.title}`}
      onClick={() => void adder.add(card)}
    >
      <Icon name={s === "added" ? "check" : "plus"} />
      <span>{s === "added" ? t("ask.courses.added") : s === "adding" ? t("ask.courses.adding") : t("ask.courses.add")}</span>
    </button>
  );
}

export function CourseCards({
  items,
  startWith,
  suggestedAllAges,
  adder,
  onOpen,
}: {
  items: AskCard[];
  startWith: { course_id: string } | null;
  suggestedAllAges: boolean;
  adder: AddCourse;
  onOpen(c: AskCard): void;
}) {
  const { t } = useTranslation();
  return (
    <div className="sug-wrap" data-guide="ask-courses" data-guide-label={t("hub.courses")}>
      {suggestedAllAges && <p className="small muted">{t("ask.courses.other")}</p>}
      <ul className="sugs">
        {items.map((c) => (
          <li className="sug" key={c.course_id}>
            <button className="open" type="button" onClick={() => onOpen(c)} aria-label={t("ask.courses.open", { title: c.title })}>
              <CourseCover courseId={c.course_id} className="ask-thumb" />
              <span className="txt">
                <span className="ttl">{c.title}</span>
                <span className="by">
                  {t("courses.lessons", { count: c.lessons_count })}, {t("courses.about", { t: formatMinutes(t, c.est_minutes) })} <LangTag lang={c.language} />
                  {startWith?.course_id === c.course_id && <span className="tag ok">{t("ask.courses.startHere")}</span>}
                </span>
                <span className="line">{c.description_short}</span>
              </span>
            </button>
            <AddButton card={c} adder={adder} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Course as a tree (chapters, lessons, key ideas) with its short description; a side sheet on desktop, a bottom sheet on phones. */
export function CourseSheet({ card, adder, onClose, onStart, starting }: { card: AskCard; adder: AddCourse; onClose(): void; onStart(c: AskCard): void; starting: boolean }) {
  const { t } = useTranslation();
  const close = useRef<HTMLButtonElement>(null);
  const tree = treeOf(card);

  useEffect(() => {
    close.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="ask-sheet" role="dialog" aria-modal="true" aria-labelledby="ask-sheet-title" data-guide="course-tree" data-guide-label={t("ask.sheet.tree")}>
        <header className="sheet-head">
          <h2 id="ask-sheet-title">{card.title}</h2>
          <button className="icon-btn" type="button" ref={close} onClick={onClose} aria-label={t("ask.sheet.close")}>
            <Icon name="x" />
          </button>
          <span className="by">
            {t("courses.lessons", { count: card.lessons_count })}, {t("courses.about", { t: formatMinutes(t, card.est_minutes) })} <LangTag lang={card.language} />
          </span>
        </header>
        <div className="sheet-body">
          <figure className="sheet-cover">
            <CourseCover courseId={card.course_id} />
          </figure>
          <p className="about">{card.description_short}</p>
          {tree.length > 0 && (
            <section aria-label={t("ask.sheet.tree")}>
              <h3 className="sub-h">{t("ask.sheet.tree")}</h3>
              <div className="tree">
                {tree.map((ch, ci) => (
                  <details key={ch.id} open={ci === 0 || tree.length <= 2}>
                    <summary>{ch.title}</summary>
                    <ol className="lessons">
                      {ch.lessons.map((l) => (
                        <li key={l.id}>
                          <div className="lesson-main">
                            <span className="lesson-title">{l.title}</span>
                            {l.key_ideas?.length > 0 && (
                              <ul className="ideas">
                                {l.key_ideas.map((k) => (
                                  <li key={k}>{k}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                          <span className="kinds">
                            <MediaIcons media={l.media} />
                          </span>
                        </li>
                      ))}
                    </ol>
                  </details>
                ))}
              </div>
            </section>
          )}
        </div>
        <footer className="sheet-foot">
          {card.first_lesson && (
            <button className="btn btn-primary" type="button" disabled={starting} onClick={() => onStart(card)}>
              <Icon name="play" />
              <span>{starting ? t("ask.sheet.starting") : t("ask.sheet.start")}</span>
            </button>
          )}
          <AddButton card={card} adder={adder} />
          <Link className="btn btn-ghost" to={`/khoa-hoc/${card.course_id}`}>
            {t("ask.sheet.page")}
          </Link>
        </footer>
      </aside>
    </>
  );
}
