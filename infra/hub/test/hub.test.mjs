import { test } from "node:test";
import assert from "node:assert/strict";
import { call, reg, makeEnv, fakeScript, pngFile, submitCourseForm, verifiedTeacher } from "./helpers.mjs";

const codeIn = (mail) => /letter-spacing:6px[^>]*>(\d{6})</.exec(mail.html)[1];

test("register and login by username and by email", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    const r = await reg(env, { email: "Lan@Gmail.com", grade: "7" });
    assert.equal(r.status, 201);
    assert.equal(r.data.account.role, "student");
    assert.equal(r.data.account.teacher_status, null);
    assert.equal(r.data.account.email, "lan@gmail.com");
    assert.equal(r.data.account.grade, "7");
    assert.equal(r.data.account.pw, undefined);
    const me = await call(env, "GET", "/api/me", { token: r.data.token });
    assert.equal(me.data.account.username, "lan.nguyen");
    assert.equal((await call(env, "GET", "/api/me")).status, 401);

    const byUser = await call(env, "POST", "/api/login", { body: { login: "lan.nguyen", password: "secret1" } });
    assert.equal(byUser.status, 200);
    const byMail = await call(env, "POST", "/api/login", { body: { login: "LAN@gmail.com", password: "secret1" } });
    assert.equal(byMail.data.account.id, r.data.account.id);
    const bad = await call(env, "POST", "/api/login", { body: { login: "lan.nguyen", password: "nope123" } });
    assert.equal(bad.status, 401);
    assert.equal(bad.data.error, "invalid_credentials");

    assert.equal((await call(env, "POST", "/api/logout", { token: byUser.data.token })).status, 204);
    assert.equal((await call(env, "GET", "/api/me", { token: byUser.data.token })).status, 401);
    assert.match([...env.HUB.m.keys()].find((k) => k.startsWith("acct:")), /^acct:a_/);
    assert.match(JSON.parse(env.HUB.m.get(`acct:${r.data.account.id}`).v).pw, /^pbkdf2-sha256\$20000\$/);
  } finally { sc.restore(); }
});

test("register rules: duplicate username/email, validation", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    await reg(env, { email: "a@gmail.com" });
    const dup = await reg(env, { display_name: "Khác" });
    assert.equal(dup.status, 409);
    assert.equal(dup.data.error, "username_taken");
    const dupMail = await reg(env, { username: "other", email: "a@gmail.com" });
    assert.equal(dupMail.data.error, "email_taken");
    for (const over of [{ username: "A b" }, { password: "12345" }, { role: "admin" }, { display_name: "" }, { role: "teacher" }]) {
      const r = await reg(env, { username: "x" + Math.random().toString(36).slice(2, 8), ...over });
      assert.equal(r.status, 422, JSON.stringify(over));
      assert.equal(r.data.error, "bad_request");
    }
  } finally { sc.restore(); }
});

test("teacher flow: form, approve, verify, submit, publish, mine, remove", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    const r = await reg(env, { role: "teacher", username: "co.hoa", display_name: "Cô Hoa", email: "hoa@gmail.com" });
    assert.equal(r.data.account.teacher_status, "chua_nop");
    const token = r.data.token, id = r.data.account.id;
    // form link mailed, built from the request origin
    const formMail = sc.mails().at(-1);
    assert.equal(formMail.to, "hoa@gmail.com");
    assert.equal(formMail.secret, "s3cret");
    const t = /https:\/\/hub\.test\/ho-so\?t=([0-9a-f]+)/.exec(formMail.html)[1];
    // not verified yet: course routes are refused
    assert.equal((await call(env, "GET", "/api/courses/mine", { token })).data.error, "teacher_unverified");
    // the form
    const page = await call(env, "GET", `/ho-so?t=${t}`);
    assert.equal(page.status, 200);
    assert.match(page.text, /Kê khai hồ sơ giáo viên/);
    assert.match(page.text, /hoa@gmail\.com/);
    assert.equal((await call(env, "GET", "/ho-so?t=zzz")).status, 404);
    const f = new FormData();
    f.set("t", t); f.set("full_name", "Nguyễn Thị Hoa"); f.set("workplace", "THCS A"); f.append("subjects", "Toán"); f.append("subjects", "Tin học");
    f.append("level", "THCS"); f.set("cert_kind", "Cử nhân Sư phạm Toán"); f.set("cert_number", "SP-1"); f.set("pledge", "1");
    f.append("photos", await pngFile());
    const sent = await call(env, "POST", "/api/ho-so", { form: f });
    assert.equal(sent.status, 200);
    assert.match(sent.text, /Đã nhận hồ sơ/);
    assert.equal((await call(env, "GET", "/api/me", { token })).data.account.teacher_status, "cho_duyet");
    assert.equal((await call(env, "GET", `/ho-so?t=${t}`)).status, 404, "form link is single use");

    // admin
    assert.equal((await call(env, "GET", "/api/admin/teachers")).status, 403);
    const list = await call(env, "GET", "/api/admin/teachers?status=cho_duyet", { admin: true });
    assert.equal(list.data.teachers.length, 1);
    const decl = list.data.teachers[0].decl;
    assert.equal(decl.full_name, "Nguyễn Thị Hoa");
    const photo = await fetch_photo(env, decl.photos[0].url);
    assert.equal(photo, 7);
    const ap = await call(env, "POST", `/api/admin/teachers/${id}/approve`, { admin: true });
    assert.equal(ap.data.account.teacher_status, "da_duyet");
    const code = codeIn(sc.mails().at(-1));

    // verify: wrong, then right
    const wrong = await call(env, "POST", "/api/teacher/verify", { token, body: { code: code === "000000" ? "000001" : "000000" } });
    assert.equal(wrong.status, 400);
    assert.equal(wrong.data.error, "wrong_code");
    assert.equal((await call(env, "GET", "/api/courses/mine", { token })).status, 403);
    const ok = await call(env, "POST", "/api/teacher/verify", { token, body: { code } });
    assert.equal(ok.data.account.teacher_status, "xac_minh");

    // submit a course
    const sub = await call(env, "POST", "/api/courses/submit", { token, form: await submitCourseForm() });
    assert.equal(sub.status, 200);
    assert.equal(sub.data.course.state, "cho_duyet");
    assert.equal(sub.data.course.kind, "new");
    assert.equal((await call(env, "POST", "/api/courses/submit", { token, form: await submitCourseForm() })).data.error, "pending");
    const bad = await submitCourseForm({ course_id: "c-x" });
    bad.set("zip_sha256", "00");
    assert.equal((await call(env, "POST", "/api/courses/submit", { token, form: bad })).data.error, "hash_mismatch");
    const queue = await call(env, "GET", "/api/admin/courses?state=cho_duyet", { admin: true });
    assert.equal(queue.data.courses[0].teacher.name, "Cô Hoa");

    // approve publishes through the script
    const before = sc.calls.length;
    const pub = await call(env, "POST", "/api/admin/courses/c-toan8/approve", { admin: true });
    assert.equal(pub.status, 200);
    const pc = sc.calls.slice(before).find((c) => c.action === "publish");
    assert.equal(pc.course_id, "c-toan8");
    assert.equal(pc.version, 1);
    assert.equal(pc.cover_name, "cover.png");
    assert.equal(Buffer.from(pc.pack_b64, "base64").length, 7);
    assert.equal(pc.entry.id, "c-toan8");
    assert.ok(pc.zip_sha256);
    const mine = await call(env, "GET", "/api/courses/mine", { token });
    assert.equal(mine.data.courses[0].state, "da_dang");
    assert.equal(mine.data.courses[0].live_version, 1);
    assert.match(sc.mails().at(-1).subject, /đã được đăng/);
    assert.equal((await call(env, "GET", "/api/admin/courses?state=da_dang", { admin: true })).data.courses.length, 1);

    // update, then reject: still live at v1
    const up = await call(env, "POST", "/api/courses/submit", { token, form: await submitCourseForm({ version: 2 }) });
    assert.equal(up.data.course.kind, "update");
    const rej = await call(env, "POST", "/api/admin/courses/c-toan8/reject", { admin: true, body: { reason: "Thiếu đáp án bài 5" } });
    assert.equal(rej.data.course.state, "tu_choi");
    assert.match(sc.mails().at(-1).html, /Thiếu đáp án bài 5/);

    // remove unpublishes
    const rm = await call(env, "POST", "/api/courses/c-toan8/remove", { token });
    assert.equal(rm.data.course.state, "da_go");
    assert.equal(sc.calls.at(-1).action, "unpublish");
    assert.equal(sc.calls.at(-1).course_id, "c-toan8");

    // another teacher cannot touch it
    const other = await verifiedTeacher(env, sc, "co.mai", "mai@gmail.com");
    assert.equal((await call(env, "POST", "/api/courses/submit", { token: other.token, form: await submitCourseForm() })).data.error, "not_owner");
    assert.equal((await call(env, "POST", "/api/courses/c-toan8/withdraw", { token: other.token })).status, 404);
  } finally { sc.restore(); }
});

async function fetch_photo(env, url) {
  const worker = (await import("../src/index.js")).default;
  const res = await worker.fetch(new Request("https://hub.test" + url, { headers: { "x-admin-key": "adm-test-key" } }), env);
  assert.equal(res.headers.get("content-type"), "image/png");
  return (await res.arrayBuffer()).byteLength;
}

test("teacher reject mails the reason and a fresh form link; resubmit works", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    const r = await reg(env, { role: "teacher", username: "co.lan", display_name: "Cô Lan", email: "lan@gmail.com" });
    const t = /ho-so\?t=([0-9a-f]+)/.exec(sc.mails().at(-1).html)[1];
    const f = new FormData();
    f.set("t", t); f.set("full_name", "L"); f.set("workplace", "W"); f.append("subjects", "Toán"); f.append("level", "THPT");
    f.set("cert_kind", "k"); f.set("cert_number", "1"); f.set("pledge", "1"); f.append("photos", await pngFile());
    await call(env, "POST", "/api/ho-so", { form: f });
    const id = r.data.account.id;
    assert.equal((await call(env, "POST", `/api/admin/teachers/${id}/reject`, { admin: true, body: {} })).status, 422);
    await call(env, "POST", `/api/admin/teachers/${id}/reject`, { admin: true, body: { reason: "Ảnh mờ" } });
    const m = sc.mails().at(-1);
    assert.match(m.html, /Ảnh mờ/);
    const t2 = /ho-so\?t=([0-9a-f]+)/.exec(m.html)[1];
    const me = await call(env, "GET", "/api/me", { token: r.data.token });
    assert.equal(me.data.account.teacher_status, "tu_choi");
    assert.equal(me.data.account.reject_reason, "Ảnh mờ");
    const page = await call(env, "GET", `/ho-so?t=${t2}`);
    assert.match(page.text, /Lần trước bị từ chối/);
    assert.match(page.text, /Ảnh mờ/);
    // resend-form from the app works while rejected, and not when waiting
    assert.equal((await call(env, "POST", "/api/teacher/resend-form", { token: r.data.token })).status, 204);
    const f2 = new FormData();
    f2.set("t", t2); f2.set("full_name", "L"); f2.set("workplace", "W"); f2.append("subjects", "Toán"); f2.append("level", "THPT");
    f2.set("cert_kind", "k"); f2.set("cert_number", "1"); f2.set("pledge", "1"); f2.append("photos", await pngFile());
    assert.equal((await call(env, "POST", "/api/ho-so", { form: f2 })).status, 200);
    assert.equal((await call(env, "POST", "/api/teacher/resend-form", { token: r.data.token })).status, 409);
    assert.equal((await call(env, "POST", "/api/teacher/resend-code", { token: r.data.token })).status, 409);
  } finally { sc.restore(); }
});

test("withdraw: back to rut_lai, or da_dang when an older version is live", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    const { token } = await verifiedTeacher(env, sc);
    await call(env, "POST", "/api/courses/submit", { token, form: await submitCourseForm() });
    const w = await call(env, "POST", "/api/courses/c-toan8/withdraw", { token });
    assert.equal(w.data.course.state, "rut_lai");
    assert.equal((await call(env, "POST", "/api/courses/c-toan8/withdraw", { token })).status, 409);
    assert.equal(env.HUB.m.has("pending:c-toan8"), false);
    assert.equal(env.HUB.m.has("pending:c-toan8:pack"), false);
    await call(env, "POST", "/api/courses/submit", { token, form: await submitCourseForm() });
    await call(env, "POST", "/api/admin/courses/c-toan8/approve", { admin: true });
    await call(env, "POST", "/api/courses/submit", { token, form: await submitCourseForm({ version: 2 }) });
    const w2 = await call(env, "POST", "/api/courses/c-toan8/withdraw", { token });
    assert.equal(w2.data.course.state, "da_dang");
    assert.equal(w2.data.course.live_version, 1);
  } finally { sc.restore(); }
});

test("forgot by email code, resend, wrong code limit; request without email", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    await reg(env, { email: "nguyen@gmail.com" });
    const f = await call(env, "POST", "/api/forgot", { body: { login: "lan.nguyen" } });
    assert.deepEqual(f.data, { via: "email", to: "n•••@gmail.com" });
    const code = codeIn(sc.mails().at(-1));
    assert.equal(sc.mails().at(-1).to, "nguyen@gmail.com");
    assert.equal((await call(env, "POST", "/api/reset", { body: { login: "lan.nguyen", code: "nope", password: "newpass1" } })).data.error, "wrong_code");
    const ok = await call(env, "POST", "/api/reset", { body: { login: "nguyen@gmail.com", code, password: "newpass1" } });
    assert.equal(ok.status, 204);
    assert.equal((await call(env, "POST", "/api/login", { body: { login: "lan.nguyen", password: "newpass1" } })).status, 200);
    assert.equal((await call(env, "POST", "/api/login", { body: { login: "lan.nguyen", password: "secret1" } })).status, 401);
    assert.equal((await call(env, "POST", "/api/reset", { body: { login: "lan.nguyen", code, password: "again12" } })).status, 400, "code is single use");

    // five wrong tries burn the code
    await call(env, "POST", "/api/forgot", { body: { login: "lan.nguyen" } });
    const c2 = codeIn(sc.mails().at(-1));
    for (let i = 0; i < 5; i++) await call(env, "POST", "/api/reset", { body: { login: "lan.nguyen", code: "999999x", password: "newpass2" } });
    assert.equal((await call(env, "POST", "/api/reset", { body: { login: "lan.nguyen", code: c2, password: "newpass2" } })).status, 400);

    // parent email is used when the pupil has none
    await reg(env, { username: "be.an", display_name: "An", parent_email: "me.an@gmail.com" });
    assert.equal((await call(env, "POST", "/api/forgot", { body: { login: "be.an" } })).data.to, "m•••@gmail.com");

    // no email: request to the teachers
    await reg(env, { username: "be.binh", display_name: "Bình" });
    assert.deepEqual((await call(env, "POST", "/api/forgot", { body: { login: "be.binh" } })).data, { via: "none" });
    assert.deepEqual((await call(env, "POST", "/api/forgot", { body: { login: "khongco" } })).data, { via: "none" });
    assert.equal((await call(env, "POST", "/api/forgot/request", { body: { login: "be.binh", phone: "0912" } })).status, 204);
    const rs = await call(env, "GET", "/api/admin/resets", { admin: true });
    assert.equal(rs.data.resets.length, 1);
    assert.equal(rs.data.resets[0].username, "be.binh");
    assert.equal(rs.data.resets[0].phone, "0912");
  } finally { sc.restore(); }
});

test("admin reset-password returns a temp password, clears the request, search works", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    await reg(env, { username: "be.binh", display_name: "Bình" });
    await call(env, "POST", "/api/forgot/request", { body: { login: "be.binh" } });
    const r = await call(env, "POST", "/api/admin/accounts/be.binh/reset-password", { admin: true });
    assert.match(r.data.temp_password, /^Mk-\d{4}-[a-z]{2}$/);
    assert.equal((await call(env, "POST", "/api/login", { body: { login: "be.binh", password: r.data.temp_password } })).status, 200);
    assert.equal((await call(env, "GET", "/api/admin/resets", { admin: true })).data.resets.length, 0);
    assert.equal((await call(env, "POST", "/api/admin/accounts/ghost/reset-password", { admin: true })).status, 404);
    assert.equal((await call(env, "GET", "/api/admin/accounts?q=bình", { admin: true })).data.accounts.length, 1);
    assert.equal((await call(env, "GET", "/api/admin/accounts?q=zzz", { admin: true })).data.accounts.length, 0);
  } finally { sc.restore(); }
});

test("outbox: mails are kept when SCRIPT_URL is missing or the script fails", async () => {
  const env = makeEnv({ SCRIPT_URL: undefined }), sc = fakeScript();
  try {
    await reg(env, { role: "teacher", username: "co.hoa", display_name: "Cô Hoa", email: "hoa@gmail.com" });
    assert.equal(sc.calls.length, 0);
    const box = await call(env, "GET", "/api/admin/outbox", { admin: true });
    assert.equal(box.data.outbox.length, 1);
    assert.equal(box.data.outbox[0].to, "hoa@gmail.com");
    assert.match(box.data.outbox[0].html, /ho-so\?t=/);
    // course approval needs the script
    const env2 = makeEnv(), sc2 = fakeScript();
    const { token } = await verifiedTeacher(env2, sc2);
    await call(env2, "POST", "/api/courses/submit", { token, form: await submitCourseForm() });
    delete env2.SCRIPT_URL;
    const ap = await call(env2, "POST", "/api/admin/courses/c-toan8/approve", { admin: true });
    assert.equal(ap.status, 503);
    assert.equal(ap.data.error, "script_missing");
    // script failing: mail goes to the outbox, publish returns 502 and keeps the course waiting
    env2.SCRIPT_URL = "https://script.test/exec";
    sc2.fail = true;
    const f = await call(env2, "POST", "/api/admin/courses/c-toan8/approve", { admin: true });
    assert.equal(f.status, 502);
    assert.equal((await call(env2, "GET", "/api/courses/mine", { token })).data.courses[0].state, "cho_duyet");
    await call(env2, "POST", "/api/forgot", { body: { login: "co.hoa" } });
    const box2 = await call(env2, "GET", "/api/admin/outbox", { admin: true });
    assert.equal(box2.data.outbox.length, 1);
    assert.match(box2.data.outbox[0].subject, /mã đặt lại mật khẩu/);
  } finally { sc.restore(); }
});

test("an unverified teacher, a student, and no token are refused on course routes", async () => {
  const env = makeEnv(), sc = fakeScript();
  try {
    const t = await reg(env, { role: "teacher", username: "co.hoa", display_name: "Cô Hoa", email: "hoa@gmail.com" });
    const s = await reg(env, { username: "hs" });
    for (const tok of [t.data.token, s.data.token]) {
      assert.equal((await call(env, "GET", "/api/courses/mine", { token: tok })).data.error, "teacher_unverified");
      assert.equal((await call(env, "POST", "/api/courses/submit", { token: tok, form: await submitCourseForm() })).status, 403);
      assert.equal((await call(env, "POST", "/api/courses/c1/remove", { token: tok })).status, 403);
    }
    assert.equal((await call(env, "GET", "/api/courses/mine")).status, 401);
    assert.equal((await call(env, "POST", "/api/ho-so", { form: new FormData() })).status, 404);
  } finally { sc.restore(); }
});

test("pages are served and self-contained", async () => {
  const env = makeEnv();
  const a = await call(env, "GET", "/quan-tri");
  assert.equal(a.status, 200);
  assert.match(a.text, /Quản trị/);
  assert.match(a.text, /x-admin-key/);
  assert.equal((await call(env, "GET", "/api/admin/outbox", { admin: false })).status, 403);
  assert.equal((await call(makeEnv({ ADMIN_KEY: undefined }), "GET", "/api/admin/outbox")).status, 403);
});
