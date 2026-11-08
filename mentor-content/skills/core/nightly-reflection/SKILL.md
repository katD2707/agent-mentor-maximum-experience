---
name: nightly-reflection
description: Job nền mỗi đêm. Viết journal, hợp nhất trí nhớ, cập nhật mastery, sửa kế hoạch tuần, hẹn việc cho ngày mai.
profiles: [student]
version: 1
---
# nightly-reflection

Job không có người học. Không hỏi, không gọi `notify_user` (đang giờ yên lặng). Làm lần lượt 8 bước. `D` = ngày hôm nay theo giờ Việt Nam, dạng `YYYY-MM-DD`.

## Bước 1. Đọc dữ liệu trong ngày
- `list_dir` `sessions/D`, rồi `read_file` từng transcript (cả `s-*.md` của chat chính và `c-*.md` của các cuộc trò chuyện riêng).
- `grep` với pattern là `D` trong `events.jsonl`.
- Không có phiên nào và không có event mới: bỏ qua bước 2, 3, 4; làm tiếp từ bước 5.

## Bước 2. Viết journal
`write_file` `me/journal/D.md`, ngắn gọn (≤ 25 dòng):
```
# Nhật ký 2026-10-28
## Chuyện gì đã xảy ra
- Ôn hàm số bậc hai 40 phút, làm 5 bài. (chat 28/10)
## Tiến bộ
- Tự tìm đúng đỉnh parabol 3 bài liên tiếp, không cần gợi ý. (events 28/10)
## Khó khăn
- Còn nhầm dấu khi tính -b/2a. (chat 28/10)
## Ghi chú cho mentor
- [suy luận] Học tốt hơn khi bắt đầu bằng 1 bài dễ. (chat 28/10, độ chắc: vừa)
```
Không chép nguyên văn lời người học. Không ghi chuyện riêng của người khác.

## Bước 3. Hợp nhất trí nhớ
Theo định dạng của skill memory-keeper:
- Thông tin mới đáng nhớ trong ngày: đưa vào đúng file `me/*.md` hoặc `goals/*.md`.
- Gộp dòng trùng lặp, giữ nguồn mới nhất.
- `me/now.md`: xóa sự kiện đã qua; chuyển ý còn giá trị vào journal hôm nay.
- Dòng `[suy luận]` được xác nhận nhiều lần: bỏ nhãn, ghi nguồn mới. Bị phủ định: xóa.

## Bước 4. Mastery
Có event mới hôm nay: `run_script` name `bkt_update`, input `{"subject": "math"}`. Sau đó `read_file` `learning/math/review-queue.md` để biết kỹ năng đến hạn ôn ngày mai.

## Bước 5. Deadline và kế hoạch tuần
- Đọc `goals/goals.md`, `goals/plans/this-week.md`, `goals/plans/term.md`, `me/now.md`.
- Đánh dấu `[x]` việc đã xong hôm nay.
- Bị chậm: **sửa** kế hoạch (dời, chia nhỏ, bớt việc), không lập lại từ đầu. Ghi lý do 1 dòng dưới mục `## Điều chỉnh`.
- Deadline trong 7 ngày tới mà chưa có trong kế hoạch: thêm vào.

## Bước 6. Việc chủ động cho ngày mai
- Ghi tối đa 3 việc vào mục `## Mentor sẽ làm` của `goals/plans/this-week.md`.
- Việc cần thức dậy đúng giờ: gọi `schedule_wake`, ví dụ `at` = `2026-10-29T17:00:00+07:00`, `job_kind` = `routine`, `prompt` = "Dùng skill spaced-review: 3 kỹ năng đến hạn ôn."
- Deadline trong 48 giờ: hẹn `schedule_wake` lúc 07:30 sáng mai, prompt "Nhắc deadline: <việc>, hạn <giờ>. Gửi bằng notify_user."
- Giờ hẹn phải ngoài `quiet_hours` trong `routines.yaml`.

## Bước 8. Giữ `me/` gọn
Mỗi file `me/*.md` ≤ 60 dòng. Dài hơn: gộp ý, chuyển chi tiết cũ xuống journal.

Câu trả lời cuối: 1–2 câu tóm tắt, ví dụ "Đã viết journal 28/10, cập nhật now.md, dời 1 bài ôn sang thứ Bảy, hẹn ôn 17:00 mai."
