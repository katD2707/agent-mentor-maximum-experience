# Mentor cho F-Eco: gói desktop tự chứa

Gói này cài một lần là dùng: `Mentor.exe` tự bật gateway đi kèm (thư mục `gateway\`) trên cổng localhost trống, không cần chạy máy chủ nào bằng tay. Gói cũ của F-Eco (chỉ có `Mentor.exe` gọi `localhost:8100`) không cần nữa.

## Trong gói

```
mentor-<phiên bản>-windows-x64.zip
  Mentor.exe                    ứng dụng (Tauri), không có bộ cập nhật riêng: F-Launcher cập nhật
  gateway\mentor-gateway.exe    gateway đóng băng bằng PyInstaller, kèm thư viện và nội dung mẫu
  THIRD_PARTY_NOTICES.md
```

Khi chạy:
- `Mentor.exe` chọn một cổng localhost trống, bật `gateway\mentor-gateway.exe` và đợi `/healthz`. Cửa sổ hiện "Đang mở Mentor…" trong lúc đó (vài giây). Thoát Mentor thì gateway tắt theo; nếu Mentor bị tắt đột ngột, gateway tự thoát sau vài giây.
- Dữ liệu (tài khoản, tiến độ, bằng chứng luyện tập, nhật ký `logs\gateway.log`, thư mục `content\`) nằm trong `FECO_APP_DATA_DIR` do F-Launcher đặt, giữ nguyên khi cập nhật. Chạy ngoài F-Launcher thì dùng `%APPDATA%\vn.mentor.app`.
- Máy học sinh không cần `git`.
- Lần đầu mở, màn đăng nhập có nút "Tạo tài khoản" (tên, mật khẩu, học sinh hoặc giáo viên). Gói không có tài khoản mẫu.
- Khóa học lấy từ danh mục công khai trên Google Drive của chủ dự án (mặc định sẵn trong gói, `MENTOR_REMOTE_CATALOG_URL`): mở khóa nào thì tải khóa đó (cần mạng lần đầu), kiểm tra mã băm rồi giữ lại để học khi mất mạng. Đặt `MENTOR_REMOTE_CATALOG_URL` rỗng thì dùng 4 khóa mẫu đi kèm.
- Tính năng AI cần khóa do người dùng nhập trong ứng dụng. Chưa có khóa thì mọi phần còn lại vẫn chạy.

## Dựng gói

Cần `uv`, `pnpm`, Rust trên Windows. Từ gốc repo Mentor:

```powershell
powershell -ExecutionPolicy Bypass -File integrations\feco\build.ps1
```

Kết quả: `dist\mentor-<phiên bản>-windows-x64.zip` (khoảng 85 MB, dưới giới hạn 2 GB). Script chỉ ghi vào `dist\` (không cài gì lên máy). Thêm `-Clean` để xóa môi trường dựng tạm `dist\standalone` sau khi xong. Phiên bản lấy từ `apps/app/src-tauri/tauri.conf.json` và được ghi vào `f-app.toml`.

## Việc chủ dự án phải làm trước khi nộp

1. Điền `license` trong `f-app.toml` (repo Mentor chưa có tệp LICENSE) và `privacy_policy` bằng một địa chỉ https thật (hiện là chỗ giữ chỗ, ghi `TODO`).
2. **Ký số.** F-Eco bắt buộc chữ ký Authenticode, gói không ký sẽ bị từ chối (`invalid_package`). `Mentor.exe` và `gateway\mentor-gateway.exe` do script dựng **chưa được ký**. Dựng xong, ký cả hai tệp (và các `.dll` trong `_internal` nếu chính sách yêu cầu) ngay trong thư mục `dist\standalone\windows-x64`, rồi nén lại giữ nguyên thư mục đó: `powershell -ExecutionPolicy Bypass -File integrations\feco\build.ps1 -SkipGateway -SkipApp -PackStage`. Không dùng `Compress-Archive` của Windows PowerShell 5.1 vì nó ghi đường dẫn có dấu `\` trong zip.
3. `f-dev validate --manifest integrations\feco\f-app.toml`.

## Chạy thử trên F-Eco dev (không cần ký, không qua duyệt)

Trong repo F-Eco (Git Bash), khi hạ tầng và `feco-server` đang chạy với kho TUF dev (`scripts/dev-launcher.sh setup` đã chạy):

```bash
MENTOR_DESKTOP_ZIP=/d/duong-dan/mentor-0.2.2-windows-x64.zip MENTOR_VERSION=0.2.3 scripts/dev-apps.sh mentor
```

`MENTOR_VERSION` phải lớn hơn bản Mentor đã có trong kho dev (nếu chưa có thì bỏ). Sau đó mở F-Launcher dev, bấm **Đồng bộ**, cài và mở Mentor. Chỉ dùng mục desktop; mục web của lệnh này cần gateway đã vá đăng nhập F-Eco, gói này chưa có.

## Nhập vào F-Eco (quản trị viên)

1. Lấy `mentor-<phiên bản>-windows-x64.zip` đã ký cùng `f-app.toml`.
2. Nộp: `f-dev publish --manifest f-app.toml --package mentor-<phiên bản>-windows-x64.zip` (cần `FDEV_TOKEN` và `FDEV_SERVER`). Gói là một tệp zip cho một hệ điều hành, tệp chạy là `Mentor.exe` ở gốc zip.
3. Duyệt trong cổng nhà phát triển (lần đầu có duyệt tay), chọn kênh `stable` hoặc `beta` và tỉ lệ phát hành.
4. Mentor chưa khai báo `[scopes]`, nên F-Launcher mở app không cần mã đăng nhập F-Eco. Đăng nhập bằng F-Eco (OIDC) chưa có trong gói này.

Chỉ có bản Windows x64. Chưa có bản macOS.
