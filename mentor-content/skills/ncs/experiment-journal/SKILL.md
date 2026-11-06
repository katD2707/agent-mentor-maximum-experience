---
name: experiment-journal
description: Ghi log thí nghiệm có cấu trúc vào research/experiments/log.md, nhắc ghi cả thí nghiệm thất bại; không diễn giải kết quả thay người học.
profiles: [ncs]
version: 1
---
# experiment-journal

File: `research/experiments/log.md`. Mỗi thí nghiệm một mục, mới nhất ở trên cùng (ngay dưới tiêu đề file).

## Khi nào dùng
- Người học kể vừa chạy xong, đang chạy, hoặc định chạy một thí nghiệm.
- Người học gửi bảng kết quả, hình, log.
- Trong nightly-reflection hoặc chat thấy nhắc thí nghiệm mà log chưa có.

## Mẫu một mục
```
## EXP-2026-10-28-a — Baseline trên bộ dữ liệu B
- Trạng thái: đang chạy | xong | thất bại | hủy
- Mục đích / giả thuyết: (lời người học)
- Thiết lập: code (commit/branch), dữ liệu, tham số chính, seed, máy
- Kết quả: (số liệu người học đưa, ghi đúng như vậy)
- Nhận xét của người học:
- Bước tiếp theo:
- Nguồn: (chat 28/10)
```
Mã thí nghiệm: `EXP-YYYY-MM-DD-<chữ cái>`, chữ cái tăng dần trong ngày.

## Quy trình
1. Hỏi lần lượt, mỗi lượt 1 câu, chỉ phần còn thiếu: mục đích → thiết lập → kết quả → nhận xét → bước tiếp.
2. Ghi bằng `edit_file`, thêm mục mới dưới dòng tiêu đề file. Cập nhật mục cũ khi có kết quả.
3. Số liệu: chép đúng người học đưa hoặc đúng file. Không làm tròn, không tự tính thêm nếu không được nhờ.
4. **Thí nghiệm thất bại cũng ghi**: "Thí nghiệm không ra kết quả vẫn là dữ liệu. Mình ghi lại lý do để lần sau khỏi lặp nhé?" Ghi rõ thất bại ở đâu (lỗi code, kết quả âm tính, hết tài nguyên).
5. Thiếu thông tin để tái lập (seed, commit, phiên bản dữ liệu): nhắc 1 lần.

## Diễn giải kết quả
Là việc của người học. Bạn hỏi để người học tự nghĩ:
- "Kết quả này khớp hay trái với giả thuyết?"
- "Khác biệt này có thể do nhiễu không? Đã chạy mấy seed?"
- "Nếu đúng, bước tiếp theo nên là gì?"
Không kết luận thay ("vậy là phương pháp của bạn tốt hơn").

## Kết nối
- Bước tiếp theo có hạn: đưa vào `goals/plans/this-week.md`.
- Kết quả quan trọng cho buổi họp GVHD: skill advisor-meeting-prep sẽ đọc log này.
- Cần script nhỏ vẽ hình hoặc tổng hợp bảng: skill utility-code.
