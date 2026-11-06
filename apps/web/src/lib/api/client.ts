import type { Progress, Recommendation, SessionSummary } from "../practice/progressTypes";
import type {
  ActivityEntry,
  ArchivedFilter,
  Conversation,
  ConversationHit,
  ConversationPatch,
  AppNotification,
  ChatHistoryEntry,
  ClientMessage,
  Engagement,
  GoogleCalendarStatus,
  HistoryEntry,
  Me,
  MobileToken,
  NotificationActionResult,
  OnboardingRequest,
  ParentLinkStart,
  ParentLinkStatus,
  ReportSummary,
  RequestLinkResponse,
  SandboxWarmResult,
  ServerMessage,
  SetupGuideState,
  TourPatch,
  TourState,
  VerifyCodeResponse,
  Settings,
  TreeEntry,
  UploadResult,
  VapidKey,
  WorkspaceFile,
} from "../types";
import type { PracticeApi } from "../practice/types";
import { HttpPractice } from "./practiceHttp";

/** Error from the gateway. `status` is the HTTP status (0 for network failures). */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isApiError(e: unknown, status?: number): e is ApiError {
  return e instanceof ApiError && (status === undefined || e.status === status);
}

export type ConnectionState = "connecting" | "open" | "closed";

export interface ChatSocketHandlers {
  onMessage: (msg: ServerMessage) => void;
  onConnectionChange?: (state: ConnectionState) => void;
}

export interface ChatSocket {
  send: (msg: ClientMessage) => boolean;
  close: () => void;
}

/** Everything the web app needs from the gateway (CONTRACTS.md section 5). */
export interface ApiClient {
  readonly mode: "http" | "mock";
  /** `/api/practice`: practice, mock exams, diagnostic, progress (CONTRACTS 10.3). */
  readonly practice: PracticeApi;

  requestLink(email: string): Promise<RequestLinkResponse>;
  /**
   * Completes a magic link. Real mode returns the gateway URL the browser must navigate to
   * (GET /auth/verify sets the cookie and redirects). Mock mode signs in directly and returns null.
   */
  verifyLink(token: string): Promise<string | null>;
  /** Signs in with the 6-digit code from the login email (sets the session cookie). */
  verifyCode(email: string, code: string): Promise<VerifyCodeResponse>;
  logout(): Promise<{ ok: true }>;
  getMe(): Promise<Me>;
  completeOnboarding(body: OnboardingRequest): Promise<Me>;

  startParentLink(): Promise<ParentLinkStart>;
  getParentLink(): Promise<ParentLinkStatus>;
  /** Dev only: pretend the parent consented on Zalo. */
  devVerifyParent(): Promise<void>;

  upload(file: File | Blob, filename?: string): Promise<UploadResult>;
  createMobileToken(): Promise<MobileToken>;
  mobileUpload(token: string, file: File | Blob, filename?: string): Promise<{ path: string }>;

  getTree(prefix?: string): Promise<TreeEntry[]>;
  getFile(path: string): Promise<WorkspaceFile>;
  putFile(path: string, content: string, baseSha: string): Promise<{ sha: string }>;
  deleteFile(path: string): Promise<{ ok: true }>;
  getHistory(path: string): Promise<HistoryEntry[]>;
  exportWorkspace(): Promise<Blob>;
  deleteAccount(): Promise<{ ok: true }>;

  getActivity(opts?: { limit?: number; before?: string }): Promise<ActivityEntry[]>;
  /** Visible messages of one day (Asia/Ho_Chi_Minh); default today. */
  getChatHistory(date?: string): Promise<ChatHistoryEntry[]>;
  getReports(): Promise<ReportSummary[]>;
  getSettings(): Promise<Settings>;
  putSettings(settings: Settings): Promise<Settings>;
  /** First-login setup guide: true = closed (kept server-side, every device), false = show it again. */
  setSetupGuideDismissed(dismissed: boolean): Promise<SetupGuideState>;
  /** First-run tour progress and seen tips, kept server-side (CONTRACTS 12). */
  getTour(): Promise<TourState>;
  updateTour(patch: TourPatch): Promise<TourState>;

  /** NCS only (403 for THPT). */
  getGoogleCalendar(): Promise<GoogleCalendarStatus>;
  /**
   * Starts the Google OAuth flow. Real mode returns the gateway URL the browser must navigate to (it redirects to
   * Google and back to /settings?calendar=connected|error). Mock mode connects directly and returns null.
   */
  connectGoogleCalendar(): Promise<string | null>;
  /** Revokes the grant at Google and forgets the tokens. */
  disconnectGoogleCalendar(): Promise<{ ok: true }>;

  /**
   * Starts the learner's sandbox in the background (chat/pop-up focus) so the first message skips the cold start.
   * Returns at once; progress arrives as sandbox_status on the chat socket. The gateway throttles it per learner.
   */
  warmSandbox(): Promise<SandboxWarmResult>;

  connectChat(handlers: ChatSocketHandlers): ChatSocket;

  // ---- interaction layer (CONTRACTS 9) ----

  /** Applies a nudge action (`open`, `snooze_1h`, `done`, `start_focus`, `answer:<x>`); `open` returns the prefill. */
  notificationAction(id: string, action: string): Promise<NotificationActionResult>;
  /** Recent notifications, newest first (the centre, and `?notification=<id>` from a push click). */
  getNotifications(limit?: number): Promise<AppNotification[]>;
  /** Streak, today's focus minutes and the week's progress. */
  getEngagement(): Promise<Engagement>;
  /** VAPID application server key (base64url); `enabled: false` = Web Push is off on this gateway. */
  getVapidPublicKey(): Promise<VapidKey & { subscribed_devices?: number }>;
  subscribePush(subscription: PushSubscriptionJSON, device?: string): Promise<{ ok: true }>;
  /** Removes this device (by endpoint), or every device of the learner when no endpoint is given. */
  unsubscribePush(endpoint?: string): Promise<{ ok: true }>;

  // ---- progress (CONTRACTS 10.3, P serves; W2 consumes) ----
  getProgress(subject?: string): Promise<Progress>;
  getRecommendations(subject?: string): Promise<Recommendation[]>;
  listPracticeSessions(opts?: { subject?: string; limit?: number }): Promise<SessionSummary[]>;

  // ---- conversations (CONTRACTS 10.5, S serves; W2 consumes) ----
  listConversations(archived?: ArchivedFilter): Promise<Conversation[]>;
  createConversation(body?: { title?: string; subject?: string | null }): Promise<Conversation>;
  updateConversation(id: string, patch: ConversationPatch): Promise<Conversation>;
  deleteConversation(id: string): Promise<{ ok: true }>;
  searchConversations(q: string): Promise<ConversationHit[]>;
  /** Transcript of one named conversation (`GET /chat/history?conversation_id=`, CONTRACTS 10.6). */
  getConversationHistory(id: string): Promise<ChatHistoryEntry[]>;
}

/** Normalises GET /push/vapid-public-key: `{enabled, public_key, subscribed_devices}` (older drafts: a bare key). */
export function vapidKeyFrom(body: unknown): VapidKey & { subscribed_devices?: number } {
  if (typeof body === "string") return { enabled: true, public_key: body };
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    const key = typeof b.public_key === "string" && b.public_key ? b.public_key : null;
    return {
      enabled: b.enabled === undefined ? key !== null : b.enabled === true && key !== null,
      public_key: key,
      subscribed_devices: typeof b.subscribed_devices === "number" ? b.subscribed_devices : undefined,
    };
  }
  return { enabled: false, public_key: null };
}

type Query = Record<string, string | number | undefined>;

function buildQuery(q?: Query): string {
  if (!q) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v !== undefined && v !== "") params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.detail === "string") return b.detail;
    if (typeof b.error === "string") return b.error;
    if (typeof b.message === "string") return b.message;
  }
  return `HTTP ${status}`;
}

export class HttpApiClient implements ApiClient {
  readonly mode = "http" as const;
  readonly practice: PracticeApi;
  private readonly base: string;

  constructor(base: string) {
    this.base = base.replace(/\/+$/, "");
    this.practice = new HttpPractice((method, path, opts) => this.request(method, path, opts));
  }

  private url(path: string, query?: Query): string {
    return `${this.base}${path}${buildQuery(query)}`;
  }

  private async request<T>(
    method: string,
    path: string,
    opts: { query?: Query; json?: unknown; form?: FormData; raw?: boolean } = {},
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    let body: BodyInit | undefined;
    if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.json);
    } else if (opts.form) {
      body = opts.form;
    }
    let res: Response;
    try {
      res = await fetch(this.url(path, opts.query), {
        method,
        headers,
        body,
        credentials: "include",
      });
    } catch (e) {
      throw new ApiError(0, "Không kết nối được tới máy chủ.", e);
    }
    if (!res.ok) {
      let errBody: unknown = undefined;
      try {
        errBody = await res.json();
      } catch {
        // non-JSON error body
      }
      throw new ApiError(res.status, errorMessage(errBody, res.status), errBody);
    }
    if (opts.raw) return (await res.blob()) as T;
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  requestLink(email: string) {
    return this.request<RequestLinkResponse>("POST", "/auth/request-link", { json: { email } });
  }

  async verifyLink(token: string) {
    return this.url("/auth/verify", { token });
  }

  verifyCode(email: string, code: string) {
    return this.request<VerifyCodeResponse>("POST", "/auth/verify-code", { json: { email, code } });
  }

  logout() {
    return this.request<{ ok: true }>("POST", "/auth/logout");
  }

  getMe() {
    return this.request<Me>("GET", "/me");
  }

  completeOnboarding(body: OnboardingRequest) {
    return this.request<Me>("POST", "/onboarding", { json: body });
  }

  startParentLink() {
    return this.request<ParentLinkStart>("POST", "/parent-link");
  }

  getParentLink() {
    return this.request<ParentLinkStatus>("GET", "/parent-link");
  }

  async devVerifyParent() {
    await this.request<unknown>("POST", "/dev/parent-link/verify");
  }

  upload(file: File | Blob, filename?: string) {
    const form = new FormData();
    form.append("file", file, filename ?? (file instanceof File ? file.name : "upload.bin"));
    return this.request<UploadResult>("POST", "/uploads", { form });
  }

  createMobileToken() {
    return this.request<MobileToken>("POST", "/uploads/mobile-token");
  }

  mobileUpload(token: string, file: File | Blob, filename?: string) {
    const form = new FormData();
    form.append("file", file, filename ?? (file instanceof File ? file.name : "upload.bin"));
    return this.request<{ path: string }>("POST", `/m/${encodeURIComponent(token)}`, { form });
  }

  getTree(prefix?: string) {
    return this.request<TreeEntry[]>("GET", "/workspace/tree", { query: { prefix } });
  }

  getFile(path: string) {
    return this.request<WorkspaceFile>("GET", "/workspace/file", { query: { path } });
  }

  putFile(path: string, content: string, baseSha: string) {
    return this.request<{ sha: string }>("PUT", "/workspace/file", {
      json: { path, content, base_sha: baseSha },
    });
  }

  deleteFile(path: string) {
    return this.request<{ ok: true }>("DELETE", "/workspace/file", { query: { path } });
  }

  getHistory(path: string) {
    return this.request<HistoryEntry[]>("GET", "/workspace/history", { query: { path } });
  }

  exportWorkspace() {
    return this.request<Blob>("GET", "/workspace/export", { raw: true });
  }

  deleteAccount() {
    return this.request<{ ok: true }>("DELETE", "/account");
  }

  getActivity(opts: { limit?: number; before?: string } = {}) {
    return this.request<ActivityEntry[]>("GET", "/activity", {
      query: { limit: opts.limit ?? 50, before: opts.before },
    });
  }

  getChatHistory(date?: string) {
    return this.request<ChatHistoryEntry[]>("GET", "/chat/history", { query: { date } });
  }

  getReports() {
    return this.request<ReportSummary[]>("GET", "/reports");
  }

  getSettings() {
    return this.request<Settings>("GET", "/settings");
  }

  putSettings(settings: Settings) {
    return this.request<Settings>("PUT", "/settings", { json: settings });
  }

  setSetupGuideDismissed(dismissed: boolean) {
    return this.request<SetupGuideState>("PUT", "/settings/setup-guide", { json: { dismissed } });
  }

  getTour() {
    return this.request<TourState>("GET", "/onboarding");
  }

  updateTour(patch: TourPatch) {
    return this.request<TourState>("PUT", "/onboarding", { json: patch });
  }

  getGoogleCalendar() {
    return this.request<GoogleCalendarStatus>("GET", "/integrations/google-calendar");
  }

  async connectGoogleCalendar() {
    return this.url("/integrations/google-calendar/connect");
  }

  disconnectGoogleCalendar() {
    return this.request<{ ok: true }>("DELETE", "/integrations/google-calendar");
  }

  warmSandbox() {
    return this.request<SandboxWarmResult>("POST", "/sandbox/warm");
  }

  connectChat(handlers: ChatSocketHandlers): ChatSocket {
    return new ReconnectingChatSocket(wsUrl(this.base), handlers);
  }

  notificationAction(id: string, action: string) {
    return this.request<NotificationActionResult>("POST", `/notifications/${encodeURIComponent(id)}/action`, { json: { action } });
  }

  getNotifications(limit = 30) {
    return this.request<AppNotification[]>("GET", "/notifications", { query: { limit } });
  }

  getEngagement() {
    return this.request<Engagement>("GET", "/engagement");
  }

  async getVapidPublicKey() {
    return vapidKeyFrom(await this.request<unknown>("GET", "/push/vapid-public-key"));
  }

  subscribePush(subscription: PushSubscriptionJSON, device?: string) {
    return this.request<{ ok: true }>("POST", "/push/subscribe", { json: device ? { subscription, device } : { subscription } });
  }

  unsubscribePush(endpoint?: string) {
    return this.request<{ ok: true }>("DELETE", "/push/subscribe", { json: endpoint ? { endpoint } : {} });
  }

  getProgress(subject?: string) {
    return this.request<Progress>("GET", "/practice/progress", { query: { subject } });
  }

  getRecommendations(subject?: string) {
    return this.request<Recommendation[]>("GET", "/practice/recommendations", { query: { subject } });
  }

  listPracticeSessions(opts: { subject?: string; limit?: number } = {}) {
    return this.request<SessionSummary[]>("GET", "/practice/sessions", { query: { subject: opts.subject, limit: opts.limit ?? 30 } });
  }

  listConversations(archived: ArchivedFilter = "false") {
    return this.request<Conversation[]>("GET", "/conversations", { query: { archived } });
  }

  createConversation(body: { title?: string; subject?: string | null } = {}) {
    return this.request<Conversation>("POST", "/conversations", { json: body });
  }

  updateConversation(id: string, patch: ConversationPatch) {
    return this.request<Conversation>("PATCH", `/conversations/${encodeURIComponent(id)}`, { json: patch });
  }

  deleteConversation(id: string) {
    return this.request<{ ok: true }>("DELETE", `/conversations/${encodeURIComponent(id)}`);
  }

  searchConversations(q: string) {
    return this.request<ConversationHit[]>("GET", "/conversations/search", { query: { q } });
  }

  getConversationHistory(id: string) {
    return this.request<ChatHistoryEntry[]>("GET", "/chat/history", { query: { conversation_id: id, limit: 300 } });
  }
}

/** ws(s):// URL for /ws/chat derived from the API base (absolute or relative). */
export function wsUrl(base: string): string {
  let abs = base;
  if (!/^https?:\/\//.test(base)) {
    const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
    abs = origin + (base.startsWith("/") ? base : `/${base}`);
  }
  return abs.replace(/^http/, "ws").replace(/\/+$/, "") + "/ws/chat";
}

/** WebSocket with JSON framing and exponential-backoff reconnects. */
class ReconnectingChatSocket implements ChatSocket {
  private ws: WebSocket | null = null;
  private closed = false;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly url: string,
    private readonly handlers: ChatSocketHandlers,
  ) {
    this.open();
  }

  private open() {
    if (this.closed) return;
    this.handlers.onConnectionChange?.("connecting");
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.handlers.onConnectionChange?.("open");
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      try {
        this.handlers.onMessage(JSON.parse(ev.data) as ServerMessage);
      } catch {
        // ignore malformed frames
      }
    };
    ws.onclose = () => {
      this.ws = null;
      this.handlers.onConnectionChange?.("closed");
      if (this.closed) return;
      const delay = Math.min(30_000, 1000 * 2 ** this.attempt++);
      this.timer = setTimeout(() => this.open(), delay);
    };
    ws.onerror = () => {
      ws.close();
    };
  }

  send(msg: ClientMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  close() {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
    this.ws = null;
  }
}
