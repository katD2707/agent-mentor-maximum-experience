import { afterEach, describe, expect, it, vi } from "vitest";
import { MockApiClient } from "./api/mock/mockApi";
import {
  buildSetupSteps,
  desktopDownloadUrl,
  desktopDownloadUrlLinux,
  isLinuxDesktop,
  isStepDone,
  loadVisited,
  PAPER_PROMPTS,
  saveVisited,
  shouldAutoOpen,
  type SetupContext,
} from "./setupGuide";

const ids = (ctx: SetupContext) => buildSetupSteps(ctx).map((s) => s.id);
const DL = "https://example.com/Mentor-Setup.exe";

describe("setup guide steps", () => {
  it("THPT: parent link, phone photo, desktop, proactivity, memory, privacy; no NCS steps", () => {
    expect(ids({ role: "thpt", desktopDownloadUrl: DL, inboundEmailAddress: "x@inbox", calendar: { available: true, connected: false } })).toEqual([
      "parent",
      "phone",
      "desktop",
      "proactivity",
      "memory",
      "privacy",
    ]);
  });

  it("NCS: calendar, email, papers, desktop, proactivity, memory, privacy; no THPT steps", () => {
    expect(ids({ role: "ncs", desktopDownloadUrl: DL, inboundEmailAddress: "x@inbox", calendar: { available: true, connected: false } })).toEqual([
      "calendar",
      "email",
      "papers",
      "desktop",
      "proactivity",
      "memory",
      "privacy",
    ]);
  });

  it("hides the desktop step without a download URL, and calendar/email when not configured", () => {
    const steps = ids({ role: "ncs", desktopDownloadUrl: null, inboundEmailAddress: null, calendar: { available: false, connected: false } });
    expect(steps).toEqual(["papers", "proactivity", "memory", "privacy"]);
    // calendar status still loading: hidden until we know the server has the integration
    expect(ids({ role: "ncs", inboundEmailAddress: "x@inbox" })).not.toContain("calendar");
    expect(ids({ role: null })).toEqual([]);
  });

  it("inside the desktop app the desktop step is done and has no download button", () => {
    const d = buildSetupSteps({ role: "thpt", desktopDownloadUrl: DL, inDesktopApp: true }).find((s) => s.id === "desktop")!;
    expect(d.status).toBe("done");
    expect(d.action).toBeNull();
    const web = buildSetupSteps({ role: "thpt", desktopDownloadUrl: DL }).find((s) => s.id === "desktop")!;
    expect(web.action).toEqual({ kind: "external", href: DL, label: "Tải app (Windows)" });
  });

  it("Linux desktops get the Linux package when there is one, everyone else the Windows installer", () => {
    const LX = "https://example.com/Mentor_0.1.0_amd64.deb";
    const desktop = (ctx: Partial<SetupContext>) => buildSetupSteps({ role: "thpt", ...ctx }).find((s) => s.id === "desktop");
    expect(desktop({ desktopDownloadUrl: DL, desktopDownloadUrlLinux: LX, linuxDesktop: true })!.action).toEqual({
      kind: "external",
      href: LX,
      label: "Tải app (Linux)",
    });
    expect(desktop({ desktopDownloadUrl: DL, desktopDownloadUrlLinux: LX, linuxDesktop: false })!.action).toEqual({
      kind: "external",
      href: DL,
      label: "Tải app (Windows)",
    });
    // no Linux package: Linux sees the Windows step as before; Linux-only server: hidden on Windows
    expect(desktop({ desktopDownloadUrl: DL, linuxDesktop: true })!.action).toMatchObject({ href: DL });
    expect(desktop({ desktopDownloadUrlLinux: LX, linuxDesktop: false })).toBeUndefined();
    expect(desktop({ desktopDownloadUrlLinux: LX, linuxDesktop: true })!.action).toMatchObject({ href: LX });
    // inside the Linux app: done, Linux wording, no button
    const inApp = desktop({ desktopDownloadUrl: DL, linuxDesktop: true, inDesktopApp: true })!;
    expect(inApp.status).toBe("done");
    expect(inApp.action).toBeNull();
    expect(inApp.body).not.toContain("Ctrl+Alt+M");
  });

  it("tells Linux desktops from Android, ChromeOS, Windows and macOS", () => {
    expect(isLinuxDesktop("Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0")).toBe(true);
    expect(isLinuxDesktop("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")).toBe(true);
    expect(isLinuxDesktop("Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36")).toBe(false);
    expect(isLinuxDesktop("Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36")).toBe(false);
    expect(isLinuxDesktop("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0")).toBe(false);
    expect(isLinuxDesktop("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15")).toBe(false);
  });

  it("live statuses: parent link, calendar, forwarded mail", () => {
    const status = (ctx: SetupContext, id: string) => buildSetupSteps(ctx).find((s) => s.id === id)?.status;
    expect(status({ role: "thpt", parentLink: "verified" }, "parent")).toBe("done");
    expect(status({ role: "thpt", parentLink: "pending" }, "parent")).toBe("todo");
    expect(status({ role: "thpt" }, "parent")).toBeNull();
    expect(status({ role: "ncs", calendar: { available: true, connected: true } }, "calendar")).toBe("done");
    expect(status({ role: "ncs", calendar: { available: true, connected: false } }, "calendar")).toBe("todo");
    expect(status({ role: "ncs", inboundEmailAddress: "a@b", emailReceived: true }, "email")).toBe("done");
    expect(status({ role: "ncs", inboundEmailAddress: "a@b", emailReceived: false }, "email")).toBe("todo");
    expect(status({ role: "ncs", inboundEmailAddress: "a@b" }, "email")).toBeNull();
  });

  it("NCS email step carries the address; papers carries clickable prompts", () => {
    const steps = buildSetupSteps({ role: "ncs", inboundEmailAddress: "abc@inbox.mentor.local" });
    expect(steps.find((s) => s.id === "email")!.address).toBe("abc@inbox.mentor.local");
    const papers = steps.find((s) => s.id === "papers")!;
    expect(papers.prompts).toEqual(PAPER_PROMPTS);
    expect(papers.prompts!.length).toBeGreaterThanOrEqual(2);
  });

  it("a step is done by API status, or by being visited only when the API has no status", () => {
    const [parent, phone] = buildSetupSteps({ role: "thpt", parentLink: "pending" });
    expect(isStepDone(parent, new Set(["parent"]))).toBe(false); // the API says not yet
    expect(isStepDone(phone, new Set())).toBe(false);
    expect(isStepDone(phone, new Set(["phone"]))).toBe(true);
  });

  it("visited marks round-trip through storage per learner and survive bad data", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    saveVisited("u1", new Set(["memory", "privacy"]), storage);
    expect([...loadVisited("u1", storage)].sort()).toEqual(["memory", "privacy"]);
    expect(loadVisited("u2", storage).size).toBe(0);
    store.set("mentor-setup-guide-visited:u1", "{not json");
    expect(loadVisited("u1", storage).size).toBe(0);
    expect(loadVisited("u1", null).size).toBe(0);
  });
});

describe("auto-open", () => {
  it("opens once: only for active learners who never closed it, never against a gateway without the flag", () => {
    expect(shouldAutoOpen({ onboarding_state: "active", setup_guide_dismissed_at: null })).toBe(true);
    expect(shouldAutoOpen({ onboarding_state: "active", setup_guide_dismissed_at: "2026-11-03T03:00:00Z" })).toBe(false);
    expect(shouldAutoOpen({ onboarding_state: "needs_parent", setup_guide_dismissed_at: null })).toBe(false);
    expect(shouldAutoOpen({ onboarding_state: "active" })).toBe(false);
  });
});

describe("desktop download URL", () => {
  afterEach(() => vi.unstubAllEnvs());
  it("comes from NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL and must be http(s)", () => {
    vi.stubEnv("NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL", "");
    expect(desktopDownloadUrl()).toBeNull();
    vi.stubEnv("NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL", "javascript:alert(1)");
    expect(desktopDownloadUrl()).toBeNull();
    vi.stubEnv("NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL", ` ${DL} `);
    expect(desktopDownloadUrl()).toBe(DL);
    vi.stubEnv("NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL_LINUX", "file:///tmp/x.deb");
    expect(desktopDownloadUrlLinux()).toBeNull();
    vi.stubEnv("NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL_LINUX", "https://example.com/Mentor_0.1.0_amd64.deb");
    expect(desktopDownloadUrlLinux()).toBe("https://example.com/Mentor_0.1.0_amd64.deb");
  });
});

describe("mock API dismissal", () => {
  it("stores the first dismissal on Me and can reset it", async () => {
    let now = Date.parse("2026-11-03T03:00:00Z");
    const api = new MockApiClient({ persona: "ncs", now: () => now });
    const { dev_link } = await api.requestLink("duc@example.edu.vn");
    await api.verifyLink(new URL(dev_link!).searchParams.get("token")!);
    expect((await api.getMe()).setup_guide_dismissed_at).toBeNull();
    const first = (await api.setSetupGuideDismissed(true)).setup_guide_dismissed_at;
    expect(first).toBe("2026-11-03T03:00:00.000Z");
    now += 3600_000;
    expect((await api.setSetupGuideDismissed(true)).setup_guide_dismissed_at).toBe(first);
    expect((await api.getMe()).setup_guide_dismissed_at).toBe(first);
    expect((await api.setSetupGuideDismissed(false)).setup_guide_dismissed_at).toBeNull();
  });
});
