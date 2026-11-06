/**
 * Mascot state logic (CONTRACTS 9). Pure functions, so the rules are testable without a DOM:
 * - crisis context always wins and shows `calm` (never celebrate or play in a turn that looks crisis-related);
 * - a one-shot (`celebrate`, `wave`, `happy`) plays next;
 * - then the work the mentor is doing: `sleepy` sandbox, `thinking` tools, `talking` text, `listening` typing.
 */
import type { ConnectionState } from "./api/client";
import type { ApprovalRequest, MascotState, NotificationKind, SandboxState } from "./types";
import { MASCOT_STATES } from "./types";

/**
 * Replies that point the learner at support lines, or talk about self-harm, put the turn in crisis context.
 * Deliberately broad: a false positive only makes the mascot calm and skips confetti.
 */
const CRISIS_RE =
  /(đường dây nóng|đường dây hỗ trợ|tổng đài (tư vấn|hỗ trợ|bảo vệ)|hotline|crisis line|tự tử|tự sát|tự (làm )?hại|hại bản thân|self[- ]harm|suicid|khủng hoảng|(gọi|số|tổng đài)\s*(ngay\s*)?(111|113|115)(?!\d))/iu;

export function isCrisisText(text: string): boolean {
  return CRISIS_RE.test(text);
}

const CRISIS_ACTION_RE = /crisis|safety|khủng hoảng|an toàn/i;

/** An approval raised by the safety flow (e.g. `flag_crisis`, `safety.*`). */
export function isCrisisApproval(a: Pick<ApprovalRequest, "action" | "summary">): boolean {
  return CRISIS_ACTION_RE.test(a.action) || CRISIS_ACTION_RE.test(a.summary);
}

export interface MascotInput {
  connection: ConnectionState;
  sandbox: SandboxState | null;
  /** A tool is running in the current turn. */
  toolsRunning: boolean;
  /** Reply text is streaming. */
  streaming: boolean;
  /** A turn is in flight (sent, no reply text yet). */
  inFlight: boolean;
  /** The learner is typing in the composer. */
  composing: boolean;
  /** The current turn looks crisis-related. */
  crisis: boolean;
  /** A transient one-shot (celebrate / wave / happy) still playing. */
  oneShot: MascotState | null;
}

const PLAYFUL: ReadonlySet<MascotState> = new Set(["celebrate", "happy", "wave"]);

export function deriveMascotState(i: MascotInput): MascotState {
  if (i.crisis) return "calm";
  if (i.oneShot && PLAYFUL.has(i.oneShot)) return i.oneShot;
  if (i.connection === "closed" || i.sandbox === "sleeping") return "sleepy";
  if (i.toolsRunning) return "thinking";
  if (i.streaming) return "talking";
  if (i.inFlight || i.sandbox === "waking") return "thinking";
  if (i.composing) return "listening";
  return "idle";
}

/** Server hints (notifications) are untrusted strings: keep only known states. */
export function sanitizeMascot(s: unknown, fallback: MascotState = "idle"): MascotState {
  return typeof s === "string" && (MASCOT_STATES as readonly string[]).includes(s) ? (s as MascotState) : fallback;
}

/** How long a one-shot state lasts when the element does not report `mascot-done` (the fallback mark). */
export const ONE_SHOT_MS: Partial<Record<MascotState, number>> = { celebrate: 2200, wave: 1600, happy: 3500 };

/** Default mascot per notification kind when the sender gave none (Built N). */
export function mascotForKind(kind: NotificationKind | string | undefined): MascotState {
  switch (kind) {
    case "checkin":
      return "wave";
    case "review":
    case "focus_end":
      return "happy";
    case "celebration":
      return "celebrate";
    default:
      return "idle";
  }
}
