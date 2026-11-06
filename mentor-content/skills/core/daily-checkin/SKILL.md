---
name: daily-checkin
description: Check-in buổi sáng (gợi ý 3 việc chính hôm nay) và tổng kết buổi tối (1-2 câu hỏi) bằng lời nhắn có nút trả lời và thẻ checkin trong chat; xử lý câu trả lời từ lời nhắn.
profiles: [thpt, ncs]
version: 1
---
# daily-checkin

Ba phần: **A** check-in sáng, **B** tổng kết tối (đều là job, không có người học), **C** job ngắn khi người học bấm nút trả lời trên lời nhắn. Hệ thống đã kiểm mức chủ động, giờ yên lặng và giới hạn tin mỗi ngày trước khi chạy A và B: không cần kiểm lại.

Quy tắc chung:
- Giọng nhẹ nhàng. Không trách, không đếm ngày bị lỡ, không tạo áp lực thời gian. Người học bỏ qua lời nhắn thì thôi, không nhắc lại.
- Journal 2 ngày gần nhất có dấu hiệu khủng hoảng, hoặc người học đang rất mệt, buồn: không gửi gì, câu trả lời cuối "BỎ QUA: để người học nghỉ ngơi." Lời nhắn không bao giờ nói về cảm xúc, sức khỏe, điểm số hay chuyện riêng.
- Mỗi job tối đa 1 `notify_user` và 1 thẻ checkin. Màn hình khóa chỉ hiện câu chung; nội dung của bạn chỉ hiện trong ứng dụng.
- Chỉ đề xuất việc có nguồn trong goals/ hoặc kế hoạch tuần. Không bịa việc.

## A. Check-in sáng
1. `read_file` `goals/plans/this-week.md`, `goals/goals.md` (deadline, mốc gần nhất), `me/now.md`. THPT: thêm `learning/math/review-queue.md` nếu có.
2. Chọn tối đa 3 việc cho hôm nay, cụ thể và làm được (mỗi việc ≤ 60 phút, ghi thời lượng). Thứ tự ưu tiên: deadline gần → việc kế hoạch tuần hẹn hôm nay → bài ôn đến hạn. Không có gì để đề xuất: "BỎ QUA: chưa có kế hoạch."
3. `edit_file` `goals/plans/this-week.md`: thêm (hoặc thay) mục
```
## Hôm nay (2026-11-03)
- [ ] 30 phút: 5 bài tìm đỉnh parabol
- [ ] 20 phút: đọc mục 2.3 paper Whisper
- [ ] 10 phút: ôn nhanh dấu tam thức
```
4. `show_card` kind checkin, data `{"prompt": "3 việc chính hôm nay:\n1) …\n2) …\n3) …", "options": ["Chốt vậy", "Đổi một việc", "Hôm nay bận"]}`.
5. `notify_user`: kind checkin, title "Chào buổi sáng", text "Gợi ý 3 việc hôm nay: 1) … 2) … 3) …", actions `[{"id": "answer:ok", "label": "Chốt vậy"}, {"id": "start_focus", "label": "Bắt đầu việc 1"}, {"id": "answer:change", "label": "Đổi việc"}]`, mascot wave, prefill "Mình muốn đổi kế hoạch hôm nay: ".
6. Tóm tắt 1 câu.

## B. Tổng kết tối
1. Đọc mục `## Hôm nay` trong `goals/plans/this-week.md`. Không có mục của hôm nay: "BỎ QUA: sáng nay chưa check-in." Cả 3 việc đã `[x]`: chỉ gửi lời khen ngắn (kind celebration, không có actions), rồi dừng.
2. `show_card` kind checkin, prompt "Hôm nay 3 việc của em thế nào?", options ["Xong hết", "Được một phần", "Chưa kịp"].
3. `notify_user`: kind checkin, title "Nhìn lại hôm nay", text "Hôm nay em làm được việc nào trong 3 việc đã chọn?", actions `answer:all` "Xong hết", `answer:some` "Được một phần", `answer:none` "Chưa kịp", mascot happy, prefill "Hôm nay mình ". Có thể hỏi thêm 1 câu trong thẻ, không hơn.
4. Tóm tắt 1 câu.

## C. Trả lời từ lời nhắn
Prompt có dạng: Người học vừa trả lời lời nhắn (checkin) “…”: … — chọn “<nhãn>” (answer:<x>). Không có người học đang chat; kết quả hiện ở lần mở chat sau.
- `answer:ok` (sáng): thêm " (đã chốt)" vào tiêu đề mục Hôm nay. Không làm gì thêm.
- `answer:change` (sáng): không tự đổi. `show_card` kind checkin, prompt "Em muốn đổi việc nào?", options = 3 việc.
- `answer:all` (tối): đánh `[x]` cả 3 việc; `show_card` kind celebration, title ngắn, detail nêu 1 việc cụ thể đã xong.
- `answer:some` (tối): không tự đánh dấu. `show_card` kind checkin, prompt "Việc nào xong rồi?", options = các việc chưa `[x]`.
- `answer:none` (tối): chuyển các việc chưa xong sang ngày mai trong kế hoạch tuần, ghi 1 dòng ở mục `## Điều chỉnh`. Không trách, không hỏi lý do.
- Nhãn khác (lời nhắn do skill khác tạo): làm theo nghĩa của nhãn, ghi ngắn vào `me/now.md` nếu đáng nhớ.
- Không gọi `notify_user` trong phần C. Tóm tắt 1 câu.
