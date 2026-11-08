---
name: memory-keeper
description: Quy tắc ghi, sửa, xóa trí nhớ về người học (me/, goals/) trong lúc chat. Đọc khi nghe thông tin mới đáng nhớ, khi người học sửa thông tin, hoặc khi bảo quên.
profiles: [student]
version: 2
preload: true
---
# memory-keeper

## 1. Khi nào ghi
Ghi **ngay trong lượt chat đó** (không để sang phiên sau) khi thông tin thỏa cả hai: (a) còn đúng sau ≥ 1 tuần, (b) thay đổi cách bạn hỗ trợ.
Luôn ghi: deadline, kỳ thi, sự kiện sắp tới; người quan trọng với việc học; cách hỗ trợ vừa hiệu quả hoặc thất bại; mục tiêu mới.

Không ghi:
- mật khẩu, số tài khoản, số giấy tờ, địa chỉ nhà, số điện thoại
- chuyện nhạy cảm về người thứ ba (bệnh tật, mâu thuẫn của người khác)
- nhận xét về trí thông minh hay tính cách ("chậm hiểu", "lười")
- chẩn đoán tâm lý hoặc y tế ("trầm cảm", "ADHD")
- chuyện vặt không ảnh hưởng việc hỗ trợ ("hôm nay ăn phở")

## 2. Ghi vào đâu
| Loại thông tin | File |
|---|---|
| Lớp, trường, ngành, mục tiêu dài hạn | `me/profile.md` |
| Thầy cô, GVHD, bạn học (tên gọi + vai trò, tối thiểu) | `me/people.md` |
| Ngôn ngữ, xưng hô, giờ học, cách giải thích ưa thích | `me/preferences.md` |
| Tuần này bận gì, kỳ thi, áp lực hiện tại | `me/now.md` |
| Cách hỗ trợ hiệu quả / không hiệu quả | `me/what-works.md` |
| Mục tiêu | `goals/goals.md` |
| Việc tuần này | `goals/plans/this-week.md` |
| Lỗi Toán lặp lại | `learning/math/mistakes.md` |

## 3. Cách ghi
Ghi **một lần, ở cuối**: xử lý xong tin nhắn, quyết định hết mọi điều cần ghi trong lượt này, rồi ghi tất cả trong **một bước công cụ**, ngay trước câu trả lời. Không ghi rải rác từng dòng qua nhiều bước.
1. Nội dung file đích:
   - `me/profile.md`, `me/preferences.md`, `me/now.md`, `goals/goals.md`, `goals/plans/this-week.md` đã có nguyên văn trong context (mục "Trí nhớ cốt lõi"): **không `read_file` lại**, lấy `old` từ đó.
   - File khác (`me/people.md`, `me/what-works.md`…): `read_file` trước để không ghi đè mất nội dung. Cần nhiều file thì đọc tất cả trong cùng một bước.
2. **Mỗi file một lần gọi `edit_file`** với `edits` = danh sách mọi thay đổi cho file đó, gồm cả dòng `cập nhật`. Thêm dòng dưới đúng mục: `old` = dòng tiêu đề mục, `new` = tiêu đề + dòng mới. Sửa nhiều file thì gọi các `edit_file` cùng lúc trong một phản hồi. Chỉ dùng `write_file` khi tạo file mới.
3. Định dạng:
   - Sự kiện: `- <ý ngắn>. (<nguồn> <dd/mm>)`
   - Suy luận: `- [suy luận] <ý>. (<nguồn> <dd/mm>, độ chắc: thấp|vừa|cao)`
4. Sửa dòng `cập nhật YYYY-MM-DD` ở đầu file thành hôm nay (một phần tử trong `edits` của file đó).
5. Có lỗi (ví dụ `old` không khớp): file đó chưa được ghi gì; sửa `old` rồi gọi lại cho riêng file đó.

Ví dụ (hôm nay 28/10). Người học: "Em là Huy lớp 11. Thứ Sáu tuần sau em thi giữa kỳ Toán, sợ nhất phần hàm số."
Một bước công cụ, hai lần gọi trong cùng một phản hồi, rồi mới trả lời:
```
edit_file path=me/profile.md edits=[{old: "# Hồ sơ — cập nhật YYYY-MM-DD", new: "# Hồ sơ — cập nhật 2026-10-28"},
                                     {old: "## Cơ bản", new: "## Cơ bản\n- Tên gọi Huy, học lớp 11. (chat 28/10)"}]
edit_file path=me/now.md edits=[{old: "# Tình hình hiện tại — cập nhật YYYY-MM-DD", new: "# Tình hình hiện tại — cập nhật 2026-10-28"},
                                 {old: "## Tuần này", new: "## Tuần này\n- Thi giữa kỳ Toán thứ Sáu 6/11, lo nhất phần hàm số bậc hai. (chat 28/10)"}]
```
Ví dụ cấm và cách ghi thay: không ghi "Em ấy chậm hiểu". Ghi vào `me/what-works.md`:
```
- Hiểu nhanh hơn khi có ví dụ số cụ thể trước công thức. (chat 28/10)
```

## 4. Mâu thuẫn
- Thông tin mới trái với dòng cũ và người học nói rõ: sửa dòng cũ thành thông tin mới, nguồn mới (git giữ bản cũ).
- Chưa chắc cái nào đúng: hỏi. "Mình đang ghi là thi ngày 6/11, giờ em nói 8/11. Mình sửa thành 8/11 nhé?"

## 5. Nói với người học
- Không cần báo mỗi lần ghi. Với chuyện riêng tư (áp lực, chuyện gia đình): hỏi trước "Mình ghi lại để lần sau nhớ nhé?"
- Người học hỏi "mentor biết gì về em": dùng các file trong context, đọc thêm các file khác trong `me/`, rồi tóm tắt, kèm nguồn từng ý.
- Người học sửa một ý: sửa ngay, nguồn `(chat dd/mm)`.
- Muốn dùng một ký ức cũ: dòng đó có trong context thì dùng luôn; không thì kiểm tra bằng `grep` trước. Luôn nói nguồn.

## 6. Quên
Làm đúng quy trình "quên" trong AGENTS.md, gồm cả `me/journal/`. Không để lại dấu kiểu "(đã xóa chuyện X)".

## 7. Giữ gọn
`me/now.md` chỉ giữ việc hiện tại. Việc đã qua hoặc dòng cũ hơn 2 tuần không còn đúng: xóa, hoặc để nightly-reflection chuyển sang journal.
