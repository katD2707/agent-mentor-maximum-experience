import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { researchApi, researchPoll, ResearchError, type JobProgress, type PaperCard, type ReviewResult } from "../../api/research";
import { useAuth } from "../../state/auth";
import { errCode, extProps } from "./util";

/** "Tổng quan nhanh": a review job (CONTRACTS.md 15.4), polled every `researchPoll.ms` until it is done. */
export type ReviewState = { phase: "idle" } | { phase: "running"; progress: JobProgress | null } | { phase: "done"; result: ReviewResult } | { phase: "failed"; error: string };

export function useReview(query: string, yearMin: number | undefined) {
  const { token } = useAuth();
  const [state, setState] = useState<ReviewState>({ phase: "idle" });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const gen = useRef(0);

  const stop = useCallback(() => {
    gen.current += 1;
    clearTimeout(timer.current);
  }, []);
  useEffect(() => stop, [stop]);
  // a new search drops the old table
  useEffect(() => {
    stop();
    setState({ phase: "idle" });
  }, [query, yearMin, stop]);

  const poll = useCallback(
    (jobId: string, mine: number) => {
      if (!token) return;
      timer.current = setTimeout(async () => {
        try {
          const job = await researchApi.getJob(token, jobId);
          if (gen.current !== mine) return;
          if (job.status === "done" && job.result && "matrix" in job.result) return setState({ phase: "done", result: job.result });
          if (job.status === "failed") return setState({ phase: "failed", error: job.error ?? "internal" });
          setState({ phase: "running", progress: job.progress });
          poll(jobId, mine);
        } catch (e) {
          if (gen.current !== mine) return;
          if (e instanceof ResearchError && e.code === "network") return poll(jobId, mine); // offline for a moment: keep asking
          setState({ phase: "failed", error: errCode(e) === "job_not_found" ? "internal" : errCode(e) });
        }
      }, researchPoll.ms);
    },
    [token],
  );

  const start = useCallback(
    async (followups?: string[]) => {
      if (!token) return;
      stop();
      const mine = gen.current;
      setState({ phase: "running", progress: null });
      try {
        const { job_id } = await researchApi.startReview(token, { query, ...(yearMin ? { year_min: yearMin } : {}), ...(followups?.length ? { followups } : {}) });
        if (gen.current === mine) poll(job_id, mine);
      } catch (e) {
        if (gen.current !== mine) return;
        // one is already running: follow that one instead of starting another
        if (e instanceof ResearchError && e.code === "job_running" && e.extra.job_id) return poll(e.extra.job_id, mine);
        setState({ phase: "failed", error: errCode(e) });
      }
    },
    [token, query, yearMin, stop, poll],
  );
  const hide = useCallback(() => {
    stop();
    setState({ phase: "idle" });
  }, [stop]);
  return { state, start, hide };
}

export function ReviewPanel({ state, onSearch, onHide }: { state: ReviewState; onSearch(q: string): void; onHide(): void }) {
  const { t, i18n } = useTranslation();
  if (state.phase === "idle") return null;
  if (state.phase === "running") {
    const p = state.progress;
    return (
      <section className="rs-card rs-rv" aria-live="polite">
        <div role="status" className="rs-rv-run">
          <span className="rs-spin" aria-hidden="true" />
          <span>{p && p.stage === "reading" && p.total > 0 ? t("research.review.reading", { n: p.total }) : t("research.review.searching")}</span>
        </div>
      </section>
    );
  }
  if (state.phase === "failed")
    return (
      <section className="rs-card rs-rv">
        <p className="rs-rv-note" role="alert">
          {t(`research.review.error.${state.error}`, { defaultValue: t("research.review.error.internal") })}
        </p>
        <div>
          <button className="btn btn-quiet rs-rbtn" type="button" onClick={onHide}>
            {t("research.review.hide")}
          </button>
        </div>
      </section>
    );

  const r = state.result;
  const lang = i18n.language === "en" ? "en" : "vi";
  const byKey = new Map<string, PaperCard>(r.papers.map((p) => [p.key, p]));
  const rows = r.matrix.filter((m) => byKey.has(m.key));
  const heads = [t("research.review.cols.paper"), t("research.review.cols.problem"), t("research.review.cols.method"), t("research.review.cols.data"), t("research.review.cols.result")];
  const none = t("research.review.notStated");
  return (
    <section className="rs-card rs-rv" aria-labelledby="rs-rv-h">
      <div className="rs-rv-head">
        <h3 id="rs-rv-h" className="rs-s">
          {t("research.review.title")}
        </h3>
        <span className="muted small">{t("research.review.count", { n: rows.length || r.papers.length })}</span>
        <span className="rs-grow" />
        <button className="btn btn-quiet rs-rbtn" type="button" onClick={onHide}>
          {t("research.review.hide")}
        </button>
      </div>
      <p className="rs-rv-note" role="note">
        {lang === "en" ? r.caveat_en : r.caveat_vi}
      </p>
      {rows.length === 0 ? (
        <p className="muted">{t("research.review.noMatrix")}</p>
      ) : (
        <div className="rs-mx-wrap">
          <table className="rs-mx">
            <thead>
              <tr>
                {heads.map((h, i) => (
                  <th key={i} scope="col">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const p = byKey.get(m.key)!;
                const cells = [m.problem, m.method, m.data, m.result];
                return (
                  <tr key={m.key}>
                    <th scope="row">
                      {p.paper_id ? (
                        <Link className="rs-mx-t" to={`/nghien-cuu/paper/${encodeURIComponent(p.paper_id)}`}>
                          {p.title}
                        </Link>
                      ) : (
                        <a className="rs-mx-t" href={p.url} {...extProps}>
                          {p.title}
                        </a>
                      )}
                      <span className="rs-mx-m">
                        {p.year}
                        {p.arxiv_id && (
                          <>
                            {" · "}
                            <a href={`https://arxiv.org/abs/${p.arxiv_id}`} {...extProps}>
                              arXiv:{p.arxiv_id}
                            </a>
                          </>
                        )}
                      </span>
                    </th>
                    {cells.map((c, i) => (
                      <td key={i} data-label={heads[i + 1]} className={c === null ? "rs-null" : undefined}>
                        {c ?? none}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {r.followups.length > 0 && (
        <div className="rs-follow">
          <span className="rs-eyebrow">{t("research.review.next")}</span>
          <div className="rs-chips">
            {r.followups.map((q) => (
              <button key={q} className="rs-fchip" type="button" onClick={() => onSearch(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
