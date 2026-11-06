import { HttpApiClient, type ApiClient } from "./client";
import { MockApiClient } from "./mock/mockApi";

export { ApiError, isApiError } from "./client";
export type { ApiClient, ChatSocket, ConnectionState } from "./client";

export const IS_MOCK = process.env.NEXT_PUBLIC_API_MOCK === "1";
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";

let instance: ApiClient | null = null;

function browserStorage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** The process-wide API client. Call only in the browser (effects, handlers). */
export function getApi(): ApiClient {
  if (!instance) {
    if (IS_MOCK) {
      const mock = new MockApiClient({ storage: browserStorage(), latencyMs: 180 });
      // Debug handle for poking the fake backend from devtools/e2e scripts (mock mode only).
      if (typeof window !== "undefined") (window as unknown as { __mentorMock?: MockApiClient }).__mentorMock = mock;
      instance = mock;
    } else {
      instance = new HttpApiClient(API_BASE);
    }
  }
  return instance;
}

/** The mock client when running with NEXT_PUBLIC_API_MOCK=1, else null. */
export function getMock(): MockApiClient | null {
  const api = getApi();
  return api instanceof MockApiClient ? api : null;
}
