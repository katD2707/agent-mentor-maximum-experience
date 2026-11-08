---
name: exam-prep
description: Khi có lịch thi hoặc kiểm tra - lập kế hoạch ôn ngược từ ngày thi theo kỹ năng yếu, hẹn nhắc trước kỳ thi.
profiles: [student]
version: 2
---
# exam-prep

Dùng khi `me/now.md` có kỳ thi mới, hoặc học sinh nói sắp thi.

## Bước 1. Thu thập
Hỏi những gì chưa có trong file (mỗi lượt 1 câu):
- Môn, ngày giờ thi, hình thức (tự luận, trắc nghiệm, thời gian làm bài).
- Phạm vi thi (chương, bài). Có đề cương thì nhờ học sinh gửi ảnh vào `inbox/`.
- Mỗi ngày có bao nhiêu phút ôn được.
Ghi kỳ thi vào `me/now.md` theo skill memory-keeper.

## Bước 2. Chọn trọng tâm (Toán)
1. Đổi phạm vi thi thành danh sách id kỹ năng trong `.mentor/curricula/math.yaml`.
2. `read_file` `learning/math/skills.md`. Xếp ưu tiên:
   - Mastery thấp hoặc chưa có bằng chứng: ưu tiên cao.
   - Có lỗi lặp lại trong `learning/math/mistakes.md`: ưu tiên cao.
   - Mastery cao: chỉ ôn nhanh 1 lần.
3. Kỹ năng yếu có kỹ năng tiền đề (`prerequisites`) cũng yếu: ôn tiền đề trước.
Vật lí, Tiếng Anh: làm tương tự với `.mentor/curricula/<môn>.yaml` và `learning/<môn>/skills.md`. Môn chưa có curriculum: chia theo chương học sinh liệt kê, hỏi học sinh tự đánh giá chương nào cần củng cố.

## Bước 3. Lập kế hoạch ngược
`write_file` `goals/plans/exam-<môn>-YYYY-MM-DD.md` (ngày thi), ví dụ:
```
# Ôn thi giữa kỳ Toán — thi 2026-11-06
## Trọng tâm
- algebra.quadratic.trinomial_sign (chưa vững) · functions.quadratic.vertex (lỗi lặp lại)
## Lịch
- [ ] T6 30/10 — 30 phút: dấu tam thức, 5 bài
- [ ] T7 31/10 — 30 phút: đỉnh parabol, 5 bài
- [ ] CN 01/11 — 45 phút: trộn 2 dạng trên
- [ ] T3 03/11 — 45 phút: đề thử, tự làm, tính giờ
- [ ] T4 04/11 — 30 phút: chữa lỗi trong đề thử
- [ ] T5 05/11 — 15 phút: xem lại mistakes.md, ngủ sớm
```
Quy tắc:
- Đi ngược từ ngày thi. Ngày cuối chỉ ôn nhẹ.
- Đề thử 2–3 ngày trước thi, học sinh tự làm không gợi ý.
- Xen kẽ các dạng, không dồn một dạng một ngày dài.
- Kiểm tra khả thi theo skill goal-planning. Quá tải: cắt bớt kỹ năng mastery cao.
Chép các việc của tuần này vào `goals/plans/this-week.md`. Thêm mốc thi vào `goals/goals.md`.

## Luyện và thi thử trong app
Toán, Vật lí, Tiếng Anh có mục Luyện tập và Thi thử tính giờ. Lập kế hoạch xong, đề xuất bằng `show_card`: kind practice (`goal` weak, theo chủ đề trọng tâm) cho các buổi luyện, và kind mock (`profile_id` từ trang Luyện tập, ví dụ math.mcq-mock.2026) cho buổi đề thử 2–3 ngày trước thi. Mỗi lượt tối đa 1 thẻ. Học sinh bấm mới bắt đầu. Thi thử là đề luyện của dự án, không phải đề thật và không dự báo điểm; mock đang làm dở bạn không thấy đáp án. Sau khi học sinh làm xong, đọc `practice-log.md` và `skills.md` để chỉnh kế hoạch.

## Bước 4. Hẹn nhắc
- `schedule_wake` 2 ngày trước thi, 18:00, `job_kind` = `routine`, prompt "Dùng skill exam-prep: nhắc đề thử, kiểm tra tiến độ ôn thi <môn>."
- Giờ hẹn ngoài `quiet_hours`.

## Bước 5. Trong lúc ôn
- Bài luyện theo skill math-tutoring (kiểm bằng `sympy_check`, ghi `record_event`).
- Đề thử tự soạn (ngoài app): học sinh làm xong mới chữa; mỗi câu ghi event `independent`. Thi thử trong app tự ghi bằng chứng, đừng ghi lại.
- Bị chậm: sửa kế hoạch (dời, cắt), không lập lại.

## Sau kỳ thi
Hỏi học sinh thấy thế nào. Có bài chấm thì gợi ý chụp gửi (skill graded-work-review). Xóa kỳ thi khỏi `me/now.md`.
