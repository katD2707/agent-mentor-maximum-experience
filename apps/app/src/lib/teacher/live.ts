import { API_BASE } from "../../api/http";

export const POLL_MS = 5000;

/**
 * Calls `onTick` when something may have changed: every few seconds (the polling fallback of GET /courses?since=),
 * at once when the window comes back, and whenever the gateway pushes an event on GET /teacher/events (SSE).
 * SSE is read with fetch so the Bearer token can be sent; if the stream is missing or breaks, polling alone carries on
 * and the stream is tried again later. Returns the stop function.
 */
export function startLive(opts: { token: string; onTick: () => void; sse?: boolean; pollMs?: number }): () => void {
  const { token, onTick } = opts;
  let stopped = false;
  const poll = setInterval(onTick, opts.pollMs ?? POLL_MS);
  const vis = () => {
    if (!document.hidden) onTick();
  };
  document.addEventListener("visibilitychange", vis);

  const ctl = new AbortController();
  let retry: ReturnType<typeof setTimeout> | undefined;
  const connect = async () => {
    try {
      const res = await fetch(`${API_BASE}/teacher/events`, { headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" }, signal: ctl.signal });
      if (!res.ok || !res.body) throw new Error("no stream");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (/(^|\n)data:/.test(dec.decode(value, { stream: true }))) onTick();
      }
    } catch {
      /* polling covers it */
    }
    if (!stopped) retry = setTimeout(connect, 30000);
  };
  if (opts.sse) void connect();

  return () => {
    stopped = true;
    clearInterval(poll);
    clearTimeout(retry);
    ctl.abort();
    document.removeEventListener("visibilitychange", vis);
  };
}
