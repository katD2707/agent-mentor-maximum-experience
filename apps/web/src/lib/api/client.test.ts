import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HttpApiClient.warmSandbox", () => {
  it("POSTs /sandbox/warm with the session cookie and returns the result", async () => {
    const body = { state: "waking", warming: true, result: "started" };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await new HttpApiClient("http://gw.test/api/").warmSandbox();

    expect(res).toEqual(body);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://gw.test/api/sandbox/warm");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.body).toBeUndefined();
  });

  it("surfaces a 401 as ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "not authenticated" }), { status: 401 })));
    await expect(new HttpApiClient("http://gw.test/api").warmSandbox()).rejects.toMatchObject({ status: 401 });
  });
});
