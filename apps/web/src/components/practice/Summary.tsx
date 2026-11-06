"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getApi } from "@/lib/api";
import { fireConfetti } from "@/lib/confetti";
import { useReducedMotion } from "@/lib/motion";
import { useAsync } from "@/lib/hooks";
import {
  accuracyOf,
  earnsConfetti,
  formatClock,
  formatPoints,
  formatScore10,
  kindLabel,
  masteryChange,
  partCounts,
  partsOf,
  summaryHeadline,
  STATEMENT_POINTS,
} from "@/lib/practice/logic";
import { readCachedReport } from "@/lib/practice/reportCache";
import { practiceRoute, reviewRoute } from "@/lib/practice/routes";
import type { Report } from "@/lib/practice/types";
import { usePageShortcuts, type Shortcut } from "@/lib/shortcuts";
import { Mascot } from "../Mascot";
import { RecommendationList } from "../progress/NextSteps";
import { ErrorBox, Loading } from "../ui";

export function ScoreRing({ fraction, value, caption }: { fraction: number; value: string; caption: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const f = Math.min(1, Math.max(0, fraction));
  return (
    <div className="sring" role="img" aria-label={`${value} ${caption}`}>
      <svg viewBox="0 0 128 128" width="144" height="144" aria-hidden="true">
        <circle cx="64" cy="64" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="12" />
        <circle
          className="sring-arc"
          cx="64"
          cy="64"
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${c * f} ${c}`}
          transform="rotate(-90 64 64)"
        />
      </svg>
      <div className="sring-text">
        <strong>{value}</strong>
        <span className="faint">{caption}</span>
      </div>
    </div>
  );
}

const SUMMARY_SHORTCUTS: Shortcut[] = [
  { keys: "R", description: "Xem lại bài" },
  { keys: "Enter", description: "Luyện tiếp" },
  { keys: "Esc", description: "Về trang luyện tập" },
];

export function SummaryView({ report, sessionId }: { report: Report; sessionId: string }) {
  const router = useRouter();
  const reduce = useReducedMotion();
  const kind = report.session.kind;
  const subject = report.session.subject;
  usePageShortcuts("practice-summary", "Kết quả", SUMMARY_SHORTCUTS);

  const confettied = useRef(false);
  useEffect(() => {
    if (confettied.current || !earnsConfetti(report, kind)) return;
    confettied.current = true;
    void fireConfetti(); // already a no-op under reduced motion
  }, [report, kind]);

  const nextUp = report.recommendations.find((r) => r.action.kind !== "break");
  const again = practiceRoute({ subject });
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || document.querySelector("dialog[open]")) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "BUTTON" || tag === "A" || tag === "INPUT") return;
      if (e.key.toLowerCase() === "r") router.push(reviewRoute(sessionId));
      else if (e.key === "Escape") router.push(again);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [again, router, sessionId]);

  const acc = accuracyOf(report, kind);
  const scored = report.score_10 != null;
  const parts = partsOf(report);
  const partial = kind === "practice" && report.answered < report.total;
  const happy = earnsConfetti(report, kind);

  return (
    <div className="page page-narrow summary">
      <div className="summary-top">
        <div>
          <span className="badge badge-ok">{kindLabel(kind)}</span>
          <h1>{summaryHeadline(report, kind)}</h1>
          <div className="pills">
            <span className="badge badge-ok">
              Đúng {report.correct}/{partial ? report.answered : report.total}
              {partial ? " câu đã làm" : ""}
            </span>
            {partial && <span className="badge">Dừng ở {report.answered}/{report.total}</span>}
            <span className="badge">Thời gian {formatClock(report.minutes * 60)}</span>
            {report.hints > 0 && <span className="badge">Gợi ý {report.hints}</span>}
          </div>
          {report.disclaimer && <p className="disclaimer">{report.disclaimer}</p>}
          {kind === "mock" && !report.disclaimer && <p className="disclaimer">Điểm thi thử KHÔNG dự báo điểm thi thật.</p>}
        </div>
        <div className="summary-score">
          <Mascot state={happy && !reduce ? "celebrate" : happy ? "happy" : "idle"} size={56} />
          {scored ? (
            <ScoreRing fraction={(report.score_10 ?? 0) / 10} value={formatScore10(report.score_10!)} caption="điểm / 10 (thi thử)" />
          ) : (
            <ScoreRing fraction={acc} value={`${Math.round(acc * 100)}%`} caption="câu trả lời đúng" />
          )}
        </div>
      </div>

      {parts.length > 0 && (
        <section className="card" aria-labelledby="parts-h">
          <h2 id="parts-h">Theo từng phần</h2>
          <p className="muted">Phần II tính điểm theo số ý đúng trong mỗi câu: {[1, 2, 3, 4].map((n) => `${n} ý ${formatPoints(STATEMENT_POINTS[n])}`).join(" · ")} điểm.</p>
          <ul className="part-list">
            {parts.map((p) => {
              const c = partCounts(p);
              return (
              <li key={p.label}>
                <div>
                  <strong>{p.label}</strong>
                  <p className="faint">
                    {c.fullyCorrect}/{c.items} {c.truefalse ? "câu đúng đủ 4 ý" : "câu đúng"} · đã làm {p.answered ?? 0}/{c.items}
                  </p>
                </div>
                <div className="meter" aria-hidden="true">
                  <span style={{ width: `${Math.min(100, (p.points / Math.max(p.max_points, 1e-9)) * 100)}%` }} />
                </div>
                <strong>
                  {formatPoints(p.points)} / {formatPoints(p.max_points)} điểm
                </strong>
              </li>
              );
            })}
          </ul>
        </section>
      )}

      <section className="card" aria-labelledby="topics-h">
        <h2 id="topics-h">Theo từng chủ đề</h2>
        <p className="muted">Mức nắm vững là ước lượng của hệ thống, không phải điểm thi.</p>
        {report.per_topic.length === 0 ? (
          <p className="muted">Chưa có câu trả lời nào được ghi nhận.</p>
        ) : (
          <ul className="topic-list">
            {report.per_topic.map((t) => {
              const ch = masteryChange(t);
              return (
                <li key={t.topic}>
                  <div>
                    <strong>{t.title}</strong>
                    <p className="faint">
                      {t.right}/{t.total} đúng
                    </p>
                  </div>
                  <div>
                    <div className="meter" aria-hidden="true">
                      <span style={{ width: `${Math.round((t.mastery_after ?? 0) * 100)}%` }} />
                    </div>
                    <p className="topic-change" data-dir={ch.direction}>
                      {ch.text}
                    </p>
                  </div>
                  <span className="badge">{t.label}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <RecommendationList recs={report.recommendations.slice(0, 3)} />

      <div className="row summary-actions">
        <Link href={nextUp ? (nextUp.action.kind === "practice" ? practiceRoute({ subject }) : again) : again} className="btn btn-primary btn-lg">
          Luyện tiếp
        </Link>
        <Link href={reviewRoute(sessionId)} className="btn">
          Xem lại bài <kbd className="keycap keycap-inline">R</kbd>
        </Link>
        <Link href={`/practice?subject=${encodeURIComponent(subject)}`} className="btn btn-ghost">
          Về trang luyện tập <kbd className="keycap keycap-inline">Esc</kbd>
        </Link>
      </div>
      <p className="hint">Thấy câu nào có lỗi? Mở “Xem lại bài” rồi bấm “Báo lỗi câu hỏi” dưới câu đó.</p>
    </div>
  );
}

/** `/practice/summary/[id]`: the Report from `finish` (cached in this tab, else asked again; finish is idempotent). */
export function SummaryPage() {
  const { id } = useParams<{ id: string }>();
  const [cached] = useState(() => (typeof window === "undefined" ? null : readCachedReport(id)));
  const loaded = useAsync(() => (cached ? Promise.resolve(cached) : getApi().practice.finish(id)), [id]);
  if (loaded.error) return <div className="page"><ErrorBox error={loaded.error} onRetry={loaded.reload} /></div>;
  if (!loaded.data) return <Loading full label="Đang tổng hợp kết quả…" />;
  return <SummaryView report={loaded.data} sessionId={id} />;
}
