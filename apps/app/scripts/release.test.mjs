import { describe, expect, it } from "vitest";
import { addPlatform, checkUrl, feedUrl, nextVersion, platformBundle, validateManifest } from "./release-lib.mjs";

const SHA = "a".repeat(64);
const entry = { version: "0.2.0", notes: "n", platform: "windows-x86_64", url: "https://u.example.org/stable/0.2.0/Mentor_0.2.0_x64-setup.exe", signature: "sig", sha256: SHA, pubDate: "2026-11-07T00:00:00Z" };

describe("release helpers", () => {
  it("bumps versions", () => {
    expect(nextVersion("0.1.0", "patch")).toBe("0.1.1");
    expect(nextVersion("0.1.9", "minor")).toBe("0.2.0");
    expect(nextVersion("0.1.9", "major")).toBe("1.0.0");
    expect(nextVersion("0.1.0", "0.3.0-beta.1")).toBe("0.3.0-beta.1");
    expect(() => nextVersion("0.1.0", "soon")).toThrow();
  });
  it("accepts only https feeds without credentials", () => {
    expect(() => checkUrl("https://u.example.org/stable/latest.json")).not.toThrow();
    expect(() => checkUrl("http://u.example.org/x")).toThrow();
    expect(() => checkUrl("http://127.0.0.1:8099/x")).toThrow();
    expect(() => checkUrl("http://127.0.0.1:8099/x", { allowDevHttp: true })).not.toThrow();
    expect(() => checkUrl("https://a:b@u.example.org/x")).toThrow();
    expect(() => checkUrl("https://u.example.org/x?token=1")).toThrow();
  });
  it("builds a channel manifest and keeps other platforms of the same version", () => {
    const win = addPlatform(null, entry);
    const both = addPlatform(win, { ...entry, platform: "linux-x86_64" });
    expect(Object.keys(both.platforms)).toEqual(["windows-x86_64", "linux-x86_64"]);
    expect(Object.keys(addPlatform(both, { ...entry, version: "0.3.0" }).platforms)).toEqual(["windows-x86_64"]);
    expect(validateManifest(both).version).toBe("0.2.0");
    expect(feedUrl("https://u.example.org/", "beta", "latest.json")).toBe("https://u.example.org/beta/latest.json");
  });
  it("rejects a manifest without a signature or a sha256 pin", () => {
    expect(() => validateManifest(addPlatform(null, { ...entry, signature: "" }))).toThrow();
    expect(() => validateManifest(addPlatform(null, { ...entry, sha256: "xyz" }))).toThrow();
  });
  it("knows each OS bundle", () => {
    expect(platformBundle("win32", "x64", "0.2.0").pattern.test("Mentor_0.2.0_x64-setup.exe")).toBe(true);
    expect(platformBundle("darwin", "arm64", "0.2.0").key).toBe("darwin-aarch64");
  });
});
