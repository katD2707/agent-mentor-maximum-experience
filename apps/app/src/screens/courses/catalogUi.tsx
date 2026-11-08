import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { coverUrl, type CatalogEntry, type CatalogItem, type FacetKey, type Level } from "../../api";
import { onMediaError } from "../../lib/mediaRetry";
import { subjectName } from "../../lib/subjectNames";
import { useAuth } from "../../state/auth";
import { formatMinutes, Highlight } from "./common";

const BARS: Record<Level, number> = { basic: 1, intermediate: 2, advanced: 3 };

/** Subject, teaching language (EN badge for English courses) and difficulty (1 to 3 bars plus the word). Kids get subject and level. */
export function CourseTags({ course, kid = false }: { course: Pick<CatalogEntry, "subject" | "language" | "level">; kid?: boolean }) {
  const { t, i18n } = useTranslation();
  const lv = course.level ? BARS[course.level] : 0;
  return (
    <span className="ctags" data-testid="course-tags">
      <span className="ct ct-sub">{subjectName(course.subject, i18n.language)}</span>
      {!kid &&
        (course.language === "en" ? (
          <span className="ct ct-lang ct-en" lang="en">
            <b>EN</b> English
          </span>
        ) : (
          <span className="ct ct-lang">{t("courses.catalog.langName.vi")}</span>
        ))}
      {course.level && (
        <span className="ct ct-lv" data-level={course.level}>
          <span className="bars" aria-hidden="true">
            <i className="on" />
            <i className={lv > 1 ? "on" : undefined} />
            <i className={lv > 2 ? "on" : undefined} />
          </span>
          {t(`courses.catalog.level.${course.level}`)}
        </span>
      )}
    </span>
  );
}

/** A cover from the media URL (`?v=` makes it cacheable). Lists use plain <img>, not the offline cover store, so 10 cards stay cheap. */
export function ListCover({ course, className }: { course: Pick<CatalogEntry, "id" | "cover_sha256">; className?: string }) {
  const { token } = useAuth();
  const url = token ? coverUrl(token, course.id) : "";
  return <img className={className} src={url ? `${url}${url.includes("?") ? "&" : "?"}v=${course.cover_sha256}` : undefined} alt="" loading="lazy" onError={onMediaError} />;
}

/** Product-style card (hs-03): cover, two-line title, teacher, tags, lessons and duration, learners or "Sắp có". */
export function CourseCard({ c, words, kid, from }: { c: CatalogItem; words: string[]; kid: boolean; from: string }) {
  const { t } = useTranslation();
  const soon = c.status === "coming_soon";
  return (
    <li className="pc" tabIndex={-1} data-testid="course-card">
      <Link to={`/khoa-hoc/${c.id}`} state={{ from }}>
        <span className="pimg">
          <ListCover course={c} />
        </span>
        <span className="pbody">
          <h3>
            <Highlight text={c.title} words={words} />
          </h3>
          {!kid && (
            <span className="pt">
              <Highlight text={c.teacher_name} words={words} />
            </span>
          )}
          <CourseTags course={c} kid={kid} />
          {!kid && (
            <span className="pm">
              {t("courses.lessons", { count: c.lessons_count })}, {formatMinutes(t, c.est_minutes)}
            </span>
          )}
          <span className="pf">{soon ? <span className="tag">{t("courses.soon")}</span> : <span>{t(c.students === 1 ? "courses.catalog.studentsOne" : "courses.catalog.students", { count: c.students })}</span>}</span>
        </span>
      </Link>
    </li>
  );
}

const Chev = ({ dir }: { dir: "l" | "r" }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d={dir === "l" ? "M14.5 5.5 8 12l6.5 6.5" : "M9.5 5.5 16 12l-6.5 6.5"} />
  </svg>
);

/** Always visible, even for one page: chevrons (dimmed at the ends), plain numbers, an underline on the current page, about 5 numbers. */
export function Pager({ page, pages, onGo }: { page: number; pages: number; onGo: (n: number) => void }) {
  const { t } = useTranslation();
  const lo = Math.max(1, Math.min(page - 2, pages - 4));
  const hi = Math.min(pages, lo + 4);
  const nums: number[] = [];
  for (let i = lo; i <= hi; i++) nums.push(i);
  return (
    <nav className="pager" aria-label={t("courses.catalog.page")}>
      <button type="button" disabled={page <= 1} onClick={() => onGo(page - 1)} aria-label={t("courses.catalog.prevPage")}>
        <Chev dir="l" />
      </button>
      {nums.map((n) => (
        <button key={n} type="button" aria-current={n === page ? "page" : undefined} onClick={() => n !== page && onGo(n)} aria-label={t("courses.catalog.pageN", { n })}>
          {n}
        </button>
      ))}
      <button type="button" disabled={page >= pages} onClick={() => onGo(page + 1)} aria-label={t("courses.catalog.nextPage")}>
        <Chev dir="r" />
      </button>
    </nav>
  );
}

/** The label of a facet value in the current interface language. */
export function useFacetLabel() {
  const { t, i18n } = useTranslation();
  return (k: FacetKey, v: string): string => {
    switch (k) {
      case "band":
        return t(`courses.catalog.band.${v}`);
      case "subject":
        return subjectName(v, i18n.language);
      case "language":
        return t(`courses.catalog.langName.${v}`);
      case "level":
        return t(`courses.catalog.level.${v}`);
      case "duration":
        return t(`courses.catalog.duration.${v}`);
      case "media":
        return t(`courses.media.${v}`);
      case "status":
        return t(`courses.catalog.status.${v}`);
      default:
        return v;
    }
  };
}
