import { afterEach, describe, expect, it, vi } from "vitest";
import { httpApi } from "./api/http";
import { ApiError } from "./api/types";

afterEach(() => vi.unstubAllGlobals());

describe("course on Drive not downloaded yet", () => {
  it("maps the gateway's 503 needs_network to its own error code", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "needs_network" }), { status: 503 })));
    const e = await httpApi.getPackBytes("t", "c1", 1).catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e.code).toBe("needs_network");
  });

  it("keeps other failures as they were", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 503 })));
    const e = await httpApi.getPackBytes("t", "c1", 1).catch((x) => x);
    expect(e.code).toBe("unknown");
  });
});
