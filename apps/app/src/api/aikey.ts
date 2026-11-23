import { API_BASE } from "./http";

/** `/api/ai-key`: the user's own AI key for this installation (the gateway calls the provider directly). Never carries the key back. */
export interface AiKeyStatus {
  mode: "direct" | "router";
  /** false only in direct mode with no key saved */
  configured: boolean;
  masked_key: string | null;
  base: string;
  default_base: string;
  models: Record<string, string>;
}
export interface AiKeyProbe {
  ok: boolean;
  code: "ok" | "bad_key" | "model_not_found" | "rate_limited" | "network" | "provider_error";
  message: string;
}
export interface AiKeyForm {
  base?: string;
  /** blank keeps the saved key */
  key?: string;
}
export class AiKeyError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}

const mock = () => import.meta.env.VITE_API_MOCK === "1";
const MOCK: AiKeyStatus = { mode: "router", configured: true, masked_key: null, base: "", default_base: "", models: {} };

async function call<T>(token: string, method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ai-key${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new AiKeyError(0, "network");
  }
  const json = (await res.json().catch(() => ({}))) as { error?: string };
  if (!res.ok) throw new AiKeyError(res.status, json.error ?? "unknown");
  return json as T;
}

export const aiKeyApi = {
  get: (token: string): Promise<AiKeyStatus> => (mock() ? Promise.resolve(MOCK) : call(token, "GET", "")),
  save: (token: string, form: AiKeyForm): Promise<AiKeyStatus> => (mock() ? Promise.resolve(MOCK) : call(token, "PUT", "", form)),
  /** One tiny chat call with the form's values (or the saved ones); always answers `{ok, code}` */
  test: (token: string, form: AiKeyForm): Promise<AiKeyProbe> => (mock() ? Promise.resolve({ ok: true, code: "ok", message: "" }) : call(token, "POST", "/test", form)),
  remove: (token: string): Promise<AiKeyStatus> => (mock() ? Promise.resolve(MOCK) : call(token, "DELETE", "")),
};
