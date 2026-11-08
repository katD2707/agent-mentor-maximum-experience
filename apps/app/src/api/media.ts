import { API_BASE } from "./http";
import { mockAssetUrl, mockCoverUrl } from "./mock-courses";

/**
 * The ONE place that turns an asset/cover into a URL an <img>, <video> or <audio> element can load.
 * <img> cannot send an Authorization header, so the gateway accepts the session token as `?t=<token>`
 * on the asset and cover routes. If the backend chooses another mechanism, change `withToken` only.
 */
export function withToken(url: string, token: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(token)}`;
}

const isMock = () => import.meta.env.VITE_API_MOCK === "1";

/** Short-lived media token from POST /media-token (the session token is not accepted on media routes). */
let mediaToken: string | null = null;
export const setMediaToken = (t: string | null) => (mediaToken = t);
export const hasMediaToken = () => mediaToken !== null;
export const getMediaToken = () => mediaToken;

/** How to mint a fresh media token for the signed-in user (set by the auth provider). */
let tokenSource: (() => Promise<string>) | null = null;
export const setMediaTokenSource = (fn: (() => Promise<string>) | null) => (tokenSource = fn);

let refreshing: Promise<string | null> | null = null;
/** New media token, shared by concurrent callers. Null when there is no signed-in user or the call failed. */
export function refreshMediaToken(): Promise<string | null> {
  if (!tokenSource) return Promise.resolve(null);
  refreshing ??= tokenSource()
    .then((t) => (setMediaToken(t), t))
    .catch(() => null)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

const isNetworkMediaUrl = (url: string) => url.startsWith(API_BASE) && /[?&]t=/.test(url);
const swapToken = (url: string, t: string) => url.replace(/([?&])t=[^&]*/, `$1t=${encodeURIComponent(t)}`);

/**
 * An <img>/<video>/<audio> on a media URL failed. If the cause is an expired media token (401), mint a new one and
 * return the URL with it; null for any other cause (or a URL that is not a network media URL).
 */
export async function recoverMediaUrl(url: string): Promise<string | null> {
  if (!isNetworkMediaUrl(url)) return null;
  let status = 0;
  try {
    status = (await fetch(url, { headers: { Range: "bytes=0-0" } })).status;
  } catch {
    return null;
  }
  if (status !== 401) return null;
  const t = await refreshMediaToken();
  return t ? swapToken(url, t) : null;
}

/** fetch() of a media URL, retried once with a fresh token on 401. */
export async function fetchMedia(url: string): Promise<Response> {
  const res = await fetch(url);
  if (res.status !== 401 || !isNetworkMediaUrl(url)) return res;
  const t = await refreshMediaToken();
  return t ? fetch(swapToken(url, t)) : res;
}

/**
 * onError for <img>, <video>, <audio>: swap in a fresh token when the 401 was the reason, once until the element
 * loads again (so a lazy cover or a long-lived player recovers from every later expiry, never in a loop).
 * `giveUp` runs when the element still fails (or failed for another reason).
 */
export function retryMedia(el: HTMLImageElement | HTMLMediaElement, giveUp?: () => void): void {
  if (el.dataset.mediaRetried) return giveUp?.();
  el.dataset.mediaRetried = "1";
  void recoverMediaUrl(el.currentSrc || el.src).then((next) => {
    if (!next) return giveUp?.();
    el.addEventListener(el instanceof HTMLMediaElement ? "loadeddata" : "load", () => delete el.dataset.mediaRetried, { once: true });
    el.src = next;
    if (el instanceof HTMLMediaElement) el.load();
  });
}

export function assetUrl(token: string, courseId: string, version: number, path: string): string {
  if (isMock()) return mockAssetUrl(courseId, path) ?? "";
  const p = path.split("/").map(encodeURIComponent).join("/");
  return withToken(`${API_BASE}/courses/${courseId}/versions/${version}/assets/${p}`, mediaToken ?? token);
}

export function coverUrl(token: string, courseId: string): string {
  if (isMock()) return mockCoverUrl(courseId) ?? "";
  return withToken(`${API_BASE}/courses/${courseId}/cover`, mediaToken ?? token);
}
