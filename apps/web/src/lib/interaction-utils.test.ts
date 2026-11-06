import { describe, expect, it } from "vitest";
import { vapidKeyFrom } from "./api/client";
import { deriveMascotState, isCrisisText, mascotForKind, sanitizeMascot, type MascotInput } from "./mascot";
import { createReducedMotionStore, rise } from "./motion";
import { deviceLabel, swUrl, urlBase64ToUint8Array } from "./push";
import { isQuietNow } from "./quietHours";

describe("useReducedMotion store", () => {
  function fakeHost(initial: boolean) {
    const listeners = new Set<() => void>();
    const mql = {
      matches: initial,
      addEventListener: (_: string, cb: () => void) => listeners.add(cb),
      removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
    };
    return {
      host: { matchMedia: (q: string) => (expect(q).toBe("(prefers-reduced-motion: reduce)"), mql as unknown as MediaQueryList) },
      set(v: boolean) {
        mql.matches = v;
        for (const l of listeners) l();
      },
      listeners,
    };
  }

  it("reads the media query and follows changes", () => {
    const f = fakeHost(false);
    const store = createReducedMotionStore(() => f.host);
    expect(store.getSnapshot()).toBe(false);
    let calls = 0;
    const off = store.subscribe(() => calls++);
    f.set(true);
    expect(calls).toBe(1);
    expect(store.getSnapshot()).toBe(true);
    off();
    expect(f.listeners.size).toBe(0);
  });

  it("is false and inert without a window (SSR)", () => {
    const store = createReducedMotionStore(() => undefined);
    expect(store.getSnapshot()).toBe(false);
    expect(() => store.subscribe(() => {})()).not.toThrow();
  });

  it("turns every entrance into a fade under reduced motion", () => {
    expect(rise(true).initial).toEqual({ opacity: 0 });
    expect(rise(true).animate).toEqual({ opacity: 1 });
    expect(rise(false).initial).toMatchObject({ opacity: 0, y: 8, scale: 0.98 });
  });
});

describe("mascot state", () => {
  const base: MascotInput = {
    connection: "open",
    sandbox: "ready",
    toolsRunning: false,
    streaming: false,
    inFlight: false,
    composing: false,
    crisis: false,
    oneShot: null,
  };

  it("follows the work: sleepy, thinking, talking, listening, idle", () => {
    expect(deriveMascotState(base)).toBe("idle");
    expect(deriveMascotState({ ...base, composing: true })).toBe("listening");
    expect(deriveMascotState({ ...base, inFlight: true })).toBe("thinking");
    expect(deriveMascotState({ ...base, inFlight: true, streaming: true })).toBe("talking");
    expect(deriveMascotState({ ...base, inFlight: true, streaming: true, toolsRunning: true })).toBe("thinking");
    expect(deriveMascotState({ ...base, sandbox: "sleeping" })).toBe("sleepy");
    expect(deriveMascotState({ ...base, oneShot: "celebrate", streaming: true })).toBe("celebrate");
  });

  it("is calm in crisis context, even over a celebration", () => {
    expect(deriveMascotState({ ...base, crisis: true, oneShot: "celebrate", streaming: true })).toBe("calm");
  });

  it("recognises support-line replies and keeps maths numbers out", () => {
    expect(isCrisisText("Bạn có thể gọi ngay 111, miễn phí.")).toBe(true);
    expect(isCrisisText("Đường dây nóng hỗ trợ luôn mở.")).toBe(true);
    expect(isCrisisText("Kết quả là 111 + 4 = 115.")).toBe(false);
    expect(isCrisisText("Giải bất phương trình x² − 5x + 6 < 0.")).toBe(false);
  });

  it("maps notification kinds and untrusted hints", () => {
    expect(mascotForKind("checkin")).toBe("wave");
    expect(mascotForKind("focus_end")).toBe("happy");
    expect(mascotForKind("deadline")).toBe("idle");
    expect(sanitizeMascot("dance", "idle")).toBe("idle");
    expect(sanitizeMascot("calm")).toBe("calm");
  });
});

describe("quiet hours (VN time)", () => {
  const at = (iso: string) => Date.parse(iso);
  it("wraps past midnight and ignores empty or invalid ranges", () => {
    expect(isQuietNow(["22:00", "07:00"], at("2026-11-03T23:30:00+07:00"))).toBe(true);
    expect(isQuietNow(["22:00", "07:00"], at("2026-11-04T06:59:00+07:00"))).toBe(true);
    expect(isQuietNow(["22:00", "07:00"], at("2026-11-04T07:00:00+07:00"))).toBe(false);
    expect(isQuietNow(["12:00", "13:00"], at("2026-11-04T12:30:00+07:00"))).toBe(true);
    expect(isQuietNow(["08:00", "08:00"], at("2026-11-04T08:00:00+07:00"))).toBe(false);
    expect(isQuietNow(["25:00", "07:00"], at("2026-11-04T01:00:00+07:00"))).toBe(false);
    expect(isQuietNow(null, Date.now())).toBe(false);
  });
});

describe("web push helpers", () => {
  it("decodes a base64url VAPID key to 65 bytes", () => {
    const k = urlBase64ToUint8Array("BOMUsiQ_zRFnC6Qg6JRJA_QDA0AhmK2snyUdpE6ITxG_t1rottYcI06ZekBPxUZJegkXP2itzYxNM-7kVssWgpw");
    expect(k).toHaveLength(65);
    expect(k[0]).toBe(4); // uncompressed P-256 point
  });

  it("passes an absolute API base to the service worker", () => {
    expect(swUrl("/api", "https://mentor.example")).toBe("/sw.js?api=https%3A%2F%2Fmentor.example%2Fapi");
    expect(swUrl("http://localhost:8000/api/", "http://localhost:3000")).toBe("/sw.js?api=http%3A%2F%2Flocalhost%3A8000%2Fapi");
  });

  it("labels devices without identifying details", () => {
    expect(deviceLabel("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36")).toBe(
      "Chrome · Windows",
    );
    expect(deviceLabel("")).toBe("Trình duyệt");
  });

  it("normalises the VAPID endpoint (disabled = no key)", () => {
    expect(vapidKeyFrom({ enabled: true, public_key: "k", subscribed_devices: 2 })).toEqual({ enabled: true, public_key: "k", subscribed_devices: 2 });
    expect(vapidKeyFrom({ enabled: false, public_key: null })).toEqual({ enabled: false, public_key: null, subscribed_devices: undefined });
    expect(vapidKeyFrom("bare")).toEqual({ enabled: true, public_key: "bare" });
  });
});
