// Mentor hub: accounts, teacher approval and the course review queue. Cloudflare Worker + KV (binding HUB).
import { json, fail, html, esc, randHex, sha256Hex, toB64, timingEq, code6, hashPassword, verifyPassword, listAll, getJ, putJ } from "./util.js";
import { callScript, sendMail, mails } from "./mail.js";
import { hoSoPage, receivedPage, noticePage, adminPage } from "./pages.js";

const DAY = 86400;
const USERNAME_RE = /^[a-z0-9][a-z0-9._-]{1,31}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const COURSE_ID_RE = /^[A-Za-z0-9._-]{1,64}$/;
const MAX_PHOTO = 5 * 1024 * 1024;
const MAX_PACK = 20 * 1024 * 1024;
const GRADES = new Set([...Array(12)].map((_, i) => String(i + 1)).concat("dh"));
const EXT = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif" };
const MIME = { jpg: "image/jpeg", png: "image/png", webp: "image/webp", gif: "image/gif" };

const now = () => new Date().toISOString();
const clean = (v, max = 200) => String(v ?? "").trim().slice(0, max);
async function body(request) {
  const b = await request.json().catch(() => null);
  return b && typeof b === "object" && !Array.isArray(b) ? b : null;
}

// ----- accounts -----
const view = (a) => ({
  id: a.id, username: a.username, display_name: a.display_name, role: a.role, email: a.email || null,
  grade: a.grade || null, parent_email: a.parent_email || null, teacher_status: a.teacher_status || null, reject_reason: a.reject_reason || null,
});
const getAcct = (env, id) => (id ? getJ(env, `acct:${id}`) : null);
const saveAcct = (env, a) => putJ(env, `acct:${a.id}`, a);

async function findByLogin(env, login) {
  const l = clean(login, 120).toLowerCase();
  if (!l) return null;
  return getAcct(env, await env.HUB.get(l.includes("@") ? `email:${l}` : `user:${l}`));
}
async function newSession(env, id) {
  const token = randHex(32);
  await env.HUB.put(`sess:${await sha256Hex(token)}`, id, { expirationTtl: 90 * DAY });
  return token;
}
function bearer(request) {
  const m = /^Bearer\s+(\S+)/i.exec(request.headers.get("authorization") || "");
  return m ? m[1] : null;
}
async function authAcct(env, request) {
  const t = bearer(request);
  if (!t) return null;
  return getAcct(env, await env.HUB.get(`sess:${await sha256Hex(t)}`));
}

async function issueCode(env, purpose, id) {
  const code = code6();
  await putJ(env, `code:${purpose}:${id}`, { code, tries: 0, exp: Date.now() + DAY * 1000 }, { expirationTtl: DAY });
  return code;
}
async function checkCode(env, purpose, id, given) {
  const key = `code:${purpose}:${id}`;
  const c = await getJ(env, key);
  if (!c) return false;
  if (timingEq(c.code, clean(given, 20))) { await env.HUB.delete(key); return true; }
  c.tries = (c.tries || 0) + 1;
  if (c.tries >= 5) await env.HUB.delete(key);
  else await putJ(env, key, c, { expirationTtl: Math.max(60, Math.ceil((c.exp - Date.now()) / 1000)) });
  return false;
}
async function newFormLink(env, request, acct) {
  const t = randHex(24);
  await env.HUB.put(`form:${t}`, acct.id, { expirationTtl: 30 * DAY });
  return `${new URL(request.url).origin}/ho-so?t=${t}`;
}
async function mailFormLink(env, request, acct) {
  const [s, h] = mails.form(acct.display_name, await newFormLink(env, request, acct));
  await sendMail(env, acct.email, s, h);
}
const mask = (e) => { const [u, d] = e.split("@"); return `${u[0]}•••@${d}`; };

async function register(env, request) {
  const b = await body(request);
  if (!b) return fail("bad_request", 422);
  const role = b.role, username = clean(b.username, 40).toLowerCase(), password = String(b.password || "");
  const display = clean(b.display_name, 60), email = clean(b.email, 120).toLowerCase() || null;
  const parent = clean(b.parent_email, 120).toLowerCase() || null;
  const grade = b.grade == null || b.grade === "" ? null : String(b.grade);
  if (!["student", "teacher"].includes(role) || !USERNAME_RE.test(username) || password.length < 6 || !display) return fail("bad_request", 422);
  if ((email && !EMAIL_RE.test(email)) || (parent && !EMAIL_RE.test(parent)) || (grade && !GRADES.has(grade))) return fail("bad_request", 422);
  if (role === "teacher" && !email) return fail("bad_request", 422);
  if (await env.HUB.get(`user:${username}`)) return fail("username_taken", 409);
  if (email && (await env.HUB.get(`email:${email}`))) return fail("email_taken", 409);
  const acct = {
    id: `a_${randHex(8)}`, username, display_name: display, role, email, grade: role === "student" ? grade : null,
    parent_email: role === "student" ? parent : null, teacher_status: role === "teacher" ? "chua_nop" : null,
    reject_reason: null, pw: await hashPassword(password), created_at: now(),
  };
  await saveAcct(env, acct);
  await env.HUB.put(`user:${username}`, acct.id);
  if (email) await env.HUB.put(`email:${email}`, acct.id);
  if (role === "teacher") await mailFormLink(env, request, acct);
  return json({ token: await newSession(env, acct.id), account: view(acct) }, 201);
}

async function login(env, request) {
  const b = await body(request);
  if (!b) return fail("bad_request", 422);
  const a = await findByLogin(env, b.login);
  if (!a || !(await verifyPassword(String(b.password || ""), a.pw))) return fail("invalid_credentials", 401);
  return json({ token: await newSession(env, a.id), account: view(a) });
}

async function forgot(env, request) {
  const b = await body(request);
  const a = b && (await findByLogin(env, b.login));
  const to = a && (a.email || a.parent_email);
  if (!to) return json({ via: "none" });
  const [s, h] = mails.reset(a.display_name, await issueCode(env, "reset", a.id));
  await sendMail(env, to, s, h);
  return json({ via: "email", to: mask(to) });
}
async function forgotRequest(env, request) {
  const b = await body(request);
  const a = b && (await findByLogin(env, b.login));
  if (a) await putJ(env, `reset:${Date.now()}:${a.username}`, { username: a.username, display_name: a.display_name, phone: clean(b.phone, 30), at: now() });
  return new Response(null, { status: 204 });
}
async function reset(env, request) {
  const b = await body(request);
  const a = b && (await findByLogin(env, b.login));
  if (!a) return fail("wrong_code", 400);
  if (String(b.password || "").length < 6) return fail("bad_request", 422);
  if (!(await checkCode(env, "reset", a.id, b.code))) return fail("wrong_code", 400);
  a.pw = await hashPassword(String(b.password));
  await saveAcct(env, a);
  return new Response(null, { status: 204 });
}

// ----- teacher -----
async function teacherAccount(env, request, path) {
  const a = await authAcct(env, request);
  if (!a) return fail("unauthorized", 401);
  if (a.role !== "teacher") return fail("not_teacher", 403);
  const st = a.teacher_status;
  if (path === "/api/teacher/resend-form") {
    if (st !== "chua_nop" && st !== "tu_choi") return fail("bad_state", 409);
    await mailFormLink(env, request, a);
    return new Response(null, { status: 204 });
  }
  if (path === "/api/teacher/resend-code") {
    if (st !== "da_duyet") return fail("bad_state", 409);
    const [s, h] = mails.code(a.display_name, await issueCode(env, "verify", a.id));
    await sendMail(env, a.email, s, h);
    return new Response(null, { status: 204 });
  }
  if (path === "/api/teacher/verify") {
    if (st === "xac_minh") return json({ account: view(a) });
    const b = await body(request);
    if (st !== "da_duyet" || !b || !(await checkCode(env, "verify", a.id, b.code))) return fail("wrong_code", 400);
    a.teacher_status = "xac_minh";
    await saveAcct(env, a);
    return json({ account: view(a) });
  }
  return fail("not_found", 404);
}

async function formAcct(env, t) {
  const id = t ? await env.HUB.get(`form:${clean(t, 80)}`) : null;
  return getAcct(env, id);
}
async function hoSoGet(env, request) {
  const t = new URL(request.url).searchParams.get("t");
  const a = await formAcct(env, t);
  if (!a) return html(noticePage("Liên kết không dùng được", "Liên kết đã hết hạn hoặc không đúng. Bạn mở app Mentor và chọn “Gửi lại email” để nhận liên kết mới."), 404);
  if (a.teacher_status !== "chua_nop" && a.teacher_status !== "tu_choi") return html(noticePage("Hồ sơ đã nộp", "Hồ sơ của bạn đang được xem hoặc đã duyệt. Bạn có thể đóng trang này."));
  return html(hoSoPage({ t, email: a.email, reason: a.teacher_status === "tu_choi" ? a.reject_reason : null }));
}
async function hoSoPost(env, request) {
  let f;
  try { f = await request.formData(); } catch (e) { return html(noticePage("Chưa gửi được", "Biểu mẫu không đọc được. Bạn thử lại nhé."), 400); }
  const a = await formAcct(env, f.get("t"));
  if (!a || (a.teacher_status !== "chua_nop" && a.teacher_status !== "tu_choi")) return html(noticePage("Liên kết không dùng được", "Liên kết đã hết hạn hoặc hồ sơ đã được nộp."), 404);
  const bad = (m) => html(noticePage("Chưa gửi được", m), 422);
  const d = {
    full_name: clean(f.get("full_name"), 100), workplace: clean(f.get("workplace"), 160),
    subjects: f.getAll("subjects").map((s) => clean(s, 40)).filter(Boolean).slice(0, 12),
    level: f.getAll("level").map((s) => clean(s, 40)).filter(Boolean).join(", ").slice(0, 100),
    cert_kind: clean(f.get("cert_kind"), 160), cert_number: clean(f.get("cert_number"), 80),
  };
  if (!d.full_name || !d.workplace || !d.subjects.length || !d.level || !d.cert_kind || !d.cert_number) return bad("Bạn điền đủ các ô nhé.");
  if (f.get("pledge") !== "1") return bad("Bạn cần đánh dấu ô cam đoan.");
  const files = f.getAll("photos").filter((x) => x && typeof x === "object" && x.size > 0);
  if (files.length < 1 || files.length > 3) return bad("Bạn thêm từ 1 đến 3 ảnh nhé.");
  const photos = [];
  for (const [i, file] of files.entries()) {
    const ext = EXT[file.type];
    if (!ext) return bad("Ảnh cần là JPG, PNG hoặc WebP.");
    if (file.size > MAX_PHOTO) return bad("Mỗi ảnh nhỏ hơn 5 MB nhé.");
    const key = `${a.id}-${Date.now().toString(36)}${i}.${ext}`;
    await env.HUB.put(`photo:${key}`, await file.arrayBuffer());
    photos.push({ key, name: i + 1 });
  }
  await putJ(env, `decl:${a.id}`, { ...d, photos, at: now() });
  a.teacher_status = "cho_duyet";
  await saveAcct(env, a);
  await env.HUB.delete(`form:${clean(f.get("t"), 80)}`);
  return html(receivedPage());
}

// ----- courses -----
const courseView = (c) => ({ course_id: c.course_id, title: c.title, version: c.version, kind: c.kind, state: c.state, live_version: c.live_version ?? null, reason: c.reason || null, updated_at: c.updated_at });
async function verifiedTeacher(env, request) {
  const a = await authAcct(env, request);
  if (!a) return [null, fail("unauthorized", 401)];
  if (a.role !== "teacher" || a.teacher_status !== "xac_minh") return [null, fail("teacher_unverified", 403)];
  return [a, null];
}
async function allCourses(env) {
  const names = await listAll(env.HUB, "course:");
  return (await Promise.all(names.map((n) => getJ(env, n)))).filter(Boolean);
}
const touch = (c, patch) => Object.assign(c, patch, { updated_at: now() });

async function courseSubmit(env, request) {
  const [a, e] = await verifiedTeacher(env, request);
  if (e) return e;
  let f;
  try { f = await request.formData(); } catch (x) { return fail("bad_request", 422); }
  const id = clean(f.get("course_id"), 80), version = parseInt(f.get("version"), 10), title = clean(f.get("title"), 160);
  let entry, meta;
  try { entry = JSON.parse(f.get("entry")); meta = JSON.parse(f.get("meta")); } catch (x) { return fail("bad_request", 422); }
  const pack = f.get("pack"), cover = f.get("cover");
  if (!COURSE_ID_RE.test(id) || !(version >= 1) || !title || !entry || typeof entry !== "object" || !pack || typeof pack !== "object") return fail("bad_request", 422);
  if (pack.size > MAX_PACK) return fail("too_big", 413);
  const packBuf = await pack.arrayBuffer();
  if (f.get("zip_sha256") && (await sha256Hex(packBuf)) !== String(f.get("zip_sha256")).toLowerCase()) return fail("hash_mismatch", 422);
  const old = await getJ(env, `course:${id}`);
  if (old && old.owner !== a.id) return fail("not_owner", 409);
  if (old && old.state === "cho_duyet") return fail("pending", 409);
  const course = touch(old || { course_id: id, owner: a.id, live_version: null, live_entry: null }, {
    title, version, kind: old && old.live_version ? "update" : "new", state: "cho_duyet", reason: null,
  });
  await env.HUB.put(`pending:${id}:pack`, packBuf);
  const hasCover = cover && typeof cover === "object" && cover.size > 0;
  if (hasCover) await env.HUB.put(`pending:${id}:cover`, await cover.arrayBuffer());
  await putJ(env, `pending:${id}`, { entry, meta, zip_sha256: clean(f.get("zip_sha256"), 80), zip_bytes: packBuf.byteLength, cover_name: hasCover ? clean(f.get("cover_name"), 80) || "cover.png" : null, has_cover: !!hasCover, version, at: now() });
  await putJ(env, `course:${id}`, course);
  return json({ course: courseView(course) });
}

async function dropPending(env, id) {
  await Promise.all([`pending:${id}`, `pending:${id}:pack`, `pending:${id}:cover`].map((k) => env.HUB.delete(k)));
}

async function courseMine(env, request) {
  const [a, e] = await verifiedTeacher(env, request);
  if (e) return e;
  return json({ courses: (await allCourses(env)).filter((c) => c.owner === a.id).map(courseView) });
}
async function courseAction(env, request, id, action) {
  const [a, e] = await verifiedTeacher(env, request);
  if (e) return e;
  const c = await getJ(env, `course:${id}`);
  if (!c || c.owner !== a.id) return fail("not_found", 404);
  if (action === "withdraw") {
    if (c.state !== "cho_duyet") return fail("bad_state", 409);
    await dropPending(env, id);
    touch(c, { state: c.live_version ? "da_dang" : "rut_lai", reason: null });
    await putJ(env, `course:${id}`, c);
    return json({ course: courseView(c) });
  }
  return unpublish(env, c, null);
}
async function unpublish(env, c, reason) {
  if (!c.live_version) return fail("bad_state", 409);
  if (!env.SCRIPT_URL) return fail("script_missing", 503);
  try { await callScript(env, { action: "unpublish", course_id: c.course_id }); } catch (e) { return fail("script_failed", 502); }
  await dropPending(env, c.course_id);
  touch(c, { state: "da_go", live_version: null, live_entry: null, reason: reason || null });
  await putJ(env, `course:${c.course_id}`, c);
  return json({ course: courseView(c) });
}

// ----- admin -----
const isAdmin = (env, request) => !!env.ADMIN_KEY && timingEq((request.headers.get("x-admin-key") || "").trim(), String(env.ADMIN_KEY).trim());

async function teacherDetail(env, a) {
  const decl = await getJ(env, `decl:${a.id}`);
  return { ...view(a), submitted_at: decl ? decl.at : null, decl: decl ? { ...decl, photos: decl.photos.map((p) => ({ key: p.key, url: `/api/admin/photo/${p.key}` })) } : null };
}
async function allAccounts(env) {
  const names = await listAll(env.HUB, "acct:");
  return (await Promise.all(names.map((n) => getJ(env, n)))).filter(Boolean);
}
const needReason = (b) => (b && clean(b.reason, 500)) || null;

async function admin(env, request, url, path) {
  const m = request.method;
  let r;
  if (path === "/api/admin/teachers" && m === "GET") {
    const st = url.searchParams.get("status") || "cho_duyet";
    const list = (await allAccounts(env)).filter((a) => a.role === "teacher" && a.teacher_status === st);
    const out = await Promise.all(list.map((a) => teacherDetail(env, a)));
    return json({ teachers: out.sort((x, y) => String(x.submitted_at).localeCompare(String(y.submitted_at))) });
  }
  if ((r = /^\/api\/admin\/teachers\/([\w-]+)(?:\/(approve|reject))?$/.exec(path))) {
    const a = await getAcct(env, r[1]);
    if (!a || a.role !== "teacher") return fail("not_found", 404);
    if (!r[2] && m === "GET") return json({ teacher: await teacherDetail(env, a) });
    if (m !== "POST") return fail("not_found", 404);
    if (a.teacher_status !== "cho_duyet") return fail("bad_state", 409);
    if (r[2] === "approve") {
      a.teacher_status = "da_duyet"; a.reject_reason = null;
      await saveAcct(env, a);
      const [s, h] = mails.approved(a.display_name, await issueCode(env, "verify", a.id));
      await sendMail(env, a.email, s, h);
      return json({ account: view(a) });
    }
    const reason = needReason(await body(request));
    if (!reason) return fail("reason_required", 422);
    a.teacher_status = "tu_choi"; a.reject_reason = reason;
    await saveAcct(env, a);
    const [s, h] = mails.teacherRejected(a.display_name, reason, await newFormLink(env, request, a));
    await sendMail(env, a.email, s, h);
    return json({ account: view(a) });
  }
  if ((r = /^\/api\/admin\/photo\/([\w.-]+)$/.exec(path)) && m === "GET") {
    const buf = await env.HUB.get(`photo:${r[1]}`, "arrayBuffer");
    if (!buf) return fail("not_found", 404);
    return new Response(buf, { headers: { "content-type": MIME[r[1].split(".").pop()] || "image/jpeg", "cache-control": "private, max-age=3600" } });
  }
  if (path === "/api/admin/courses" && m === "GET") {
    const st = url.searchParams.get("state") || "cho_duyet";
    const out = [];
    for (const c of (await allCourses(env)).filter((x) => x.state === st)) {
      const o = await getAcct(env, c.owner);
      const p = st === "cho_duyet" ? await getJ(env, `pending:${c.course_id}`) : null;
      out.push({ ...courseView(c), teacher: o ? { name: o.display_name, email: o.email } : null, entry: p ? p.entry : c.live_entry || null, zip_bytes: p ? p.zip_bytes : null });
    }
    return json({ courses: out });
  }
  if ((r = /^\/api\/admin\/courses\/([\w.-]+)\/(approve|reject|remove)$/.exec(path)) && m === "POST") {
    const c = await getJ(env, `course:${r[1]}`);
    if (!c) return fail("not_found", 404);
    const o = await getAcct(env, c.owner);
    const name = o ? o.display_name : "bạn";
    if (r[2] === "approve") {
      if (c.state !== "cho_duyet") return fail("bad_state", 409);
      if (!env.SCRIPT_URL) return fail("script_missing", 503);
      const p = await getJ(env, `pending:${c.course_id}`);
      const pack = await env.HUB.get(`pending:${c.course_id}:pack`, "arrayBuffer");
      if (!p || !pack) return fail("pending_missing", 409);
      const cover = p.has_cover ? await env.HUB.get(`pending:${c.course_id}:cover`, "arrayBuffer") : null;
      try {
        await callScript(env, {
          action: "publish", course_id: c.course_id, version: c.version, entry: p.entry, meta: p.meta, pack_b64: toB64(pack),
          zip_sha256: p.zip_sha256, zip_bytes: p.zip_bytes, cover_b64: cover ? toB64(cover) : null, cover_name: p.cover_name,
        });
      } catch (e) { return fail("script_failed", 502); }
      await dropPending(env, c.course_id);
      touch(c, { state: "da_dang", live_version: c.version, live_entry: p.entry, reason: null });
      await putJ(env, `course:${c.course_id}`, c);
      if (o) { const [s, h] = mails.courseApproved(name, c.title); await sendMail(env, o.email, s, h); }
      return json({ course: courseView(c) });
    }
    const reason = needReason(await body(request));
    if (!reason) return fail("reason_required", 422);
    if (r[2] === "reject") {
      if (c.state !== "cho_duyet") return fail("bad_state", 409);
      await dropPending(env, c.course_id);
      touch(c, { state: "tu_choi", reason });
      await putJ(env, `course:${c.course_id}`, c);
      if (o) { const [s, h] = mails.courseRejected(name, c.title, reason); await sendMail(env, o.email, s, h); }
      return json({ course: courseView(c) });
    }
    const res = await unpublish(env, c, reason);
    if (res.status === 200 && o) { const [s, h] = mails.courseRemoved(name, c.title, reason); await sendMail(env, o.email, s, h); }
    return res;
  }
  if (path === "/api/admin/resets" && m === "GET") {
    const names = (await listAll(env.HUB, "reset:")).sort();
    return json({ resets: (await Promise.all(names.map((n) => getJ(env, n)))).filter(Boolean).reverse() });
  }
  if (path === "/api/admin/accounts" && m === "GET") {
    const q = clean(url.searchParams.get("q"), 80).toLowerCase();
    const rows = (await allAccounts(env)).filter((a) => !q || `${a.display_name} ${a.username} ${a.email || ""}`.toLowerCase().includes(q));
    return json({ accounts: rows.slice(0, 200).map(view) });
  }
  if ((r = /^\/api\/admin\/accounts\/([^/]+)\/reset-password$/.exec(path)) && m === "POST") {
    const u = await env.HUB.get(`user:${decodeURIComponent(r[1]).toLowerCase()}`);
    const a = await getAcct(env, u);
    if (!a) return fail("not_found", 404);
    const chars = "abcdefghjkmnpqrstuvwxyz";
    const temp = `Mk-${1000 + (crypto.getRandomValues(new Uint32Array(1))[0] % 9000)}-${chars[crypto.getRandomValues(new Uint8Array(1))[0] % chars.length]}${chars[crypto.getRandomValues(new Uint8Array(1))[0] % chars.length]}`;
    a.pw = await hashPassword(temp);
    await saveAcct(env, a);
    for (const k of await listAll(env.HUB, "reset:")) if (k.endsWith(`:${a.username}`)) await env.HUB.delete(k);
    return json({ temp_password: temp });
  }
  if (path === "/api/admin/outbox" && m === "GET") {
    const names = (await listAll(env.HUB, "outbox:")).sort().reverse();
    return json({ outbox: await Promise.all(names.map(async (n) => ({ key: n, ...(await getJ(env, n)) }))) });
  }
  if ((r = /^\/api\/admin\/outbox\/([\w:-]+)$/.exec(path)) && m === "DELETE") {
    await env.HUB.delete(r[1].startsWith("outbox:") ? r[1] : `outbox:${r[1]}`);
    return new Response(null, { status: 204 });
  }
  return fail("not_found", 404);
}

// ----- router -----
export async function handle(request, env) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "") || "/";
  const m = request.method;
  let r;
  if (m === "OPTIONS") return new Response(null, { status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type,x-admin-key", "access-control-allow-methods": "GET,POST,DELETE,OPTIONS" } });
  if (path === "/" || path === "/api/health") return json({ ok: true, service: "mentor-hub" });
  if (path === "/ho-so" && m === "GET") return hoSoGet(env, request);
  if (path === "/api/ho-so" && m === "POST") return hoSoPost(env, request);
  if (path === "/quan-tri" && m === "GET") return html(adminPage());

  if (path.startsWith("/api/admin/")) return isAdmin(env, request) ? admin(env, request, url, path) : fail("forbidden", 403);

  if (m === "POST") {
    if (path === "/api/register") return register(env, request);
    if (path === "/api/login") return login(env, request);
    if (path === "/api/forgot") return forgot(env, request);
    if (path === "/api/forgot/request") return forgotRequest(env, request);
    if (path === "/api/reset") return reset(env, request);
    if (path === "/api/logout") {
      const t = bearer(request);
      if (t) await env.HUB.delete(`sess:${await sha256Hex(t)}`);
      return new Response(null, { status: 204 });
    }
    if (path.startsWith("/api/teacher/")) return teacherAccount(env, request, path);
    if (path === "/api/courses/submit") return courseSubmit(env, request);
    if ((r = /^\/api\/courses\/([\w.-]+)\/(withdraw|remove)$/.exec(path))) return courseAction(env, request, r[1], r[2]);
  }
  if (m === "GET") {
    if (path === "/api/me") {
      const a = await authAcct(env, request);
      return a ? json({ account: view(a) }) : fail("unauthorized", 401);
    }
    if (path === "/api/courses/mine") return courseMine(env, request);
  }
  return fail("not_found", 404);
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (e) {
      return json({ error: "server_error" }, 500);
    }
  },
};
