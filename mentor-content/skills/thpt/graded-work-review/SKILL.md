---
name: graded-work-review
description: Phân tích ảnh bài kiểm tra Toán đã được giáo viên chấm - ghi bằng chứng, ghi event classroom_graded, cập nhật mastery, tìm lỗi lặp lại.
profiles: [thpt]
version: 1
---
# graded-work-review

Đầu vào: một ảnh bài kiểm tra đã chấm, thường ở `inbox/`. Kết quả do **giáo viên** chấm là nguồn sự thật; không tự chấm lại.

## Bước 1. Đọc ảnh
`look_at_image` với `path` là ảnh, `question`:
"Chép lại bài kiểm tra này. Với từng câu: số câu, đề bài, bài làm của học sinh, giáo viên chấm đúng hay sai (dấu tích, gạch, điểm từng câu), lời phê nếu có. Cuối cùng: tên bài kiểm tra, ngày, tổng điểm. Chỗ nào không đọc được thì ghi KHÔNG ĐỌC ĐƯỢC."
- Ảnh mờ, thiếu trang, nhiều chỗ không đọc được: dừng, nhờ học sinh chụp lại. Không đoán.
- Không phải môn Toán: chỉ lưu evidence (bước 2), không ghi event.

## Bước 2. Ghi evidence
`write_file` `learning/evidence/YYYY-MM-DD-<slug>.md`, ví dụ `learning/evidence/2026-10-25-kiem-tra-15p.md`:
```
# Kiểm tra 15 phút Toán — 2026-10-25
- Ảnh gốc: inbox/IMG_0412.jpg
- Kết quả chung: (chép đúng như trên bài)

## Câu 1
- Đề: Tìm đỉnh của parabol y = x^2 - 4x + 3
- Kỹ năng: functions.quadratic.vertex
- Giáo viên chấm: đúng
## Câu 2
- Đề: ...
- Kỹ năng: algebra.quadratic.inequality
- Giáo viên chấm: sai
- Lỗi: [cẩu thả] chép nhầm dấu ở dòng 2
- Lời phê: (chép nếu có)
```
Kỹ năng: `grep` từ khóa trong `.mentor/curricula/math.yaml`. Không tìm được id phù hợp: ghi "chưa gắn kỹ năng" và không ghi event cho câu đó.
File này riêng tư của học sinh, **không bao giờ** đưa vào báo cáo phụ huynh.

## Bước 3. Ghi event cho từng câu đọc được
`run_script` name `record_event`, mỗi câu một lần:
```
{"type": "graded_work_ingested", "subject": "math", "skill_ids": ["functions.quadratic.vertex"],
 "correct": true, "mode": "classroom_graded", "hint_count": 0,
 "source_ref": "learning/evidence/2026-10-25-kiem-tra-15p.md", "grader": "teacher"}
```
`correct` theo đúng chấm của giáo viên. Câu được nửa điểm: `correct` = false.

## Bước 4. Cập nhật mastery
`run_script` name `bkt_update`, input `{"subject": "math"}`.

## Bước 5. Phân loại lỗi
Với mỗi câu sai, phân loại:
- `[kiến thức]`: hiểu sai hoặc chưa biết cách làm.
- `[cẩu thả]`: biết cách nhưng sai dấu, chép sai, tính nhầm.
- **Lặp lại**: lỗi cùng loại, cùng kỹ năng đã có trong `learning/math/mistakes.md`.
Cập nhật `learning/math/mistakes.md` (cách ghi như skill math-tutoring), nguồn `(ảnh bài kiểm tra dd/mm)`.

## Bước 6. Nói với học sinh
Theo thứ tự, ngắn gọn:
1. Điều làm tốt: "Câu 1 em tìm đỉnh rất gọn."
2. Một đến hai lỗi quan trọng nhất, ưu tiên lỗi lặp lại. Không liệt kê hết.
3. Đề nghị luyện 2–3 bài cùng dạng (skill math-tutoring), không ép.
Không bình luận về điểm số theo kiểu đánh giá con người ("điểm thế này là kém"). Nếu học sinh buồn vì điểm: đọc skill wellbeing-and-crisis mục 1.

## Bước 7. Ghi nhận
Thêm dòng vào `inbox/processed.md` như skill intake-document. Giữ ảnh gốc ở `inbox/`.
