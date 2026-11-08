---
name: spaced-review
description: Ôn ngắn theo lịch giãn cách - lấy kỹ năng đến hạn trong review-queue.md, ra 3-5 câu ngắn, chấm bằng sympy_check, ghi events.
profiles: [student]
version: 2
---
# spaced-review

`learning/math/review-queue.md` do script `bkt_update` sinh ra: danh sách kỹ năng đến hạn ôn. Không sửa tay file này.

## A. Job buổi tối (routine evening_review, không có người học)
1. `read_file` `learning/math/review-queue.md`. Không có kỹ năng đến hạn hôm nay: dừng, câu trả lời cuối "BỎ QUA: không có kỹ năng đến hạn ôn."
2. Học sinh đã có buổi ôn hôm nay (đã có file `learning/math/review/YYYY-MM-DD.md` hôm nay): dừng.
3. Chọn tối đa 3 kỹ năng đến hạn sớm nhất. Ưu tiên kỹ năng có lỗi lặp lại trong `learning/math/mistakes.md`.
4. Ra 3–5 câu ngắn (mỗi câu ≤ 3 phút), đổi số so với bài cũ. Kiểm đáp án mọi câu trong **một** lần gọi `run_script` name `sympy_check` với `checks` (mỗi câu kind `solve`, `answer` là đáp án dự kiến). `correct` sai: sửa câu, không dùng câu chưa kiểm.
5. `write_file` `learning/math/review/YYYY-MM-DD.md`:
```
# Ôn nhanh 2026-10-28 (10 phút)
1. Giải x**2 - 7*x + 10 = 0  · algebra.quadratic.formula
2. Tìm đỉnh của y = 2*x**2 - 8*x + 1  · functions.quadratic.vertex
3. Giải x**2 - 4 < 0  · algebra.quadratic.inequality
<!-- đáp án (đã kiểm sympy_check, không cho học sinh xem trước): x = 2; x = 5 | (2, -7) | -2 < x < 2 -->
```
6. Báo theo mục Chủ động của AGENTS.md: `notify_user` kind review, title "Ôn nhanh tối nay", text "Có 3 câu ôn nhanh 10 phút cho tối nay. Em sẵn sàng thì nhắn mình nhé.", actions open "Ôn ngay", snooze_1h "Để sau 1 giờ", prefill "Mình ôn nhanh nhé". Mức `off` hoặc giờ yên lặng: không báo, để học sinh tự mở.

## B. Chat: làm bài ôn
1. Đưa từng câu một. Học sinh trả lời xong mới đưa câu tiếp.
2. Chấm bằng `sympy_check` với đáp án của học sinh. Không chấm bằng trí nhớ.
3. Sai: 1 gợi ý chỉ vào lỗi (bậc 3 của scaffolded-help), cho làm lại 1 lần.
4. Mỗi câu ghi `record_event` như skill math-tutoring, `source_ref` = file ôn hôm nay. Không gợi ý: `independent`; có gợi ý: `guided`.
Kiểm tra nhanh (câu chọn đáp án): `show_card` kind flashcard, `skill` là id trong review-queue, 3–4 lựa chọn, đáp án đúng đã kiểm bằng `sympy_check`; reveal = chữ cái đúng + lý do ngắn. Câu trả lời đến dạng `[card:flashcard answer B]`: chấm và ghi `record_event` như bước 2–4 (`source_ref` là file chat hệ thống đưa).
5. Xong: `run_script` name `bkt_update`, input `{"subject": "math"}`. Nói ngắn kết quả: "3 câu, em tự làm đúng 2. Dạng bất phương trình mình hẹn ôn lại sau vài ngày."

## C. Luyện tập trong app (mọi môn)
Môn Toán, Vật lí, Tiếng Anh có mục Luyện tập: học sinh luyện theo bộ câu hỏi của hệ thống, điểm mạnh yếu tự cập nhật vào `skills.md` và `review-queue.md`. Kết quả mỗi buổi là một dòng trong `learning/<môn>/practice-log.md`. Đừng `record_event` lại các câu đó.
- Có kỹ năng đến hạn ôn (review-queue) mà học sinh chưa luyện gần đây (xem ngày dòng cuối `practice-log.md`): gợi ý một bộ luyện bằng `show_card` kind practice, `subject`, `minutes` 10 hoặc 20, `goal` weak, `title` ngắn, `reason` nêu kỹ năng đến hạn. Một thẻ mỗi lượt. Không mở, không chấm hộ: học sinh bấm mới bắt đầu.
- Môn không phải Toán: `learning/<môn>/review-queue.md` có thể chưa có; khi đó dùng `skills.md` (kỹ năng mastery thấp hoặc ít bằng chứng) để chọn chủ đề.

## Lưu ý
- Ngắn là chính: tối đa 10–15 phút. Học sinh mệt: làm 1–2 câu cũng được.
- Không biến buổi ôn thành bài giảng dài. Hổng kiến thức lớn: hẹn buổi riêng (skill math-tutoring).
