import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../client";
import type { ServerMessage } from "../../types";
import { MockApiClient } from "./mockApi";

function memoryStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
  };
}

async function signedIn(persona: "thpt" | "ncs" | "new" = "thpt", now = () => Date.parse("2026-10-30T13:00:00Z")) {
  const api = new MockApiClient({ persona, now, origin: "http://localhost:3000" });
  const { dev_link } = await api.requestLink("hs@example.com");
  const token = new URL(dev_link!).searchParams.get("token")!;
  expect(await api.verifyLink(token)).toBeNull();
  return api;
}

async function expectStatus(p: Promise<unknown>, status: number) {
  await expect(p).rejects.toBeInstanceOf(ApiError);
  await p.catch((e: ApiError) => expect(e.status).toBe(status));
}

describe("MockApiClient auth and onboarding", () => {
  it("requires a session, then signs in through the dev magic link", async () => {
    const api = new MockApiClient({ persona: "thpt", origin: "http://localhost:3000" });
    await expectStatus(api.getMe(), 401);
    await expectStatus(api.requestLink("not-an-email"), 422);
    const r = await api.requestLink("hs@example.com");
    expect(r.sent).toBe(true);
    expect(r.dev_link).toMatch(/^http:\/\/localhost:3000\/login\/verify\?token=/);
    const token = new URL(r.dev_link!).searchParams.get("token")!;
    await api.verifyLink(token);
    await expectStatus(api.verifyLink(token), 400); // single use
    const me = await api.getMe();
    expect(me).toMatchObject({ email: "hs@example.com", role: "thpt", onboarding_state: "active" });
    expect(me.inbound_email_address).toMatch(/@inbox\.mentor\.local$/);
    await api.logout();
    await expectStatus(api.getMe(), 401);
  });

  it("signs in with the 6-digit login code; 5 wrong codes kill the login", async () => {
    const api = new MockApiClient({ persona: "thpt", origin: "http://localhost:3000" });
    const r = await api.requestLink("hs@example.com");
    expect(r.dev_code).toMatch(/^\d{6}$/);
    const wrong = String((Number(r.dev_code) + 1) % 1_000_000).padStart(6, "0");
    await expectStatus(api.verifyCode("hs@example.com", "12"), 422);
    await expectStatus(api.verifyCode("hs@example.com", wrong), 400);
    expect(await api.verifyCode("HS@example.com", r.dev_code!)).toEqual({ ok: true, next: "/chat" });
    expect((await api.getMe()).email).toBe("HS@example.com");
    await expectStatus(api.verifyCode("hs@example.com", r.dev_code!), 400); // one-time
    await expectStatus(api.verifyLink(new URL(r.dev_link!).searchParams.get("token")!), 400); // same login

    await api.logout();
    const r2 = await api.requestLink("hs@example.com");
    const wrong2 = String((Number(r2.dev_code) + 1) % 1_000_000).padStart(6, "0");
    for (let i = 0; i < 5; i++) await expectStatus(api.verifyCode("hs@example.com", wrong2), 400);
    await expectStatus(api.verifyCode("hs@example.com", r2.dev_code!), 400);
  });

  it("THPT onboarding is locked until the parent link is verified", async () => {
    let now = Date.parse("2026-10-28T13:00:00Z");
    const api = await signedIn("new", () => now);
    expect((await api.getMe()).onboarding_state).toBe("needs_role");
    await expectStatus(api.getTree(), 409);

    const me = await api.completeOnboarding({ role: "thpt", display_name: "Lan Anh", language: "vi" });
    expect(me).toMatchObject({ role: "thpt", display_name: "Lan Anh", onboarding_state: "needs_parent" });
    expect((await api.getParentLink()).status).toBe("none");

    const link = await api.startParentLink();
    expect(link.link_code).toMatch(/^\d{6}$/);
    expect(Date.parse(link.expires_at) - now).toBe(24 * 3600_000);
    expect((await api.getParentLink()).status).toBe("pending");

    now += 7000;
    expect((await api.getParentLink()).status).toBe("awaiting_consent");
    expect((await api.getMe()).onboarding_state).toBe("needs_parent");

    now += 7000;
    expect((await api.getParentLink()).status).toBe("verified");
    expect((await api.getMe()).onboarding_state).toBe("active");
    expect((await api.getActivity({ limit: 1 }))[0].action).toBe("parent_link_verified");
  });

  it("NCS onboarding is active immediately and has no parent link", async () => {
    const api = await signedIn("new");
    const me = await api.completeOnboarding({ role: "ncs", display_name: "Đức", language: "en" });
    expect(me.onboarding_state).toBe("active");
    expect(me.language).toBe("en");
    await expectStatus(api.startParentLink(), 400);
    expect(await api.getReports()).toEqual([]);
    expect((await api.getTree("research")).some((e) => e.path === "research/thesis.md")).toBe(true);
  });

  it("persists state to storage across instances", async () => {
    const storage = memoryStorage();
    const a = new MockApiClient({ persona: "ncs", storage });
    const { dev_link } = await a.requestLink("x@example.com");
    await a.verifyLink(new URL(dev_link!).searchParams.get("token")!);
    const b = new MockApiClient({ persona: "thpt", storage });
    expect((await b.getMe()).role).toBe("ncs");
  });
});

describe("MockApiClient workspace", () => {
  it("lists the tree without .git/.mentor except activity.jsonl, with derived dirs", async () => {
    const api = await signedIn();
    const tree = await api.getTree();
    const paths = tree.map((e) => e.path);
    expect(paths).toContain(".mentor/activity.jsonl");
    expect(paths.some((p) => p.startsWith(".git"))).toBe(false);
    expect(paths.filter((p) => p.startsWith(".mentor/"))).toEqual([".mentor/activity.jsonl"]);
    expect(tree.find((e) => e.path === "me")?.type).toBe("dir");
    const me = await api.getTree("me");
    expect(me.every((e) => e.path.startsWith("me/"))).toBe(true);
    expect(me.some((e) => e.path === "me/journal" && e.type === "dir")).toBe(true);
  });

  it("PUT uses base_sha: 409 when stale, 403 outside editable dirs", async () => {
    const api = await signedIn();
    const f = await api.getFile("me/now.md");
    const { sha } = await api.putFile("me/now.md", f.content + "- mới\n", f.sha);
    expect(sha).not.toBe(f.sha);
    await expectStatus(api.putFile("me/now.md", "cũ", f.sha), 409);
    await expectStatus(api.putFile("AGENTS.md", "x", "whatever"), 403);
    await expectStatus(api.putFile("reports/2026-10-24.md", "x", "whatever"), 403);
    await expectStatus(api.putFile("routines.yaml", "x", "whatever"), 403);
    expect((await api.getFile("me/now.md")).content).toContain("- mới");

    // Creating a new file: empty base_sha.
    await api.putFile("goals/plans/he.md", "# Hè\n", "");
    await expectStatus(api.putFile("goals/plans/he.md", "# Hè 2\n", ""), 409);
  });

  it("history shows mentor vs user authorship, newest first; directories merge", async () => {
    const api = await signedIn();
    const f = await api.getFile("me/preferences.md");
    await api.putFile("me/preferences.md", f.content.replace(/.*Học hiệu quả.*\n/, ""), f.sha);
    const h = await api.getHistory("me/preferences.md");
    expect(h[0].author).toBe("user");
    expect(h.map((x) => x.author)).toContain("mentor");
    expect(h.at(-1)!.author).toBe("system");
    const dir = await api.getHistory("me");
    expect(dir.length).toBeGreaterThan(h.length);
    expect(dir[0].message).toMatch(/^me\/preferences\.md: /);
    expect(Date.parse(dir[0].ts)).toBeGreaterThanOrEqual(Date.parse(dir[1].ts));
  });

  it("deletes (forget) only editable files and logs it", async () => {
    const api = await signedIn();
    await api.deleteFile("me/people.md");
    await expectStatus(api.getFile("me/people.md"), 404);
    await expectStatus(api.deleteFile("AGENTS.md"), 403);
    const [latest] = await api.getActivity({ limit: 1 });
    expect(latest).toMatchObject({ actor: "user", action: "delete_file", target: "me/people.md" });
  });

  it("uploads land in inbox/ and the export is a zip", async () => {
    const api = await signedIn();
    const r = await api.upload(new Blob(["đề bài"], { type: "text/plain" }), "Đề bài 1.txt");
    expect(r).toEqual({ path: "inbox/2026-10-30-De-bai-1.txt", mime_type: "text/plain" });
    expect((await api.getFile(r.path)).content).toBe("đề bài");
    const r2 = await api.upload(new Blob(["x"], { type: "text/plain" }), "Đề bài 1.txt");
    expect(r2.path).toBe("inbox/2026-10-30-De-bai-1-2.txt");

    const tok = await api.createMobileToken();
    const token = tok.upload_url.split("/m/")[1];
    const m = await api.mobileUpload(token, new Blob([new Uint8Array([1, 2, 3])], { type: "image/png" }), "bai.png");
    expect(m.path).toMatch(/^inbox\/.*bai\.png$/);
    await expectStatus(api.mobileUpload("bad", new Blob(["x"]), "a.png"), 410);

    const zip = new Uint8Array(await (await api.exportWorkspace()).arrayBuffer());
    expect([...zip.slice(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04]);
  });
});

describe("MockApiClient activity, reports, settings", () => {
  it("paginates activity newest first with `before`", async () => {
    const api = await signedIn();
    const page1 = await api.getActivity({ limit: 5 });
    expect(page1).toHaveLength(5);
    for (let i = 1; i < page1.length; i++) expect(Date.parse(page1[i - 1].ts)).toBeGreaterThanOrEqual(Date.parse(page1[i].ts));
    const page2 = await api.getActivity({ limit: 5, before: page1[4].ts });
    expect(Date.parse(page2[0].ts)).toBeLessThan(Date.parse(page1[4].ts));
  });

  it("lists THPT reports", async () => {
    const api = await signedIn("thpt");
    const reports = await api.getReports();
    expect(reports.length).toBeGreaterThan(0);
    expect((await api.getFile(reports[0].path)).content).toMatch(/^---\nperiod_start:/);
  });

  it("settings respect user_editable and rewrite routines.yaml as a user commit", async () => {
    const api = await signedIn("thpt");
    const s = await api.getSettings();
    expect(s.quiet_hours).toEqual(["22:00", "07:00"]);
    const locked = s.routines.find((r) => !r.user_editable)!;
    await expectStatus(
      api.putSettings({ ...s, routines: s.routines.map((r) => (r.id === locked.id ? { ...r, enabled: false } : r)) }),
      422,
    );
    await expectStatus(api.putSettings({ ...s, quiet_hours: ["25:00", "07:00"] }), 422);

    const editable = s.routines.find((r) => r.user_editable)!;
    const next = await api.putSettings({
      ...s,
      proactivity: "high",
      language: "en",
      routines: s.routines.map((r) => (r.id === editable.id ? { ...r, enabled: !r.enabled } : r)),
    });
    expect(next.proactivity).toBe("high");
    expect(next.routines.find((r) => r.id === editable.id)!.enabled).toBe(!editable.enabled);
    expect((await api.getMe()).language).toBe("en");
    expect((await api.getFile("routines.yaml")).content).toContain("proactivity: high");
    expect((await api.getHistory("routines.yaml"))[0].author).toBe("user");
  });

  it("serves chat history per day from sessions/<date>/s-<YYYYMMDD>.jsonl", async () => {
    const api = await signedIn("thpt");
    const day = await api.getChatHistory("2026-10-27");
    expect(day).toHaveLength(4);
    expect(day[0]).toMatchObject({ role: "user", attachments: [] });
    expect(day[1].role).toBe("mentor");
    expect(await api.getChatHistory("2020-01-01")).toEqual([]);
    expect((await api.getChatHistory()).length).toBe(0); // "today" = 2026-10-30 in these tests
    await expectStatus(api.getChatHistory("hôm qua"), 422);
  });

  it("delete account wipes everything and signs out", async () => {
    const api = await signedIn();
    await api.deleteAccount();
    await expectStatus(api.getMe(), 401);
  });
});

describe("MockChatSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  async function connect(persona: "thpt" | "ncs" = "thpt") {
    const api = await signedIn(persona, () => Date.now());
    const msgs: ServerMessage[] = [];
    const conn: string[] = [];
    const sock = api.connectChat({ onMessage: (m) => msgs.push(m), onConnectionChange: (c) => conn.push(c) });
    await vi.advanceTimersByTimeAsync(3000);
    return { api, sock, msgs, conn };
  }

  it("wakes the sandbox, then streams a turn with a tool pair and turn_done", async () => {
    const { sock, msgs, conn } = await connect();
    expect(conn).toEqual(["connecting", "open"]);
    expect(msgs.filter((m) => m.type === "sandbox_status").map((m) => (m as { state: string }).state)).toEqual([
      "sleeping",
      "waking",
      "ready",
    ]);
    msgs.length = 0;

    expect(sock.send({ type: "user_message", client_msg_id: "c1", text: "Chào mentor", attachments: [] })).toBe(true);
    await vi.advanceTimersByTimeAsync(10_000);

    const types = msgs.map((m) => m.type);
    expect(types[0]).toBe("sandbox_status");
    expect(types.indexOf("tool_started")).toBeLessThan(types.indexOf("tool_finished"));
    expect(types.indexOf("tool_finished")).toBeLessThan(types.indexOf("text_delta"));
    expect(types).not.toContain("approval_request");
    const text = msgs.filter((m) => m.type === "text_delta").map((m) => (m as { text: string }).text).join("");
    expect(text).toContain("Lan Anh");
    expect(msgs.at(-2)).toEqual({ type: "turn_done", client_msg_id: "c1" });
    expect(msgs.at(-1)).toEqual({ type: "sandbox_status", state: "ready" });
    sock.close();
  });

  it("asks for approval and waits for the decision", async () => {
    const { sock, msgs } = await connect("ncs");
    msgs.length = 0;
    sock.send({ type: "user_message", client_msg_id: "c1", text: "Đặt lịch viết luận văn giúp mình", attachments: [] });
    await vi.advanceTimersByTimeAsync(10_000);

    const req = msgs.find((m) => m.type === "approval_request");
    expect(req).toBeDefined();
    expect(msgs.some((m) => m.type === "turn_done")).toBe(false);

    const approvalId = (req as Extract<ServerMessage, { type: "approval_request" }>).approval.approval_id;
    sock.send({ type: "approval_decision", approval_id: approvalId, decision: "approve", scope: "once" });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(msgs.some((m) => m.type === "tool_started" && m.tool === "calendar.create_event")).toBe(true);
    expect(msgs.some((m) => m.type === "turn_done")).toBe(true);
    sock.close();
  });

  it("mentor memory edits during a turn make a stale editor get 409", async () => {
    const { api, sock } = await connect();
    const before = await api.getFile("me/now.md");
    sock.send({ type: "user_message", client_msg_id: "c1", text: "Nhớ giúp mình: thứ Bảy học nhóm", attachments: [] });
    await vi.advanceTimersByTimeAsync(10_000);
    const after = await api.getFile("me/now.md");
    expect(after.content).toContain("thứ Bảy học nhóm");
    expect((await api.getHistory("me/now.md"))[0].author).toBe("mentor");
    await expectStatus(api.putFile("me/now.md", before.content + "x", before.sha), 409);
    sock.close();
  });

  it("records both sides of a turn in today's history", async () => {
    const { api, sock } = await connect();
    const before = (await api.getChatHistory()).length;
    sock.send({ type: "user_message", client_msg_id: "c1", text: "Chào mentor", attachments: [{ path: "inbox/a.png", mime_type: "image/png" }] });
    await vi.advanceTimersByTimeAsync(10_000);
    const h = await api.getChatHistory();
    expect(h).toHaveLength(before + 2);
    expect(h.at(-2)).toMatchObject({ role: "user", text: "Chào mentor", attachments: ["inbox/a.png"] });
    expect(h.at(-1)!.role).toBe("mentor");
    expect(h.at(-1)!.text!.length).toBeGreaterThan(20);
    sock.close();
  });

  it("announces phone uploads with upload_received", async () => {
    const { api, sock, msgs } = await connect();
    const tok = await api.createMobileToken();
    const { path } = await api.mobileUpload(tok.upload_url.split("/m/")[1], new Blob(["x"], { type: "image/png" }), "bai.png");
    expect(msgs.at(-1)).toEqual({ type: "upload_received", path });
    sock.close();
    await api.mobileUpload(tok.upload_url.split("/m/")[1], new Blob(["y"], { type: "image/png" }), "bai2.png");
    expect(msgs.filter((m) => m.type === "upload_received")).toHaveLength(1);
  });

  it("emits an error for /loi and sends notifications", async () => {
    const { sock, msgs } = await connect();
    sock.send({ type: "user_message", client_msg_id: "c1", text: "/loi", attachments: [] });
    await vi.advanceTimersByTimeAsync(5_000);
    expect(msgs.some((m) => m.type === "error")).toBe(true);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(msgs.some((m) => m.type === "notification")).toBe(true);
    sock.close();
    const count = msgs.length;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(msgs.length).toBe(count);
  });

  it("refuses to chat before onboarding is complete", async () => {
    const api = await signedIn("new", () => Date.now());
    const msgs: ServerMessage[] = [];
    const sock = api.connectChat({ onMessage: (m) => msgs.push(m) });
    await vi.advanceTimersByTimeAsync(100);
    expect(msgs[0].type).toBe("error");
    expect(sock.send({ type: "user_message", client_msg_id: "c", text: "hi", attachments: [] })).toBe(false);
  });
});

describe("MockApiClient Google Calendar", () => {
  it("connects and disconnects for NCS only", async () => {
    const api = await signedIn("ncs");
    expect(await api.getGoogleCalendar()).toEqual({ available: true, connected: false, email: null, scopes: [] });
    expect(await api.connectGoogleCalendar()).toBeNull();
    expect(await api.getGoogleCalendar()).toMatchObject({ connected: true, email: "hs@example.com" });
    await api.disconnectGoogleCalendar();
    expect((await api.getGoogleCalendar()).connected).toBe(false);

    const thpt = await signedIn("thpt");
    await expectStatus(thpt.getGoogleCalendar(), 403);
    await expectStatus(thpt.connectGoogleCalendar(), 403);
  });
});

describe("MockApiClient.warmSandbox", () => {
  it("needs a session and reports the always-awake mock sandbox", async () => {
    await expectStatus(new MockApiClient({ persona: "thpt" }).warmSandbox(), 401);
    expect(await (await signedIn("ncs")).warmSandbox()).toEqual({ state: "ready", warming: false, result: "already_running" });
    expect((await (await signedIn("new")).warmSandbox()).result).toBe("not_active");
  });
});
