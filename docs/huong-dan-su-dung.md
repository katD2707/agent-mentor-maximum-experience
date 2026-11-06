# Hướng dẫn sử dụng Mentor

Dành cho học sinh THPT, phụ huynh và nghiên cứu sinh, sinh viên trong đợt dùng thử.

- Trang web: `https://<DOMAIN>`
- App máy tính (Windows 10, 11): tệp `Mentor-Setup-<phiên bản>.exe` do nhóm dự án gửi cho bạn
- App máy tính (Linux: Ubuntu 22.04, 24.04 và các bản tương tự): tệp `Mentor_<phiên bản>_amd64.deb` hoặc
  `Mentor-<phiên bản>-x86_64.AppImage`, xem mục 2, "Cài trên Linux"

---

## 1. Mentor là gì

Mentor là người hướng dẫn học tập riêng của bạn, chạy bằng trí tuệ nhân tạo (AI). Mentor nhớ mục tiêu,
kế hoạch và cách học hợp với bạn, nên mỗi lần trò chuyện không phải kể lại từ đầu.

**Mentor làm giúp bạn những việc phụ:** sắp xếp kế hoạch, theo dõi deadline, nhắc lịch ôn, tóm tắt tài
liệu, chuẩn bị buổi họp với giáo viên hướng dẫn, tìm thông tin như lịch thi hay hạn nộp hồ sơ.

**Mentor không làm bài hộ bạn.** Khi bạn bí, Mentor hỏi bạn đã thử đến đâu rồi gợi ý từng bước, từ gợi ý
chung tới chỉ đúng chỗ sai, đưa ví dụ tương tự, và chỉ giải thích trọn vẹn khi thật cần.

- Học sinh THPT: Mentor không đưa lời giải đầy đủ khi bạn chưa tự làm. Gửi bài làm của bạn trước, Mentor
  mới đưa lời giải để bạn so sánh.
- Nghiên cứu sinh, sinh viên: Mentor không viết luận văn, paper hay code thí nghiệm chính thay bạn. Mentor
  góp ý chi tiết cho bản nháp bạn đã tự viết, và có thể viết đoạn code nhỏ như vẽ biểu đồ hay xử lý bảng.

Mentor có thể sai. Thông tin quan trọng như ngày thi hay hạn nộp hồ sơ, hãy kiểm tra lại ở nguồn chính
thức (khi tìm trên web, Mentor ghi link nguồn để bạn mở xem).

---

## 2. Cài app máy tính

App máy tính hiện một **bong bóng chữ M** ở góc màn hình. Bấm vào là mở khung chat nhỏ, không cần mở
trình duyệt.

### Cài đặt

1. Tải tệp `Mentor-Setup-<phiên bản>.exe` rồi mở nó. Không cần quyền quản trị (admin).
2. Windows có thể hiện màn hình xanh **"Windows đã bảo vệ PC của bạn"** (tiếng Anh: *Windows protected
   your PC*). Lý do là app chưa có chữ ký số, không phải vì app có virus. Bấm **Thông tin thêm** (*More
   info*), rồi **Vẫn chạy** (*Run anyway*).
   - Nếu trình duyệt Edge báo tệp "không thường được tải xuống": bấm **...** cạnh tệp, chọn **Giữ lại**
     (*Keep*).
3. Trình cài đặt bằng tiếng Anh: bấm **Next** hai lần (giữ nguyên thư mục cài), bấm **Install**, rồi
   **Finish**. Để tick *Run Mentor* thì app mở luôn; tick *Create desktop shortcut* nếu muốn có biểu tượng
   ngoài màn hình.
4. Nếu máy thiếu thành phần WebView2 của Microsoft, trình cài đặt tự tải về. Lúc này máy cần có mạng.

### Lần chạy đầu tiên

- Khung chat tự mở ra ở trang **Đăng nhập** (xem mục 4). Trong app máy tính, bạn đăng nhập bằng **mã 6
  số** trong email.
- Sau khi đăng nhập, bong bóng **M** màu xanh nằm ở **góc dưới bên phải**, ngay trên thanh tác vụ.

### Dùng hằng ngày

- **Bấm bong bóng** hoặc nhấn **Ctrl+Alt+M** để mở hoặc thu gọn khung chat.
- Khung chat tự thu gọn khi bạn bấm ra ngoài hoặc nhấn **Esc**.
- **Kéo bong bóng** đến chỗ bạn thích. Thả ra, nó tự dính vào cạnh màn hình gần nhất và nhớ vị trí đó.
- **Con số màu đỏ** trên bong bóng là số tin Mentor gửi trong lúc khung chat đang đóng.
- **Bấm chuột phải** vào bong bóng: mở khung chat, mở bản web đầy đủ, ẩn bong bóng, thoát.
- Nút **mở trang đầy đủ** (góc trên khung chat) mở Mentor trong trình duyệt, nơi có thêm trí nhớ, kế
  hoạch, cài đặt.
- Khi khung chat đang mở, bong bóng hiện dấu X: bấm vào để thu gọn. Alt+F4 cũng chỉ thu gọn. Muốn tắt hẳn,
  chọn **Thoát Mentor** ở menu chuột phải của bong bóng hoặc ở biểu tượng khay.

### Biểu tượng ở khay hệ thống

Biểu tượng **M** nằm cạnh đồng hồ (nếu không thấy, bấm mũi tên **^**). Bấm chuột trái để mở hoặc thu gọn
khung chat. Bấm chuột phải để mở menu:

| Mục trong menu | Tác dụng |
|---|---|
| Mở / thu gọn khung chat | Như bấm bong bóng |
| Mở ứng dụng web | Mở Mentor trong trình duyệt |
| Hiện bong bóng | Bỏ tick để giấu bong bóng, tick lại để hiện |
| Bong bóng: luôn hiện | Mặc định. Bong bóng hiện cả khi chưa đăng nhập (dạng viền rỗng, bấm vào để đăng nhập) |
| Bong bóng: chỉ khi đã đăng nhập | Bong bóng chỉ hiện sau khi bạn đăng nhập |
| Khởi động cùng Windows | Tick để Mentor tự chạy khi bật máy. Mặc định tắt |
| Thoát Mentor | Tắt app |

Mở Mentor lần nữa trong khi app đang chạy chỉ làm khung chat hiện ra, không mở thêm cửa sổ.

### Cài trên Linux

Dành cho máy 64-bit chạy Ubuntu 22.04, 24.04 hoặc bản dựa trên Ubuntu (Linux Mint 21 trở lên). Nhóm dự
án gửi bạn một trong hai tệp sau.

**Cách 1: tệp `.deb` (nên dùng)**

1. Mở thư mục có tệp vừa tải (thường là **Tải về** / *Downloads*), bấm chuột phải vào chỗ trống, chọn
   **Mở trong Terminal** (*Open in Terminal*).
2. Gõ lệnh sau (nhớ có `./` ở đầu tên tệp), nhấn Enter rồi nhập mật khẩu máy:

   ```
   sudo apt install ./Mentor_<phiên bản>_amd64.deb
   ```

   Máy cần có mạng: `apt` tự cài thêm những gói còn thiếu.
3. Mở **Mentor** từ danh sách ứng dụng (nhóm *Giáo dục* / *Education*).

Cập nhật: cài tệp `.deb` mới theo cách trên. Gỡ: `sudo apt remove mentor`.

**Cách 2: tệp AppImage** (không cần cài, chạy thẳng)

1. Cài FUSE 2 một lần (cần mật khẩu máy):
   - Ubuntu 22.04: `sudo apt install libfuse2`
   - Ubuntu 24.04: `sudo apt install libfuse2t64`
2. Chuyển tệp `Mentor-<phiên bản>-x86_64.AppImage` vào một thư mục cố định (ví dụ thư mục nhà). Mục
   **Khởi động khi đăng nhập** nhớ đúng chỗ của tệp, nên đừng di chuyển hay đổi tên tệp sau đó.
3. Cho phép chạy tệp: bấm chuột phải vào tệp → **Thuộc tính** (*Properties*) → bật **Cho phép chạy như
   chương trình** (*Executable as Program*). Hoặc trong Terminal:
   `chmod +x Mentor-<phiên bản>-x86_64.AppImage`
4. Bấm đúp vào tệp để mở Mentor.

**Khác với Windows**

- Biểu tượng **M** nằm trên **thanh trên cùng**, bên phải. Bấm vào luôn mở menu (bấm chuột trái không
  mở thẳng khung chat như trên Windows); mục đầu tiên **Mở / thu gọn khung chat**. Con số cạnh biểu
  tượng là số tin mới.
- Ubuntu có sẵn phần hiện biểu tượng này. Trên các bản GNOME khác (Debian, Fedora), cần bật tiện ích
  **AppIndicator and KStatusNotifierItem Support**. Không có biểu tượng thì vẫn dùng bong bóng: bấm để mở
  khung chat, bấm chuột phải để có menu.
- Trong menu, **Nhắc nhở: thông báo hệ thống** (thay cho "thông báo Windows") và **Khởi động khi đăng
  nhập** (thay cho "Khởi động cùng Windows").
- **Ctrl+Alt+M** chỉ chạy khi đăng nhập phiên **Ubuntu on Xorg** (chọn ở nút bánh răng màn hình đăng
  nhập). Ở phiên mặc định (Wayland), dùng bong bóng hoặc biểu tượng trên thanh trên cùng.
- Ở phiên Wayland, Mentor tự chạy qua XWayland để bong bóng nằm đúng góc màn hình và luôn nổi trên các
  cửa sổ khác. Nếu bạn đặt tỉ lệ màn hình lẻ (125%, 150%), chữ trong Mentor có thể hơi mờ.

---

## 3. Dùng trên web

Mở `https://<DOMAIN>` bằng Chrome, Edge, Firefox hoặc Safari, trên máy tính hay điện thoại đều
được. Bản web có đủ mọi chức năng; dùng nó nếu máy bạn không chạy Windows hay Linux, hoặc bạn không muốn
cài app.

Thanh bên trái của bản web có: Trò chuyện, Mentor biết gì về tôi, Mục tiêu & kế hoạch, Học tập (THPT) hoặc
Nghiên cứu (NCS), Báo cáo phụ huynh (THPT), Hoạt động, Workspace, Cài đặt.

---

## 4. Đăng nhập

Mentor không dùng mật khẩu.

1. Nhập email, bấm **Gửi liên kết đăng nhập** (trên app máy tính: **Gửi mã đăng nhập**).
2. Mở email từ Mentor. Thư có **một liên kết** và **một mã 6 số**:
   - trên web: bấm liên kết, hoặc gõ mã 6 số vào ô **Nhập mã 6 số**;
   - trên app máy tính: gõ **mã 6 số** (bấm liên kết sẽ đăng nhập trình duyệt, không phải app).
3. Liên kết và mã dùng được trong khoảng 15 phút. Gõ sai mã 5 lần thì mã bị huỷ; khi đó gửi lại email để
   lấy mã mới.

Bạn giữ trạng thái đăng nhập khoảng 30 ngày. Muốn đăng xuất trên web: nút **Đăng xuất** ở cuối thanh bên
trái.

---

## 5. Làm quen lần đầu

Lần đầu đăng nhập, Mentor hỏi:

- **Bạn là**: *Học sinh THPT* hoặc *Nghiên cứu sinh / Sinh viên*. Mentor đồng hành khác nhau cho hai
  nhóm này.
- **Tên hiển thị**: tên Mentor dùng để gọi bạn.
- **Ngôn ngữ**: tiếng Việt hoặc English (đổi lại được trong Cài đặt).

Học sinh THPT cần đọc và đồng ý các điều khoản (báo cáo cho phụ huynh, cảnh báo an toàn; xem mục 6 và
mục 11), rồi liên kết với phụ huynh. Nghiên cứu sinh, sinh viên vào trò chuyện được ngay.

---

## 6. Học sinh THPT: liên kết với phụ huynh qua Zalo

Học sinh chỉ bắt đầu trò chuyện được sau khi phụ huynh xác nhận.

**Học sinh:** màn hình hiện **mã liên kết 6 số** và (nếu có) **mã QR**. Mã dùng một lần, hết hạn sau 24
giờ. Hết hạn thì bấm **Tạo mã mới**.

**Phụ huynh:**

1. Mở Zalo, **quét mã QR** trên màn hình của con, hoặc tìm tên bot hiện trên màn hình.
2. **Gửi mã 6 số** cho bot.
3. Đọc lời giới thiệu, rồi trả lời **ĐỒNG Ý**.

Màn hình của con tự chuyển sang "Phụ huynh đã xác nhận", con bấm **Bắt đầu trò chuyện**.

**Phụ huynh nhận được gì:**

- **Báo cáo học tập 2 tuần một lần** qua Zalo: tiến độ mục tiêu, mức độ đều đặn khi học, xu hướng tiến bộ
  theo từng chủ đề. Báo cáo do AI soạn và có ghi rõ điều đó.
- Báo cáo **không có** điểm từng bài, **không có** nội dung trò chuyện, nhật ký hay những gì con kể riêng
  với Mentor.
- **Cảnh báo an toàn** trong trường hợp nghiêm trọng (xem mục 11).
- Bot **chỉ gửi tin**, không trả lời câu hỏi. Phụ huynh muốn biết thêm thì hỏi trực tiếp con.

**Học sinh xem được đúng báo cáo phụ huynh nhận**, ở mục **Báo cáo phụ huynh**, sau khi báo cáo đã gửi.

Lưu ý: mỗi tài khoản Zalo hiện chỉ liên kết được với một học sinh. Gửi sai mã nhiều lần thì phải đợi 1
giờ.

---

## 7. Trò chuyện, gửi ảnh và bài kiểm tra

Gõ tin nhắn rồi nhấn **Enter** (Shift+Enter để xuống dòng). Lần đầu trong ngày, Mentor có thể mất vài giây
để "thức dậy"; trạng thái hiện ở đầu khung chat.

**Gửi kèm ảnh, tài liệu** (ảnh, PDF, Word .docx, .txt, .md):

- bấm **Đính kèm**, hoặc kéo thả tệp vào khung chat, hoặc dán ảnh bằng **Ctrl+V**;
- bấm **Chụp màn hình** để chụp đề bài đang mở trên máy;
- **Từ điện thoại**: bấm **Từ điện thoại**, quét mã QR bằng camera điện thoại, chụp bài làm hoặc chọn ảnh,
  bấm **Gửi**. Ảnh tự được đính kèm vào tin nhắn trên máy tính. Mã QR hết hạn sau khoảng 15 phút.

**Học sinh THPT, bài kiểm tra đã được giáo viên chấm (môn Toán):** chụp rõ cả bài rồi gửi cho Mentor.
Mentor đọc từng câu, giữ nguyên kết quả giáo viên chấm (không chấm lại), cập nhật mức độ thành thạo từng kỹ
năng ở mục **Học tập** và tìm lỗi bạn hay lặp lại. Ảnh mờ hay thiếu trang thì Mentor nhờ bạn chụp lại.

**Các nút khác trong khung chat:**

- **Hôm trước**: xem lại trò chuyện các ngày trước.
- **Bảng phụ**: thông báo của Mentor và **Việc cần duyệt**. Khi Mentor muốn làm gì đó ra bên ngoài (ví dụ
  thêm lịch), Mentor hỏi bạn trước bằng một thẻ có nút **Đồng ý**, **Đồng ý cả phiên** và **Từ chối**.
- Nút **Bật thông báo trên máy** (trong Bảng phụ, nếu có) cho phép trình duyệt hiện thông báo của Mentor.

---

## 8. Trí nhớ của Mentor

Mentor chỉ nhớ những gì được ghi lại, và bạn xem được hết ở mục **Mentor biết gì về tôi**: hồ sơ, việc
hiện tại, sở thích học, người quen, điều gì hiệu quả với bạn.

- Mỗi dòng thường kèm nguồn và ngày (ví dụ "chat 28/10"). Dòng ghi **Suy luận** là điều Mentor tự đoán, không
  phải bạn nói. Đoán sai thì sửa hoặc xoá.
- Tab **Từng mục**: bấm **Quên mục này** để xoá một dòng. **Quên cả tệp** để xoá cả tệp.
- Tab **Sửa**: tự sửa nội dung rồi bấm **Lưu**.
- Tab **Lịch sử**: ai đã thay đổi gì, khi nào.
- Trong chat, bạn cũng có thể nói **"quên chuyện X đi"**. Mentor xoá mọi dòng liên quan đến X và báo lại
  đã xoá ở tệp nào.

Mentor không ghi mật khẩu, số tài khoản, giấy tờ tuỳ thân, chuyện riêng tư của người khác, hay nhận xét về
trí thông minh, tính cách của bạn.

Mục **Hoạt động** liệt kê mọi việc Mentor đã làm, kể cả lúc bạn không trò chuyện.

---

## 9. Mục tiêu, kế hoạch, deadline

- Kể với Mentor điều bạn muốn đạt được, Mentor giúp chia thành kế hoạch học kỳ và kế hoạch tuần. Xem và
  sửa ở mục **Mục tiêu & kế hoạch**.
- Báo deadline cho Mentor trong chat (ngày thi, hạn nộp bài, lịch họp). Mentor nhắc lại ngày và còn bao
  lâu để bạn kiểm tra.
- Mentor có những việc chạy định kỳ: chuẩn bị bài ôn nhanh buổi tối (THPT), tổng kết tuần vào chiều Chủ
  nhật, tìm paper mới mỗi sáng thứ Hai (NCS). Bật, tắt các việc này ở **Cài đặt**.
- **Mức độ chủ động** (Cài đặt): *Tắt* (Mentor chỉ trả lời khi bạn hỏi), *Vừa* (mặc định: tối đa 1 thông
  báo mỗi ngày, luôn báo deadline trong 48 giờ tới), *Nhiều*. **Giờ yên lặng** mặc định từ 22:00 đến 07:00:
  Mentor không gửi thông báo trong khoảng này.
- **Email chuyển tiếp** (Cài đặt, nếu tài khoản của bạn có): chuyển thư từ trường, giáo viên hướng dẫn hay
  ban tổ chức hội nghị tới địa chỉ này, Mentor đọc và ghi deadline. Chỉ chuyển thư liên quan đến việc học.

---

## 10. Dành cho nghiên cứu sinh, sinh viên

- **Tìm paper**: nhờ Mentor tìm paper theo chủ đề (arXiv, Semantic Scholar). Mỗi sáng thứ Hai, Mentor tự
  tìm paper mới theo từ khoá trong ghi chú luận văn và thêm tối đa 5 paper vào **Hàng đợi đọc** ở mục
  **Nghiên cứu**, kèm lý do liên quan. Mentor chỉ gửi từ khoá nghiên cứu ra ngoài, không gửi tên hay thông
  tin của bạn.
- **Đọc paper cùng Mentor**: bạn tóm tắt và nhận xét trước, Mentor góp ý sau. Ghi chú lưu trong mục
  Nghiên cứu.
- **Đọc trang web**: dán link (trang hội nghị, thông báo của khoa...), Mentor đọc trang rồi trả lời, có ghi
  nguồn. Mentor cũng đọc được link tệp PDF (ví dụ bài báo trên arXiv): tệp được lưu vào inbox/web/ để
  Mentor đọc tiếp các trang sau khi cần.
- **Deadline hội nghị**: Mentor đổi giờ AoE và các múi giờ khác sang giờ Việt Nam, nhắc trước 7 ngày và
  trước 48 giờ.
- **Google Calendar**: vào **Cài đặt → Google Calendar → Kết nối Google Calendar** và cho phép quyền xem,
  sửa sự kiện. Mentor xem lịch để lên kế hoạch tuần. Mentor chỉ thêm, sửa, xoá sự kiện sau khi bạn bấm đồng
  ý trong chat, và chỉ sửa, xoá sự kiện do chính Mentor tạo. Ngắt kết nối bất cứ lúc nào trong Cài đặt.
  (Nếu Cài đặt ghi "Máy chủ chưa bật tích hợp Google Calendar" thì tính năng này chưa có trong đợt thử.)
- Một số tính năng tìm kiếm có thể chưa được bật trên máy chủ. Khi đó Mentor sẽ nói thẳng, không bịa kết
  quả.

---

## 11. Quyền riêng tư và an toàn

**Mentor lưu gì về bạn:** những tệp bạn thấy ở mục **Workspace**: trí nhớ (me/), mục tiêu và kế hoạch
(goals/), học tập hoặc nghiên cứu, tài liệu bạn gửi (inbox/), báo cáo đã gửi phụ huynh (THPT), cùng lịch sử
trò chuyện. Ngoài ra là thông tin tài khoản (email, tên hiển thị) và nhật ký ở mục **Hoạt động**.

**Bảo vệ dữ liệu:**

- Kết nối giữa máy bạn và máy chủ được mã hoá (https).
- Bản sao lưu được mã hoá bằng khoá riêng của từng người. Thông tin Zalo của phụ huynh và quyền truy cập
  Google Calendar cũng được mã hoá.
- Nội dung trò chuyện được xử lý bằng mô hình AI, có thể trên máy chủ đặt ngoài Việt Nam.

**Tải dữ liệu về:** mục **Workspace → Tải về (.zip)**.

**Xoá tài khoản:** mục **Workspace → Xoá tài khoản…**, gõ **XOÁ** để xác nhận. Tài khoản, toàn bộ
workspace, lịch sử và các bản sao lưu bị xoá vĩnh viễn; liên kết với phụ huynh bị huỷ; quyền Google Calendar
bị thu hồi. Hệ thống chỉ giữ lại bản ghi tối thiểu về việc phụ huynh đồng ý và các cảnh báo an toàn đã gửi,
vì đây là hồ sơ pháp lý. Nên tải bản zip về trước khi xoá.

Khi bạn bấm "Quên" một dòng trong trí nhớ, Mentor không còn thấy dòng đó nữa; bản cũ chỉ hết hẳn khi bạn
xoá tài khoản.

### Học sinh THPT: cảnh báo an toàn gửi phụ huynh

Mentor là người đồng hành học tập, nhưng sự an toàn của em quan trọng hơn mọi bài học.

Nếu trong lúc trò chuyện có dấu hiệu em đang gặp nguy hiểm nghiêm trọng (có ý định tự làm hại bản thân,
đang bị bạo lực hoặc xâm hại, có ý định làm hại người khác, hay định bỏ nhà đi), Mentor sẽ:

- dừng việc học, lắng nghe em, không phán xét;
- đưa em số **Tổng đài 111** (bảo vệ trẻ em, miễn phí, 24/7). Nguy hiểm ngay thì gọi **113** (công an)
  hoặc **115** (cấp cứu);
- khuyến khích em nói chuyện với một người lớn em tin tưởng.

Khi đó hệ thống cũng **tự động gửi một tin ngắn cho phụ huynh qua Zalo**, kể cả trong giờ yên lặng:

> Hệ thống ghi nhận con cần được hỗ trợ. Phụ huynh vui lòng liên hệ với con, hoặc gọi Tổng đài 111.

Tin này **không kèm nội dung trò chuyện**, không nói em đã kể gì. Mentor cũng không nhắc đến tin này trong
lúc trò chuyện. Đây là điều em đã đồng ý khi đăng ký, để khi em cần, có người thân biết và đến bên em.

Mentor cũng có thể hiểu nhầm, ví dụ một câu nói đùa. Nếu vậy, em cứ nói thật với bố mẹ; điều bố mẹ cần
chỉ là biết chắc em vẫn ổn.

Nghiên cứu sinh, sinh viên không có cảnh báo gửi người thân. Nếu bạn đang gặp khó khăn, hãy liên hệ người
thân, hoặc gọi 115 khi nguy hiểm.

---

## 12. Câu hỏi thường gặp, gặp sự cố

**Không nhận được email đăng nhập?** Xem thư mục Spam, Quảng cáo (Promotions). Đợi 1 đến 2 phút, rồi bấm
**Dùng email khác**, nhập lại email và gửi lại. Mã chỉ dùng được khoảng 15 phút.

**Windows chặn không cho cài?** Xem mục 2: bấm **Thông tin thêm → Vẫn chạy**.

**Không thấy bong bóng?** Tìm biểu tượng **M** cạnh đồng hồ (bấm **^**), bấm chuột phải, tick **Hiện bong
bóng**. Nếu đang chọn "chỉ khi đã đăng nhập", bong bóng chỉ hiện sau khi đăng nhập.

**Ctrl+Alt+M không có tác dụng?** Có thể một phần mềm khác đã dùng tổ hợp phím này. Dùng bong bóng hoặc
biểu tượng ở khay hệ thống.

**Khung chat trắng hoặc báo lỗi?** Kiểm tra mạng, thử mở `https://<DOMAIN>` trong trình duyệt. Nếu
web cũng không vào được, có thể máy chủ đang bảo trì; báo cho nhóm dự án.

**"Mất kết nối" hoặc "Mentor đang thức dậy…"?** Đợi vài giây, Mentor tự kết nối lại.

**Mentor nhớ sai về mình?** Vào **Mentor biết gì về tôi**, sửa hoặc bấm **Quên mục này**.

**Mentor gửi nhiều thông báo quá?** **Cài đặt → Mức độ chủ động**, chọn *Tắt* hoặc *Vừa*, và đặt **Giờ yên
lặng**.

**Mã liên kết phụ huynh hết hạn?** Bấm **Tạo mã mới** và gửi lại mã mới cho phụ huynh.

**Tôi dùng Mac hoặc Linux?** Linux: xem mục 2, "Cài trên Linux". Mac: chưa có app, dùng bản web.

**Linux: Ctrl+Alt+M không chạy, hoặc không thấy biểu tượng M?** Xem mục 2, "Khác với Windows".

**Linux: bong bóng hoặc khung chat trắng, đen hay app tự tắt?** Thường do driver card màn hình. Mở
Terminal, chạy `WEBKIT_DISABLE_COMPOSITING_MODE=1 mentor-desktop` (bản AppImage: thay `mentor-desktop` bằng
đường dẫn tới tệp AppImage). Nếu cách này được, báo cho nhóm dự án.

**Gỡ app máy tính?** **Cài đặt Windows → Ứng dụng → Ứng dụng đã cài đặt → Mentor → Gỡ cài đặt**. Gỡ app
không xoá tài khoản; muốn xoá tài khoản, xem mục 11.

**Cần trợ giúp khác?** Liên hệ nhóm dự án qua kênh bạn nhận được tệp cài đặt.
