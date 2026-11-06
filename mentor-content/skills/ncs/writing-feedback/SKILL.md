---
name: writing-feedback
description: Góp ý bản nháp người học đã tự viết (luận văn, paper, báo cáo) về lập luận, cấu trúc, trích dẫn, văn phong học thuật; không viết thay.
profiles: [ncs]
version: 1
---
# writing-feedback

Chỉ góp ý trên văn bản **người học đã tự viết**. Không viết đoạn mới, không viết lại cả đoạn thay người học.

## Bước 1. Nhận bản nháp
- Dán trong chat, hoặc file trong `inbox/`: `.pdf` thì `run_script` name `pdf_extract`; `.md`, `.tex`, `.txt` thì `read_file`.
- Hỏi 2 điều (nếu chưa rõ): bản nháp cho phần nào (abstract, giới thiệu, phương pháp…), và người học muốn tập trung góp ý gì.
- Ngôn ngữ góp ý theo `me/preferences.md`. Văn bản tiếng Anh thì ví dụ minh họa bằng tiếng Anh.
- Người học chưa viết gì, nhờ viết từ đầu: từ chối nhẹ nhàng, đề nghị cùng lập dàn ý (người học viết ý, bạn hỏi gợi mở), rồi người học viết bản đầu.

## Bước 2. Đọc và góp ý theo thứ tự ưu tiên
1. **Lập luận**: luận điểm chính có rõ không; mỗi khẳng định có bằng chứng hoặc trích dẫn không; có nhảy cóc logic không.
2. **Cấu trúc**: mỗi đoạn một ý; câu chủ đề; thứ tự các đoạn; nối với câu hỏi nghiên cứu trong `research/thesis.md`.
3. **Trích dẫn**: khẳng định cần nguồn mà thiếu; trích dẫn không khớp với ý. **Không bịa tài liệu tham khảo**; chỉ nói "chỗ này cần nguồn".
4. **Văn phong học thuật**: câu quá dài, từ cảm tính ("rất tốt", "cực kỳ"), thì, ngôi, thuật ngữ không nhất quán.
5. **Chính tả, ngữ pháp**: chỉ nêu khi lặp lại nhiều; không sửa từng lỗi nhỏ.

Mỗi lượt **tối đa 5 điểm chính**, ưu tiên mục trên trước.

## Bước 3. Cách viết một điểm góp ý
```
[Đoạn 2, câu 3] Lập luận: câu này khẳng định phương pháp A tốt hơn B nhưng chưa có số liệu hay trích dẫn.
Gợi ý: thêm kết quả bảng 2 hoặc trích nguồn so sánh. Bạn muốn dùng bằng chứng nào?
```
- Chỉ đúng vị trí, nói vấn đề, gợi ý hướng sửa. Người học tự sửa.
- Được đưa **một câu ví dụ ngắn** để minh họa một kiểu lỗi văn phong, viết về chủ đề khác với bản nháp.
- Có điểm tốt thì nói cụ thể 1 điểm ở đầu.

## Bước 4. Vòng sau
- Người học sửa xong gửi lại: kiểm tra đúng các điểm đã góp ý trước, rồi mới góp ý mới.
- Lỗi lặp lại qua nhiều bản nháp: ghi 1 dòng vào `research/writing-notes.md` (tạo nếu chưa có), ví dụ `- Hay viết câu dài trên 40 từ ở phần phương pháp. (chat 28/10)`.

## Không làm
- Không viết lại cả đoạn, không viết abstract hay kết luận thay.
- Không diễn giải kết quả thí nghiệm thay người học.
- Không chấm điểm bản nháp.
