import { describe, expect, it } from "vitest";
import type { ApprovalRequest, ServerMessage } from "../types";
import { chatReducer, historyToMessages, initialChatState, isTurnInFlight, type ChatState } from "./reducer";

const NOW = "2026-10-28T13:00:00.000Z";
let n = 0;
const server = (s: ChatState, msg: ServerMessage) => chatReducer(s, { type: "server", msg, id: `m${++n}`, now: NOW });
const send = (s: ChatState, id: string, text = "xin chào") =>
  chatReducer(s, { type: "send", clientMsgId: id, text, attachments: [], now: NOW });

const approval: ApprovalRequest = {
  approval_id: "ap_1",
  action: "calendar.create_event",
  summary: "Tạo sự kiện",
  details: { start: "2026-10-29T20:00:00+07:00" },
  expires_at: "2026-10-28T13:10:00.000Z",
};

describe("chatReducer", () => {
  it("streams a full turn: send → tools → deltas → turn_done", () => {
    let s = chatReducer(initialChatState, { type: "connection", state: "open" });
    s = server(s, { type: "sandbox_status", state: "ready" });
    s = send(s, "c1", "Hôm nay ôn gì?");
    expect(isTurnInFlight(s)).toBe(true);
    expect(s.messages).toHaveLength(1);
    expect(s.messages[0]).toMatchObject({ role: "user", status: "sending", clientMsgId: "c1" });

    s = server(s, { type: "sandbox_status", state: "busy" });
    s = server(s, { type: "tool_started", tool: "read_file", summary: "Đang đọc me/now.md" });
    expect(s.activeTurn).toBe("c1");
    expect(s.messages[1]).toMatchObject({ role: "mentor", status: "streaming", clientMsgId: "c1" });
    expect(s.messages[1].tools).toEqual([{ tool: "read_file", summary: "Đang đọc me/now.md", status: "running" }]);

    s = server(s, { type: "tool_finished", tool: "read_file", summary: "Đã đọc me/now.md" });
    expect(s.messages[1].tools[0]).toMatchObject({ status: "done", summary: "Đã đọc me/now.md" });

    s = server(s, { type: "text_delta", text: "Chào " });
    s = server(s, { type: "text_delta", text: "bạn!" });
    expect(s.messages).toHaveLength(2);
    expect(s.messages[1].text).toBe("Chào bạn!");

    s = server(s, { type: "turn_done", client_msg_id: "c1" });
    expect(s.messages.map((m) => m.status)).toEqual(["done", "done"]);
    expect(isTurnInFlight(s)).toBe(false);
    expect(s.sandbox).toBe("busy");
    s = server(s, { type: "sandbox_status", state: "ready" });
    expect(s.sandbox).toBe("ready");
  });

  it("keeps consecutive turns apart", () => {
    let s = send(initialChatState, "c1");
    s = server(s, { type: "text_delta", text: "một" });
    s = server(s, { type: "turn_done", client_msg_id: "c1" });
    s = send(s, "c2");
    s = server(s, { type: "text_delta", text: "hai" });
    expect(s.messages.filter((m) => m.role === "mentor").map((m) => m.text)).toEqual(["một", "hai"]);
    expect(s.messages[3].clientMsgId).toBe("c2");
  });

  it("marks the turn as failed on a server error", () => {
    let s = send(initialChatState, "c1");
    s = server(s, { type: "text_delta", text: "đang…" });
    s = server(s, { type: "error", error: "Lỗi giả lập" });
    expect(s.error).toBe("Lỗi giả lập");
    expect(s.messages.map((m) => m.status)).toEqual(["error", "error"]);
    expect(isTurnInFlight(s)).toBe(false);
    s = chatReducer(s, { type: "clear_error" });
    expect(s.error).toBeNull();
  });

  it("fails in-flight turns when the socket closes", () => {
    let s = chatReducer(initialChatState, { type: "connection", state: "open" });
    s = send(s, "c1");
    s = chatReducer(s, { type: "connection", state: "closed" });
    expect(s.connection).toBe("closed");
    expect(s.sandbox).toBeNull();
    expect(s.messages[0].status).toBe("error");
    expect(s.error).toMatch(/Mất kết nối/);
  });

  it("send_failed marks only that user message", () => {
    let s = send(initialChatState, "c1");
    s = chatReducer(s, { type: "send_failed", clientMsgId: "c1", error: "offline" });
    expect(s.messages[0].status).toBe("error");
    expect(s.queuedTurns).toEqual([]);
    expect(s.error).toBe("offline");
  });

  it("tracks approvals separately from messages, without duplicates", () => {
    let s = send(initialChatState, "c1");
    s = server(s, { type: "approval_request", approval });
    s = server(s, { type: "approval_request", approval });
    expect(s.approvals).toHaveLength(1);
    expect(s.messages.every((m) => m.role === "user")).toBe(true);
    s = chatReducer(s, { type: "approval_decided", approvalId: "ap_1", decision: "approve", scope: "session" });
    expect(s.approvals[0]).toMatchObject({ status: "approved", scope: "session" });
    s = chatReducer(s, { type: "approval_expired", approvalId: "ap_1" });
    expect(s.approvals[0].status).toBe("approved");
    s = chatReducer(s, { type: "dismiss_approval", approvalId: "ap_1" });
    expect(s.approvals).toEqual([]);
  });

  it("expires pending approvals", () => {
    let s = server(initialChatState, { type: "approval_request", approval });
    s = chatReducer(s, { type: "approval_expired", approvalId: "ap_1" });
    expect(s.approvals[0].status).toBe("expired");
  });

  it("collects notifications newest first and marks them read", () => {
    let s = server(initialChatState, { type: "notification", text: "một", created_at: NOW });
    s = server(s, { type: "notification", text: "hai", created_at: NOW });
    expect(s.notifications.map((x) => x.text)).toEqual(["hai", "một"]);
    expect(s.notifications.every((x) => !x.read)).toBe(true);
    s = chatReducer(s, { type: "notifications_read" });
    expect(s.notifications.every((x) => x.read)).toBe(true);
    s = chatReducer(s, { type: "dismiss_notification", id: s.notifications[0].id });
    expect(s.notifications).toHaveLength(1);
  });

  it("restores a saved transcript, closing anything left open", () => {
    let s = send(initialChatState, "c1");
    s = server(s, { type: "text_delta", text: "dở dang" });
    const restored = chatReducer(initialChatState, { type: "restore", messages: s.messages });
    expect(restored.messages.map((m) => m.status)).toEqual(["error", "error"]);
    expect(isTurnInFlight(restored)).toBe(false);
  });

  it("puts server history before live messages and converts path attachments", () => {
    const history = historyToMessages(
      [
        { ts: "2026-10-28T20:31:00+07:00", role: "user", text: "ảnh bài", attachments: ["inbox/bai.jpg"] },
        { ts: "2026-10-28T20:31:40+07:00", role: "mentor", text: "Mình xem rồi", attachments: [] },
      ],
      "2026-10-28",
    );
    expect(history[0].attachments).toEqual([{ path: "inbox/bai.jpg", mime_type: "image/jpeg" }]);
    expect(history.every((m) => m.status === "done")).toBe(true);
    expect(initialChatState.historySource).toBe("loading");
    let s = send(initialChatState, "c1", "mới");
    s = chatReducer(s, { type: "history_loaded", messages: history });
    expect(s.historySource).toBe("server");
    expect(s.messages.map((m) => m.text)).toEqual(["ảnh bài", "Mình xem rồi", "mới"]);
  });

  it("falls back to the local copy and marks the source", () => {
    const s = chatReducer(initialChatState, { type: "restore", messages: [] });
    expect(s.historySource).toBe("local");
  });

  it("ignores upload_received (handled outside the reducer)", () => {
    const s = server(initialChatState, { type: "upload_received", path: "inbox/a.png" });
    expect(s.messages).toEqual([]);
  });
});
