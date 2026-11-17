import type { MascotGuides, MascotLang } from "@mentor/mentor-mascot/mascot";

/** What Mực says about each area marked with data-guide="<key>". */
export const GUIDES: MascotGuides = {
  "login-role": {
    vi: "Chạm vào hình học sinh hoặc giáo viên. Tài khoản phải đúng với vai trò em chọn.",
    en: "Tap the student or teacher picture. Your account has to match the role you pick.",
  },
  courses: {
    vi: "Khóa của em: chạm một khóa để học tiếp và luyện tập theo mức. Ô cuối dải để tìm khóa mới.",
    en: "Your courses: tap one to carry on and practise by level. The last tile finds a new course.",
  },
  "course-today": {
    vi: "Bài hôm nay do Mentor xếp sẵn. Chỉ cần nhấn nút lớn để học tiếp đúng chỗ em đang dừng.",
    en: "Today's lesson is planned by Mentor. Just press the big button to continue where you stopped.",
  },
  "my-courses": {
    vi: "Các khóa em đã thêm, kèm tiến độ. Khóa đã tải về máy thì học được cả khi mất mạng.",
    en: "The courses you've added, with progress. Downloaded courses work even without internet.",
  },
  "more-courses": {
    vi: "Các khóa khác hợp với lớp em. Nhấn Xem tất cả để tìm thêm khóa.",
    en: "Other courses for your grade. Press See all to find more.",
  },
  "course-search": {
    vi: "Gõ tên môn hoặc chủ đề, ví dụ “điện trường”, để tìm khóa hợp với lớp của em.",
    en: "Type a subject or topic, like “electric field”, to find courses for your grade.",
  },
  "course-tree": {
    vi: "Chạm một nhóm để gập hoặc mở. Dấu tích là xong.",
    en: "Tap a group to fold or open it. A tick means done.",
  },
  "course-next": {
    vi: "Mentor đưa em tới đúng chỗ nên học bây giờ.",
    en: "Mentor takes you to what to do now.",
  },
  "player-progress": {
    vi: "Thanh này cho biết em học được bao nhiêu của bài. Nút X để dừng, Mentor nhớ chỗ em dừng.",
    en: "This bar shows how much of the lesson you've done. The X stops here; Mentor remembers your place.",
  },
  practice: {
    vi: "Luyện tập nằm trong từng khóa: mở khóa ở dải Khóa của em, xem mục Luyện tập theo mức. Hoặc nhắn Mực “cho em luyện tập”.",
    en: "Practice lives in each course: open one from Your courses and see Practice by level. Or tell Mực “let me practise”.",
  },
  "course-practice": {
    vi: "Mức từ dễ tới khó. Ổ khóa là mức của gói khác.",
    en: "Levels from easy to hard. A lock means another plan.",
  },
  "practice-quick": {
    vi: "Mentor chọn sẵn câu hỏi cho hôm nay. Bấm Bắt đầu là làm.",
    en: "Mentor picked today's questions. Press Start.",
  },
  "practice-resume": {
    vi: "Em còn một bài làm dở. Nhấn Làm tiếp để vào đúng câu em dừng.",
    en: "You have a session left half done. Press Continue to return to the question where you stopped.",
  },
  "practice-mock": {
    vi: "Đề thi thử có đồng hồ. Đáp án hiện sau khi nộp; đề chỉ để luyện.",
    en: "Mock exams have a clock. Answers show after you submit; just for practice.",
  },
  "practice-courses": {
    vi: "Bài kiểm tra của từng khóa, chỉ gồm những bài em đã học tới.",
    en: "Each course's tests, using only the lessons you've reached.",
  },
  "practice-answer": {
    vi: "Bấm vào đáp án em chọn. Sai thì Mentor chỉ ra chỗ nhầm ngay.",
    en: "Tap your answer. If it's wrong, Mentor shows the slip right away.",
  },
  "practice-progress": {
    vi: "Thanh này cho biết em đã làm bao nhiêu câu. Nút X lưu bài lại, em quay lại làm tiếp được.",
    en: "This bar shows how many questions you've done. The X saves your place so you can come back.",
  },
  "practice-hint": {
    vi: "Cần gợi ý thì nhấn đây. Mỗi câu có một gợi ý, và câu có dùng gợi ý được Mentor ghi nhận riêng.",
    en: "Press here for a hint. Each question has one, and Mentor notes when you used it.",
  },
  "practice-feedback": {
    vi: "Sau mỗi câu: đáp án đúng màu xanh và một câu nói rõ chỗ em nhầm. Xong nhấn Câu tiếp.",
    en: "After each question: the right answer in green and one sentence on where it slipped. Then press Next.",
  },
  "practice-clock": {
    vi: "Đồng hồ của bài thi thử, tính theo máy chủ. Hết giờ bài tự nộp.",
    en: "The mock exam clock, kept by the server. When it reaches zero the exam is handed in for you.",
  },
  "practice-flag": {
    vi: "Đánh dấu câu em chưa chắc để quay lại sau. Bảng Tất cả câu cho thấy câu nào đã làm, câu nào đánh dấu.",
    en: "Flag a question you're unsure about to return to it. The All questions grid shows what's answered or flagged.",
  },
  "practice-result": {
    vi: "Điểm của lần luyện này. Câu sai sẽ được làm lại vào buổi sau.",
    en: "Your score. Missed questions come back next session.",
  },
  "practice-review": {
    vi: "Xem lại từng câu: em chọn gì, đáp án đúng và lời giải.",
    en: "Go through each question: what you chose, the right answer and the solution.",
  },
  ask: {
    vi: "Trò chuyện với Mực: Mực gợi ý việc nên làm. Ở ô bên dưới em chụp bài, gõ hoặc nói để hỏi bài, tìm khóa, xin luyện tập hay thêm mục tiêu.",
    en: "Talking with Mực: Mực suggests what to do. In the box below, snap, type or talk to ask about homework, find a course, practise or add a goal.",
  },
  "ask-composer": {
    vi: "Gõ câu hỏi vào ô, hoặc nhấn máy ảnh để chụp bài, nút ảnh để chọn ảnh có sẵn, micro để nói. Nhấn nút tím để gửi.",
    en: "Type your question here, or press the camera to snap an exercise, the picture button to pick a photo, the microphone to talk. Press the purple button to send.",
  },
  "ask-camera": {
    vi: "Đưa một bài vào trong khung, giữ máy thật yên rồi nhấn nút tròn để chụp. Cũng chọn được ảnh có sẵn.",
    en: "Fit one exercise inside the frame, hold steady and press the round button. You can also pick a photo you already have.",
  },
  "ask-courses": {
    vi: "Các khóa Mentor gợi ý. Nhấn tên khóa để xem cây nội dung, nhấn Thêm để đưa khóa vào lịch học và tải về máy.",
    en: "Courses Mentor suggests. Tap a title to see its contents, tap Add to put it in your plan and download it.",
  },
  "ask-choices": {
    vi: "Ảnh có nhiều bài. Chọn bài em muốn giải, Mentor sẽ giải từng bước.",
    en: "The photo has several exercises. Pick the one you want and Mentor solves it step by step.",
  },
  "ask-solution": {
    vi: "Lời giải từng bước. Mentor để dành bước cuối cho em tự thử, rồi nhấn Xem bước cuối để kiểm tra.",
    en: "A step-by-step solution. Mentor keeps the last step for you to try, then press Show last step to check.",
  },
  progress: {
    vi: "Vòng này cho biết tuần này em học được bao nhiêu buổi. Chạm để xem lịch tuần và mục tiêu.",
    en: "This ring shows how many sessions you have done this week. Tap it for the week and your goals.",
  },
  "progress-goals": {
    vi: "Thanh tím là phần đã xong. Nhãn bên phải cho biết em đang đúng nhịp hay hơi chậm, Mentor tự thêm buổi khi cần.",
    en: "The purple bar is what is done. The tag says if you are on track; Mentor adds sessions when needed.",
  },
  "progress-week": {
    vi: "Mentor tự xếp và tự dời lịch khi em bỏ buổi. Ô viền tím là hôm nay. Chạm một ô để vào học luôn.",
    en: "Mentor plans the week and moves sessions you miss. The purple box is today. Tap a box to start.",
  },
  "progress-courses": {
    vi: "Từng khóa em học và đã được bao nhiêu phần trăm. Chạm tên khóa để mở.",
    en: "Each course you study and how far you are. Tap a name to open it.",
  },
  research: {
    vi: "Nghiên cứu: đề tài của bạn, việc sắp tới, paper cần đọc và nhật ký thí nghiệm. Mentor tìm paper mới mỗi thứ Hai.",
    en: "Research: your topic, what is coming up, the papers to read and your experiment log. Mentor looks for new papers every Monday.",
  },
  "research-tabs": {
    vi: "Bốn chương: Đọc, Lịch, Thí nghiệm và Đề tài. Chấm tím là có paper mới, chấm cam là sắp tới hạn nộp.",
    en: "Four chapters: Read, Schedule, Experiments and Topic. A purple dot means new papers, an orange one a deadline coming up.",
  },
  "research-hero": {
    vi: "Paper bạn nên đọc tiếp và lý do Mentor chọn. Nhấn Đọc tiếp để mở paper.",
    en: "The paper to read next and why Mentor picked it. Press Keep reading to open it.",
  },
  "research-topic": {
    vi: "Đề tài và các từ khóa Mentor dùng để tìm paper. Bỏ từ khóa không hợp, hoặc nhấn Sửa để đổi đề tài.",
    en: "Your topic and the keywords Mentor searches with. Remove one that does not fit, or press Edit to change the topic.",
  },
  "research-search": {
    vi: "Tìm paper theo chủ đề, tên bài hoặc tác giả. Mặc định lấy từ arXiv; thêm Semantic Scholar hoặc Asta bằng key của bạn để có thêm số trích dẫn và đoạn trích.",
    en: "Search papers by topic, title or author. It uses arXiv by default; add Semantic Scholar or Asta with your own key for citation counts and snippets.",
  },
  "research-upcoming": {
    vi: "Họp với giáo viên hướng dẫn và các hạn nộp. Thêm một hạn bằng một dòng, ví dụ nộp bài 16/11, 23:59 AoE; Mentor đổi sang giờ Việt Nam.",
    en: "Advisor meetings and deadlines. Add one in a line, like submit 16/11, 23:59 AoE; Mentor converts it to Vietnam time.",
  },
  "research-agenda": {
    vi: "Khung agenda Mentor soạn từ nhật ký và buổi họp trước. Bạn điền kết quả mới và câu hỏi mở; sau buổi họp ghi vài dòng để Mentor tách việc cần làm.",
    en: "The agenda Mentor drafted from your log and the last meeting. Fill in new results and open questions; after the meeting jot a few lines and Mentor splits out the to-dos.",
  },
  "research-reading": {
    vi: "Paper cần đọc, tối đa 5 bài đang đọc. Đánh dấu đã đọc để có chỗ cho bài mới, hoặc nhận gợi ý của Mentor.",
    en: "Papers to read, at most 5 at a time. Mark one read to free a slot, or take one of Mentor's suggestions.",
  },
  "research-milestones": {
    vi: "Các mốc luận văn theo thời gian. Mốc tiếp theo được tô đậm.",
    en: "Your thesis milestones in time order. The next one is highlighted.",
  },
  "research-log": {
    vi: "Ghi nhanh thí nghiệm vừa chạy, kèm ảnh bảng kết quả nếu có. Mentor chép lại số liệu, không nhận xét kết quả thay bạn.",
    en: "Jot down the experiment you just ran, with a photo of the result table if you like. Mentor restates the numbers and does not judge the result for you.",
  },
  "research-paper": {
    vi: "Một paper: tự tóm tắt trước, rồi Mentor góp ý. Bên dưới là hỏi về paper và các bài liên quan.",
    en: "One paper: write your own summary first, then Mentor gives feedback. Below are questions about the paper and related papers.",
  },
  "research-summary": {
    vi: "Viết tóm tắt bằng lời của bạn, ít nhất 20 ký tự. Mentor chỉ góp ý sau khi bạn viết.",
    en: "Write a summary in your own words, at least 20 characters. Mentor only gives feedback after you write.",
  },
  "research-ask": {
    vi: "Hỏi về paper này. Câu trả lời kèm đoạn trích dẫn; nếu không thấy đoạn nào, Mentor nói thẳng là không tìm thấy.",
    en: "Ask about this paper. Answers come with quoted passages; if nothing is found, Mentor says so plainly.",
  },
  "research-related": {
    vi: "Các bài trích dẫn paper này và các bài paper này trích dẫn. Cần key Semantic Scholar hoặc Asta.",
    en: "Papers that cite this one and papers it cites. Needs a Semantic Scholar or Asta key.",
  },
  "research-sources": {
    vi: "Nguồn tìm paper: arXiv luôn bật; thêm Semantic Scholar hoặc Asta bằng key của riêng bạn, gỡ bất cứ lúc nào.",
    en: "Paper sources: arXiv is always on; add Semantic Scholar or Asta with your own key and remove it any time.",
  },
  settings: {
    vi: "Cài đặt: đổi lớp, ngôn ngữ, giao diện, và tạm tắt nhắc học khi em cần yên tĩnh.",
    en: "Settings: change grade, language, theme, and pause reminders when you need quiet.",
  },
  back: {
    vi: "Nút này đưa em về màn Hôm nay, nơi Mực gợi ý việc nên làm.",
    en: "This takes you back to Today, where Mực suggests what to do.",
  },
  drop: {
    vi: "Kéo ảnh chụp sách, PDF, slide hay video vào đây. Gửi xong có thể đóng app, khóa soạn xong sẽ tự hiện.",
    en: "Drag book photos, PDFs, slides or videos here. You can close the app; the course appears when it's ready.",
  },
  "teacher-courses": {
    vi: "Nhãn màu cho biết khóa đang được soạn, cần bạn xem hay đã xuất bản.",
    en: "The coloured tag shows if a course is being prepared, needs you, or is published.",
  },
  "gv-back": {
    vi: "Nút nhỏ này đưa bạn về màn gửi bài giảng và danh sách khóa học.",
    en: "This small button takes you back to the send-lesson screen and your course list.",
  },
  "gv-note": {
    vi: "Ghi chú không bắt buộc, ví dụ lớp nào, trình độ ra sao. Gõ trước khi thả tệp để Mentor soạn cho đúng đối tượng.",
    en: "An optional note, like which class and what level. Type it before dropping files so Mentor writes for the right students.",
  },
  "gv-sending": {
    vi: "Tiến độ tải tệp lên. Khi đủ rồi bạn đóng app được, Mentor đọc tiếp ở phía máy chủ.",
    en: "Upload progress. Once it's complete you can close the app; Mentor keeps reading on the server.",
  },
  "gv-outline": {
    vi: "Sửa thẳng ở đây: đổi tên, kéo để đổi thứ tự, xóa hoặc thêm bài.",
    en: "Edit right here: rename, drag to reorder, delete or add lessons.",
  },
  "gv-retake": {
    vi: "Ảnh này mờ hoặc tối. Bấm Chụp lại để gửi lại đúng trang đó.",
    en: "This photo is blurry or dark. Tap Retake to resend that page.",
  },
  "gv-level": {
    vi: "Mức độ của khóa, để Mentor soạn bài vừa sức học sinh. Cần xác nhận mức độ trước khi xuất bản.",
    en: "The course level, so Mentor writes at the right difficulty. Confirm it before you publish.",
  },
  "gv-compose": {
    vi: "Gõ điều cần sửa rồi gửi. Mentor làm theo luôn, không hỏi lại.",
    en: "Type what to change. Mentor just does it.",
  },
  "gv-go": {
    vi: "Bấm khi đã ưng cấu trúc. Mentor soạn xong sẽ báo bạn.",
    en: "Press when the structure looks right. Mentor tells you when it's done.",
  },
  "gv-review": {
    vi: "Bôi đen câu chưa ưng rồi bấm Nhận xét. Mentor sửa luôn.",
    en: "Select a sentence you don't like and comment. Mentor fixes it.",
  },
  "gv-text-comment": {
    vi: "Bôi đen một đoạn chữ rồi bấm Nhận xét. Mentor sẽ sửa đúng đoạn đó.",
    en: "Highlight some text, then press Comment. Mentor fixes exactly that part.",
  },
  "gv-video-comment": {
    vi: "Tua tới đoạn cần sửa rồi bấm Nhận xét tại giây đó.",
    en: "Scrub to the part to fix, then comment at that second.",
  },
  "gv-image-pin": {
    vi: "Bấm vào chỗ chưa đúng trên hình để cắm ghim và ghi nhận xét.",
    en: "Click the wrong spot on the figure to pin a comment.",
  },
  "gv-comment-box": {
    vi: "Viết bạn muốn sửa thế nào rồi bấm Gửi. Mentor sửa luôn, không hỏi lại.",
    en: "Write what should change and press Send. Mentor fixes it straight away, no questions back.",
  },
  "gv-comments": {
    vi: "Mentor sửa theo từng nhận xét. Xong thì nhãn đổi thành Đã sửa.",
    en: "Mentor fixes each one; the tag turns to Fixed.",
  },
  "gv-publish": {
    vi: "Đưa bản này tới học sinh. Ai đang học bản cũ vẫn giữ tiến độ.",
    en: "Sends this version to students. Anyone mid-course keeps their progress.",
  },
};

const strip = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d");

const KEYWORDS: Record<string, string[]> = {
  "login-role": ["dang nhap", "vai tro", "login", "role", "sign in"],
  courses: ["khoa hoc", "bai hoc", "tim khoa", "course", "lesson", "search"],
  "course-today": ["hom nay", "hoc tiep", "bai hom nay", "today", "continue", "tonight"],
  "my-courses": ["khoa cua em", "tai ve", "offline", "mat mang", "my courses", "download", "progress", "sao"],
  "more-courses": ["khoa khac", "xem tat ca", "other courses", "see all"],
  "course-search": ["tim", "tim kiem", "moi lua tuoi", "search", "find", "all ages"],
  "course-tree": ["cay", "bai hoc", "noi dung", "tick", "tree", "lessons", "outline"],
  "course-next": ["tiep tuc", "bat dau", "hoc tiep", "continue", "start"],
  "player-progress": ["thanh tien do", "dong", "dung lai", "tiep tuc", "luu", "close", "resume", "save", "bar"],
  practice: ["luyen", "thi thu", "bai tap", "practice", "exam", "quiz"],
  "course-practice": ["muc", "nhan biet", "thong hieu", "van dung", "o khoa", "goi", "level", "lock", "plan"],
  "practice-quick": ["bat dau", "bo cau hoi", "10 cau", "quick", "start", "questions"],
  "practice-resume": ["lam tiep", "dang do", "continue", "resume", "unfinished"],
  "practice-mock": ["thi thu", "thi thu o dau", "de thi", "mock", "exam", "paper"],
  "practice-courses": ["theo khoa", "tung khoa", "by course", "per course"],
  "practice-progress": ["bao nhieu cau", "luu", "thoat", "how many", "save", "exit"],
  "practice-hint": ["goi y", "hint", "help"],
  "practice-answer": ["dap an", "chon", "answer", "pick", "choose"],
  "practice-feedback": ["dap an", "sai", "giai thich", "answer", "wrong", "explanation"],
  "practice-clock": ["dong ho", "het gio", "thoi gian", "clock", "timer", "time"],
  "practice-flag": ["danh dau", "cau chua chac", "flag", "mark", "grid"],
  "practice-result": ["ket qua", "diem", "lam lai", "result", "score", "redo"],
  "practice-review": ["xem lai", "review", "check answers"],
  ask: ["hoi", "chup", "anh", "noi", "giai", "ask", "photo", "solve", "voice"],
  "ask-composer": ["gui", "go", "chup", "micro", "camera", "send", "type", "talk", "photo", "library"],
  "ask-camera": ["khung", "chup", "giu yen", "frame", "hold", "shutter", "camera"],
  "ask-courses": ["them", "goi y", "khoa", "add", "suggest", "course", "tree"],
  "ask-choices": ["nhieu bai", "chon bai", "several", "which", "choose"],
  "ask-solution": ["buoc cuoi", "tung buoc", "loi giai", "last step", "step", "solution", "tip", "similar", "tuong tu"],
  progress: ["tien do", "muc tieu", "lich", "progress", "goal", "plan", "schedule"],
  "progress-goals": ["muc tieu", "them muc tieu", "han", "deadline", "goal", "add goal"],
  "progress-week": ["lich hoc", "tuan nay", "buoi hoc", "ly do", "week", "schedule", "session", "reason"],
  "progress-courses": ["vung", "can de y", "diem manh", "strong", "weak", "watch", "course progress"],
  research: ["nghien cuu", "de tai", "luan van", "paper", "research", "thesis", "topic"],
  "research-tabs": ["chuong", "tab", "lich", "thi nghiem", "chapter", "schedule", "experiments"],
  "research-hero": ["doc tiep", "paper nen doc", "keep reading", "next paper"],
  "research-topic": ["tu khoa", "de tai", "keyword", "topic"],
  "research-search": ["tim paper", "arxiv", "semantic scholar", "asta", "search paper", "key"],
  "research-upcoming": ["han nop", "hop", "deadline", "meeting", "advisor", "gvhd", "aoe"],
  "research-agenda": ["agenda", "ghi chu", "buoi hop", "notes"],
  "research-reading": ["can doc", "da doc", "goi y", "reading list", "mark read", "suggestion"],
  "research-milestones": ["moc", "milestone", "timeline"],
  "research-log": ["nhat ky", "thi nghiem", "experiment", "log", "commit", "seed"],
  "research-paper": ["doc paper", "paper", "bai bao"],
  "research-summary": ["tom tat", "summary", "gop y", "feedback"],
  "research-ask": ["hoi ve paper", "trich dan", "ask paper", "cited", "passage"],
  "research-related": ["lien quan", "trich dan", "related", "cites", "references"],
  "research-sources": ["nguon", "go key", "source", "remove key"],
  settings: ["cai dat", "nhac", "im lang", "ngon ngu", "lop", "settings", "reminder", "quiet", "language", "grade", "theme", "toi"],
  back: ["quay lai", "ve", "back", "home"],
  drop: ["gui", "tai len", "tha", "upload", "send", "drop", "file"],
  "teacher-courses": ["xuat ban", "duyet", "publish", "review"],
  "gv-back": ["quay lai", "ve", "back"],
  "gv-note": ["ghi chu", "lop", "note", "class"],
  "gv-sending": ["tai len", "tien do gui", "dong app", "upload", "sending"],
  "gv-outline": ["sua ten", "doi thu tu", "keo", "xoa bai", "them bai", "rename", "reorder", "drag", "delete", "add lesson"],
  "gv-retake": ["chup lai", "trang loi", "khong doc duoc", "retake", "unreadable", "blurry"],
  "gv-level": ["muc do", "trinh do", "level", "difficulty"],
  "gv-compose": ["soan", "nhan thay doi", "gop bai", "compose", "merge", "change"],
  "gv-go": ["soan", "soan bai", "soan noi dung", "compose", "write lessons"],
  "gv-review": ["xem lai", "duyet noi dung", "nhan xet", "review", "comment"],
  "gv-text-comment": ["boi den", "chon chu", "nhan xet chu", "highlight", "select text"],
  "gv-video-comment": ["nhan xet video", "dung video", "giay", "pause", "timestamp"],
  "gv-image-pin": ["ghim", "nhan xet hinh", "cham vao hinh", "pin", "picture", "image"],
  "gv-comment-box": ["gui nhan xet", "viet nhan xet", "send comment"],
  "gv-comments": ["but do", "dang sua", "da sua", "red pen", "fixing", "fixed"],
  "gv-publish": ["xuat ban", "ban moi", "ban 2", "publish", "version"],
};

/**
 * Answers "how do I…" questions from the guide map, preferring areas on the current screen.
 * Replaced by a light-model endpoint in P5; the local version keeps Mực useful offline.
 */
export async function askGuide(question: string, lang: MascotLang): Promise<string> {
  const q = strip(question);
  const visible = new Set(Array.from(document.querySelectorAll<HTMLElement>("[data-guide]"), (el) => el.dataset.guide ?? ""));
  let best: string | null = null;
  let score = 0;
  for (const [key, words] of Object.entries(KEYWORDS)) {
    const s = words.filter((w) => q.includes(w)).length * (visible.has(key) ? 2 : 1);
    if (s > score) {
      best = key;
      score = s;
    }
  }
  if (best) return GUIDES[best][lang];
  return lang === "vi"
    ? "Em thử nhấn giữ rồi kéo mình tới chỗ em muốn hỏi, mình sẽ giải thích ngay chỗ đó."
    : "Press and hold me, then drag me onto the part you're curious about and I'll explain it.";
}
