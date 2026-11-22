import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, type PCourseLevels } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import type { ChuongTest } from "../../api/chuong";
import { ladderBand, lessonState, type Row } from "./logic";
import { RecapRows, type Playable } from "./Recap";

/** The way into a lesson from the coop; leaving the lesson comes back here (`from=khoa`). */
export const lessonTo = (courseId: string, lessonId?: string) => `/khoa-hoc/${encodeURIComponent(courseId)}/hoc?${lessonId ? `lesson=${encodeURIComponent(lessonId)}&` : ""}from=khoa`;

function Summary({ icon, title, end = "" }: { icon: "book" | "layers"; title: string; end?: string }) {
  return (
    <summary className="ck-node">
      <span className="ck-chev">
        <Icon name="chev" />
      </span>
      <span className="ck-ic">
        <Icon name={icon} />
      </span>
      <span className="ck-t">{title}</span>
      <span className="ck-end">{end}</span>
    </summary>
  );
}

/** The inside of one course (lg-03): lessons (done / now / later) with the recap rows, the practice ladder, the mock exam. */
export function CourseTree({ row, band, name, recaps, tests, onListen }: { row: Row; band: string | null | undefined; name: string; recaps: Playable[]; tests: ChuongTest[]; onListen(p: Playable): void }) {
  const { t } = useTranslation();
  const kid = band === "g1_5";
  const loc = useLocation();
  const back = { back: `${loc.pathname}${loc.search}` };
  return (
    <nav className="ck-tree" aria-label={t("lg.cg.treeAria", { title: row.title })}>
      <details className="ck-grp" open>
        <Summary icon="book" title={t("lg.cg.lessons")} />
        <RecapRows list={recaps} kid={kid} name={name} onOpen={onListen} />
        <div className="ck-kids">
          {row.lessons.map((l, i) => {
            const st = lessonState(row, i);
            const body = (
              <>
                <span className="ck-no">{i + 1}</span>
                <span className="ck-t">{l.title}</span>
                <span className="ck-end">
                  {st === "done" ? kid ? <span className="ck-stars" aria-label={t("lg.cg.stars2")}>★★</span> : <Icon name="check" /> : st === "now" ? <Icon name="play" /> : null}
                </span>
              </>
            );
            const cls = `ck-node ${st === "now" ? "ck-nowrow" : st === "done" ? "ck-done" : "ck-later"}`;
            return st === "later" ? (
              <span key={l.id} className={cls}>
                {body}
              </span>
            ) : (
              <Link key={l.id} className={cls} to={lessonTo(row.id, l.id)} state={back} aria-current={st === "now" ? "step" : undefined}>
                {body}
              </Link>
            );
          })}
        </div>
      </details>
      <Ladder row={row} band={band} tests={tests} />
    </nav>
  );
}

/** "Luyện tập": the level ladder. Each open level starts a practice on this course; the mock exam sits under it. */
function Ladder({ row, band, tests }: { row: Row; band: string | null | undefined; tests: ChuongTest[] }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const loc = useLocation();
  const kind = ladderBand(band);
  const [data, setData] = useState<PCourseLevels | null>(null);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    practice.courseLevels(token, row.id).then(
      (d) => alive && setData(d),
      () => alive && setData(null), // the lessons still work; practice shows once it can be read
    );
    return () => {
      alive = false;
    };
  }, [token, row.id]);
  const names = t(`lg.cg.ladder.${kind}`, { returnObjects: true }) as unknown as string[];
  const levels = (data?.levels ?? []).filter((l) => l.items > 0 && (kind !== "kid" || l.level <= 3));
  const mock = kind === "kid" ? undefined : tests.find((x) => x.course_id === row.id);
  const back = { back: `${loc.pathname}${loc.search}` };
  const kidMark = kind === "kid";
  if (!levels.length && !mock) return null;
  return (
    <>
      {levels.length > 0 && data && (
        <details className="ck-grp" open>
          <Summary icon="layers" title={t("lg.cg.practice")} />
          <div className="ck-kids">
            {levels.map((l) => {
              const open = l.studied >= data.min_items;
              const now = data.suggested === l.level;
              const pct = l.studied ? Math.round((l.correct / l.studied) * 100) : 0;
              const state = l.solid ? "ck-done" : now ? "ck-nowrow" : "";
              const no = kidMark ? <span className="ck-stars">{"★".repeat(l.level)}</span> : <span className="ck-no">{l.level}</span>;
              const label = names[l.level - 1] ?? String(l.level);
              const end = l.solid ? <Icon name="check" /> : kidMark ? (now ? <Icon name="play" /> : null) : <>{pct}%</>;
              const inner = (
                <>
                  {no}
                  <span className="ck-t">{label}</span>
                  <span className="ck-end ck-pct">{end}</span>
                </>
              );
              return open ? (
                <Link key={l.level} className={`ck-node ${state}`} to={`/kiem-tra/${encodeURIComponent(row.id)}?state=luyen&level=${l.level}&from=chuong`} state={back} aria-current={now && !l.solid ? "step" : undefined}>
                  {inner}
                </Link>
              ) : (
                <span key={l.level} className="ck-node ck-later">
                  {inner}
                </span>
              );
            })}
          </div>
        </details>
      )}
      {mock && (
        <Link className="ck-node" to={`/kiem-tra/${encodeURIComponent(row.id)}?state=thi&from=chuong`} state={back}>
          <span className="ck-ic">
            <Icon name="clock" />
          </span>
          <span className="ck-t">{t("lg.cg.mock", { items: mock.items, minutes: mock.minutes })}</span>
          <span className="ck-end" />
        </Link>
      )}
    </>
  );
}
