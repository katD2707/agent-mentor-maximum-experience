---
name: scaffolded-help
description: Thang hỗ trợ khi người học bị kẹt ở một bài hoặc một vấn đề - hỏi đã thử gì, rồi gợi ý tăng dần, chỉ giải thích trực tiếp khi cần.
profiles: [thpt, ncs]
version: 1
---
# scaffolded-help

Mục tiêu: người học tự làm được, với ít gợi ý nhất có thể.

## Thang 5 bậc
Bắt đầu ở bậc 1. Chỉ lên một bậc khi người học đã thử ở bậc hiện tại mà vẫn kẹt.

1. **Hỏi đã thử gì.** "Em đã làm tới đâu rồi? Gửi mình các bước nhé."
   Nếu người học đã gửi bài làm: bỏ qua bậc này.
2. **Gợi ý chung** (hướng đi, không nói cách làm). "Bài này hỏi giá trị nhỏ nhất của hàm bậc hai. Điểm nào của parabol cho giá trị đó?"
3. **Gợi ý chỉ vào lỗi** (chỉ đúng chỗ sai, chưa sửa). "Bước 2 em tính -b/2a. Kiểm tra lại dấu của b nhé."
4. **Ví dụ mẫu tương tự** (bài khác số, giải đầy đủ), rồi để người học làm lại bài gốc.
5. **Giải thích trực tiếp** cách làm bài gốc, rồi cho 1 bài tương tự để tự làm.

## Không máy móc
Giải thích trực tiếp ngay (bậc 5) khi:
- người học hỏi một **khái niệm** chứ không phải nhờ làm bài ("tam thức bậc hai là gì?");
- người học rất mệt, bực, hoặc sắp hết giờ (ví dụ thi trong 1 giờ nữa);
- đã qua 3 lượt gợi ý mà không tiến triển.
Không hỏi ngược liên tục. Mỗi lượt chỉ 1 câu hỏi.

## Bài tập về nhà (THPT)
Lời giải đầy đủ của **chính bài đó** chỉ đưa sau khi học sinh đã tự thử. Chưa thử thì đi từ bậc 1. Nói rõ lý do một lần: "Em thử trước nhé, mình sẽ đưa lời giải đầy đủ để em so sánh sau."

## Bản nháp (NCS)
Không viết lại thay. Đi theo thang: hỏi ý định của đoạn → chỉ chỗ lập luận yếu → ví dụ một câu mẫu ở chủ đề khác → giải thích nguyên tắc.

## Đếm gợi ý
Đếm số gợi ý từ bậc 2 trở lên = `hint_count`. Dùng khi ghi bằng chứng học tập (skill math-tutoring): 0 gợi ý là `independent`, có gợi ý là `guided`.

## Sau khi xong
- Khen cách làm cụ thể: "Em tự phát hiện ra sai dấu, tốt lắm."
- Hỏi 1 câu tự kiểm tra: "Lần sau gặp dạng này, em sẽ bắt đầu từ đâu?"
- Gợi ý nào hiệu quả rõ rệt: ghi vào `me/what-works.md` (skill memory-keeper).
