# Tài khoản demo (chỉ môi trường dev)

Hai tài khoản có sẵn dữ liệu "đã dùng vài tuần" để thử mọi tính năng mà không phải dùng thật nhiều tuần.
Mọi người, trường, sự kiện và email trong dữ liệu đều là **giả lập** (email `@example.com`, workshop
"VietNLP 2027" không có thật). Không dùng dữ liệu thật của ai.

| Email | Người học | Profile |
|---|---|---|
| `demo.thpt@example.com` | Nguyễn Minh Anh, lớp 11 | THPT, phụ huynh đã xác nhận (dev) |
| `demo.ncs@example.com` | Trần Thu Lan, NCS năm 2 ngành NLP | NCS |

## Tạo hoặc tạo lại

Cần stack dev đang chạy (`infra/dev-up.ps1`: gateway `MENTOR_ENV=dev` ở cổng 8000, web ở cổng 3000).

```powershell
uv run python infra/seed-demo.py            # tạo hai tài khoản (bỏ qua tài khoản đã có)
uv run python infra/seed-demo.py --reset    # xoá hai tài khoản rồi tạo lại từ đầu
uv run python infra/seed-demo.py --no-chat  # không chạy 3 lượt chat thật (tiết kiệm quota)
uv run python infra/seed-demo.py --only ncs # chỉ một tài khoản
uv run python infra/seed-demo.py --delete   # chỉ xoá
```

Script chỉ chạy khi gateway ở chế độ dev (`request-link` trả `dev_link`), và chỉ đi qua API của gateway
(đăng nhập dev, onboarding, xác nhận phụ huynh dev, ghi file như trang web, tải tệp lên, email đến qua
`/internal/email/inbound`). Không ghi thẳng vào `var-dev`.

Mặc định script chạy 3 lượt chat với mô hình thật (2 THPT, 1 NCS) để lịch sử chat không trống. Hai email
gửi vào tài khoản NCS còn kích hoạt 2 job `intake` chạy nền, cũng dùng mô hình thật.

## Đăng nhập

1. Lấy link đăng nhập mới:
   ```powershell
   uv run python infra/seed-demo.py --login demo.thpt@example.com
   uv run python infra/seed-demo.py --login demo.ncs@example.com
   ```
   Lệnh in ra `dev_link` và `dev_code` (mã 6 số). Cũng có thể gõ email ở trang đăng nhập rồi gọi
   `POST http://127.0.0.1:8000/api/auth/request-link` với `{"email": "..."}` để lấy link.
2. Mở `dev_link` trong trình duyệt. Giữ nguyên `localhost` (không đổi sang `127.0.0.1`) để cookie khớp với
   web `http://localhost:3000`. Hoặc nhập mã 6 số ở trang đăng nhập.
3. Mỗi email chỉ lấy được 5 link mỗi giờ (mỗi lần chạy script tốn 1, `--reset` tốn 2).

## Có gì trong tài khoản

**THPT (Minh Anh):** hồ sơ, việc hiện tại, sở thích, người liên quan, điều gì hiệu quả (có dòng
`[suy luận]`), mỗi dòng có nguồn và ngày trong 3-4 tuần qua; 6 nhật ký; mục tiêu "Toán cuối học kỳ I"
có hạn và mốc, kế hoạch tuần và học kỳ; `learning/math/` (mastery, lịch ôn, lỗi hay gặp, một bài kiểm tra
cũ trong `learning/evidence/`); ảnh bài kiểm tra 15 phút đã chấm trong `inbox/`.

**NCS (Thu Lan):** hồ sơ và việc hiện tại; `research/thesis.md` (đề tài, 3 câu hỏi nghiên cứu, từ khoá,
trạng thái chương, mốc); hàng đợi đọc với paper arXiv có thật (đã kiểm tra mã); 2 ghi chú paper; nhật ký
thí nghiệm; biên bản họp GVHD lần trước; mục tiêu có deadline workshop (giờ AoE đã đổi sang giờ VN) và
lịch họp GVHD; 5 nhật ký; 2 email gửi vào `inbox/email/` (GVHD hẹn họp, CFP workshop); 1 tệp PDF dạng chữ
trong `inbox/`. Khoảng 1 phút sau, job `intake` đọc từng email, cập nhật `goals/goals.md`, `me/now.md`,
`me/people.md`, gửi một thông báo, rồi xoá file email và ghi lại vào `inbox/processed.md` (đúng skill
intake-document). Vì vậy trong Workspace có thể không còn thấy file email gốc.

## Thử gì

**THPT**
- Gửi kèm ảnh bài kiểm tra (đã có trong Workspace → `inbox/`; tải về rồi đính kèm lại) và hỏi
  "Mentor xem giúp em bài kiểm tra này".
- "Mentor nhớ gì về em?", hoặc mở "Mentor biết gì về tôi".
- Báo cáo phụ huynh: mục "Báo cáo phụ huynh" (nếu lượt chat của script đã gửi được), hoặc nhờ mentor soạn
  và gửi báo cáo 2 tuần.
- "Quên chuyện tập văn nghệ đi."
- Cài đặt → Mức độ chủ động, giờ yên lặng.

**NCS**
- "Tìm giúp mình paper mới về Vietnamese legal question answering."
- Đọc trang: "Đọc giúp mình https://arxiv.org/abs/2307.03172"; PDF: "Tóm tắt giúp mình tệp PDF
  lab-technote trong inbox".
- "Hạn nộp full paper VietNLP 2027 là mấy giờ theo giờ Việt Nam?" (AoE).
- "Thầy Hùng vừa gửi email gì?", "Chuẩn bị agenda họp với thầy Hùng."
- Google Calendar: Cài đặt → Google Calendar (chỉ khi máy chủ dev có `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET`).

## Giới hạn

- `events.jsonl` không ghi được qua API, nên bảng mastery và lịch ôn được tính sẵn bằng đúng code
  `bkt_update` từ các event giả lập. Lần đầu mentor chạy `bkt_update` (ví dụ sau khi xem ảnh bài kiểm tra),
  hai file này được tính lại chỉ từ event thật, nên mastery cũ sẽ mất.
- Lịch sử chỉnh sửa của các file mẫu ghi tác giả "user" và thời điểm chạy script, không phải ngày trong
  nội dung.
- Lịch sử chat chỉ có các lượt chat thật mà script chạy (hôm nay).
