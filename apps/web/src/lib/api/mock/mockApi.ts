import { ApiError, type ApiClient, type ChatSocket, type ChatSocketHandlers } from "../client";
import type {
  ActivityEntry,
  AppNotification,
  Author,
  ChatCard,
  ChatHistoryEntry,
  ArchivedFilter,
  Conversation,
  ConversationHit,
  ConversationPatch,
  Engagement,
  GoogleCalendarStatus,
  HistoryEntry,
  Me,
  MobileToken,
  NotificationActionResult,
  NotificationKind,
  NotificationPayload,
  OnboardingRequest,
  ParentLinkStart,
  ParentLinkState,
  ParentLinkStatus,
  ReportSummary,
  RequestLinkResponse,
  Role,
  SandboxWarmResult,
  SetupGuideState,
  TourPatch,
  TourState,
  VerifyCodeResponse,
  Settings,
  TreeEntry,
  UploadResult,
  WorkspaceFile,
} from "../../types";
import { isUserEditable } from "../../types";
import { fakeSha, isoLocal, localDateStamp, randomId } from "../../format";
import { buildZip } from "../../zip";
import { buildSeed, routinesYaml, sessionPath, type Persona } from "./seed";
import { mascotForKind } from "../../mascot";
import { isQuietNow } from "../../quietHours";
import { MockChatSocket } from "./mockChat";
import { MockPractice } from "./mockPractice";
import { MockConversations } from "./mockConversations";
import { mockProgress, mockRecommendations, mockSessions } from "./mockProgress";
import type { Progress, Recommendation, SessionSummary } from "../../practice/progressTypes";

const STORAGE_KEY = "mentor-mock-state-v1";
const ACTIVITY_PATH = ".mentor/activity.jsonl";
const PARENT_PENDING_MS = 6000;
const PARENT_CONSENT_MS = 12000;

interface MockFile {
  content: string;
  sha: string;
  modified_at: string;
  /** Newest first. */
  history: HistoryEntry[];
}

export interface MockState {
  version: 1;
  persona: Persona;
  loggedIn: boolean;
  pendingTokens: Record<string, string>;
  /** email -> newest 6-digit code and the magic-link token it belongs to (optional: older saved states lack it) */
  pendingCodes?: Record<string, { code: string; token: string; attempts: number }>;
  me: Me;
  files: Record<string, MockFile>;
  activity: ActivityEntry[];
  reports: ReportSummary[];
  settings: Settings;
  parentLink: { code: string; expires_at: string; started_at: number; forced?: ParentLinkState } | null;
  autoParentVerify: boolean;
  mobileTokens: Record<string, string>;
  /** Connected Google account (optional: older saved states lack it). */
  googleCalendar?: { email: string } | null;
  /** Interaction layer (CONTRACTS 9; optional: older saved states lack it). */
  engagement?: { date: string; focusMinutes: number; done: number; milestones: number };
  push?: PushSubscriptionJSON | null;
}

/** A valid P-256 public key (base64url) so PushManager.subscribe accepts it in mock mode. Not a secret. */
export const MOCK_VAPID_PUBLIC_KEY = "BOMUsiQ_zRFnC6Qg6JRJA_QDA0AhmK2snyUdpE6ITxG_t1rottYcI06ZekBPxUZJegkXP2itzYxNM-7kVssWgpw";

export interface MockOptions {
  /** Where to persist state between page loads; null keeps it in memory only. */
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  /** Simulated network latency per call. */
  latencyMs?: number;
  /** Multiplier for chat timings (0 = as fast as possible, for tests). */
  chatSpeed?: number;
  now?: () => number;
  origin?: string;
  persona?: Persona;
}

function commitSha(path: string, content: string, ts: string, n: number): string {
  return fakeSha(`${path}\u0000${content}\u0000${ts}\u0000${n}`);
}

function hiddenPath(path: string): boolean {
  if (path === ACTIVITY_PATH) return false;
  return path === ".git" || path.startsWith(".git/") || path === ".mentor" || path.startsWith(".mentor/");
}

function sanitizeName(name: string): string {
  const base = name.split(/[\\/]/).pop() || "tep";
  return (
    base
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      .replace(/[^A-Za-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "tep"
  );
}

export class MockApiClient implements ApiClient {
  readonly mode = "mock" as const;
  /** Fake `/api/practice` (own small bank; persists in the same storage under its own key). */
  readonly practice: MockPractice;
  state: MockState;
  private readonly opts: Required<Omit<MockOptions, "storage" | "persona">> & {
    storage: MockOptions["storage"];
  };
  private commitCounter = 0;
  private listeners = new Set<() => void>();
  /** Open fake chat sockets, so phone uploads can announce themselves. */
  private sockets = new Set<MockChatSocket>();
  /** Bumped on every state change (snapshot for useSyncExternalStore). */
  version = 0;
  /** Notifications sent in this page load, newest first (GET /notifications, POST .../action). In memory only. */
  private notifications: AppNotification[] = [];
  private nextNotificationId = 1;
  /** Cards shown in this page load, by id (for card_action). */
  readonly cards = new Map<string, ChatCard>();
  /** Named conversations (CONTRACTS 10.5). `activeConversation` = target of the turn now running (set by the socket). */
  readonly conversations: MockConversations;
  activeConversation: string | null = null;

  constructor(options: MockOptions = {}) {
    this.opts = {
      storage: options.storage ?? null,
      latencyMs: options.latencyMs ?? 0,
      chatSpeed: options.chatSpeed ?? 1,
      now: options.now ?? (() => Date.now()),
      origin: options.origin ?? (typeof window !== "undefined" ? window.location.origin : "http://localhost:3000"),
    };
    this.conversations = new MockConversations(this.opts.storage ?? null, this.opts.now);
    this.practice = new MockPractice({ storage: options.storage ?? null, now: this.opts.now, latencyMs: this.opts.latencyMs });
    const loaded = this.load();
    this.state = loaded ?? MockApiClient.freshState(options.persona ?? "thpt", this.opts.now());
  }

  // ------------------------------------------------------------------ state

  static freshState(persona: Persona, nowMs: number): MockState {
    const userId = "u_" + fakeSha(persona + nowMs).slice(0, 10);
    const me: Me = {
      user_id: userId,
      email: persona === "ncs" ? "duc.tran@example.edu.vn" : "lananh.nguyen@example.com",
      role: null,
      display_name: "",
      language: "vi",
      onboarding_state: "needs_role",
      inbound_email_address: null,
      setup_guide_dismissed_at: null,
      tour: { tour_step: null, tour_completed_at: null, tour_skipped_at: null, tips_seen: [] },
    };
    const state: MockState = {
      version: 1,
      persona,
      loggedIn: false,
      pendingTokens: {},
      me,
      files: {},
      activity: [],
      reports: [],
      settings: { proactivity: "normal", quiet_hours: ["22:00", "07:00"], language: "vi", routines: [] },
      parentLink: null,
      autoParentVerify: true,
      mobileTokens: {},
    };
    if (persona !== "new") MockApiClient.provision(state, persona, undefined);
    return state;
  }

  private static provision(state: MockState, role: Role, displayName: string | undefined) {
    const seed = buildSeed(role, displayName);
    let n = 0;
    state.files = {};
    for (const [path, f] of Object.entries(seed.files)) {
      const history: HistoryEntry[] = f.commits
        .map((c) => ({ sha: commitSha(path, c.message, c.ts, n++), author: c.author, ts: c.ts, message: c.message }))
        .reverse();
      state.files[path] = {
        content: f.content,
        sha: fakeSha(f.content),
        modified_at: f.commits[f.commits.length - 1].ts,
        history,
      };
    }
    state.activity = [...seed.activity].sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
    state.reports = seed.reports;
    state.settings = { ...seed.settings, language: state.me.language };
    state.me.role = role;
    state.me.display_name = seed.displayName;
    state.me.inbound_email_address = `${state.me.user_id.replace(/^u_/, "")}@inbox.mentor.local`;
    state.me.onboarding_state = "active";
  }

  private load(): MockState | null {
    const s = this.opts.storage;
    if (!s) return null;
    try {
      const raw = s.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as MockState;
      if (parsed.version !== 1) return null;
      parsed.me.setup_guide_dismissed_at ??= null; // states saved before the setup guide existed
      // saved before the tour existed: do not start it for a learner who was already using the app
      parsed.me.tour ??= { tour_step: null, tour_completed_at: null, tour_skipped_at: new Date().toISOString(), tips_seen: [] };
      return parsed;
    } catch {
      return null;
    }
  }

  private save() {
    try {
      this.opts.storage?.setItem(STORAGE_KEY, JSON.stringify(this.state));
    } catch {
      // storage full or unavailable: keep going in memory
    }
    this.version++;
    for (const l of this.listeners) l();
  }

  /** Subscribe to state changes (used by the mock settings panel). */
  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private nowIso(): string {
    return isoLocal(new Date(this.opts.now()));
  }

  private async delay() {
    if (this.opts.latencyMs > 0) await new Promise((r) => setTimeout(r, this.opts.latencyMs));
  }

  private requireSession() {
    if (!this.state.loggedIn) throw new ApiError(401, "Chưa đăng nhập.");
  }

  private requireActive() {
    this.requireSession();
    if (this.state.me.onboarding_state !== "active") {
      throw new ApiError(409, "Tài khoản chưa hoàn tất onboarding.");
    }
  }

  // ------------------------------------------------------------ mock controls

  /** Replace everything with a fresh persona. Keeps the session if one exists. */
  resetPersona(persona: Persona, keepLoggedIn = true) {
    const wasLoggedIn = this.state.loggedIn;
    this.state = MockApiClient.freshState(persona, this.opts.now());
    this.state.loggedIn = keepLoggedIn && wasLoggedIn;
    this.save();
  }

  setAutoParentVerify(on: boolean) {
    this.state.autoParentVerify = on;
    this.save();
  }

  /** Move the parent link one step forward (pending → awaiting_consent → verified). */
  advanceParentLink() {
    const pl = this.state.parentLink;
    if (!pl) return;
    const cur = this.parentStatus();
    pl.forced = cur === "pending" ? "awaiting_consent" : "verified";
    this.parentStatus();
    this.save();
  }

  // ------------------------------------------------------------ files (internal)

  private writeFile(path: string, content: string, author: Author, message: string) {
    const ts = this.nowIso();
    const prev = this.state.files[path];
    const entry: HistoryEntry = { sha: commitSha(path, content, ts, ++this.commitCounter), author, ts, message };
    this.state.files[path] = {
      content,
      sha: fakeSha(content),
      modified_at: ts,
      history: [entry, ...(prev?.history ?? [])],
    };
  }

  addActivity(e: Omit<ActivityEntry, "ts"> & { ts?: string }) {
    this.state.activity.unshift({ ts: e.ts ?? this.nowIso(), ...e });
    this.save();
  }

  /** Used by the fake mentor to change memory during a chat turn. */
  mentorEdit(path: string, transform: (old: string) => string, message: string) {
    const old = this.state.files[path]?.content ?? "";
    this.writeFile(path, transform(old), "mentor", message);
    this.save();
  }

  /** Append one visible message to today's session transcript (what the harness writes). */
  appendChat(entry: ChatHistoryEntry) {
    if (this.activeConversation) {
      this.conversations.append(this.activeConversation, entry);
      return;
    }
    const path = sessionPath(localDateStamp(new Date(this.opts.now())));
    const old = this.state.files[path]?.content ?? "";
    this.writeFile(path, old + JSON.stringify(entry) + "\n", "mentor", "Lưu transcript phiên");
    this.save();
  }

  /** A card was updated (focus extended/ended): history keeps it once, at its first position, newest content. */
  replaceChatCard(card: ChatCard) {
    const path = sessionPath(localDateStamp(new Date(this.opts.now())));
    const f = this.state.files[path];
    if (!f) return;
    const lines = f.content.split("\n").map((l) => {
      try {
        const e = JSON.parse(l) as ChatHistoryEntry;
        return e.card?.id === card.id ? JSON.stringify({ ...e, card }) : l;
      } catch {
        return l;
      }
    });
    this.writeFile(path, lines.join("\n"), "mentor", "Cập nhật thẻ");
    this.save();
  }

  nowIsoLocal(): string {
    return this.nowIso();
  }

  private activityJsonl(): string {
    return [...this.state.activity]
      .reverse()
      .map((a) => JSON.stringify(a))
      .join("\n") + "\n";
  }

  // ------------------------------------------------------------------ auth

  async requestLink(email: string): Promise<RequestLinkResponse> {
    await this.delay();
    const e = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) throw new ApiError(422, "Email không hợp lệ.");
    const token = randomId("mock_");
    const code = String(Math.floor(Math.random() * 1_000_000)).padStart(6, "0");
    this.state.pendingTokens[token] = e;
    (this.state.pendingCodes ??= {})[e.toLowerCase()] = { code, token, attempts: 0 };
    this.save();
    return { sent: true, dev_link: `${this.opts.origin}/login/verify?token=${token}`, dev_code: code };
  }

  async verifyCode(email: string, code: string): Promise<VerifyCodeResponse> {
    await this.delay();
    const e = email.trim().toLowerCase();
    const c = code.replace(/\s+/g, "");
    if (!/^\d{6}$/.test(c)) throw new ApiError(422, "Mã đăng nhập gồm 6 chữ số.");
    const pending = this.state.pendingCodes?.[e];
    if (!pending || !this.state.pendingTokens[pending.token]) throw new ApiError(400, "code invalid or expired");
    if (pending.code !== c) {
      pending.attempts += 1;
      if (pending.attempts >= 5) delete this.state.pendingTokens[pending.token];
      this.save();
      throw new ApiError(400, "code invalid or expired");
    }
    delete this.state.pendingTokens[pending.token];
    delete this.state.pendingCodes![e];
    this.state.loggedIn = true;
    this.state.me.email = email.trim();
    this.save();
    return { ok: true, next: this.state.me.onboarding_state === "active" ? "/chat" : "/onboarding" };
  }

  async verifyLink(token: string): Promise<string | null> {
    await this.delay();
    const email = this.state.pendingTokens[token];
    if (!email) throw new ApiError(400, "Liên kết không hợp lệ hoặc đã được dùng.");
    delete this.state.pendingTokens[token];
    this.state.loggedIn = true;
    this.state.me.email = email;
    this.save();
    return null;
  }

  async logout() {
    await this.delay();
    this.state.loggedIn = false;
    this.save();
    return { ok: true as const };
  }

  async getMe(): Promise<Me> {
    await this.delay();
    this.requireSession();
    if (this.state.me.onboarding_state === "needs_parent") this.parentStatus();
    return structuredClone(this.state.me);
  }

  async completeOnboarding(body: OnboardingRequest): Promise<Me> {
    await this.delay();
    this.requireSession();
    if (body.role !== "thpt" && body.role !== "ncs") throw new ApiError(422, "Vai trò không hợp lệ.");
    const name = body.display_name.trim();
    if (!name) throw new ApiError(422, "Cần nhập tên hiển thị.");
    this.state.me.language = body.language;
    MockApiClient.provision(this.state, body.role, name);
    this.state.me.onboarding_state = body.role === "thpt" ? "needs_parent" : "active";
    this.save();
    return structuredClone(this.state.me);
  }

  // ------------------------------------------------------------ parent link

  private parentStatus(): ParentLinkState {
    const pl = this.state.parentLink;
    if (!pl) return "none";
    let status: ParentLinkState = pl.forced ?? "pending";
    if (this.state.autoParentVerify && !pl.forced) {
      const elapsed = this.opts.now() - pl.started_at;
      status = elapsed >= PARENT_CONSENT_MS ? "verified" : elapsed >= PARENT_PENDING_MS ? "awaiting_consent" : "pending";
    }
    if (status === "verified" && this.state.me.onboarding_state === "needs_parent") {
      this.state.me.onboarding_state = "active";
      this.state.activity.unshift({
        ts: this.nowIso(),
        actor: "system",
        action: "parent_link_verified",
        target: null,
        summary: "Phụ huynh đã đồng ý liên kết qua Zalo.",
      });
      this.save();
    }
    return status;
  }

  async startParentLink(): Promise<ParentLinkStart> {
    await this.delay();
    this.requireSession();
    if (this.state.me.role !== "thpt") throw new ApiError(400, "Chỉ học sinh THPT cần liên kết phụ huynh.");
    const code = String(100000 + Math.floor(Math.random() * 900000));
    const expires_at = new Date(this.opts.now() + 24 * 3600_000).toISOString();
    this.state.parentLink = { code, expires_at, started_at: this.opts.now() };
    this.save();
    return { link_code: code, expires_at, bot_name: "Mentor Phụ huynh", bot_url: "https://zalo.me/mentor-phu-huynh-demo" };
  }

  async getParentLink(): Promise<ParentLinkStatus> {
    await this.delay();
    this.requireSession();
    const status = this.parentStatus();
    return { status, expires_at: this.state.parentLink?.expires_at ?? null };
  }

  async devVerifyParent(): Promise<void> {
    await this.delay();
    this.requireSession();
    if (!this.state.parentLink) throw new ApiError(400, "Chưa có mã liên kết.");
    this.state.parentLink.forced = "verified";
    this.save();
  }

  // ------------------------------------------------------------------ uploads

  private async storeUpload(file: File | Blob, filename: string | undefined, actor: Author): Promise<UploadResult> {
    const name = sanitizeName(filename ?? (file instanceof File ? file.name : "anh-dan.png"));
    const mime = file.type || "application/octet-stream";
    let path = `inbox/${localDateStamp(new Date(this.opts.now()))}-${name}`;
    for (let i = 2; this.state.files[path]; i++) path = path.replace(/(\.[^.]*)?$/, `-${i}$1`);
    const isText = mime.startsWith("text/") || /json|markdown|yaml/.test(mime);
    let content: string;
    if (isText && file.size < 200_000) {
      content = await file.text();
    } else {
      content = `[Tệp nhị phân ${name}, ${file.size} byte, ${mime}. Bản mock không lưu nội dung.]\n`;
    }
    this.writeFile(path, content, actor, `Tải lên ${name}`);
    this.addActivity({ actor, action: "upload", target: path, summary: `Tải lên tệp ${name}.` });
    return { path, mime_type: mime };
  }

  async upload(file: File | Blob, filename?: string): Promise<UploadResult> {
    await this.delay();
    this.requireActive();
    if (file.size > 25 * 1024 * 1024) throw new ApiError(413, "Tệp quá lớn (tối đa 25 MB).");
    return this.storeUpload(file, filename, "user");
  }

  async createMobileToken(): Promise<MobileToken> {
    await this.delay();
    this.requireActive();
    const token = randomId("m");
    const expires_at = new Date(this.opts.now() + 15 * 60_000).toISOString();
    this.state.mobileTokens[token] = expires_at;
    this.save();
    return { upload_url: `${this.opts.origin}/m/${token}`, expires_at };
  }

  async mobileUpload(token: string, file: File | Blob, filename?: string) {
    await this.delay();
    const exp = this.state.mobileTokens[token];
    if (!exp || Date.parse(exp) < this.opts.now()) throw new ApiError(410, "Mã tải lên đã hết hạn.");
    const r = await this.storeUpload(file, filename, "user");
    for (const s of this.sockets) s.announceUpload(r.path);
    return { path: r.path };
  }

  // ---------------------------------------------------------------- workspace

  async getTree(prefix?: string): Promise<TreeEntry[]> {
    await this.delay();
    this.requireActive();
    const files: TreeEntry[] = Object.entries(this.state.files)
      .filter(([p]) => !hiddenPath(p))
      .map(([path, f]) => ({ path, type: "file" as const, size: new TextEncoder().encode(f.content).length, modified_at: f.modified_at }));
    files.push({
      path: ACTIVITY_PATH,
      type: "file",
      size: new TextEncoder().encode(this.activityJsonl()).length,
      modified_at: this.state.activity[0]?.ts ?? this.nowIso(),
    });
    const dirs = new Map<string, TreeEntry>();
    for (const f of files) {
      const parts = f.path.split("/");
      for (let i = 1; i < parts.length; i++) {
        const d = parts.slice(0, i).join("/");
        const prev = dirs.get(d);
        if (!prev || prev.modified_at < f.modified_at) dirs.set(d, { path: d, type: "dir", size: 0, modified_at: f.modified_at });
      }
    }
    let all = [...dirs.values(), ...files];
    if (prefix) {
      const p = prefix.replace(/\/+$/, "");
      all = all.filter((e) => e.path === p || e.path.startsWith(p + "/")).filter((e) => e.path !== p);
    }
    return all.sort((a, b) => a.path.localeCompare(b.path));
  }

  async getFile(path: string): Promise<WorkspaceFile> {
    await this.delay();
    this.requireActive();
    if (path === ACTIVITY_PATH) {
      const content = this.activityJsonl();
      return { path, content, sha: fakeSha(content) };
    }
    if (hiddenPath(path)) throw new ApiError(403, "Không được phép xem tệp này.");
    const f = this.state.files[path];
    if (!f) throw new ApiError(404, "Không tìm thấy tệp.");
    return { path, content: f.content, sha: f.sha };
  }

  async putFile(path: string, content: string, baseSha: string): Promise<{ sha: string }> {
    await this.delay();
    this.requireActive();
    if (!isUserEditable(path)) throw new ApiError(403, "Chỉ được sửa tệp trong me/, goals/, learning/, research/.");
    const cur = this.state.files[path];
    if ((cur && cur.sha !== baseSha) || (!cur && baseSha)) {
      throw new ApiError(409, "Tệp đã thay đổi kể từ khi bạn mở.", { detail: "stale base_sha", current_sha: cur?.sha ?? null });
    }
    this.writeFile(path, content, "user", `Người học sửa ${path}`);
    this.addActivity({ actor: "user", action: "write_file", target: path, summary: `Bạn đã sửa ${path}.` });
    return { sha: this.state.files[path].sha };
  }

  async deleteFile(path: string) {
    await this.delay();
    this.requireActive();
    if (!isUserEditable(path)) throw new ApiError(403, "Chỉ được xoá tệp trong me/, goals/, learning/, research/.");
    if (!this.state.files[path]) throw new ApiError(404, "Không tìm thấy tệp.");
    delete this.state.files[path];
    this.addActivity({ actor: "user", action: "delete_file", target: path, summary: `Bạn đã xoá ${path}.` });
    return { ok: true as const };
  }

  async getHistory(path: string): Promise<HistoryEntry[]> {
    await this.delay();
    this.requireActive();
    const f = this.state.files[path];
    if (f) return structuredClone(f.history);
    const p = path.replace(/\/+$/, "");
    const merged: HistoryEntry[] = [];
    for (const [fp, file] of Object.entries(this.state.files)) {
      if (!fp.startsWith(p + "/")) continue;
      for (const h of file.history) merged.push({ ...h, message: `${fp}: ${h.message}` });
    }
    if (merged.length === 0 && !p) throw new ApiError(404, "Không có lịch sử.");
    return merged.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
  }

  async exportWorkspace(): Promise<Blob> {
    await this.delay();
    this.requireActive();
    const enc = new TextEncoder();
    const entries = Object.entries(this.state.files)
      .filter(([p]) => !hiddenPath(p))
      .map(([path, f]) => ({ path, data: enc.encode(f.content) }));
    entries.push({ path: ACTIVITY_PATH, data: enc.encode(this.activityJsonl()) });
    const bytes = buildZip(entries);
    return new Blob([bytes.buffer as ArrayBuffer], { type: "application/zip" });
  }

  async deleteAccount() {
    await this.delay();
    this.requireSession();
    this.state = MockApiClient.freshState("new", this.opts.now());
    this.save();
    return { ok: true as const };
  }

  // ------------------------------------------------------------ activity etc.

  async getActivity(opts: { limit?: number; before?: string } = {}): Promise<ActivityEntry[]> {
    await this.delay();
    this.requireActive();
    const limit = Math.max(1, Math.min(200, opts.limit ?? 50));
    const before = opts.before ? Date.parse(opts.before) : Infinity;
    return structuredClone(this.state.activity.filter((a) => Date.parse(a.ts) < before).slice(0, limit));
  }

  async getChatHistory(date?: string): Promise<ChatHistoryEntry[]> {
    await this.delay();
    this.requireActive();
    const d = date ?? localDateStamp(new Date(this.opts.now()));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) throw new ApiError(422, "Ngày phải có dạng YYYY-MM-DD.");
    const f = this.state.files[sessionPath(d)];
    if (!f) return [];
    return f.content
      .split("\n")
      .filter(Boolean)
      .flatMap((l) => {
        try {
          return [JSON.parse(l) as ChatHistoryEntry];
        } catch {
          return [];
        }
      });
  }

  async getReports(): Promise<ReportSummary[]> {
    await this.delay();
    this.requireActive();
    if (this.state.me.role !== "thpt") return [];
    return structuredClone(this.state.reports);
  }

  // ------------------------------------------------------------ Google Calendar (NCS)

  private requireNcs() {
    this.requireActive();
    if (this.state.me.role !== "ncs") throw new ApiError(403, "Google Calendar chỉ dành cho NCS.");
  }

  async getGoogleCalendar(): Promise<GoogleCalendarStatus> {
    await this.delay();
    this.requireNcs();
    const gc = this.state.googleCalendar;
    return gc
      ? { available: true, connected: true, email: gc.email, scopes: ["openid", "https://www.googleapis.com/auth/calendar.events"] }
      : { available: true, connected: false, email: null, scopes: [] };
  }

  async connectGoogleCalendar(): Promise<string | null> {
    await this.delay();
    this.requireNcs();
    this.state.googleCalendar = { email: this.state.me.email };
    this.save();
    return null;
  }

  async disconnectGoogleCalendar() {
    await this.delay();
    this.requireNcs();
    this.state.googleCalendar = null;
    this.save();
    return { ok: true as const };
  }

  async getSettings(): Promise<Settings> {
    await this.delay();
    this.requireActive();
    return structuredClone({ ...this.state.settings, language: this.state.me.language });
  }

  async putSettings(next: Settings): Promise<Settings> {
    await this.delay();
    this.requireActive();
    const timeRe = /^([01]\d|2[0-3]):[0-5]\d$/;
    if (!["off", "normal", "high"].includes(next.proactivity)) throw new ApiError(422, "Mức chủ động không hợp lệ.");
    if (!timeRe.test(next.quiet_hours[0]) || !timeRe.test(next.quiet_hours[1])) {
      throw new ApiError(422, "Giờ yên lặng phải có dạng HH:MM.", { detail: "quiet_hours must be HH:MM" });
    }
    const cur = new Map(this.state.settings.routines.map((r) => [r.id, r]));
    for (const r of next.routines) {
      const old = cur.get(r.id);
      if (!old) continue; // a new learner routine, as the gateway allows
      const changed = old.enabled !== r.enabled || old.cron !== r.cron || (old.prompt ?? null) !== (r.prompt ?? null);
      if (!old.user_editable && changed) {
        throw new ApiError(422, `Routine ${r.id} không cho phép thay đổi.`, { detail: `routine ${r.id} is not user_editable` });
      }
    }
    const routines = this.state.settings.routines.map((old) => {
      const r = next.routines.find((x) => x.id === old.id);
      return r ? { ...old, enabled: r.enabled, cron: r.cron, prompt: r.prompt ?? null } : old;
    });
    for (const r of next.routines) if (!cur.has(r.id)) routines.push({ ...r, prompt: r.prompt ?? null, user_editable: true });
    this.state.settings = { proactivity: next.proactivity, quiet_hours: [...next.quiet_hours], language: next.language, routines };
    this.state.me.language = next.language;
    this.writeFile("routines.yaml", routinesYaml(this.state.settings), "user", "Cập nhật cài đặt");
    this.addActivity({ actor: "user", action: "settings", target: "routines.yaml", summary: "Bạn đã cập nhật cài đặt." });
    return this.getSettings();
  }

  async getTour(): Promise<TourState> {
    await this.delay();
    this.requireActive();
    return structuredClone(this.state.me.tour!);
  }

  async updateTour(patch: TourPatch): Promise<TourState> {
    await this.delay();
    this.requireActive();
    const t = (this.state.me.tour ??= { tour_step: null, tour_completed_at: null, tour_skipped_at: null, tips_seen: [] });
    const now = new Date(this.opts.now()).toISOString();
    if ("restart" in patch) {
      t.tour_completed_at = null;
      t.tour_skipped_at = null;
      t.tour_step = "welcome";
    } else if ("step" in patch) {
      if (!["welcome", "ask", "practice", "time"].includes(patch.step)) throw new ApiError(422, "Bước không hợp lệ.");
      t.tour_step = patch.step;
    } else if ("complete" in patch) {
      t.tour_step = null;
      t.tour_completed_at ??= now;
    } else if ("skip" in patch) {
      t.tour_step = null;
      t.tour_skipped_at ??= now;
    } else if ("tip" in patch) {
      if (!/^[a-z0-9_-]{1,40}$/.test(patch.tip)) throw new ApiError(422, "Mã mẹo không hợp lệ.");
      if (!t.tips_seen.includes(patch.tip) && t.tips_seen.length < 50) t.tips_seen = [...t.tips_seen, patch.tip];
    } else {
      throw new ApiError(422, "Không có gì để cập nhật.");
    }
    this.save();
    return structuredClone(t);
  }

  async setSetupGuideDismissed(dismissed: boolean): Promise<SetupGuideState> {
    await this.delay();
    this.requireSession();
    if (this.state.me.onboarding_state === "needs_role") throw new ApiError(409, "onboarding not finished");
    const me = this.state.me;
    if (!dismissed) me.setup_guide_dismissed_at = null;
    else me.setup_guide_dismissed_at ??= new Date(this.opts.now()).toISOString(); // first dismissal is kept
    this.save();
    return { setup_guide_dismissed_at: me.setup_guide_dismissed_at };
  }

  // ------------------------------------------------------------ interaction layer (CONTRACTS 9)

  get chatSpeed(): number {
    return this.opts.chatSpeed;
  }

  /** Quiet hours right now (mock: from settings, VN time). */
  inQuietHours(): boolean {
    return isQuietNow(this.state.settings.quiet_hours, this.opts.now());
  }

  /** Stores a notification like the gateway does and gives it an int id (Built N). */
  recordNotification(n: Omit<NotificationPayload, "id">): NotificationPayload & { id: number } {
    const id = this.nextNotificationId++;
    const rec: AppNotification = {
      id,
      kind: n.kind ?? "nudge",
      title: n.title ?? "",
      body: n.body ?? n.text,
      actions: n.actions ?? [],
      mascot: n.mascot ?? mascotForKind(n.kind),
      prefill: n.prefill ?? null,
      text: n.text,
      created_at: n.created_at,
      status: "delivered",
      delivered_at: n.created_at,
      read_at: null,
      answer: null,
    };
    this.notifications.unshift(rec);
    this.notifications = this.notifications.slice(0, 100);
    return { ...n, id, mascot: rec.mascot as NotificationPayload["mascot"] };
  }

  async getNotifications(limit = 30): Promise<AppNotification[]> {
    await this.delay();
    this.requireActive();
    return structuredClone(this.notifications.slice(0, Math.max(1, Math.min(100, limit))));
  }

  private engagementToday() {
    const date = localDateStamp(new Date(this.opts.now()));
    const e = this.state.engagement;
    if (!e || e.date !== date) {
      this.state.engagement = { date, focusMinutes: 0, done: 0, milestones: e?.milestones ?? 0 };
    }
    return this.state.engagement!;
  }

  /** The fake mentor records a finished focus session / milestone. */
  addFocusMinutes(minutes: number) {
    const e = this.engagementToday();
    e.focusMinutes += Math.max(0, Math.round(minutes));
    e.done += 1;
    this.save();
  }

  addMilestone() {
    this.engagementToday().milestones += 1;
    this.save();
  }

  async getEngagement(): Promise<Engagement> {
    await this.delay();
    this.requireActive();
    const e = this.engagementToday();
    const ncs = this.state.me.role === "ncs";
    const baseWeek = ncs ? 185 : 140;
    return {
      streak_days: ncs ? 6 : 4,
      today: { focus_minutes: e.focusMinutes, done: e.done },
      week: {
        focus_minutes: baseWeek + e.focusMinutes,
        milestones_done: (ncs ? 1 : 2) + e.milestones,
        mistakes_fixed: ncs ? 2 : 5,
        active_days: e.focusMinutes > 0 || e.done > 0 ? 5 : 4,
      },
    };
  }

  async notificationAction(id: string, action: string): Promise<NotificationActionResult> {
    await this.delay();
    this.requireActive();
    const n = this.notifications.find((x) => String(x.id) === String(id));
    if (!n) throw new ApiError(404, "Không tìm thấy thông báo.");
    const always = ["open", "done", "snooze_1h"];
    if (!always.includes(action) && !n.actions.some((a) => a.id === action)) {
      throw new ApiError(422, "Thông báo này không có lựa chọn đó.");
    }
    const label = n.actions.find((a) => a.id === action)?.label ?? action;
    this.addActivity({ actor: "user", action: "notification_action", target: String(n.id), summary: `Bạn chọn “${label}” cho thông báo “${n.title || n.text}”.` });
    const base = { ok: true, action, id: n.id };
    if (action === "snooze_1h") {
      n.status = "snoozed";
      // Mock: "an hour" is 60 s so the reschedule is visible.
      const until = new Date(this.opts.now() + 60_000 * this.opts.chatSpeed);
      setTimeout(() => {
        for (const sock of this.sockets) sock.redeliver(n);
      }, 60_000 * this.opts.chatSpeed);
      return { ...base, snoozed_until: until.toISOString() };
    }
    if (action === "start_focus") {
      for (const sock of this.sockets) sock.startFocusFromNudge(n.kind === "review" ? 15 : 25);
      return { ...base, job_id: randomId("job_") };
    }
    if (action.startsWith("answer:")) {
      n.answer = action.slice("answer:".length);
      return { ...base, job_id: randomId("job_") };
    }
    n.read_at = new Date(this.opts.now()).toISOString();
    if (action === "done") n.status = "dismissed";
    if (action === "open") return { ...base, prefill: n.prefill };
    return base;
  }

  /** Devtools / e2e: `__mentorMock.nudge("deadline")` sends a rich notification to the open chat. */
  nudge(kind: NotificationKind = "checkin") {
    for (const sock of this.sockets) sock.notify(kind);
  }

  /** Mock: Web Push is "enabled" with a real-format key so the opt-in flow can be exercised. */
  async getVapidPublicKey() {
    await this.delay();
    this.requireActive();
    return { enabled: true, public_key: MOCK_VAPID_PUBLIC_KEY, subscribed_devices: this.state.push ? 1 : 0 };
  }

  async subscribePush(subscription: PushSubscriptionJSON) {
    await this.delay();
    this.requireActive();
    if (!subscription?.endpoint) throw new ApiError(422, "Đăng ký thông báo không hợp lệ.");
    this.state.push = subscription;
    this.save();
    return { ok: true as const };
  }

  async unsubscribePush() {
    await this.delay();
    this.requireActive();
    this.state.push = null;
    this.save();
    return { ok: true as const };
  }

  // ------------------------------------------------------------------ chat

  /** The mock sandbox wakes on connect (MockChatSocket.boot), so a warm-up has nothing left to do. */
  async warmSandbox(): Promise<SandboxWarmResult> {
    await this.delay();
    this.requireSession();
    if (this.state.me.onboarding_state !== "active") return { state: "sleeping", warming: false, result: "not_active" };
    return { state: "ready", warming: false, result: "already_running" };
  }

  // ------------------------------------------------------------------ progress and conversations (W2)

  private requireThpt() {
    this.requireActive();
    if (this.state.me.role !== "thpt") throw new ApiError(403, "Chỉ dành cho học sinh THPT.");
  }

  async getProgress(subject?: string): Promise<Progress> {
    await this.delay();
    this.requireThpt();
    return mockProgress(subject, this.opts.now());
  }

  async getRecommendations(subject?: string): Promise<Recommendation[]> {
    await this.delay();
    this.requireThpt();
    return mockRecommendations(subject, this.opts.now());
  }

  async listPracticeSessions(opts: { subject?: string; limit?: number } = {}): Promise<SessionSummary[]> {
    await this.delay();
    this.requireThpt();
    return mockSessions(opts.subject, opts.limit ?? 30, this.opts.now());
  }

  async listConversations(archived: ArchivedFilter = "false"): Promise<Conversation[]> {
    await this.delay();
    this.requireActive();
    return this.conversations.list(archived);
  }

  async createConversation(body: { title?: string; subject?: string | null } = {}): Promise<Conversation> {
    await this.delay();
    this.requireActive();
    return this.conversations.create(body);
  }

  async updateConversation(id: string, patch: ConversationPatch): Promise<Conversation> {
    await this.delay();
    this.requireActive();
    return this.conversations.update(id, patch);
  }

  async deleteConversation(id: string): Promise<{ ok: true }> {
    await this.delay();
    this.requireActive();
    this.conversations.remove(id);
    return { ok: true };
  }

  async searchConversations(q: string): Promise<ConversationHit[]> {
    await this.delay();
    this.requireActive();
    return this.conversations.search(q, await this.getChatHistory());
  }

  async getConversationHistory(id: string): Promise<ChatHistoryEntry[]> {
    await this.delay();
    this.requireActive();
    return this.conversations.history(id);
  }

  connectChat(handlers: ChatSocketHandlers): ChatSocket {
    if (!this.state.loggedIn || this.state.me.onboarding_state !== "active") {
      queueMicrotask(() => {
        handlers.onConnectionChange?.("closed");
        handlers.onMessage({ type: "error", error: "Chưa thể trò chuyện: tài khoản chưa sẵn sàng." });
      });
      return { send: () => false, close: () => {} };
    }
    const sock = new MockChatSocket(this, handlers, {
      speed: this.opts.chatSpeed,
      now: this.opts.now,
      onClose: () => this.sockets.delete(sock),
    });
    this.sockets.add(sock);
    return sock;
  }
}
