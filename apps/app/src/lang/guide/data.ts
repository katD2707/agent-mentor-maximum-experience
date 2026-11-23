/** What the chicken guide says about each part of the screens (texts approved in mockups/ga-guide.js). */
export interface GuideText {
  vi: { t: string; d: string };
  en: { t: string; d: string };
}
export interface GuideDef extends GuideText {
  /** CSS selector of the part */
  sel: string;
  /** only on this screen key */
  page?: string;
}
export const G = (sel: string, vt: string, vd: string, et: string, ed: string, page?: string): GuideDef => ({ sel, page, vi: { t: vt, d: vd }, en: { t: et, d: ed } });

export const GUIDE_DEFS: GuideDef[] = [
  // login
  G(".lg-roles", "Chọn vai trò", "Chạm hình học sinh hoặc giáo viên. Vai trò phải khớp với tài khoản.", "Pick your role", "Tap student or teacher. It must match your account.", "login"),
  G("#lg-f-acc", "Tài khoản", "Nhập tên tài khoản trường hoặc thầy cô đưa cho em.", "Account", "Enter the account your school or teacher gave you.", "login"),
  G("#lg-f-pw", "Mật khẩu", "Nhập mật khẩu. Bấm hình con mắt để xem lại.", "Password", "Enter your password. Tap the eye to check it.", "login"),
  G("#lg-login", "Đăng nhập", "Bấm sau khi đã chọn vai trò và điền đủ.", "Log in", "Press after picking a role and filling both boxes.", "login"),
  // first run
  G(".lg-lang", "Ngôn ngữ", "Chạm để chọn tiếng Việt hoặc tiếng Anh.", "Language", "Tap to choose Vietnamese or English.", "first"),
  G(".lg-pick", "Em là ai", "Chọn bạn sẽ đứng trong làng cùng các chú gà.", "Who are you", "Pick who stands in the village with the chickens.", "first"),
  G("#lg-perches", "Ba ô đậu", "Chọn gà cho các ô, mỗi gà là một môn. Thêm gà sau ở Chợ gà.", "Three perches", "Pick chickens for the perches, one per subject. Add more later at the market.", "first"),
  // the chicken's coop
  G(".ck-stages", "Gà lớn dần", "Học bài, luyện tập, đánh boss đều cho gà kinh nghiệm. Đủ 100 điểm là lên cấp.", "Growing up", "Lessons, practice and boss fights give experience. 100 points make a level.", "chuong"),
  G(".ck-says", "Gà gợi ý", "Việc nên học tiếp của môn này. Bấm nút để vào bài.", "Suggestion", "What to study next in this subject. Press the button to start.", "chuong"),
  G(".ck-courses", "Khóa của gà", "Các khóa em đang học và đã học. Bấm một khóa để mở các bài.", "Courses", "The courses you are on or finished. Tap one to open its lessons.", "chuong"),
  // lessons and practice
  G(".lp-gsp", "Gà đi cùng", "Gà học cùng em suốt bài. Làm xong bài, gà được kinh nghiệm.", "Your study buddy", "Your chicken studies with you all lesson and gets experience when you finish.", "lesson"),
  G("[data-guide=\"practice-answer\"]", "Chọn đáp án", "Làm bài rồi bấm Kiểm tra. Sai thì gà chỉ ra chỗ nhầm ngay.", "Pick an answer", "Answer, then press Check. If it is wrong the chicken shows the slip right away.", "run"),
  G("[data-guide=\"practice-clock\"]", "Đồng hồ", "Đề thi có giờ. Hết giờ máy tự nộp bài.", "Clock", "Exams have a clock. At zero the paper is handed in for you.", "run"),
  G("[data-guide=\"practice-progress\"]", "Số câu đã làm", "Thanh này cho biết em làm tới câu nào.", "Questions done", "This bar shows how far you are.", "run"),
  G("[data-guide=\"practice-hint\"]", "Gợi ý", "Bí thì bấm gợi ý, gà nhắc một ý nhỏ.", "Hint", "Stuck? Tap hint and the chicken gives a small nudge.", "run"),
  // the arena, course tests, study room, progress, library
  G(".ar-filters", "Lọc đề", "Chọn năm hoặc môn để tìm đề hợp với em.", "Filter papers", "Pick a year or subject to find the right paper.", "arena"),
  G(".ar-rows", "Mỗi đề một boss", "Đề thi có tính giờ như ngày thi. Nộp bài xong gà đánh boss: đúng từ nửa số câu là hạ boss.", "One boss per paper", "Papers are timed like exam day. After you submit your chicken fights the boss: half right or more beats it.", "arena"),
  G(".ar-rows", "Bài kiểm tra", "Thi thử cả khóa hoặc làm từng mức. Đáp án hiện sau khi nộp.", "Course tests", "Take a mock of the whole course or one level. Answers show after you submit.", "tests"),
  G(".lg-sr-opts.durs", "Học bao lâu", "Chọn số phút. Mỗi phút gà được 1 điểm, học trọn thêm 5 điểm.", "How long", "Pick the minutes. 1 point a minute, 5 more for a full session.", "study"),
  G("#lg-sr-tp-goiy", "Học gì", "Chọn bài gà gợi ý, hoặc tự học bằng sách vở của em.", "What to study", "Pick the suggested lesson, or study from your own books.", "study"),
  G(".lg-sr-rule", "Cách tính điểm", "Giữ đủ giờ thì gà được thưởng thêm. Học đủ 10 phút là giữ chuỗi ngày.", "How points work", "A full session earns a bonus. 10 minutes keeps your streak.", "study"),
  G(".lg-pg-ga", "Gà của em", "Mỗi gà một ô: tuần này được bao nhiêu kinh nghiệm và còn bao nhiêu nữa thì lên cấp.", "Your chickens", "One box per chicken: this week's points and how many more it needs for the next level.", "progress"),
  G(".lg-pg-goals", "Mục tiêu", "Thanh xanh là phần đã xong. Mentor tự thêm buổi khi em hơi chậm.", "Goals", "The green bar is what is done. Mentor adds sessions when you fall behind.", "progress"),
  G(".lg-pg-week", "Lịch tuần", "Mentor xếp lịch và dời buổi em bỏ lỡ. Ô viền đậm là hôm nay.", "This week", "Mentor plans the week and moves sessions you miss. The outlined box is today.", "progress"),
  G(".lg-pg-rules", "Cách gà lớn", "Mỗi việc học cho gà bao nhiêu điểm kinh nghiệm.", "How chickens grow", "How many points each kind of study gives.", "progress"),
  G(".rs-tabs", "Bốn chương", "Đọc, Lịch, Thí nghiệm và Đề tài.", "Four chapters", "Read, Schedule, Experiments and Topic.", "library"),
  G(".rs-search", "Tìm paper", "Gõ chủ đề, tên bài hoặc tác giả.", "Find papers", "Type a topic, a title or an author.", "library"),
  // the teacher screens (gv-01..gv-04)
  G("[data-guide=\"drop\"]", "Thả tài liệu", "Kéo ảnh chụp sách, PDF, slide hay video vào đây. Gửi xong có thể đóng app, khóa soạn xong sẽ tự hiện.", "Drop your material", "Drag book photos, PDFs, slides or videos here. You can close the app; the course appears when it is ready.", "gv-home"),
  G("[data-guide=\"teacher-courses\"]", "Khóa của bạn", "Nhãn màu cho biết khóa đang được soạn, cần bạn xem hay đã xuất bản.", "Your courses", "The coloured tag shows if a course is being prepared, needs you, or is published.", "gv-home"),
  G("#outline", "Cấu trúc khóa", "Sửa thẳng ở đây: đổi tên, kéo để đổi thứ tự, xóa hoặc thêm bài.", "Course structure", "Edit right here: rename, drag to reorder, delete or add lessons.", "gv-course"),
  G("[data-guide=\"gv-retake\"]", "Trang chưa đọc được", "Ảnh này mờ hoặc tối. Bấm Chụp lại để gửi lại đúng trang đó.", "Unreadable page", "This photo is blurry or dark. Tap Retake to resend that page.", "gv-course"),
  G("[data-guide=\"gv-compose\"]", "Nhắn Mentor", "Gõ điều cần sửa rồi gửi. Mentor làm theo luôn, không hỏi lại.", "Message Mentor", "Type what to change. Mentor just does it.", "gv-course"),
  G("[data-guide=\"gv-go\"]", "Soạn nội dung", "Bấm khi đã ưng cấu trúc. Mentor soạn xong sẽ báo bạn.", "Write the lessons", "Press when the structure looks right. Mentor tells you when it is done.", "gv-course"),
  G(".gv-lab-chicken", "Gà chính", "Mentor đoán sẵn môn. Mỗi khóa nằm trong đúng một gà.", "Main chicken", "Mentor guessed the subject. Each course sits in exactly one chicken.", "gv-labels"),
  G(".gv-lab-topics", "Chủ đề", "Vài từ khóa ngắn, dùng để ghép với câu hỏi trong đề thi.", "Topics", "A few short keywords, used to match exam questions.", "gv-labels"),
  G(".gv-lab-goals", "Mục tiêu khóa", "Mỗi dòng một điều học sinh làm được sau khóa. Học sinh thấy ở đầu khóa.", "Course goals", "One line per thing students can do after the course. They see it at the start.", "gv-labels"),
  G("[data-guide=\"gv-level\"]", "Mức độ", "Mức độ của khóa, để Mentor soạn bài vừa sức học sinh.", "Level", "The course level, so Mentor writes at the right difficulty.", "gv-review"),
  G(".gv-steps", "Các bước", "Mỗi bước là một màn hình học sinh sẽ thấy. Chọn bước để xem và sửa.", "Steps", "Each step is one screen students see. Pick one to view and edit.", "gv-review"),
  G("[data-guide=\"gv-publish\"]", "Xuất bản", "Đưa bản này tới học sinh. Ai đang học bản cũ vẫn giữ tiến độ.", "Publish", "Sends this version to students. Anyone mid-course keeps their progress.", "gv-review"),
  // the village
  G("#lg-say", "Việc hôm nay", "Gà nói trước một việc nên làm bây giờ. Mở khung trò chuyện ở góc dưới để trả lời.", "Today", "Your chicken suggests one thing to do now. Open the chat in the corner to answer.", "village"),
  G(".lg-actor.ga .lg-hit", "Gà của em", "Mỗi chú gà là một môn. Bấm vào gà để vào chuồng xem các khóa.", "Your chickens", "Each chicken is a subject. Tap one to see its courses.", "village"),
  G("#lg-ring", "Tuần này", "Vòng này cho biết em học được mấy buổi trong tuần. Bấm để xem lịch.", "This week", "The ring shows how many sessions you did this week. Tap to see the plan.", "village"),
  G(".lg-place[data-sign=\"arena\"]", "Các nơi trong làng", "Chạm bảng gỗ để đến đó: Đấu trường, Phòng tự học, Chợ gà. Chạm lần nữa nếu em muốn đến nhanh hơn.", "Places", "Tap a wooden sign to go there: Arena, Study room, Chicken market. Tap again to get there faster.", "village"),
  G(".lg-place.lg-market", "Chợ gà", "Nhận thêm gà để học thêm môn, miễn phí.", "Chicken market", "Take more chickens to study more subjects, free.", "village"),
  G("#lg-tray", "Khung trò chuyện", "Nhắn, chụp bài, chụp vở hoặc nói. Gà trả lời ngay tại đây.", "Chat", "Type, snap homework, snap your notes or talk. Your chicken answers right here.", "village"),
  G("[data-settings]", "Cài đặt", "Đổi ngôn ngữ, nền sáng tối, nhắc học. Muốn yên tĩnh thì chọn Tạm im lặng.", "Settings", "Change language, theme and reminders. Pick Quiet for a while to stop them.", "village"),
];

export const HELLO = "hello";
export type TourStepRef = string | typeof HELLO | GuideDef;
/** Parts each screen walks through the first time (3 at most); parts missing or hidden at that moment are skipped. */
export const GUIDE_TOURS: Record<string, TourStepRef[]> = {
  login: [".lg-roles", "#lg-f-acc"],
  first: [".lg-lang", ".lg-pick", "#lg-perches"],
  village: [HELLO, ".lg-actor.ga .lg-hit", '.lg-place[data-sign="arena"]'],
  chuong: [".ck-stages", ".ck-says", ".ck-courses"],
  arena: [".ar-rows", ".ar-filters"],
  tests: [".ar-rows"],
  study: [".lg-sr-opts.durs", "#lg-sr-tp-goiy", ".lg-sr-rule"],
  progress: [".lg-pg-ga", ".lg-pg-week", ".lg-pg-goals"],
  library: [".rs-tabs", ".rs-search"],
  run: ['[data-guide="practice-answer"]', '[data-guide="practice-clock"]'],
  "gv-home": [HELLO, '[data-guide="drop"]', '[data-guide="teacher-courses"]'],
  "gv-course": ["#outline", '[data-guide="gv-retake"]', '[data-guide="gv-go"]'],
  "gv-labels": [".gv-lab-chicken", ".gv-lab-goals", ".gv-lab-topics"],
  "gv-review": [".gv-steps", '[data-guide="gv-level"]', '[data-guide="gv-publish"]'],
};
