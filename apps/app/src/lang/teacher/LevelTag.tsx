import { useTranslation } from "react-i18next";
import type { CourseLevel } from "../../api/teacher";
import { levelBars } from "../../lib/teacher/level";

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

/** Bars plus the word (Cơ bản / Nâng cao / Luyện thi): the pill in the review header or the quiet one in a course row. */
export function LevelTag({ level, pill = false }: { level: CourseLevel; pill?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className={`lvx-tag${pill ? " pill" : ""}`} data-level={level}>
      <LevelBars level={level} />
      <span>{t(`lg.gvl.levelOf.${level}`)}</span>
    </span>
  );
}
