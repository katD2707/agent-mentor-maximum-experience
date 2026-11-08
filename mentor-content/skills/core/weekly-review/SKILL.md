---
name: weekly-review
description: Tổng kết cuối tuần - tóm tắt bằng chứng trong tuần, mời người học tự đánh giá, đề xuất mục tiêu và kế hoạch tuần sau.
profiles: [student]
version: 1
---
# weekly-review

Hai phần: **A** chạy trong job (không có người học), **B** trong chat khi người học trả lời.

## A. Job: chuẩn bị tổng kết
1. Đọc 7 ngày gần nhất: `list_dir` `me/journal` rồi `read_file` các journal trong tuần; `goals/plans/this-week.md`; `goals/goals.md`.
   - `grep` các ngày trong tuần ở `events.jsonl`; `read_file` `learning/math/skills.md` và `learning/math/mistakes.md`.
2. Thêm vào cuối `goals/plans/this-week.md` mục:
```
## Tổng kết tuần (đến 2026-11-01)
- Xong: 4 trên 6 việc. Chưa xong: ôn dấu tam thức, đề thử.
- Bằng chứng: tự làm đúng 5 bài tìm đỉnh parabol không gợi ý. (events 29/10–31/10)
- Lỗi lặp lại: nhầm dấu khi chuyển vế. (mistakes.md)
- Đề xuất tuần sau: 1) ôn dấu tam thức; 2) làm 1 đề thử 45 phút.
```
   Chỉ ghi điều có nguồn. Không có dữ liệu thì ghi "Tuần này chưa có dữ liệu" và không bịa.
   Rồi `show_card` kind weekly: milestones_done = số việc/mốc xong, mistakes_fixed = số lỗi đã sửa, highlight = 1 câu có nguồn (phút tập trung và chuỗi ngày hệ thống tự tính). Tuần người học có vẻ buồn hay căng thẳng: không gửi thẻ.
3. Báo người học theo mục Chủ động của AGENTS.md, 1 tin: "Tuần này em đã xong 4 việc. Dành 5 phút cùng mình tổng kết và chọn mục tiêu tuần sau nhé?"

## B. Chat: tự đánh giá và chốt tuần sau
Khi người học mở chat sau tin nhắn tổng kết (hoặc tự hỏi "tổng kết tuần"):
1. Cho xem tóm tắt ngắn (3–4 dòng) từ mục Tổng kết tuần.
2. Hỏi lần lượt, mỗi lượt 1 câu:
   - "Tuần này em thấy làm tốt nhất điều gì?"
   - "Điều gì khó hoặc làm em chậm lại?"
   - "Tuần sau em muốn tập trung vào gì?"
3. Đề xuất 1–3 mục tiêu tuần sau, dựa trên câu trả lời và đề xuất ở mục A. Người học chọn.
4. Lập kế hoạch tuần mới theo skill goal-planning, kiểm tra khả thi. `write_file` `goals/plans/this-week.md` bản mới (git giữ bản cũ). Chép mục Tổng kết tuần cũ vào journal hôm nay trước khi ghi đè.
5. Ghi điều rút ra về cách học vào `me/what-works.md` (skill memory-keeper), nguồn `(chat dd/mm)`.

Người học không trả lời đến hết thứ Hai: tự chuyển việc chưa xong sang tuần mới, giữ đề xuất ở mục `## Đề xuất của mentor`, không hỏi lại nhiều lần.

## Lưu ý
- Không chấm điểm người học. Nói về việc và cách làm, không nói về con người.
- Tuần không tốt: ghi nhận, hỏi cái gì cản trở, giảm tải tuần sau.
