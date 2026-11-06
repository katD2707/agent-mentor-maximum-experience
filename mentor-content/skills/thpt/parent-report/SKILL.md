---
name: parent-report
description: Job báo cáo phụ huynh 2 tuần/lần - tiến độ mục tiêu, mức độ đều đặn, xu hướng theo chủ đề, lời nhắc gián tiếp khi cần; soạn bản nháp .mentor/report-drafts/ rồi gửi.
profiles: [thpt]
version: 3
---
# parent-report

Job chạy **mỗi tuần** nhưng báo cáo chỉ gửi **2 tuần/lần**. Báo cáo luôn viết bằng tiếng Việt, gửi phụ huynh. Bản nháp nằm ở `.mentor/report-drafts/` (học sinh không thấy); chỉ khi đã gửi xong, hệ thống mới chuyển nó sang `reports/` và học sinh mới xem được. Không tự ghi vào `reports/` (chỉ đọc).

## Bước 1. Kiểm tra 14 ngày
`list_dir` `reports/` (chỉ chứa báo cáo đã gửi). Lấy file `YYYY-MM-DD.md` có ngày mới nhất = ngày báo cáo trước. Bản nháp chưa gửi trong `.mentor/report-drafts/` không tính.
- Có báo cáo trước, cách hôm nay **dưới 13 ngày** (ví dụ chỉ 7 ngày): dừng. Câu trả lời cuối: "BỎ QUA: chưa đủ 2 tuần kể từ báo cáo trước."
- Chưa có báo cáo nào: `list_dir` `me/journal`. Journal cũ nhất cách hôm nay dưới 13 ngày, hoặc chưa có journal: dừng, "BỎ QUA: chưa đủ 2 tuần dữ liệu."
- Còn lại: làm tiếp. `period_start` = ngày sau báo cáo trước (hoặc ngày journal cũ nhất), `period_end` = hôm nay.
(Ngưỡng 13 ngày để không bị lệch khi job chạy trễ vài giờ.)

## Bước 2. Thu thập (chỉ dữ liệu có cấu trúc)
- **Mục tiêu**: `goals/goals.md`, `goals/plans/this-week.md`. Đếm mốc đã xong trong kỳ.
- **Đều đặn**: `list_dir` `me/journal`, đếm số file có ngày trong kỳ = số ngày có học. Không đọc nội dung journal.
- **Xu hướng theo chủ đề**: `list_dir` `.mentor/curricula`; với **mỗi môn có file curriculum** (Toán, Vật lí, Tiếng Anh...) `read_file` `learning/<môn>/skills.md` (không có file hoặc chưa có dòng nào: bỏ môn đó, không bịa); tên kỹ năng lấy từ `.mentor/curricula/<môn>.yaml`. Gộp theo chủ đề, so với báo cáo trước (nếu có). Chỉ dùng các từ:
  - mastery từ 0.8: **vững**
  - 0.5 đến 0.8, hoặc tăng so với kỳ trước: **đang tiến bộ**
  - dưới 0.5: **cần củng cố**
  - ít bằng chứng: **cần thêm dữ liệu**
  - chưa có bằng chứng: **chưa có dữ liệu**
  Không dùng từ "yếu". Không nêu điểm luyện tập hay thi thử.
- **Luyện tập**: đếm số dòng trong kỳ ở `learning/<môn>/practice-log.md` (nếu có) = số buổi luyện của môn đó. Chỉ nói số buổi, không nêu điểm, số câu đúng, giờ.
- **Lời nhắc gián tiếp**: `run_script` name `wellbeing_window`, input `{"days": 30, "threshold": 0.4}`. Chỉ khi kết quả `trigger_nudge` = true mới thêm lời nhắc, và đặt `includes_wellbeing_nudge: true`.

## Bước 3. Viết báo cáo
`write_file` `.mentor/report-drafts/YYYY-MM-DD.md` (ngày hôm nay). Đúng khung sau:
```markdown
---
period_start: 2026-10-24
period_end: 2026-11-06
includes_wellbeing_nudge: false
---
# Báo cáo học tập 2 tuần (24 tháng 10 đến 6 tháng 11)

## Tiến độ mục tiêu
- Ôn thi giữa kỳ Toán: đã xong 3 trên 4 mốc ôn tập.

## Mức độ đều đặn
- Con học cùng mentor 9 trên 14 ngày, chủ yếu vào buổi tối.

## Xu hướng theo chủ đề
Toán:
- Hàm số bậc hai: vững.
- Dấu của tam thức bậc hai: đang tiến bộ.
- Bất phương trình bậc hai: cần củng cố.
Vật lí:
- Khí lí tưởng: cần thêm dữ liệu.

## Luyện tập
- Con đã luyện tập 4 buổi trong hai tuần.

## Hai tuần tới
- Tập trung ôn bất phương trình bậc hai.

Báo cáo được tạo tự động bởi AI mentor, chỉ mang tính tham khảo.
```
Khi `trigger_nudge` = true, thêm mục này ngay trước dòng cuối, giữ nguyên câu chữ:
```markdown
## Lời nhắn
Thời gian gần đây con có vẻ chịu nhiều áp lực. Phụ huynh nên dành thêm thời gian trò chuyện với con.
```

**Tuyệt đối không có** trong báo cáo:
- điểm từng bài kiểm tra, con số dạng 7/10, chữ điểm đi kèm số;
- dấu `/` giữa hai số, kể cả ngày tháng: viết "24 tháng 10", không viết 24/10;
- dấu ngoặc kép, trích lời học sinh, các cụm "con nói", "con kể", "con chia sẻ", "con tâm sự";
- cảm xúc tức thời, nội dung chat, nội dung `me/`, journal, `learning/evidence/`, lỗi sai cụ thể;
- tên thầy cô, bạn bè; chẩn đoán; chuyện khủng hoảng.
Dòng cuối luôn là: Báo cáo được tạo tự động bởi AI mentor, chỉ mang tính tham khảo.

## Bước 4. Kiểm tra rồi gửi
1. `run_script` name `check_report`, input `{"path": ".mentor/report-drafts/2026-11-06.md"}`.
2. `ok` = false: sửa đúng các mục trong `violations`, kiểm tra lại. Tối đa 2 lần; vẫn lỗi thì dừng, câu trả lời cuối nêu lỗi, không gửi.
3. `ok` = true: gọi `send_parent_report` với `path` = `.mentor/report-drafts/2026-11-06.md`. Hệ thống kiểm tra lại rồi mới gửi.
4. Câu trả lời cuối: "Đã gửi báo cáo kỳ 24 tháng 10 đến 6 tháng 11", có hay không lời nhắc gián tiếp.

Không báo cho học sinh qua `notify_user` về báo cáo; học sinh xem trong mục Báo cáo trên web.
