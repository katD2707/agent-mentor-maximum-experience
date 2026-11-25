// Test harness: in-memory KV, a fake Apps Script (global fetch), and small request helpers.
import worker from "../src/index.js";
import { sha256Hex } from "../src/util.js";

export class FakeKV {
  constructor() { this.m = new Map(); }
  _live(k) {
    const e = this.m.get(k);
    if (!e) return null;
    if (e.exp && e.exp <= Date.now()) { this.m.delete(k); return null; }
    return e;
  }
  async get(k, type = "text") {
    const e = this._live(k);
    if (!e) return null;
    if (type === "json") return JSON.parse(typeof e.v === "string" ? e.v : new TextDecoder().decode(e.v));
    if (type === "arrayBuffer") return typeof e.v === "string" ? new TextEncoder().encode(e.v).buffer : e.v.slice(0);
    return typeof e.v === "string" ? e.v : new TextDecoder().decode(e.v);
  }
  async put(k, v, opts = {}) {
    this.m.set(k, { v: v instanceof ArrayBuffer ? v.slice(0) : v, exp: opts.expirationTtl ? Date.now() + opts.expirationTtl * 1000 : null, ttl: opts.expirationTtl });
  }
  async delete(k) { this.m.delete(k); }
  async list({ prefix = "" } = {}) {
    const keys = [...this.m.keys()].filter((k) => k.startsWith(prefix) && this._live(k)).sort().map((name) => ({ name }));
    return { keys, list_complete: true };
  }
}

export const ORIGIN = "https://hub.test";
export const ADMIN_KEY = "adm-test-key";

export function makeEnv(extra = {}) {
  return { HUB: new FakeKV(), ADMIN_KEY, SCRIPT_URL: "https://script.test/exec", SCRIPT_SECRET: "s3cret", ...extra };
}

// Replaces global fetch with a fake Apps Script that records calls. Returns { calls, restore, failNext }.
export function fakeScript() {
  const real = globalThis.fetch;
  const st = { calls: [], fail: false };
  globalThis.fetch = async (url, init) => {
    const body = JSON.parse(init.body);
    st.calls.push(body);
    if (st.fail) return new Response("boom", { status: 500 });
    if (body.secret !== "s3cret") return Response.json({ ok: false, error: "forbidden" });
    if (body.action === "publish") return Response.json({ ok: true, pack_id: "pack1", cover_id: "cover1" });
    return Response.json({ ok: true });
  };
  st.restore = () => { globalThis.fetch = real; };
  st.mails = () => st.calls.filter((c) => c.action === "mail");
  return st;
}

export async function call(env, method, path, { body, token, admin, form } = {}) {
  const headers = {};
  let payload;
  if (token) headers.authorization = `Bearer ${token}`;
  if (admin) headers["x-admin-key"] = ADMIN_KEY;
  if (form) payload = form;
  else if (body !== undefined) { headers["content-type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await worker.fetch(new Request(ORIGIN + path, { method, headers, body: payload }), env);
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch (e) { /* html or empty */ }
  return { status: res.status, data, text };
}

export const reg = (env, over = {}) => call(env, "POST", "/api/register", { body: { role: "student", username: "lan.nguyen", password: "secret1", display_name: "Lan", ...over } });

export async function pngFile(name = "a.png") {
  return new File([new Uint8Array([137, 80, 78, 71, 1, 2, 3])], name, { type: "image/png" });
}

export async function submitCourseForm(over = {}) {
  const pack = new Uint8Array([80, 75, 3, 4, 9, 9, 9]);
  const f = new FormData();
  f.set("course_id", over.course_id || "c-toan8");
  f.set("version", String(over.version || 1));
  f.set("title", over.title || "Toán 8");
  f.set("entry", JSON.stringify({ id: over.course_id || "c-toan8", title: "Toán 8", version: over.version || 1 }));
  f.set("meta", JSON.stringify({ id: over.course_id || "c-toan8", lessons: [] }));
  f.set("pack", new File([pack], "pack.zip", { type: "application/zip" }));
  f.set("zip_sha256", await sha256Hex(pack));
  f.set("cover", new File([new Uint8Array([1, 2])], "cover.png", { type: "image/png" }));
  f.set("cover_name", "cover.png");
  return f;
}

// Registers a teacher and walks them to status xac_minh. Returns { token, id, script }.
export async function verifiedTeacher(env, script, username = "co.hoa", email = "hoa@gmail.com") {
  const r = await reg(env, { role: "teacher", username, display_name: "Cô Hoa", email });
  const token = r.data.token, id = r.data.account.id;
  const link = /ho-so\?t=([0-9a-f]+)/.exec(script.mails().at(-1).html)[1];
  const f = new FormData();
  f.set("t", link); f.set("full_name", "Nguyễn Thị Hoa"); f.set("workplace", "THCS A"); f.append("subjects", "Toán");
  f.append("level", "THCS"); f.set("cert_kind", "Cử nhân Sư phạm Toán"); f.set("cert_number", "123"); f.set("pledge", "1");
  f.append("photos", await pngFile());
  await call(env, "POST", "/api/ho-so", { form: f });
  await call(env, "POST", `/api/admin/teachers/${id}/approve`, { admin: true });
  const code = /letter-spacing:6px[^>]*>(\d{6})</.exec(script.mails().at(-1).html)[1];
  await call(env, "POST", "/api/teacher/verify", { token, body: { code } });
  return { token, id };
}
