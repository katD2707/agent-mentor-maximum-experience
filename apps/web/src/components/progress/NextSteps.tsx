"use client";

import Link from "next/link";
import { actionRoute } from "@/lib/practice/routes";
import { reasonText, splitRecommendations, subjectName } from "@/lib/practice/progress";
import type { Recommendation } from "@/lib/practice/progressTypes";
import { getApi } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { Icon } from "../Icon";

/** Pure rendering of "Bước tiếp theo": up to 3 steps (first has the one primary button) and a gentle break card. */
export function RecommendationList({ recs, compact = false }: { recs: Recommendation[]; compact?: boolean }) {
  const { steps, rest } = splitRecommendations(recs);
  if (steps.length === 0 && !rest) return null;
  return (
    <section className={compact ? "next-steps compact" : "next-steps"} aria-labelledby="next-h">
      <h2 id="next-h">Bước tiếp theo</h2>
      {rest && (
        <div className="break-card" role="note">
          <Icon name="heart" size={18} />
          <div>
            <strong>{rest.title}</strong>
            <p className="muted">{reasonText(rest.reason)}</p>
          </div>
        </div>
      )}
      {steps.length > 0 && (
        <ol className="step-list">
          {steps.map((r, i) => {
            const href = actionRoute(r.action, r.subject);
            return (
              <li key={`${r.code}-${r.subject ?? ""}-${i}`}>
                <div className="step-text">
                  <strong>{r.title}</strong>
                  {r.subject && <span className="badge">{subjectName(r.subject)}</span>}
                  <p className="muted">{reasonText(r.reason)}</p>
                </div>
                {href && (
                  <Link href={href} className={i === 0 ? "btn btn-primary btn-sm" : "btn btn-sm"}>
                    {r.action.kind === "diagnostic" ? "Bắt đầu" : r.action.kind === "progress" ? "Xem" : "Mở"}
                    <span className="sr-only">: {r.title}</span>
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/**
 * Loads GET /practice/recommendations and shows them. Renders nothing while loading or when the gateway cannot
 * answer (older gateway, NCS profile), so the surrounding screen never breaks over it.
 */
export function NextSteps({ subject, compact = false, limit }: { subject?: string; compact?: boolean; limit?: number }) {
  const q = useAsync(() => getApi().getRecommendations(subject), [subject ?? ""]);
  if (q.error != null || !q.data) return null;
  return <RecommendationList recs={limit ? q.data.slice(0, limit) : q.data} compact={compact} />;
}
