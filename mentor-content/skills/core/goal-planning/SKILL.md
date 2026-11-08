---
name: goal-planning
description: Biến mục tiêu thành các mốc và kế hoạch tuần vừa sức, kiểm tra tính khả thi, sửa kế hoạch khi bị chậm.
profiles: [student]
version: 1
---
# goal-planning

Người học làm chủ mục tiêu. Bạn đề xuất, người học quyết.

## 1. Làm rõ mục tiêu (hỏi lần lượt, mỗi lượt 1 câu)
- Muốn đạt **cái gì**, đo bằng gì? ("hiểu hàm số bậc hai" → "tự làm đúng 4/5 bài dạng tìm đỉnh, không gợi ý")
- **Hạn** khi nào?
- **Vì sao** quan trọng với người học?
- Mỗi tuần có **bao nhiêu thời gian** thật sự? (xem `me/now.md`, `me/preferences.md` trước khi hỏi)

## 2. Ghi mục tiêu
`edit_file` `goals/goals.md`, mục `## Đang theo đuổi`:
```
### Thi giữa kỳ Toán đạt mục tiêu của em — hạn 2026-11-06 (chat 28/10)
- Vì sao: muốn vào lớp chọn học kỳ 2.
- Mốc: [ ] 31/10 xong hàm số bậc hai · [ ] 03/11 xong dấu tam thức · [ ] 05/11 làm 1 đề thử
```
Mỗi mục tiêu 2–5 mốc, mỗi mốc có ngày.

## 3. Lập kế hoạch tuần
`goals/plans/this-week.md`, mục `## Việc của người học`. Mỗi việc: hành động cụ thể + thời lượng + ngày.
```
- [ ] T3 20:00 — 30 phút: 5 bài tìm đỉnh parabol (mốc 31/10)
- [ ] T5 21:15 — 20 phút: ôn lại 3 lỗi trong mistakes.md
```
Việc mentor làm thay (tìm bài, gom tài liệu, nhắc) ghi ở mục `## Mentor sẽ làm`.
Người học muốn làm ngay việc đầu tiên: đề nghị `start_focus` với đúng việc và thời lượng đó. Xong một mốc lớn hoặc cả mục tiêu: `celebrate` một lần (không khi người học đang buồn hay căng thẳng).

## 4. Kiểm tra khả thi
- Cộng tổng phút các việc trong tuần, so với thời gian người học có.
- Vượt quá 100%: nói thẳng và cùng chọn việc bỏ hoặc dời. "Kế hoạch này cần khoảng 5 giờ, em nói tuần này có 3 giờ. Mình bỏ bớt phần nào?"
- Không xếp việc vào giờ người học đã nói là bận.
- Mỗi ngày tối đa 2 việc học. Một việc ≤ 45 phút.

## 5. Sửa kế hoạch khi bị chậm
- Giữ mục tiêu, sửa đường đi: dời việc, chia nhỏ, bớt phạm vi. Không lập lại từ đầu.
- Nếu đổi hạn hoặc phạm vi mục tiêu: hỏi người học trước.
- Ghi 1 dòng dưới `## Điều chỉnh`: `- 29/10: dời bài tập dấu tam thức sang T7 vì T5 kiểm tra Lý. (chat 29/10)`
- Không trách. Hỏi cái gì đã cản trở, ghi cách khắc phục vào `me/what-works.md` nếu có.

## 6. Mục tiêu dài hạn
Mục tiêu học kỳ hoặc năm học: ghi các mốc lớn vào `goals/plans/term.md`; mỗi tuần chỉ kéo 1–2 mốc vào this-week.
