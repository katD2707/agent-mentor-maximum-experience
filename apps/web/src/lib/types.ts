/**
 * Types for the gateway API (CONTRACTS.md section 5) and the shared Python schemas
 * in packages/mentor-schemas (activity.py, routines.py, sandbox_api.py).
 * Datetimes are ISO 8601 strings on the wire.
 */

export type Role = "thpt" | "ncs";
export type Language = "vi" | "en";
export type OnboardingState = "needs_role" | "needs_parent" | "active";

export interface Me {
  user_id: string;
  email: string;
  role: Role | null;
  display_name: string;
  language: Language;
  onboarding_state: OnboardingState;
  inbound_email_address: string | null;
  /**
   * When the learner closed the first-login setup guide; null = open it on the next visit.
   * Missing (undefined) on gateways older than the field: the guide then never opens by itself.
   */
  setup_guide_dismissed_at?: string | null;
  /** First-run tour progress and seen tips (CONTRACTS 12). Missing on older gateways: the tour never starts. */
  tour?: TourState;
}

export type TourStepId = "welcome" | "ask" | "practice" | "time";

/** GET/PUT /onboarding: where the learner is in the first-run tour (shared by the web app and the desktop pop-up). */
export interface TourState {
  /** where to resume; null = not started, or finished/skipped */
  tour_step: TourStepId | null;
  tour_completed_at: string | null;
  tour_skipped_at: string | null;
  /** ids of the one-time tips already shown */
  tips_seen: string[];
}

/** PUT /onboarding: one change per call. */
export type TourPatch = { step: TourStepId } | { complete: true } | { skip: true } | { restart: true } | { tip: string };

/** PUT /settings/setup-guide */
export interface SetupGuideState {
  setup_guide_dismissed_at: string | null;
}

export interface RequestLinkResponse {
  sent: true;
  dev_link?: string;
  /** dev only: the 6-digit login code from the same email */
  dev_code?: string;
}

/** POST /auth/verify-code: the session cookie is set; `next` is where the full web app would go. */
export interface VerifyCodeResponse {
  ok: true;
  next: "/chat" | "/onboarding";
}

export interface OnboardingRequest {
  role: Role;
  display_name: string;
  language: Language;
}

export interface ParentLinkStart {
  link_code: string;
  expires_at: string;
  bot_name: string;
  /** null when the gateway has no ZALO_BOT_URL configured */
  bot_url: string | null;
  /** MENTOR_ENV=dev: the gateway accepts POST /dev/parent-link/verify */
  dev_verify?: boolean;
}

export type ParentLinkState = "none" | "pending" | "awaiting_consent" | "verified";

export interface ParentLinkStatus {
  status: ParentLinkState;
  expires_at?: string | null;
}

export interface UploadResult {
  path: string;
  mime_type: string;
}

export interface MobileToken {
  upload_url: string;
  expires_at: string;
}

export interface TreeEntry {
  path: string;
  type: "file" | "dir";
  size: number;
  modified_at: string;
}

export interface WorkspaceFile {
  path: string;
  content: string;
  sha: string;
}

export type Author = "mentor" | "user" | "system";

export interface HistoryEntry {
  sha: string;
  author: Author;
  ts: string;
  message: string;
}

/** mentor_schemas.activity.ActivityEntry */
export interface ActivityEntry {
  ts: string;
  actor: Author;
  action: string;
  target?: string | null;
  summary: string;
  session_id?: string | null;
  job_id?: string | null;
}

export interface ReportSummary {
  path: string;
  period_start: string;
  period_end: string;
  sent_at?: string | null;
}

/** mentor_schemas.routines.ProactivityLevel */
export type ProactivityLevel = "off" | "normal" | "high";

/** mentor_schemas.routines.Routine */
export interface Routine {
  id: string;
  enabled: boolean;
  cron: string;
  job_kind: string;
  prompt?: string | null;
  user_editable: boolean;
}

/** mentor_schemas.routines.RoutinesFile (timezone omitted by the settings endpoint). */
export interface RoutinesFile {
  timezone?: string;
  proactivity: ProactivityLevel;
  quiet_hours: [string, string];
  routines: Routine[];
}

/** GET /integrations/google-calendar (NCS only). `available` is false when the gateway has no Google OAuth client. */
export interface GoogleCalendarStatus {
  available: boolean;
  connected: boolean;
  /** the connected Google account */
  email: string | null;
  scopes: string[];
}

export interface Settings {
  proactivity: ProactivityLevel;
  quiet_hours: [string, string];
  language: Language;
  routines: Routine[];
}

/** mentor_schemas.sandbox_api.ApprovalRequest */
export interface ApprovalRequest {
  approval_id: string;
  action: string;
  summary: string;
  details: Record<string, unknown>;
  expires_at: string;
}

export type ApprovalDecisionValue = "approve" | "deny";
export type ApprovalScope = "once" | "session";

export type SandboxState = "sleeping" | "waking" | "ready" | "busy";

/** POST /sandbox/warm. `warming` is true when a start was launched or is already in flight. */
export interface SandboxWarmResult {
  state: SandboxState;
  warming: boolean;
  result: "started" | "starting" | "already_running" | "busy" | "throttled" | "disabled" | "not_active" | "error";
}

export interface ChatAttachment {
  path: string;
  mime_type: string;
}

/**
 * GET /chat/history?date=YYYY-MM-DD (CONTRACTS "Sessions and chat history"). The harness stores
 * attachments as plain paths; objects are accepted too.
 */
export interface ChatHistoryEntry {
  ts: string;
  /** CONTRACTS 9 (Built H): cards are their own items `{ts, role: "card", card}`. */
  role: "user" | "mentor" | "card";
  text?: string;
  attachments?: (string | ChatAttachment)[];
  card?: ChatCard | null;
  /** On the turn's last mentor item: the quick replies (shown only when it is the newest item). */
  suggestions?: SuggestionItem[];
  /** On a user item created by a card click; `text` is then the echo. */
  card_action?: { card_id: string; kind: string; action: string; value?: string | null };
}

// ---- Interaction layer (CONTRACTS.md section 9) ----

/** States of the `<mentor-mascot>` custom element (packages/mentor-mascot). */
export type MascotState = "idle" | "listening" | "thinking" | "talking" | "happy" | "celebrate" | "sleepy" | "calm" | "wave";

export const MASCOT_STATES: readonly MascotState[] = [
  "idle",
  "listening",
  "thinking",
  "talking",
  "happy",
  "celebrate",
  "sleepy",
  "calm",
  "wave",
];

export interface SuggestionItem {
  label: string;
  text: string;
}

interface CardBase {
  /** `card-YYYYMMDD-<12 hex>`; a card event with a known id is an update of that card. */
  id: string;
  /** ISO with +07:00 */
  created_at: string;
}

export interface FlashcardCard extends CardBase {
  kind: "flashcard";
  skill: string;
  front: string;
  choices?: string[];
  reveal?: string;
}
export interface DeadlineCard extends CardBase {
  kind: "deadline";
  title: string;
  /** ISO, VN time */
  due_at: string;
  source?: string;
}
export interface FocusCard extends CardBase {
  kind: "focus";
  task: string;
  /** Total planned minutes (after an extension: the new total). */
  minutes: number;
  ends_at: string;
  /** Set once the session was ended (done early or on time). */
  ended_at?: string | null;
}
export interface CelebrationCard extends CardBase {
  kind: "celebration";
  title: string;
  detail?: string;
}
export interface WeeklyCard extends CardBase {
  kind: "weekly";
  focus_minutes: number;
  milestones_done: number;
  mistakes_fixed: number;
  streak_days: number;
  highlight?: string;
}
export interface CheckinCard extends CardBase {
  kind: "checkin";
  prompt: string;
  options: string[];
}

/** CONTRACTS 10.6 (S): opens the practice setup prefilled; nothing starts without the learner's click. */
export interface PracticeCard extends CardBase {
  kind: "practice";
  subject: string;
  minutes: number;
  goal?: "balanced" | "weak" | "challenge";
  topics?: string[];
  title: string;
  reason: string;
}
/** CONTRACTS 10.6 (S): opens the mock confirmation dialog. */
export interface MockCard extends CardBase {
  kind: "mock";
  subject: string;
  profile_id: string;
  title: string;
}

export type ChatCard = FlashcardCard | DeadlineCard | FocusCard | CelebrationCard | WeeklyCard | CheckinCard | PracticeCard | MockCard;
export type ChatCardKind = ChatCard["kind"];

export type NotificationKind = "checkin" | "deadline" | "review" | "focus_end" | "celebration" | "report" | "nudge";

/** Action ids: `open`, `snooze_1h`, `done`, `start_focus`, `answer:<x>`. */
export interface NotificationAction {
  id: string;
  label: string;
}

/** POST /notifications/{id}/action. `open` returns the chat prefill. */
export interface NotificationActionResult {
  ok?: boolean;
  action?: string;
  id?: number | string;
  prefill?: string | null;
  snoozed_until?: string;
  job_id?: string;
}

/** GET /notifications (CONTRACTS 9, Built N). */
export interface AppNotification {
  id: number | string;
  kind: NotificationKind;
  title: string;
  body: string;
  actions: NotificationAction[];
  mascot: MascotState | string;
  prefill: string | null;
  text: string;
  created_at: string;
  status?: string;
  delivered_at?: string | null;
  read_at?: string | null;
  answer?: string | null;
}

/** GET /engagement */
export interface Engagement {
  streak_days: number;
  today: { focus_minutes: number; done: number };
  week: { focus_minutes: number; milestones_done: number; mistakes_fixed: number; active_days: number };
}

/** GET /push/vapid-public-key; `enabled: false, public_key: null` when the gateway has no VAPID keys. */
export interface VapidKey {
  enabled?: boolean;
  public_key: string | null;
}

// ---- WebSocket /ws/chat ----

export type ClientMessage =
  | {
      type: "user_message";
      client_msg_id: string;
      text: string;
      attachments: ChatAttachment[];
      /** CONTRACTS 10.5: a named conversation (`c-<id>`); omitted = today's main chat. */
      conversation_id?: string;
    }
  | {
      type: "approval_decision";
      approval_id: string;
      decision: ApprovalDecisionValue;
      scope: ApprovalScope;
    }
  | {
      /**
       * CONTRACTS 9. `client_msg_id` is a W addition (optional for the gateway): if the gateway echoes it in the
       * `turn_done` of the turn it starts, the UI can match the two; the UI does not depend on it.
       */
      type: "card_action";
      card_id: string;
      action: string;
      value?: string;
      client_msg_id?: string;
      conversation_id?: string;
    };

/**
 * `notification` on the WebSocket. `text` is the old field (kept for compatibility); the rest is CONTRACTS 9 and
 * may be missing on an older gateway.
 */
export interface NotificationPayload {
  text: string;
  created_at: string;
  /** int on the gateway (Built N); kept as given. */
  id?: number | string;
  /** Several bundled into one (the fields are those of the most important). */
  bundled_ids?: number[];
  kind?: NotificationKind;
  title?: string;
  body?: string;
  actions?: NotificationAction[];
  mascot?: MascotState;
  prefill?: string | null;
}

export type ServerMessage =
  | { type: "sandbox_status"; state: SandboxState }
  | { type: "text_delta"; text: string }
  | { type: "tool_started"; tool: string; summary: string }
  | { type: "tool_finished"; tool: string; summary: string }
  | { type: "approval_request"; approval: ApprovalRequest }
  | { type: "turn_done"; client_msg_id: string }
  | ({ type: "notification" } & NotificationPayload)
  | { type: "suggestions"; client_msg_id?: string; items: SuggestionItem[] }
  | { type: "card"; card: ChatCard }
  /** The learner's bubble for a card click, sent before the click's turn starts (Built H). */
  | { type: "card_echo"; client_msg_id: string; card_id: string; action: string; value?: string | null; text: string }
  /** `card_id` set: a refused card click (no turn ran). */
  | { type: "error"; error: string; card_id?: string }
  /** Optional: a file arrived through the phone upload page (POST /m/{token}). */
  | { type: "upload_received"; path: string };

/** Paths the learner may write through PUT/DELETE /workspace/file. */
export const EDITABLE_PREFIXES = ["me/", "goals/", "learning/", "research/"] as const;

export function isUserEditable(path: string): boolean {
  return EDITABLE_PREFIXES.some((p) => path.startsWith(p)) && !path.split("/").includes("..");
}

// ---- Conversations (CONTRACTS 10.5, S) ----

/** `GET /conversations`. The main daily chat is not listed; the web adds it as the first entry. */
export interface Conversation {
  id: string;
  session_id?: string;
  title: string;
  subject?: string | null;
  created_at?: string;
  updated_at?: string;
  archived?: boolean;
}

/** `?archived=` of `GET /conversations`: active ones (default), archived ones, or both. */
export type ArchivedFilter = "false" | "true" | "all";

/** `PATCH /conversations/{id}`; `subject: null` clears the tag. */
export interface ConversationPatch {
  title?: string;
  subject?: string | null;
  archived?: boolean;
}

/** `GET /conversations/search?q=` hit; the web highlights `snippet` itself. */
export interface ConversationHit {
  conversation_id: string | null;
  session_id?: string;
  /** null for the daily chat (or an untitled conversation) */
  title?: string | null;
  date?: string;
  ts?: string;
  role?: "user" | "mentor";
  snippet: string;
}
