import type { TeacherCourseSummary } from "../../api/teacher";
import { statusTag, type Tone } from "./status";

/** What one course row shows when the hub is on (mockups/gv-01): chips, actions and a line under the row, all from `hub.state`. */
export type RowAction = "continue" | "edit" | "withdraw" | "remove";
export interface HubChip {
  tone: Tone;
  key: string;
  params?: Record<string, number>;
}
export interface HubRowView {
  chips: HubChip[];
  actions: RowAction[];
  /** the owner's reason (Bị từ chối) */
  why: string | null;
  /** "Học sinh vẫn thấy bản cũ." under a live course whose new version waits */
  oldVersion: boolean;
}

const DRAFT: HubChip = { tone: "", key: "lg.hub.course.draft" };

export function hubRowView(c: TeacherCourseSummary): HubRowView {
  const h = c.hub;
  // not sent yet (or the hub is offline): the draft, or what the gateway says (reading, composing ...)
  if (!h) {
    if (c.status === "review" || c.status === "revising") return { chips: [DRAFT], actions: ["continue"], why: null, oldVersion: false };
    if (c.status === "published") return { chips: [statusChip(c)], actions: ["edit"], why: null, oldVersion: false };
    return { chips: [statusChip(c)], actions: [], why: null, oldVersion: false };
  }
  const live: HubChip = { tone: "ok", key: "lg.hub.course.live" };
  switch (h.state) {
    case "cho_duyet":
      return h.live_version
        ? { chips: [live, { tone: "wait", key: "lg.hub.course.newWait" }], actions: ["withdraw", "remove"], why: null, oldVersion: true }
        : { chips: [{ tone: "wait", key: "lg.hub.course.wait" }], actions: ["withdraw"], why: null, oldVersion: false };
    case "tu_choi":
      return { chips: [{ tone: "err", key: "lg.hub.course.rejected" }], actions: ["edit"], why: h.reason, oldVersion: false };
    case "da_dang":
      return { chips: [live], actions: ["edit", "remove"], why: null, oldVersion: false };
    case "da_go":
      return { chips: [DRAFT], actions: ["continue"], why: null, oldVersion: false };
    case "rut_lai":
      return { chips: [DRAFT], actions: ["continue"], why: null, oldVersion: false };
  }
}

function statusChip(c: TeacherCourseSummary): HubChip {
  const s = statusTag(c);
  return { tone: s.tone, key: s.key, params: s.params };
}

