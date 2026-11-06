/** Where W2 links into W1's practice screens (agreed in CONTRACTS 10, "W2 coordination"). */
import type { RecommendationAction } from "./progressTypes";

function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, Array.isArray(v) ? v.join(",") : String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const practiceRoute = (o: { subject?: string; minutes?: number; goal?: string; topics?: string[] } = {}) =>
  `/practice${qs(o)}`;
export const mockRoute = (o: { subject?: string; profile_id?: string } = {}) => `/practice/mock${qs(o)}`;
export const diagnosticRoute = (o: { subject?: string } = {}) => `/practice/diagnostic${qs(o)}`;
export const reviewRoute = (sessionId: string) => `/practice/review/${encodeURIComponent(sessionId)}`;
export const progressRoute = (subject?: string) => `/progress${qs({ subject })}`;

/** Route for a recommendation's action; `break` has no route (a gentle card, no button). */
export function actionRoute(a: RecommendationAction, subject?: string | null): string | null {
  const p = (a.params ?? {}) as Record<string, unknown>;
  const subj = (typeof p.subject === "string" ? p.subject : subject) ?? undefined;
  switch (a.kind) {
    case "practice":
      return practiceRoute({
        subject: subj,
        minutes: typeof p.minutes === "number" ? p.minutes : undefined,
        goal: typeof p.goal === "string" ? p.goal : undefined,
        topics: Array.isArray(p.topics) ? (p.topics as string[]) : undefined,
      });
    case "mock":
      return mockRoute({ subject: subj, profile_id: typeof p.profile_id === "string" ? p.profile_id : undefined });
    case "diagnostic":
      return diagnosticRoute({ subject: subj });
    case "progress":
      return progressRoute(subj);
    default:
      return null;
  }
}
