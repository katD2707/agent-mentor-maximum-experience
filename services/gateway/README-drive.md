# Khóa học trên Google Drive

Tạm thời Drive là nơi lưu khóa học (chưa có kho dữ liệu phía server). Mỗi khóa là một file zip (pack.json + assets),
kèm `course.json`, ảnh bìa và một `catalog.json` công khai. App cài trên máy chỉ tải khóa khi học sinh mở lần đầu.

## Chủ sở hữu: đưa khóa học lên Drive (làm một lần)

1. Google Cloud Console: tạo project, bật **Google Drive API**, tạo **OAuth client ID** loại **Desktop app**.
   Màn hình đồng ý OAuth: thêm tài khoản Google của bạn vào danh sách Test users.
2. Tải file JSON của client, lưu thành `.secrets/google-oauth-client.json` ở thư mục gốc repo (thư mục `.secrets/` đã nằm trong .gitignore).
3. Chạy trong `services/gateway`:

```powershell
uv run python -m mentor_gateway.content.drive login      # mở trình duyệt, đăng nhập một lần
uv run python -m mentor_gateway.content.drive push-all   # đưa mọi khóa đã xuất bản lên Drive (chạy lại được, file không đổi thì bỏ qua)
uv run python -m mentor_gateway.content.drive status     # còn khóa nào chưa đồng bộ
```

`push-all` in ra mã file của catalog công khai. Đó là giá trị `MENTOR_REMOTE_CATALOG_URL` cho bản cài đặt.
Quyền dùng là `drive.file` (chỉ thấy các file do chính app tạo). Token lưu ở `.secrets/google-drive-token.json`, không đưa vào git.

Sau đó, mỗi lần giáo viên xuất bản (hoặc đổi nhãn một khóa đã xuất bản), gateway tự đẩy lên Drive ở nền, thử lại nếu lỗi.
Nếu vẫn lỗi, khóa hiện nhãn "chưa đồng bộ" trong danh sách của giáo viên; chạy `push-all` để đồng bộ lại.

## Bản cài đặt trên máy người dùng

| Biến | Ý nghĩa |
| --- | --- |
| `MENTOR_REMOTE_CATALOG_URL` | mã file hoặc link công khai của catalog (bắt buộc để dùng Drive) |
| `MENTOR_CONTENT_DIR` | thư mục nội dung trên máy (catalog và khóa đã tải nằm ở đây) |
| `MENTOR_DRIVE_API_KEY` | tùy chọn: khóa API công khai, tải qua `files.get?alt=media` |
| `MENTOR_REMOTE_SYNC_MINUTES` | chu kỳ kiểm tra catalog (mặc định 30) |

Khi mở app và định kỳ, catalog được tải về (dùng ETag nên rất nhẹ). Khóa chỉ được tải khi mở lần đầu, kiểm tra sha256 rồi mới dùng.
Khóa đã tải dùng được khi không có mạng; khóa chưa tải sẽ báo "Cần mạng để tải khóa này lần đầu".
Không đặt `MENTOR_REMOTE_CATALOG_URL` thì mọi thứ chạy như cũ với `mentor-content` trên máy.
