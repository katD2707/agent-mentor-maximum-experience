// Small helpers: JSON replies, hashing, codes, KV listing. No dependencies.
const enc = new TextEncoder();

export function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
}
export const fail = (code, status = 400) => json({ error: code }, status);
export function html(body, status = 200) {
  return new Response(body, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function toHex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
export function randHex(bytes) {
  return toHex(crypto.getRandomValues(new Uint8Array(bytes)));
}
export async function sha256Hex(data) {
  return toHex(await crypto.subtle.digest("SHA-256", typeof data === "string" ? enc.encode(data) : data));
}
export function toB64(buf) {
  const u = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return btoa(s);
}
export function timingEq(a, b) {
  a = String(a); b = String(b);
  let d = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) d |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return d === 0;
}
export function code6() {
  return String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000).padStart(6, "0");
}

// PBKDF2-SHA256. Free-plan Workers have ~10 ms CPU, so the default is a modest 20000 rounds; the count is stored in the hash.
export const PBKDF2_ITER = 20000;
async function derive(password, salt, iter) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  return crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations: iter }, key, 256);
}
export async function hashPassword(password, iter = PBKDF2_ITER) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  return `pbkdf2-sha256$${iter}$${toHex(salt)}$${toHex(await derive(password, salt, iter))}`;
}
export async function verifyPassword(password, stored) {
  const [alg, iter, salt, hash] = String(stored || "").split("$");
  if (alg !== "pbkdf2-sha256" || !salt) return false;
  const s = new Uint8Array(salt.match(/../g).map((h) => parseInt(h, 16)));
  return timingEq(toHex(await derive(password, s, Number(iter))), hash);
}

export async function listAll(kv, prefix) {
  const names = [];
  let cursor;
  do {
    const r = await kv.list({ prefix, cursor });
    names.push(...r.keys.map((k) => k.name));
    cursor = r.list_complete ? undefined : r.cursor;
  } while (cursor);
  return names;
}
export const getJ = (env, key) => env.HUB.get(key, "json");
export const putJ = (env, key, val, opts) => env.HUB.put(key, JSON.stringify(val), opts);
