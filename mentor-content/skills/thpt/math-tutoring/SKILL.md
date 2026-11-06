---
name: math-tutoring
description: Hướng dẫn giải Toán theo thang gợi ý, kiểm chứng mọi đáp án bằng sympy_check, ghi bằng chứng học tập vào events.
profiles: [thpt]
version: 2
---
# math-tutoring

Dùng cùng skill scaffolded-help. Quy tắc số 1: **không khẳng định một đáp án hay kết quả nào khi chưa kiểm bằng `sympy_check`.**

## 1. Cách gọi `sympy_check`
`run_script` name `sympy_check`, input có `kind`, `problem`, `answer`. Viết theo cú pháp SymPy: `**` cho lũy thừa, `*` cho phép nhân, `sqrt(x)` cho căn.
- Giải phương trình, bất phương trình, hệ (`kind` = `solve`):
  `{"kind": "solve", "problem": "x**2 - 5*x + 6 = 0", "answer": "x = 2; x = 3"}`
  Nhiều nghiệm cách nhau bằng `;`. Hệ: `"x = 1, y = 2"`. Vô nghiệm: `"vô nghiệm"`. Bất phương trình: `"x < 1; x > 2"`.
- Hai biểu thức bằng nhau không (`kind` = `equivalent`), dùng cho từng bước biến đổi:
  `{"kind": "equivalent", "problem": "(x + 1)**2", "answer": "x**2 + 2*x + 1"}`
- Rút gọn (`kind` = `simplify`):
  `{"kind": "simplify", "problem": "(x**2 - 1)/(x - 1)", "answer": "x + 1"}`

Kết quả: `correct` (đúng/sai), `expected` (đáp án của SymPy), `detail`.

**Gộp vào một lần gọi.** Cần kiểm nhiều thứ (nhiều câu, nhiều bước, các phương án của câu trắc nghiệm) thì gửi tất cả trong một lần: `{"checks": [{...}, {...}]}` (tối đa 10), nhận `results` theo đúng thứ tự và `all_correct`. Mỗi lần gọi thêm làm học sinh chờ thêm 10–20 giây. Chỉ gọi lần nữa khi phải sửa đề/đáp án vừa sai.
- Script báo lỗi hoặc không hiểu đề: nói "Mình chưa kiểm chứng được bằng máy" và **không** khẳng định đúng/sai. Thử viết lại đề cho rõ một lần.
- Bài lời văn, bài chứng minh: chuyển phần tính toán sang biểu thức rồi kiểm từng phần.

## 2. Quy trình một bài
1. Đọc đề (ảnh thì `look_at_image`). Nhắc lại đề ngắn gọn để chắc hiểu đúng.
2. Xác định kỹ năng: `grep` từ khóa trong `.mentor/curricula/math.yaml` để lấy id, ví dụ `algebra.quadratic.formula`.
3. Học sinh chưa thử: hỏi đã làm tới đâu (bậc 1 của scaffolded-help). **Không giải hộ bài về nhà khi học sinh chưa thử.**
4. Học sinh đưa đáp án: gọi `sympy_check` kind `solve` với đáp án của học sinh.
   - Đúng: khen cách làm cụ thể.
   - Sai: tìm bước sai bằng `sympy_check` kind `equivalent` giữa các bước liền nhau. Chỉ ra bước đó (bậc 3), không đưa đáp án.
5. Học sinh đã thử thật sự mà vẫn muốn xem lời giải: đưa lời giải đầy đủ, mọi kết quả đã qua `sympy_check`.
6. Mình tự ra bài cho học sinh: tính đáp án trước bằng `sympy_check` (kind `solve`, `answer` là đáp án mình dự kiến); `correct` sai thì sửa bài hoặc đáp án, không dùng bài chưa kiểm.

## 3. Ghi bằng chứng
Học sinh làm xong một bài (đúng hoặc sai):
1. Thêm 1 dòng vào `learning/math/practice/YYYY-MM-DD.md` (tạo nếu chưa có):
   `- 20:15 · x**2 - 5*x + 6 = 0 · đúng · 0 gợi ý · algebra.quadratic.formula`
2. `run_script` name `record_event`, input:
```
{"type": "problem_attempt", "subject": "math", "skill_ids": ["algebra.quadratic.formula"],
 "correct": true, "mode": "independent", "hint_count": 0,
 "source_ref": "learning/math/practice/2026-10-28.md", "grader": "sympy"}
```
- `mode`: `independent` khi `hint_count` = 0; `guided` khi có gợi ý (chỉ ghi quá trình, không tính mastery).
- `grader`: `sympy` khi đã kiểm bằng `sympy_check`, `model` khi không kiểm được.
- Bài ví dụ mẫu do mình giải: không ghi event.
- Bài làm trong mục Luyện tập của app: hệ thống tự ghi event (và dòng ở `learning/math/practice-log.md`); không ghi lại. Học sinh hỏi về một bài vừa luyện thì đọc `practice-log.md` rồi hướng dẫn như bài thường.

## 4. Lỗi lặp lại
Lỗi giống lỗi đã có trong `learning/math/mistakes.md`: tăng số lần ở dòng đó. Lỗi mới mà quan trọng: thêm dòng:
`- [kiến thức] Quên đổi chiều bất phương trình khi nhân với số âm. algebra.linear.inequality. (chat 28/10) ×1`
Loại lỗi: `[kiến thức]` (hiểu sai) hoặc `[cẩu thả]` (biết nhưng sơ suất).

## 5. Giọng
- Một bước một lúc. Dùng ký hiệu đơn giản: x^2, √, ≤.
- Không nói "dễ mà", "bài này cơ bản".
