import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Icon, type IconName } from "../../components/Icon";

/** hs-11: the research space split into chapters, one tab each, like files open in an editor. */
export const CHAPTERS = ["read", "schedule", "experiments", "topic"] as const;
export type Chapter = (typeof CHAPTERS)[number];
const ICONS: Record<Chapter, IconName> = { read: "book", schedule: "clock", experiments: "chart", topic: "target" };
const KEY = "mentor.researchTab";

export function savedChapter(): Chapter {
  try {
    const v = localStorage.getItem(KEY) as Chapter | null;
    return v && CHAPTERS.includes(v) ? v : "read";
  } catch {
    return "read";
  }
}

export function rememberChapter(c: Chapter) {
  try {
    localStorage.setItem(KEY, c);
  } catch {
    /* private window: the tab just isn't remembered */
  }
}

/** A dot on a tab: something new there ("new"), or a deadline coming up ("hot"). The text is read out, not shown. */
export type ChapterDot = { kind: "new" | "hot"; label: string } | null;

export function useChapter() {
  const [tab, setTab] = useState<Chapter>(savedChapter);
  const pick = (c: Chapter) => {
    setTab(c);
    rememberChapter(c);
  };
  return [tab, pick] as const;
}

export function ChapterTabs({ tab, onPick, dots, panels }: { tab: Chapter; onPick(c: Chapter): void; dots: Partial<Record<Chapter, ChapterDot>>; panels: Record<Chapter, ReactNode> }) {
  const { t } = useTranslation();
  const refs = useRef<Partial<Record<Chapter, HTMLButtonElement | null>>>({});
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, c: Chapter) => {
    const i = CHAPTERS.indexOf(c);
    const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: CHAPTERS.length - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    const next = CHAPTERS[(to + CHAPTERS.length) % CHAPTERS.length];
    onPick(next);
    refs.current[next]?.focus();
  };
  return (
    <div className="rs-chapters">
      <div className="rs-tabs" role="tablist" aria-label={t("research.tabs.label")} data-guide="research-tabs" data-guide-label={t("research.tabs.label")}>
        {CHAPTERS.map((c) => {
          const on = c === tab;
          const dot = dots[c];
          return (
            <button
              key={c}
              ref={(el) => {
                refs.current[c] = el;
              }}
              className="rs-tab"
              type="button"
              role="tab"
              id={`rs-tab-${c}`}
              aria-controls={`rs-panel-${c}`}
              aria-selected={on}
              tabIndex={on ? 0 : -1}
              onClick={() => onPick(c)}
              onKeyDown={(e) => onKey(e, c)}
            >
              <Icon name={ICONS[c]} />
              <span>{t(`research.tabs.${c}`)}</span>
              {dot && (
                <span className={`rs-tdot${dot.kind === "hot" ? " hot" : ""}`} title={dot.label}>
                  <span className="rs-sr">{dot.label}</span>
                </span>
              )}
            </button>
          );
        })}
      </div>
      {CHAPTERS.map((c) => (
        <section key={c} className="rs-panel" role="tabpanel" id={`rs-panel-${c}`} aria-labelledby={`rs-tab-${c}`} hidden={c !== tab}>
          {c === tab && panels[c]}
        </section>
      ))}
    </div>
  );
}
