import type { Ref } from "react";
import { useTranslation } from "react-i18next";
import type { CourseLevel } from "../../api/teacher";
import { LEVELS, levelBars } from "../../lib/teacher/level";

/** 1-3 bars, filled up to the level. Decoration only: the word next to it carries the meaning. */
export function LevelBars({ level }: { level: CourseLevel }) {
  const n = levelBars(level);
  return (
    <span className="lvx-bars" aria-hidden="true">
      {[1, 2, 3].map((i) => (
        <i key={i} className={n >= i ? "on" : ""} />
      ))}
    </span>
  );
}

/** Bars plus the word: the pill in the review header (`pill`) or the quiet one in a course row. */
export function LevelTag({ level, pill = false }: { level: CourseLevel; pill?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className={`lvx-tag${pill ? " pill" : ""}`} data-level={level}>
      <LevelBars level={level} />
      <span>{t(`gv.levelOf.${level}`)}</span>
    </span>
  );
}

interface Props {
  /** the pre-selected or chosen level */
  value: CourseLevel | null;
  /** the agent's guess, marked "Gợi ý" until the teacher confirms */
  suggested: CourseLevel | null;
  confirmed: boolean;
  /** the teacher tried to publish without confirming */
  nudged: boolean;
  /** "Mức độ mới sẽ có trong bản N" when the pick differs from what students see */
  nextVersion: number | null;
  busy: boolean;
  onPick(l: CourseLevel): void;
  onConfirm(): void;
  rowRef?: Ref<HTMLDivElement>;
}

/** gv-03: three options, one tap confirms. Mentor only suggests. */
export function LevelPicker({ value, suggested, confirmed, nudged, nextVersion, busy, onPick, onConfirm, rowRef }: Props) {
  const { t } = useTranslation();
  const need = !confirmed && nudged;
  const note = nextVersion ? t("gv.levelNext", { version: nextVersion }) : need ? t("gv.levelNeed") : null;
  return (
    <div ref={rowRef} className={`lvx-row${need ? " need" : ""}`} id="levelrow" data-guide="gv-level" data-guide-label={t("gv.levelLabel")}>
      <div className="lvx-top">
        <span className="lvx-label" id="lvx-l">
          {t("gv.levelLabel")}
        </span>
        {!confirmed && value && (
          <button type="button" className="btn btn-primary lvx-ok" disabled={busy} onClick={onConfirm}>
            <span>{t("gv.levelConfirm")}</span>
          </button>
        )}
      </div>
      <div className="lvx-seg" role="radiogroup" aria-labelledby="lvx-l">
        {LEVELS.map((l) => (
          <button key={l} type="button" className="lvx-opt" role="radio" aria-checked={value === l} disabled={busy} data-level={l} onClick={() => onPick(l)}>
            <LevelBars level={l} />
            <span>{t(`gv.levelOf.${l}`)}</span>
            {!confirmed && suggested === l && <em className="sug">{t("gv.levelSuggested")}</em>}
          </button>
        ))}
      </div>
      {note && (
        <p className="lvx-note" role="status">
          {note}
        </p>
      )}
    </div>
  );
}
