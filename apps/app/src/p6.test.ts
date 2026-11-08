import { describe, expect, it } from "vitest";
import { fetchPack, PackTooNewError } from "./lib/offline";
import { APP_VERSION, compareVersions, needsNewerApp } from "./lib/version";
import { canRestart, fetchUpdate, percentOf, installUpdate, isBusyRoute, type UpdateStatus } from "./lib/updater";

describe("versions", () => {
  it("compares numerically, not as text", () => {
    expect(compareVersions("0.10.0", "0.9.2")).toBe(1);
    expect(compareVersions("1.0", "1.0.0")).toBe(0);
    expect(compareVersions("0.2.0-beta.1", "0.2.0")).toBe(0);
    expect(compareVersions("0.1.0", "0.1.1")).toBe(-1);
  });
  it("a pack needs a newer app only when its minimum is above ours", () => {
    expect(needsNewerApp(undefined)).toBe(false);
    expect(needsNewerApp(APP_VERSION)).toBe(false);
    expect(needsNewerApp("99.0.0")).toBe(true);
  });
});

describe("pack min_app_version", () => {
  const api = (min: string) => ({
    getPackBytes: async () => new TextEncoder().encode(JSON.stringify({ course_id: "c", version: 1, min_app_version: min, chapters: [] })).buffer as ArrayBuffer,
    getAssetBlob: async () => new Blob(),
  });
  it("opens a pack this app can show", async () => {
    expect((await fetchPack(api("0.1.0"), "t", "c", 1)).pack.course_id).toBe("c");
  });
  it("refuses a pack that needs a newer app, before anything is stored", async () => {
    await expect(fetchPack(api("99.0.0"), "t", "c", 1)).rejects.toBeInstanceOf(PackTooNewError);
  });
});

describe("update flow", () => {
  const run = async (fn: (set: (s: UpdateStatus) => void) => Promise<unknown>) => {
    const seen: UpdateStatus["kind"][] = [];
    await fn((s) => seen.push(s.kind));
    return seen;
  };
  it("checks, downloads, then waits as ready", async () => {
    const calls: string[] = [];
    const seen = await run((set) => fetchUpdate(set, async (c) => (calls.push(c), c === "update_check" ? { version: "0.1.1", notes: null } : undefined)));
    expect(calls).toEqual(["update_check", "update_download"]);
    expect(seen).toEqual(["downloading", "ready"]);
  });
  it("stays quiet when there is nothing new or the check fails, and shows a failed download", async () => {
    expect(await run((set) => fetchUpdate(set, async () => null))).toEqual(["none"]);
    expect(await run((set) => fetchUpdate(set, async () => Promise.reject(new Error("offline"))))).toEqual(["none"]);
    expect(await run((set) => fetchUpdate(set, async (c) => (c === "update_check" ? { version: "0.1.1", notes: null } : Promise.reject(new Error("sha256")))))).toEqual(["downloading", "failed"]);
    expect(await run((set) => installUpdate("0.1.1", set, async () => Promise.reject(new Error("x"))))).toEqual(["installing", "failed"]);
  });
  it("asks the channel's feed and reports what the check found", async () => {
    const args: unknown[] = [];
    const call = async (c: string, a?: Record<string, unknown>) => (c === "update_check" ? (args.push(a), { version: "0.2.0-beta.1", notes: null }) : undefined);
    const res = await fetchUpdate(() => undefined, call, { channel: "beta", listen: async () => () => undefined });
    expect(args).toEqual([{ channel: "beta" }]);
    expect(res).toEqual({ kind: "found", version: "0.2.0-beta.1" });
    expect(await fetchUpdate(() => undefined, async () => null)).toEqual({ kind: "latest" });
    expect(await fetchUpdate(() => undefined, async () => Promise.reject(new Error("offline")))).toEqual({ kind: "error" });
  });
  it("shows download progress as a percentage, none when the size is unknown", async () => {
    const seen: UpdateStatus[] = [];
    let push: (p: { downloaded: number; total: number | null }) => void = () => undefined;
    let unlistened = false;
    await fetchUpdate((s) => seen.push(s), async (c) => {
      if (c === "update_check") return { version: "0.1.1", notes: null };
      push({ downloaded: 50, total: 200 });
      push({ downloaded: 200, total: 200 });
      return undefined;
    }, { listen: async (h) => ((push = h), () => void (unlistened = true)) });
    expect(seen.map((s) => (s.kind === "downloading" ? s.percent : s.kind))).toEqual([null, 25, 100, "ready"]);
    expect(unlistened).toBe(true);
    expect(percentOf(5, null)).toBeNull();
    expect(percentOf(300, 200)).toBe(100);
  });
  it("never restarts in a lesson or practice run, only when idle or hidden", () => {
    expect(isBusyRoute("/khoa-hoc/c1/hoc")).toBe(true);
    expect(isBusyRoute("/luyen-tap/p1/lam")).toBe(true);
    expect(isBusyRoute("/khoa-hoc/c1")).toBe(false);
    expect(canRestart({ path: "/khoa-hoc/c1/hoc", hidden: true, idleMs: 999999 })).toBe(false);
    expect(canRestart({ path: "/", hidden: false, idleMs: 1000 })).toBe(false);
    expect(canRestart({ path: "/", hidden: false, idleMs: 61_000 })).toBe(true);
    expect(canRestart({ path: "/tien-do", hidden: true, idleMs: 0 })).toBe(true);
  });
});
