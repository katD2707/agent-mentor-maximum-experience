---
name: advisor-meeting-prep
description: Trước buổi họp GVHD - gom tiến độ, kết quả mới, câu hỏi mở thành agenda; sau buổi họp - ghi quyết định và việc cần làm có hạn.
profiles: [ncs]
version: 1
---
# advisor-meeting-prep

File họp: `research/meetings/YYYY-MM-DD-gvhd.md` (ngày họp).

## A. Trước buổi họp (1–2 ngày trước)
1. Gom từ lần họp trước đến nay:
   - `list_dir` `research/meetings`, `read_file` file họp gần nhất: việc đã hứa làm.
   - `research/experiments/log.md`: thí nghiệm mới, kể cả thất bại.
   - `research/thesis.md`: mốc tiến độ.
   - `goals/plans/this-week.md`, `research/reading-queue.md` (paper đã đọc).
2. Viết bản nháp agenda:
```
# Họp GVHD — 2026-11-04
## Việc đã hứa lần trước
- [x] Chạy lại baseline trên bộ dữ liệu B (log 30/10)
- [ ] Viết xong mục 3.2 — mới được nửa
## Kết quả mới
- (người học điền: 1–2 kết quả, kèm hình hoặc bảng)
## Câu hỏi mở
- (người học điền)
## Cần GVHD quyết định
-
## Ghi chú trong buổi họp
## Việc cần làm sau họp
```
   Bạn điền phần sự kiện có nguồn (việc đã hứa, log). Phần **Kết quả mới** và **Câu hỏi mở** để người học tự viết.
3. Nhắn người học (hoặc trong chat): "Mình đã chuẩn bị khung agenda họp thứ Tư. Bạn điền kết quả mới và câu hỏi mở nhé."
4. Người học viết xong câu hỏi: giúp làm rõ (cụ thể chưa, GVHD có đủ bối cảnh để trả lời không, câu nào cần GVHD quyết). Không đặt câu hỏi thay.

## B. Sau buổi họp
1. Hỏi người học: "Buổi họp chốt những gì?" Nhận ghi chú dạng gõ, ảnh (`look_at_image`) hoặc file trong `inbox/`.
2. Ghi vào mục Ghi chú trong buổi họp, đúng ý người học, nguồn `(chat dd/mm)`.
3. Tách **Việc cần làm sau họp**, mỗi việc có hạn:
   `- [ ] Thêm thí nghiệm ablation cho mô-đun X — hạn 2026-11-11`
   Việc chưa có hạn: hỏi người học.
4. Đưa việc vào `goals/plans/this-week.md`; hạn vào danh sách deadline (skill deadline-watch). Mốc luận văn thay đổi: cập nhật `research/thesis.md`.
5. Lịch họp tiếp theo: ghi vào `me/now.md`; nếu đã kết nối Google Calendar và người học muốn, `calendar_create_event` cho buổi họp (công cụ tự hỏi duyệt); `schedule_wake` trước buổi họp 2 ngày lúc 09:00, `job_kind` = `routine`, prompt "Dùng skill advisor-meeting-prep: chuẩn bị agenda họp GVHD ngày <ngày>."

## Lưu ý
- Thông tin về GVHD chỉ ghi tối thiểu (tên gọi, vai trò) vào `me/people.md`.
- Không ghi nhận xét cá nhân về GVHD.
