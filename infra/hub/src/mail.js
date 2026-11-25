// Mail through the Apps Script web app; anything that cannot be sent lands in the outbox for the owner to relay.
import { esc, putJ, randHex } from "./util.js";

// Call the Apps Script web app. Throws on any failure. Returns the parsed reply (ok: true).
export async function callScript(env, payload) {
  if (!env.SCRIPT_URL) throw new Error("script_missing");
  const res = await fetch(String(env.SCRIPT_URL).trim(), {
    method: "POST",
    redirect: "follow",
    headers: { "content-type": "text/plain;charset=utf-8" },
    body: JSON.stringify({ secret: String(env.SCRIPT_SECRET || "").trim(), ...payload }),
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* not json */ }
  if (!res.ok || !data || data.ok !== true) throw new Error((data && data.error) || "script_failed");
  return data;
}

export async function sendMail(env, to, subject, htmlBody) {
  if (!to) return false;
  try {
    await callScript(env, { action: "mail", to, subject, html: htmlBody });
    return true;
  } catch (e) {
    const at = new Date().toISOString();
    await putJ(env, `outbox:${Date.now()}:${randHex(3)}`, { to, subject, html: htmlBody, at, error: String(e.message || e) });
    return false;
  }
}

const wrap = (inner) => `<div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.55;color:#3a2010;max-width:520px;margin:0 auto;padding:20px;background:#fff7e6;border-radius:12px">
<p style="font-weight:bold;color:#7d4c22;font-size:18px;margin:0 0 12px">Mentor</p>${inner}
<p style="color:#6b4a2e;font-size:14px;margin-top:20px">Cần giúp gì, bạn cứ trả lời email này.</p></div>`;
const btn = (href, label) => `<p><a href="${esc(href)}" style="display:inline-block;background:#1b7340;color:#fff;text-decoration:none;font-weight:bold;padding:12px 22px;border-radius:10px">${esc(label)}</a></p>`;
const codeBox = (c) => `<p style="font-size:30px;font-weight:bold;letter-spacing:6px;background:#fffdf7;border:2px dashed #d6b27a;border-radius:10px;padding:12px;text-align:center;margin:14px 0">${esc(c)}</p>`;
const why = (r) => `<p style="background:#fde4dc;border-radius:10px;padding:10px 12px"><b>Lý do:</b> ${esc(r)}</p>`;

export const mails = {
  form(name, link) {
    return ["Mentor: kê khai hồ sơ giáo viên", wrap(`<p>Chào ${esc(name)},</p><p>Cảm ơn bạn đã đăng ký dạy trên Mentor. Bước tiếp theo là kê khai hồ sơ, mất khoảng 3 phút.</p>${btn(link, "Kê khai hồ sơ")}<p style="color:#6b4a2e;font-size:14px">Liên kết dùng được trong 30 ngày.</p>`)];
  },
  approved(name, code) {
    return ["Mentor: hồ sơ của bạn đã được duyệt", wrap(`<p>Chào ${esc(name)},</p><p>Hồ sơ của bạn đã được duyệt. Đây là mã xác nhận, bạn nhập vào app Mentor để bắt đầu đăng khóa học:</p>${codeBox(code)}<p style="color:#6b4a2e;font-size:14px">Mã dùng được trong 24 giờ.</p>`)];
  },
  code(name, code) {
    return ["Mentor: mã xác nhận của bạn", wrap(`<p>Chào ${esc(name)},</p><p>Mã xác nhận của bạn:</p>${codeBox(code)}<p style="color:#6b4a2e;font-size:14px">Mã dùng được trong 24 giờ.</p>`)];
  },
  reset(name, code) {
    return ["Mentor: mã đặt lại mật khẩu", wrap(`<p>Chào ${esc(name)},</p><p>Bạn vừa xin đặt lại mật khẩu. Mã của bạn:</p>${codeBox(code)}<p style="color:#6b4a2e;font-size:14px">Mã dùng được trong 24 giờ. Nếu không phải bạn xin, cứ bỏ qua email này.</p>`)];
  },
  teacherRejected(name, reason, link) {
    return ["Mentor: hồ sơ cần chỉnh lại", wrap(`<p>Chào ${esc(name)},</p><p>Hồ sơ giáo viên của bạn chưa được duyệt lần này.</p>${why(reason)}<p>Bạn chỉnh lại rồi nộp lại nhé:</p>${btn(link, "Nộp lại hồ sơ")}`)];
  },
  courseApproved(name, title) {
    return [`Mentor: khóa “${title}” đã được đăng`, wrap(`<p>Chào ${esc(name)},</p><p>Khóa “${esc(title)}” đã được duyệt và hiện cho học sinh. Cảm ơn bạn!</p>`)];
  },
  courseRejected(name, title, reason) {
    return [`Mentor: khóa “${title}” cần chỉnh lại`, wrap(`<p>Chào ${esc(name)},</p><p>Khóa “${esc(title)}” chưa được duyệt lần này.</p>${why(reason)}<p>Bạn sửa trong app rồi gửi duyệt lại nhé.</p>`)];
  },
  courseRemoved(name, title, reason) {
    return [`Mentor: khóa “${title}” đã được gỡ`, wrap(`<p>Chào ${esc(name)},</p><p>Khóa “${esc(title)}” đã được gỡ khỏi Mentor. Học sinh đã tải về vẫn học tiếp được.</p>${why(reason)}`)];
  },
};
