import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, PracticeError, type PCourseLevels, type StartSource } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";

type Band = "kid" | "school" | "uni";
export type Plan = "co-ban" | "nang-cao" | "luyen-thi";

const PLANS: Plan[] = ["co-ban", "nang-cao", "luyen-thi"];
const RANK: Record<Plan, number> = { "co-ban": 0, "nang-cao": 1, "luyen-thi": 2 };
const PLAN_KEY = "mentor.plan";

/** Plan a level needs: 1-2 Basic, 3 Plus, 4 Exam. */
const levelRank = (level: number): number => (level <= 2 ? 0 : level === 3 ? 1 : 2);

/**
 * Plans are UI only for now (no backend data, nothing is gated server-side). Until a plan is chosen everything is open
 * (the "Exam" plan), so the ladder behaves as before.
 */
function usePlan(): [Plan, (p: Plan) => void] {
  const [plan, setPlan] = useState<Plan>(() => {
    try {
      const v = localStorage.getItem(PLAN_KEY);
      return PLANS.includes(v as Plan) ? (v as Plan) : "luyen-thi";
    } catch {
      return "luyen-thi";
    }
  });
  const set = (p: Plan) => {
    setPlan(p);
    try {
      localStorage.setItem(PLAN_KEY, p);
    } catch {
      /* private mode: the choice lasts until the page closes */
    }
  };
  return [plan, set];
}

/**
 * Practice inside a course (mockups/hs-04): the "Luyện tập" group (the level ladder, easy to hard) and the "Kiểm tra"
 * group (tests and mock exams), both folds of the course tree, plus the plans sheet. Rendered inside `nav.ct-tree`.
 */
export function CoursePractice({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const band: Band = user?.age_band === "g1_5" ? "kid" : user?.age_band === "uni" ? "uni" : "school";
  const [data, setData] = useState<PCourseLevels | null>(null);
  const [failed, setFailed] = useState(false);
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<"insufficient" | "failed" | null>(null);
  const [plan, setPlan] = usePlan();
  const [sheet, setSheet] = useState(false);
  const rank = RANK[plan];

  useEffect(() => {
    if (!token) return;
    let alive = true;
    practice.courseLevels(token, courseId).then(
      (d) => alive && setData(d),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [token, courseId]);

  useEffect(() => {
    if (!sheet) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setSheet(false);
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [sheet]);

  const start = useCallback(
    async (key: string, source: StartSource, level?: number) => {
      if (!token || starting) return;
      setStarting(key);
      setError(null);
      const state = { back: `${loc.pathname}${loc.search}` };
      try {
        const s = await practice.start(token, { source, ...(level ? { level } : {}) });
        nav(`/luyen-tap/${encodeURIComponent(s.id)}`, { state });
      } catch (e) {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`, { state });
        else setError(e instanceof PracticeError && e.code === "insufficient_content" ? "insufficient" : "failed");
        setStarting(null);
      }
    },
    [nav, starting, token, loc.pathname, loc.search],
  );

  if (failed || !data) return null; // the lessons still work; practice shows once it can be read
  const levels = data.levels.filter((l) => l.items > 0 && (band !== "kid" || l.level <= 3));
  const mocks = band === "kid" ? [] : data.mocks;
  const openPlans = () => setSheet(true);

  return (
    <>
      {levels.length > 0 && (
        <details className="ct-grp ladder" open data-guide="course-practice" data-guide-label={t("coursePractice.title")}>
          <summary className="ct-node">
            <span className="chev">
              <Icon name="chev" />
            </span>
            <span className="ic">
              <Icon name="layers" />
            </span>
            <span className="t">{t("coursePractice.title")}</span>
            <span className="end">
              <span
                className="plan-chip"
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.preventDefault();
                  openPlans();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    openPlans();
                  }
                }}
              >
                {t(`coursePractice.plan.${plan}`)}
              </span>
            </span>
          </summary>
          <div className="ct-kids">
            {levels.map((l) => {
              const open = l.studied >= data.min_items;
              const mentor = data.suggested === l.level;
              const locked = levelRank(l.level) > rank;
              const pct = l.studied ? Math.round((l.correct / l.studied) * 100) : 0;
              const name = t(`coursePractice.level.${band}.${l.level}`);
              const no = band === "kid" ? <span className="stars">{"★".repeat(l.level)}</span> : <span className="no">{l.level}</span>;
              if (locked)
                return (
                  <button key={l.level} type="button" className="ct-node locked" onClick={openPlans}>
                    {no}
                    <span className="t">{name}</span>
                    <span className="end">
                      <Icon name="lock" />
                      <span className="sr">{t("coursePractice.locked")}</span>
                    </span>
                  </button>
                );
              if (!open)
                return (
                  <span key={l.level} className="ct-node later">
                    {no}
                    <span className="t">{name}</span>
                    <span className="end" />
                  </span>
                );
              return (
                <button
                  key={l.level}
                  type="button"
                  className={`ct-node${l.solid ? " done" : mentor ? " now" : ""}`}
                  aria-current={mentor && !l.solid ? "step" : undefined}
                  disabled={!!starting}
                  onClick={() => void start(`l${l.level}`, `course:${courseId}`, l.level)}
                >
                  {no}
                  <span className="t">{name}</span>
                  <span className="end">
                    {l.solid ? (
                      <Icon name="check" />
                    ) : band === "kid" ? (
                      mentor && <Icon name="play" />
                    ) : (
                      <span className="pct">{pct}%</span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </details>
      )}

      {mocks.length > 0 && (
        <details className="ct-grp">
          <summary className="ct-node">
            <span className="chev">
              <Icon name="chev" />
            </span>
            <span className="ic">
              <Icon name="clock" />
            </span>
            <span className="t">{t("coursePractice.tests")}</span>
            <span className="end">{rank < 1 && <Icon name="lock" />}</span>
          </summary>
          {rank < 1 ? (
            <p className="ct-empty">
              <span>{t("coursePractice.inPlus")}</span>{" "}
              <button type="button" className="btn-link" onClick={openPlans}>
                {t("coursePractice.seePlans")}
              </button>
            </p>
          ) : (
            <div className="ct-kids">
              {mocks.map((m) => {
                const row = (
                  <>
                    <span className="ic">
                      <Icon name="clock" />
                    </span>
                    <span className="t">{t("coursePractice.mockLine", { title: m.title, items: m.items, minutes: m.minutes })}</span>
                  </>
                );
                if (rank < 2)
                  return (
                    <button key={m.profile_id} type="button" className="ct-node locked" onClick={openPlans}>
                      {row}
                      <span className="end">
                        <Icon name="lock" />
                        <span className="sr">{t("coursePractice.locked")}</span>
                      </span>
                    </button>
                  );
                return (
                  <button key={m.profile_id} type="button" className="ct-node" disabled={!!starting} onClick={() => void start(`m${m.profile_id}`, `mock:${m.profile_id}`)}>
                    {row}
                    <span className="end" />
                  </button>
                );
              })}
            </div>
          )}
        </details>
      )}

      {error && (
        <p className="cp-err" role="alert">
          {t(error === "insufficient" ? "coursePractice.insufficient" : "coursePractice.failed")}
        </p>
      )}

      {sheet && <PlansSheet plan={plan} onPick={(p) => (setPlan(p), setSheet(false))} onClose={() => setSheet(false)} />}
    </>
  );
}

/** The three plans side by side (hs-04). UI only: switching keeps progress and changes what is shown as open. */
function PlansSheet({ plan, onPick, onClose }: { plan: Plan; onPick: (p: Plan) => void; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <>
      <div className="ct-scrim" onClick={onClose} />
      <section className="ct-sheet" role="dialog" aria-modal="true" aria-labelledby="ct-plans-h">
        <span className="grab" aria-hidden="true" />
        <div className="sheet-h">
          <h2 id="ct-plans-h">{t("coursePractice.sheetTitle")}</h2>
          <button className="icon-btn" type="button" onClick={onClose} aria-label={t("courses.catalog.close")} autoFocus>
            <Icon name="x" />
          </button>
        </div>
        <div className="plans">
          {PLANS.map((p) => (
            <div className="plan" key={p}>
              <h3>{t(`coursePractice.planCard.${p}.name`)}</h3>
              <ul>
                <li>{t(`coursePractice.planCard.${p}.a`)}</li>
                <li>{t(`coursePractice.planCard.${p}.b`)}</li>
              </ul>
              {p === plan ? (
                <span className="tag ok">{t("coursePractice.yourPlan")}</span>
              ) : (
                <button type="button" className={RANK[p] > RANK[plan] ? "btn btn-primary" : "btn-line"} onClick={() => onPick(p)}>
                  {t(RANK[p] > RANK[plan] ? "coursePractice.upgrade" : "coursePractice.switch")}
                </button>
              )}
            </div>
          ))}
        </div>
        <p className="note">{t("coursePractice.keepProgress")}</p>
      </section>
    </>
  );
}
