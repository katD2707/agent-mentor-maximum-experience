# Mentor hub

Máy chủ trung tâm nhỏ của Mentor, chạy trên Cloudflare Worker + KV tại `https://hub.mentor-hoc.workers.dev`.

- Tài khoản và đăng nhập (học sinh, giáo viên), quên mật khẩu bằng mã qua email.
- Giáo viên: kê khai hồ sơ (`/ho-so`), chủ duyệt, mã xác nhận, gửi khóa học chờ duyệt.
- Trang quản trị cho chủ: `/quan-tri`.
- Một Google Apps Script (chạy bằng tài khoản của chủ) gửi email qua Gmail và ghi gói khóa học + `catalog.json` lên Drive.

Hợp đồng API: `CONTRACTS-HUB.md` mục 1 và 2.

## Triển khai

Cần `CLOUDFLARE_WORKERS_TOKEN` và `CLOUDFLARE_ACCOUNT_ID` trong biến môi trường.

```powershell
powershell -ExecutionPolicy Bypass -File infra\hub\deploy.ps1
```

Script tạo KV `mentor-hub` nếu chưa có (ghi id vào `wrangler.toml`), deploy worker, đặt secret `ADMIN_KEY` và `SCRIPT_SECRET`, rồi viết `.secrets\apps-script.gs`. Chạy lại bao nhiêu lần cũng được.

## Cài Apps Script (chủ làm một lần)

1. Vào https://script.google.com, chọn **New project**.
2. Xóa code mẫu, dán toàn bộ nội dung `.secrets\apps-script.gs` (không dùng `infra\hub\apps-script.gs`, bản đó chưa có secret).
3. **Deploy** → **New deployment** → loại **Web app**. Execute as: **Me**. Who has access: **Anyone**.
4. Bấm **Authorize access** và cho phép Gmail và Drive.
5. Chép URL của web app (dạng `https://script.google.com/macros/s/.../exec`).
6. Chạy lại: `powershell -ExecutionPolicy Bypass -File infra\hub\deploy.ps1 -ScriptUrl <url>`

Sửa `apps-script.gs` sau này: dán lại, rồi **Deploy** → **Manage deployments** → sửa → **New version**.

Chưa có `SCRIPT_URL` thì email vào mục "Thư chưa gửi" của trang quản trị (chủ chép mã gửi tay), và duyệt khóa học trả lỗi `script_missing`.

## Khóa quản trị

`mentor\.secrets\hub-admin-key.txt` (thư mục `.secrets` đã bị gitignore). Mở `/quan-tri`, dán khóa một lần, trình duyệt nhớ.

## Thử

```powershell
node --test "infra/hub/test/*.test.mjs"
```
