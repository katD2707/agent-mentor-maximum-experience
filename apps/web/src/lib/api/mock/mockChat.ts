import type { ChatSocket, ChatSocketHandlers } from "../client";
import type {
  AppNotification,
  ApprovalDecisionValue,
  ApprovalRequest,
  ChatAttachment,
  ChatCard,
  ClientMessage,
  NotificationKind,
  NotificationPayload,
  ServerMessage,
  SuggestionItem,
} from "../../types";
import { DEADLINE_FOCUS_MINUTES, FOCUS_EXTEND_MINUTES, gradeFlashcard } from "../../chat/cards";
import { fakeSha, isoLocal, localDateStamp, randomId } from "../../format";
import type { MockApiClient } from "./mockApi";

interface Options {
  speed: number;
  now: () => number;
  onClose?: () => void;
}

type UserMessage = Extract<ClientMessage, { type: "user_message" }>;
type CardAction = Extract<ClientMessage, { type: "card_action" }>;

const APPROVAL_RE = /(?<!hạn |thi )lịch(?! thi)|calendar|đặt hẹn|sự kiện|nhắc tôi|nhắc em|nhắc mình/i;
// \b is ASCII-only in JS, so use Unicode letter lookarounds for Vietnamese words.
const REMEMBER_RE = /(?<!\p{L})(nhớ|ghi lại|ghi nhớ|remember)(?!\p{L})/iu;
const ERROR_RE = /^\/loi\b/i;
// Interaction layer demos (CONTRACTS 9). Settings → mock panel lists them.
const ALL_CARDS_RE = /^\/(the|cards)\b/i;
const CRISIS_RE = /\/khunghoang|tự tử|muốn chết|không muốn sống|tự làm hại|làm hại bản thân/i;
const FLASH_RE = /flashcard|(?<!\p{L})thẻ(?!\p{L})|kiểm tra nhanh|đố mình|đố em/iu;
const DEADLINE_RE = /deadline|hạn chót|hạn nộp|bao giờ thi|lịch thi|còn bao lâu/i;
const FOCUS_RE = /tập trung|focus|pomodoro/i;
const CELEBRATE_RE = /xong rồi|hoàn thành|làm xong|ăn mừng|milestone/i;
const WEEKLY_RE = /tổng kết|tuần này thế nào|weekly/i;
const CHECKIN_RE = /check-?in|tâm trạng|hôm nay thế nào/i;
const NUDGE_RE = /thông báo|notify|\/nudge/i;

function chunk(text: string): string[] {
  const tokens = text.match(/\S+\s*|\s+/g) ?? [text];
  const out: string[] = [];
  for (let i = 0; i < tokens.length; i += 2) out.push(tokens.slice(i, i + 2).join(""));
  return out;
}

/**
 * In-browser stand-in for WS /api/ws/chat. Streams a canned mentor reply, reports tool calls, sometimes asks
 * for approval (waiting for the decision like the harness does), walks the sandbox through
 * sleeping → waking → ready → busy, and speaks the interaction layer: quick replies, cards, card actions and
 * rich nudges.
 */
export class MockChatSocket implements ChatSocket {
  private closed = false;
  private ready = false;
  private busy = false;
  private turnCount = 0;
  private queue: (UserMessage | CardAction)[] = [];
  private waitingApproval: { id: string; resolve: (d: ApprovalDecisionValue) => void } | null = null;
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private notifiedOnce = false;
  /** Mentor text streamed in the current turn, saved to the transcript at turn_done. */
  private reply = "";

  constructor(
    private readonly api: MockApiClient,
    private readonly handlers: ChatSocketHandlers,
    private readonly opts: Options,
  ) {
    void this.boot();
  }

  private wait(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const t = setTimeout(() => {
        this.timers.delete(t);
        resolve();
      }, ms * this.opts.speed);
      this.timers.add(t);
    });
  }

  private emit(msg: ServerMessage) {
    if (!this.closed) this.handlers.onMessage(msg);
  }

  private nowIso(): string {
    return new Date(this.opts.now()).toISOString();
  }

  private async boot() {
    this.handlers.onConnectionChange?.("connecting");
    await this.wait(80);
    if (this.closed) return;
    this.handlers.onConnectionChange?.("open");
    this.emit({ type: "sandbox_status", state: "sleeping" });
    await this.wait(400);
    this.emit({ type: "sandbox_status", state: "waking" });
    await this.wait(1600);
    if (this.closed) return;
    this.ready = true;
    this.emit({ type: "sandbox_status", state: "ready" });
    void this.drain();
    void this.scheduleNotification();
  }

  private async scheduleNotification() {
    await this.wait(25_000);
    if (this.closed || this.notifiedOnce) return;
    // The gateway applies proactivity and quiet hours; so does the mock.
    if (this.api.state.settings.proactivity === "off" || this.api.inQuietHours()) return;
    this.notify(this.api.state.me.role === "ncs" ? "nudge" : "review");
  }

  // ---------------------------------------------------------------- nudges

  private nudgePayload(kind: NotificationKind): Omit<NotificationPayload, "id"> {
    const ncs = this.api.state.me.role === "ncs";
    const name = this.api.state.me.display_name || "bạn";
    const base = { kind, created_at: this.nowIso() };
    switch (kind) {
      case "checkin":
        return {
          ...base,
          title: `Chào buổi sáng, ${name}`,
          body: ncs
            ? "3 việc cho hôm nay: ghi WER của r=16, viết 45 phút phần 3.2, đọc 1 paper trong hàng đợi."
            : "3 việc cho hôm nay: 5 câu xét dấu, ôn bất phương trình bậc hai, xem lại lỗi sai tuần trước.",
          text: "Check-in buổi sáng: 3 việc cho hôm nay.",
          actions: [
            { id: "open", label: "Bắt đầu cùng mentor" },
            { id: "snooze_1h", label: "Nhắc lại sau 1 giờ" },
          ],
          mascot: "wave",
          prefill: "Mình sẵn sàng rồi, bắt đầu việc đầu tiên nhé",
        };
      case "deadline":
        return {
          ...base,
          title: ncs ? "Hạn nộp ICASSP còn 6 tuần" : "Thi giữa kỳ Toán vào thứ Năm",
          body: ncs ? "Mình chia nhỏ việc viết theo tuần nhé?" : "Còn vài ngày, mình chia nhỏ phần ôn cho nhẹ nhàng nhé?",
          text: ncs ? "Hạn nộp ICASSP còn 6 tuần." : "Thi giữa kỳ Toán vào thứ Năm 6/11.",
          actions: [
            { id: "open", label: "Lên kế hoạch" },
            { id: "done", label: "Mình nắm rồi" },
          ],
          mascot: "listening",
          prefill: ncs ? "Chia nhỏ việc viết bài ICASSP theo tuần giúp mình" : "Lên kế hoạch ôn thi giữa kỳ Toán giúp mình",
        };
      case "focus_end":
        return {
          ...base,
          title: "Hết giờ tập trung",
          body: "Bạn làm được tới đâu rồi? Nghỉ 5 phút cho mắt nhé.",
          text: "Hết giờ tập trung.",
          actions: [
            { id: "done", label: "Xong rồi" },
            { id: "start_focus", label: "Thêm một phiên" },
            { id: "open", label: "Kể cho mentor" },
          ],
          mascot: "happy",
          prefill: "Phiên vừa rồi mình làm được: ",
        };
      case "celebration":
        return {
          ...base,
          title: "Một cột mốc mới",
          body: "Bạn vừa hoàn thành một mục tiêu. Làm tốt lắm!",
          text: "Bạn vừa hoàn thành một mục tiêu.",
          actions: [{ id: "open", label: "Xem lại" }],
          mascot: "celebrate",
          prefill: "Mình vừa hoàn thành một mục tiêu, tiếp theo nên làm gì?",
        };
      case "nudge":
        return {
          ...base,
          title: "Có 2 paper mới về LoRA cho ASR",
          body: "literature-watch đã thêm vào hàng đợi đọc của bạn.",
          text: "literature-watch: có 2 paper mới liên quan đến LoRA cho ASR trong hàng đợi đọc.",
          actions: [
            { id: "open", label: "Đọc cùng mentor" },
            { id: "snooze_1h", label: "Để sau" },
          ],
          mascot: "idle",
          prefill: "Tóm tắt giúp mình 2 paper mới về LoRA cho ASR",
        };
      case "report":
        return {
          ...base,
          title: "Báo cáo hai tuần đã gửi",
          body: "Phụ huynh vừa nhận báo cáo tiến độ. Bạn có thể xem đúng nội dung đó.",
          text: "Báo cáo hai tuần đã gửi cho phụ huynh.",
          actions: [{ id: "open", label: "Mở trò chuyện" }],
          mascot: "idle",
          prefill: null,
        };
      case "review":
      default:
        return {
          ...base,
          kind: "review",
          title: "Đến giờ ôn: 3 câu ngắn",
          body: ncs ? "Ôn nhanh 3 khái niệm LoRA trước buổi họp GVHD." : "Bất phương trình bậc hai, đến hạn hôm nay. Khoảng 10 phút.",
          text: ncs ? "Đến giờ ôn: 3 khái niệm LoRA." : "Đến giờ ôn: 3 câu ngắn về bất phương trình bậc hai (đến hạn hôm nay).",
          actions: [
            { id: "start_focus", label: "Bắt đầu 15 phút" },
            { id: "snooze_1h", label: "Nhắc sau 1 giờ" },
            { id: "open", label: "Mở" },
          ],
          mascot: "happy",
          prefill: ncs ? "Cho mình 3 câu ôn nhanh về LoRA" : "Cho mình 3 câu ôn bất phương trình bậc hai",
        };
    }
  }

  /** Sends a rich nudge (CONTRACTS 9) to this socket; the mock store gives it an int id like the gateway. */
  notify(kind: NotificationKind = "review") {
    this.notifiedOnce = true;
    const n = this.api.recordNotification(this.nudgePayload(kind));
    this.emit({ type: "notification", ...n });
    this.api.addActivity({ actor: "mentor", action: "notify_user", target: null, summary: n.text });
  }

  /** A snoozed notification comes back (same id). */
  redeliver(n: AppNotification) {
    this.emit({
      type: "notification",
      id: n.id,
      kind: n.kind,
      title: n.title,
      body: n.body,
      actions: n.actions,
      mascot: n.mascot as NotificationPayload["mascot"],
      prefill: n.prefill,
      text: n.text,
      created_at: this.nowIso(),
    });
  }

  /** POST /notifications/{id}/action start_focus: the gateway starts a focus session; it shows up as a card. */
  startFocusFromNudge(minutes: number) {
    const card = this.focusCard(minutes, this.api.state.me.role === "ncs" ? "Ôn nhanh khái niệm LoRA" : "Ôn bất phương trình bậc hai");
    this.showCard(card);
  }

  // ---------------------------------------------------------------- socket

  send(msg: ClientMessage): boolean {
    if (this.closed) return false;
    if (msg.type === "approval_decision") {
      if (this.waitingApproval && this.waitingApproval.id === msg.approval_id) {
        const w = this.waitingApproval;
        this.waitingApproval = null;
        w.resolve(msg.decision);
      }
      return true;
    }
    if (msg.type === "card_action") {
      const refusal = this.refuseCardAction(msg);
      if (refusal) {
        queueMicrotask(() => this.emit({ type: "error", error: refusal, card_id: msg.card_id }));
        return true;
      }
    }
    this.queue.push(msg);
    void this.drain();
    return true;
  }

  /** Gateway rules (Built H): unknown card, an action the kind does not take, a bad value, or a turn running. */
  private refuseCardAction(a: CardAction): string | null {
    const card = this.api.cards.get(a.card_id);
    if (!card) return "Không tìm thấy thẻ này.";
    if (this.busy || this.queue.length > 0) return "Mentor đang trả lời, bạn đợi một chút rồi chọn lại nhé.";
    const allowed: Record<string, string[]> = {
      flashcard: ["answer", "skip"],
      checkin: ["answer"],
      deadline: ["done", "start_focus"],
      focus: ["done", "extend"],
    };
    if (!(allowed[card.kind] ?? []).includes(a.action)) return "Thẻ này không nhận thao tác đó.";
    if (card.kind === "focus" && card.ended_at) return "Phiên tập trung này đã kết thúc.";
    if (card.kind === "focus" && a.action === "extend") {
      const n = Number(a.value ?? FOCUS_EXTEND_MINUTES);
      if (!Number.isInteger(n) || n < 5 || n > 60) return "Chỉ thêm được 5–60 phút.";
    }
    return null;
  }

  /** Called by the mock API when a phone upload lands in inbox/. */
  announceUpload(path: string) {
    if (this.ready) this.emit({ type: "upload_received", path });
  }

  close() {
    this.opts.onClose?.();
    this.closed = true;
    for (const t of this.timers) clearTimeout(t);
    this.timers.clear();
    this.handlers.onConnectionChange?.("closed");
  }

  private async drain() {
    if (!this.ready || this.busy) return;
    const next = this.queue.shift();
    if (!next) return;
    this.busy = true;
    try {
      this.api.activeConversation = next.type === "user_message" ? (next.conversation_id ?? null) : this.api.activeConversation;
      if (next.type === "user_message") await this.runTurn(next.client_msg_id, next.text, next.attachments);
      else await this.runCardTurn(next);
    } finally {
      this.busy = false;
    }
    void this.drain();
  }

  private async tool(tool: string, started: string, finished: string, ms = 500) {
    this.emit({ type: "tool_started", tool, summary: started });
    await this.wait(ms);
    this.emit({ type: "tool_finished", tool, summary: finished });
    await this.wait(120);
  }

  private async stream(text: string) {
    for (const piece of chunk(text)) {
      if (this.closed) return;
      this.emit({ type: "text_delta", text: piece });
      this.reply += piece;
      await this.wait(35);
    }
  }

  /** Saves the streamed text so far as one transcript entry (what the harness does around a card). */
  private flushReply(suggestions?: SuggestionItem[]) {
    if (this.reply.trim()) {
      this.api.appendChat({
        ts: this.api.nowIsoLocal(),
        role: "mentor",
        text: this.reply.trim(),
        attachments: [],
        ...(suggestions?.length ? { suggestions } : {}),
      });
    }
    this.reply = "";
  }

  // ---------------------------------------------------------------- cards

  /** `card-YYYYMMDD-<12 hex>` (Built H). */
  private cardId(): string {
    return `card-${localDateStamp(new Date(this.opts.now())).replace(/-/g, "")}-${fakeSha(randomId()).slice(0, 12)}`;
  }

  private showCard(card: ChatCard) {
    this.flushReply();
    this.api.cards.set(card.id, card);
    this.api.appendChat({ ts: this.api.nowIsoLocal(), role: "card", card });
    this.emit({ type: "card", card });
  }

  /** A newer version of a card on screen (same id): the transcript keeps it once, at its first position. */
  private updateCard(card: ChatCard) {
    this.api.cards.set(card.id, card);
    this.api.replaceChatCard(card);
    this.emit({ type: "card", card });
  }

  private flashcard(): ChatCard {
    const ncs = this.api.state.me.role === "ncs";
    return ncs
      ? {
          id: this.cardId(),
          kind: "flashcard",
          created_at: isoLocal(new Date(this.opts.now())),
          skill: "LoRA",
          front: "Trong LoRA, phần cập nhật ΔW của một lớp được biểu diễn thế nào?",
          choices: ["Tích BA với rank r nhỏ", "Một ma trận đường chéo", "Ma trận đầy đủ đã lượng tử hoá"],
          reveal: "Tích BA với rank r nhỏ: chỉ huấn luyện A và B, W gốc giữ nguyên.",
        }
      : {
          id: this.cardId(),
          kind: "flashcard",
          created_at: isoLocal(new Date(this.opts.now())),
          skill: "Bất phương trình bậc hai",
          front: "Tập nghiệm của x² − 5x + 6 < 0 là?",
          choices: ["(2; 3)", "(−∞; 2) ∪ (3; +∞)", "[2; 3]"],
          reveal: "(2; 3): tam thức âm giữa hai nghiệm 2 và 3 (hệ số a = 1 > 0).",
        };
  }

  private deadlineCard(): ChatCard {
    const ncs = this.api.state.me.role === "ncs";
    const fixed = ncs ? "2026-12-19T23:59:00+07:00" : "2026-11-06T07:30:00+07:00";
    const due = Date.parse(fixed) > this.opts.now() ? fixed : isoLocal(new Date(this.opts.now() + 3 * 86_400_000 + 5 * 3_600_000));
    return {
      id: this.cardId(),
      kind: "deadline",
      created_at: isoLocal(new Date(this.opts.now())),
      title: ncs ? "Nộp bài ICASSP 2027" : "Thi giữa kỳ Toán",
      due_at: due,
      source: ncs ? "goals/goals.md" : "Lịch thi của trường",
    };
  }

  private focusCard(minutes: number, task: string): ChatCard {
    const m = Math.min(90, Math.max(5, Math.round(minutes)));
    const card: ChatCard = {
      id: this.cardId(),
      kind: "focus",
      created_at: isoLocal(new Date(this.opts.now())),
      task,
      minutes: m,
      ends_at: isoLocal(new Date(this.opts.now() + m * 60_000)),
    };
    this.scheduleFocusEnd(card.id, m * 60_000);
    return card;
  }

  /** The harness schedules a focus_end job; done/extend cancel it (and extend schedules a new one). */
  private focusTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private scheduleFocusEnd(cardId: string, ms: number) {
    const old = this.focusTimers.get(cardId);
    if (old) {
      clearTimeout(old);
      this.timers.delete(old);
    }
    const t = setTimeout(() => {
      this.timers.delete(t);
      this.focusTimers.delete(cardId);
      const card = this.api.cards.get(cardId);
      if (this.closed || (card?.kind === "focus" && card.ended_at)) return;
      this.notify("focus_end"); // focus_end goes out even when proactivity is off (a timer the learner started)
    }, ms);
    this.timers.add(t);
    this.focusTimers.set(cardId, t);
  }

  private celebrationCard(): ChatCard {
    const ncs = this.api.state.me.role === "ncs";
    return {
      id: this.cardId(),
      kind: "celebration",
      created_at: isoLocal(new Date(this.opts.now())),
      title: ncs ? "Xong bản nháp phần 3.2!" : "Xong chủ đề xét dấu tam thức!",
      detail: ncs ? "Một bước lớn cho chương 3. Nghỉ một chút rồi mình rà lại cùng nhau nhé." : "5/5 câu đúng liên tiếp. Mastery đã lên 0.82.",
    };
  }

  private weeklyCard(): ChatCard {
    const ncs = this.api.state.me.role === "ncs";
    return {
      id: this.cardId(),
      kind: "weekly",
      created_at: isoLocal(new Date(this.opts.now())),
      focus_minutes: ncs ? 185 : 140,
      milestones_done: ncs ? 1 : 2,
      mistakes_fixed: ncs ? 2 : 5,
      streak_days: ncs ? 6 : 4,
      highlight: ncs ? "Lần đầu chạy xong thí nghiệm LoRA r=16." : "Không còn quên đổi chiều bất phương trình khi nhân số âm.",
    };
  }

  private checkinCard(): ChatCard {
    return {
      id: this.cardId(),
      kind: "checkin",
      created_at: isoLocal(new Date(this.opts.now())),
      prompt: "Hôm nay bạn thấy thế nào?",
      options: ["Ổn, sẵn sàng học", "Hơi mệt", "Đang lo về bài thi"],
    };
  }

  private suggestionsFor(text: string): SuggestionItem[] {
    const ncs = this.api.state.me.role === "ncs";
    if (FLASH_RE.test(text)) {
      return [
        { label: "Thêm một thẻ", text: "Cho mình thêm một thẻ kiểm tra nhanh" },
        { label: "Giải thích lại", text: "Giải thích lại phần này giúp mình" },
      ];
    }
    if (ncs) {
      return [
        { label: "Tập trung 45 phút", text: "Bắt đầu phiên tập trung 45 phút viết phần 3.2" },
        { label: "Hạn ICASSP?", text: "Còn bao lâu tới hạn nộp ICASSP?" },
        { label: "Tổng kết tuần", text: "Tổng kết tuần này giúp mình" },
      ];
    }
    return [
      { label: "Gửi bước đầu", text: "Bước đầu: mình tìm nghiệm của x² − 5x + 6 = 0" },
      { label: "Kiểm tra nhanh", text: "Cho mình một thẻ kiểm tra nhanh" },
      { label: "Tập trung 25 phút", text: "Bắt đầu tập trung 25 phút ôn bất phương trình" },
    ];
  }

  private finishTurn(clientMsgId: string, suggestions: SuggestionItem[]) {
    this.flushReply(suggestions);
    if (suggestions.length) this.emit({ type: "suggestions", client_msg_id: clientMsgId, items: suggestions.slice(0, 3) });
    this.emit({ type: "turn_done", client_msg_id: clientMsgId });
    this.emit({ type: "sandbox_status", state: "ready" });
  }

  // ---------------------------------------------------------------- turns

  /** The gateway's echo for a click (Built H table), stored in history as the user item's text. */
  private echoFor(card: ChatCard, a: CardAction): { text: string; value?: string } {
    const v = a.value ?? undefined;
    switch (card.kind) {
      case "flashcard": {
        if (a.action === "skip") return { text: "Bỏ qua thẻ này" };
        const choices = card.choices ?? [];
        const i = v && /^[A-D]$/i.test(v) ? "ABCD".indexOf(v.toUpperCase()) : choices.indexOf(v ?? "");
        if (i >= 0 && choices[i]) return { text: `Đã chọn: ${"ABCD"[i]}. ${choices[i]}`, value: "ABCD"[i] };
        return { text: `Trả lời: ${v ?? ""}`, value: v };
      }
      case "checkin":
        return card.options.includes(v ?? "") ? { text: `Đã chọn: ${v}`, value: v } : { text: `Trả lời: ${v ?? ""}`, value: v };
      case "deadline": {
        const n = Number(v ?? DEADLINE_FOCUS_MINUTES) || DEADLINE_FOCUS_MINUTES;
        return a.action === "done"
          ? { text: `Đã xong: ${card.title}` }
          : { text: `Bắt đầu tập trung ${n} phút cho: ${card.title}`, value: String(n) };
      }
      case "focus": {
        const n = Number(v ?? FOCUS_EXTEND_MINUTES) || FOCUS_EXTEND_MINUTES;
        return a.action === "done" ? { text: "Đã xong phiên tập trung" } : { text: `Thêm ${n} phút tập trung`, value: String(n) };
      }
      default:
        return { text: `[card:${card.kind} ${a.action}]` };
    }
  }

  private async runCardTurn(a: CardAction) {
    const card = this.api.cards.get(a.card_id);
    const clientMsgId = a.client_msg_id ?? randomId("c_");
    this.reply = "";
    if (!card) {
      this.emit({ type: "error", error: "Không tìm thấy thẻ này.", card_id: a.card_id });
      return;
    }
    const echo = this.echoFor(card, a);
    this.api.appendChat({
      ts: this.api.nowIsoLocal(),
      role: "user",
      text: echo.text,
      attachments: [],
      card_action: { card_id: card.id, kind: card.kind, action: a.action, value: echo.value ?? null },
    });
    this.emit({ type: "card_echo", client_msg_id: clientMsgId, card_id: card.id, action: a.action, value: echo.value ?? null, text: echo.text });
    this.emit({ type: "sandbox_status", state: "busy" });
    await this.wait(350);

    if (card.kind === "flashcard") {
      if (a.action === "skip") {
        await this.stream("Không sao, mình sẽ đưa thẻ này quay lại sau vài hôm.");
      } else {
        const choice = echo.value && /^[A-D]$/.test(echo.value) ? card.choices?.["ABCD".indexOf(echo.value)] : undefined;
        await this.tool("record_event", "Đang ghi lại câu trả lời", "Đã cập nhật mastery", 350);
        const ok = choice ? gradeFlashcard(card, choice) : null;
        await this.stream(
          ok === true
            ? "Chính xác! Bạn nhớ đúng mấu chốt rồi."
            : ok === false
              ? "Chưa đúng, nhưng không sao. Xem lại mặt sau của thẻ nhé, rồi mình làm thêm một câu tương tự."
              : "Cảm ơn bạn. Mình so với đáp án nhé: " + (card.reveal ?? ""),
        );
      }
      this.finishTurn(clientMsgId, this.suggestionsFor("thẻ"));
      return;
    }
    if (card.kind === "focus") {
      if (a.action === "done") {
        const startedAt = Date.parse(card.ends_at) - card.minutes * 60_000;
        const spent = Math.max(1, Math.round((this.opts.now() - startedAt) / 60_000));
        this.api.addFocusMinutes(Math.min(spent, card.minutes));
        const t = this.focusTimers.get(card.id);
        if (t) clearTimeout(t);
        this.updateCard({ ...card, ended_at: isoLocal(new Date(this.opts.now())) });
        await this.stream("\n\nXong một phiên tập trung. Nghỉ 5 phút, uống chút nước rồi kể mình nghe bạn làm được gì nhé.");
      } else {
        const n = Number(echo.value) || FOCUS_EXTEND_MINUTES;
        const end = Math.max(this.opts.now(), Date.parse(card.ends_at)) + n * 60_000;
        this.updateCard({ ...card, minutes: card.minutes + n, ends_at: isoLocal(new Date(end)) });
        this.scheduleFocusEnd(card.id, end - this.opts.now());
        await this.stream(`\n\nOk, thêm ${n} phút. Cứ từ từ.`);
      }
      this.finishTurn(clientMsgId, []);
      return;
    }
    if (card.kind === "deadline") {
      if (a.action === "done") {
        this.api.addMilestone();
        await this.stream("Tuyệt, mình đã ghi nhận việc này xong.");
      } else {
        const n = Number(echo.value) || DEADLINE_FOCUS_MINUTES;
        await this.tool("start_focus", "Đang bắt đầu phiên tập trung", "Đã đặt hẹn giờ", 300);
        this.showCard(this.focusCard(n, card.title));
        await this.stream("\n\nBắt đầu nhé. Mình sẽ không làm phiền cho tới khi hết giờ.");
      }
      this.finishTurn(clientMsgId, []);
      return;
    }
    if (card.kind === "checkin") {
      const v = a.value ?? "";
      const reply = /mệt/i.test(v)
        ? "Cảm ơn bạn đã nói thật. Hôm nay mình làm nhẹ thôi: một việc nhỏ 15 phút là đủ."
        : /lo/i.test(v)
          ? "Lo trước kỳ thi là bình thường. Mình chia phần ôn thành từng bước nhỏ nhé, bắt đầu từ phần bạn chắc nhất."
          : "Tuyệt! Vậy mình bắt đầu với việc quan trọng nhất hôm nay nhé.";
      await this.stream(reply);
      this.finishTurn(clientMsgId, this.suggestionsFor(""));
      return;
    }
    await this.stream("Mình đã nhận.");
    this.finishTurn(clientMsgId, []);
  }

  private async runTurn(clientMsgId: string, text: string, attachments: ChatAttachment[]) {
    this.turnCount++;
    this.reply = "";
    this.api.appendChat({ ts: this.api.nowIsoLocal(), role: "user", text, attachments: attachments.map((a) => a.path) });
    const role = this.api.state.me.role;
    const name = this.api.state.me.display_name || "bạn";
    this.emit({ type: "sandbox_status", state: "busy" });
    await this.wait(250);

    if (ERROR_RE.test(text.trim())) {
      await this.tool("read_file", "Đang đọc me/now.md", "Đã đọc me/now.md");
      this.emit({ type: "error", error: "Mentor gặp lỗi khi xử lý (lỗi giả lập). Bạn thử gửi lại nhé." });
      this.emit({ type: "sandbox_status", state: "ready" });
      return;
    }

    // Safety first: a crisis turn gets a calm reply with support lines, no cards, no suggestions.
    if (CRISIS_RE.test(text)) {
      await this.tool("flag_crisis", "Đang báo cho người lớn đáng tin cậy", "Đã báo", 400);
      await this.stream(
        [
          `${name} ơi, cảm ơn bạn đã nói với mình. Bạn không phải một mình đâu.`,
          "",
          "Nếu bạn đang gặp nguy hiểm, hãy gọi ngay **115** (cấp cứu) hoặc **111** (tổng đài bảo vệ trẻ em, miễn phí, 24/7).",
          "Bạn có thể kể cho mình nghe chuyện gì đang xảy ra không? Mình ở đây.",
        ].join("\n"),
      );
      this.finishTurn(clientMsgId, []);
      return;
    }

    if (ALL_CARDS_RE.test(text.trim())) {
      await this.tool("read_file", "Đang đọc me/now.md", "Đã đọc me/now.md", 300);
      await this.stream("Đây là tất cả các loại thẻ mentor có thể gửi:\n\n");
      this.showCard(this.checkinCard());
      await this.wait(250);
      this.showCard(this.flashcard());
      await this.wait(250);
      this.showCard(this.deadlineCard());
      await this.wait(250);
      this.showCard(this.focusCard(25, role === "ncs" ? "Viết nháp phần 3.2" : "Ôn bất phương trình bậc hai"));
      await this.wait(250);
      this.showCard(this.weeklyCard());
      this.flushReply(this.suggestionsFor(text));
      await this.wait(250);
      // Celebrations come last in a turn (Built H).
      this.showCard(this.celebrationCard());
      this.api.addMilestone();
      this.finishTurn(clientMsgId, this.suggestionsFor(text));
      return;
    }

    // 1. Tools
    if (attachments.length > 0) {
      for (const a of attachments) {
        if (a.mime_type.startsWith("image/")) {
          await this.tool("look_at_image", `Đang xem ${a.path}`, `Đã xem ${a.path}`);
        } else if (a.mime_type === "application/pdf") {
          await this.tool("run_script", `Đang trích văn bản từ ${a.path}`, "Đã trích xong văn bản PDF");
        } else {
          await this.tool("read_file", `Đang đọc ${a.path}`, `Đã đọc ${a.path}`);
        }
      }
    } else {
      await this.tool("read_file", "Đang đọc me/now.md", "Đã đọc me/now.md");
    }

    if (REMEMBER_RE.test(text)) {
      const d = new Date(this.opts.now());
      const stamp = `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
      this.emit({ type: "tool_started", tool: "edit_file", summary: "Đang ghi nhớ vào me/now.md" });
      this.api.mentorEdit(
        "me/now.md",
        (old) => old.replace(/(## Tuần này\n)/, `$1- ${text.trim().replace(/\s+/g, " ").slice(0, 160)} (chat ${stamp})\n`),
        "Ghi nhớ từ cuộc trò chuyện",
      );
      this.api.addActivity({ actor: "mentor", action: "edit_file", target: "me/now.md", summary: "Ghi nhớ một điều bạn vừa kể." });
      await this.wait(300);
      this.emit({ type: "tool_finished", tool: "edit_file", summary: "Đã cập nhật me/now.md" });
    }

    // 2. Interaction-layer demos: one card per recognised intent.
    if (FLASH_RE.test(text)) {
      await this.stream("Thử thẻ này nhé, chọn đáp án bạn nghĩ là đúng:\n");
      this.showCard(this.flashcard());
      this.finishTurn(clientMsgId, this.suggestionsFor(text));
      return;
    }
    if (DEADLINE_RE.test(text)) {
      await this.tool("read_file", "Đang xem goals/goals.md", "Đã xem mục tiêu và lịch");
      await this.stream("Đây là mốc gần nhất. Vẫn còn thời gian, mình chia nhỏ ra là kịp:\n");
      this.showCard(this.deadlineCard());
      this.finishTurn(clientMsgId, this.suggestionsFor(text));
      return;
    }
    if (FOCUS_RE.test(text)) {
      const minutes = Number(/(\d{1,2})\s*phút/.exec(text)?.[1] ?? (role === "ncs" ? 45 : 25));
      const task = role === "ncs" ? "Viết nháp phần 3.2 (Adapter design)" : "Ôn bất phương trình bậc hai";
      await this.tool("start_focus", "Đang bắt đầu phiên tập trung", "Đã đặt hẹn giờ", 300);
      await this.stream("Bắt đầu nhé. Mình sẽ không làm phiền cho tới khi hết giờ.\n");
      this.showCard(this.focusCard(minutes, task));
      this.finishTurn(clientMsgId, []);
      return;
    }
    if (CELEBRATE_RE.test(text)) {
      await this.tool("edit_file", "Đang đánh dấu mục tiêu", "Đã cập nhật goals/goals.md", 350);
      this.api.addMilestone();
      await this.stream("Bạn xứng đáng với điều này. Nghỉ một chút rồi mình chọn mục tiêu tiếp theo nhé.");
      this.flushReply(this.suggestionsFor(text));
      // Celebrations come last in a turn (Built H).
      this.showCard(this.celebrationCard());
      this.emit({ type: "suggestions", client_msg_id: clientMsgId, items: this.suggestionsFor(text) });
      this.emit({ type: "turn_done", client_msg_id: clientMsgId });
      this.emit({ type: "sandbox_status", state: "ready" });
      return;
    }
    if (WEEKLY_RE.test(text)) {
      await this.tool("read_file", "Đang đọc nhật ký tuần", "Đã tổng hợp tuần này", 450);
      await this.stream("Tuần này của bạn trông như thế này:\n");
      this.showCard(this.weeklyCard());
      this.finishTurn(clientMsgId, this.suggestionsFor(text));
      return;
    }
    if (CHECKIN_RE.test(text)) {
      this.showCard(this.checkinCard());
      this.finishTurn(clientMsgId, []);
      return;
    }

    // 3. Sometimes an approval
    const wantsApproval = APPROVAL_RE.test(text) || this.turnCount % 4 === 0;
    if (wantsApproval) {
      const approval: ApprovalRequest =
        role === "ncs"
          ? {
              approval_id: randomId("ap_"),
              action: "calendar.create_event",
              summary: "Tạo sự kiện “Viết nháp phần 3.2” 9:00–11:00 thứ Sáu trong Google Calendar",
              details: { calendar: "Nghiên cứu", start: "2026-10-31T09:00:00+07:00", end: "2026-10-31T11:00:00+07:00" },
              expires_at: new Date(this.opts.now() + 10 * 60_000).toISOString(),
            }
          : {
              approval_id: randomId("ap_"),
              action: "calendar.create_event",
              summary: "Tạo sự kiện “Ôn bất phương trình bậc hai” 20:00–20:45 thứ Tư trong Google Calendar",
              details: { calendar: "Cá nhân", start: "2026-10-29T20:00:00+07:00", end: "2026-10-29T20:45:00+07:00", nhac_truoc: "10 phút" },
              expires_at: new Date(this.opts.now() + 10 * 60_000).toISOString(),
            };
      await this.stream("Mình đề xuất đặt một buổi ôn vào lịch của bạn. Bạn xem thẻ duyệt bên cạnh nhé.\n\n");
      this.emit({ type: "approval_request", approval });
      const decision = await new Promise<ApprovalDecisionValue>((resolve) => {
        this.waitingApproval = { id: approval.approval_id, resolve };
      });
      if (this.closed) return;
      this.api.addActivity({
        actor: "user",
        action: decision === "approve" ? "approval:approve" : "approval:deny",
        target: approval.approval_id,
        summary: decision === "approve" ? "Bạn đã duyệt tạo sự kiện lịch." : "Bạn đã từ chối tạo sự kiện lịch.",
      });
      if (decision === "approve") {
        await this.tool("calendar.create_event", "Đang tạo sự kiện lịch", "Đã tạo sự kiện");
        await this.stream("Đã thêm vào lịch.\n\n");
      } else {
        await this.stream("Ok, mình không tạo sự kiện.\n\n");
      }
    }

    // 4. Reply
    let reply: string;
    if (attachments.length > 0) {
      const list = attachments.map((a) => `\`${a.path}\``).join(", ");
      reply =
        role === "ncs"
          ? `Mình đã nhận ${list}. Trước khi mình góp ý, ${name} tóm tắt giúp mình **đóng góp chính** của tài liệu này trong 2–3 câu nhé?`
          : `Mình đã xem ${list}. Có vẻ bạn mắc lỗi **quên đổi chiều bất phương trình** khi nhân với số âm ở câu 2. Bạn thử làm lại câu đó, viết từng bước ra cho mình xem nhé.`;
    } else if (role === "ncs") {
      reply = [
        `Chào ${name}. Theo ghi chú, thứ Hai 3/11 bạn họp GVHD và LoRA r=16 đang chạy.`,
        "",
        "Gợi ý cho hôm nay:",
        "1. Khi có WER của r=16, ghi vào `research/experiments/log.md`.",
        "2. Dành một khối 45 phút viết nháp **phần 3.2 (Adapter design)**.",
        "",
        "Bạn muốn bắt đầu từ việc nào?",
      ].join("\n");
    } else {
      reply = [
        `Chào ${name}! Mình nhớ là thứ Năm 6/11 bạn thi giữa kỳ Toán.`,
        "",
        "Tối nay mình gợi ý ôn **bất phương trình bậc hai** (mastery đang là 0.41). Thử câu này trước nhé:",
        "",
        "> Giải bất phương trình x² − 5x + 6 < 0.",
        "",
        "Bạn gửi mình **bước đầu tiên** thôi, chưa cần ra đáp số. Sai cũng không sao!",
      ].join("\n");
    }
    await this.stream(reply);

    this.api.addActivity({ actor: "mentor", action: "read_file", target: "me/now.md", summary: "Đọc ghi chú hiện tại để trả lời." });
    this.finishTurn(clientMsgId, this.suggestionsFor(text));

    if (NUDGE_RE.test(text) && !this.closed) {
      await this.wait(400);
      const kind = /\/nudge\s+(\w+)/.exec(text)?.[1] as NotificationKind | undefined;
      this.notify(kind ?? (role === "ncs" ? "nudge" : "review"));
    }
  }
}
