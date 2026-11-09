// Mực: original guide character (a purple ink droplet). Click for help, hold and drag onto anything to get it explained.
(function () {
  "use strict";
  const root = document.documentElement;
  const RM = window.matchMedia("(prefers-reduced-motion: reduce)");
  const isEn = () => root.lang === "en";
  const tr = (vi, en) => (isEn() ? en : vi);
  const PAGE = (location.pathname.split("/").pop() || "index").replace(/\.html?$/, "");
  const store = {
    get(k) { try { return localStorage.getItem("mentor-mascot-" + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem("mentor-mascot-" + k, v); } catch (e) {} },
  };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  // never hang on an animation: settle by timer too, then drop any leftover effect
  const settle = async (anim, ms) => { await Promise.race([anim.finished.catch(() => {}), wait(ms)]); try { anim.cancel(); } catch (e) {} };

  // ---------------------------------------------------------------- guides
  // page: only used on pages whose file name contains this text. Order matters for ties and quick picks.
  const G = (sel, vt, vd, et, ed, page) => ({ sel, page, vi: { t: vt, d: vd }, en: { t: et, d: ed } });
  const GUIDES = [
    // hub
    G('a.tile[href*="khoa-hoc"]', "Khóa học", "Các khóa em đang học và việc Mentor xếp cho hôm nay. Bấm vào để học tiếp.", "Courses", "The courses you're taking and what Mentor planned for today. Tap to carry on."),
    G('a.tile[href*="luyen-tap"]', "Luyện tập", "Mentor chọn sẵn câu hỏi từ bài em đang học và những câu em hay sai. Có cả thi thử.", "Practice", "Questions picked from what you're learning and what you often miss. Mock exams live here too."),
    G('a.tile[href*="hoi-bai"]', "Hỏi đáp", "Chụp bài tập, gõ hoặc nói câu hỏi. Muốn học gì cũng hỏi được, Mentor sẽ gợi ý khóa hợp với em.", "Ask", "Snap an exercise, type or talk. Ask what to learn and Mentor suggests courses."),
    G('a.tile[href*="tien-bo"]', "Tiến độ", "Xem các mục tiêu, lịch tuần Mentor xếp và em đã đi được bao xa.", "Progress", "Your goals, the weekly plan Mentor made and how far you've come."),
    // courses
    G(".today", "Việc hôm nay", "Mentor xếp sẵn theo giờ em hay học và bài em đang dở. Chỉ cần bấm nút là học.", "Today", "Mentor plans this from when you usually study and what you left unfinished. Just press the button.", "hs-02b"),
    G(".kid-tile", "Khóa của em", "Chạm vào hình để học. Càng nhiều sao là em càng giỏi.", "Your courses", "Tap a picture to learn. More stars means you're doing great."),
    G(".course", "Khóa em đang học", "Thanh tím cho biết em đã xong bao nhiêu. Bấm vào để học tiếp.", "Your course", "The purple bar shows how much you've done. Tap to continue."),
    G(".search", "Tìm khóa học", "Gõ tên môn hoặc chủ đề, ví dụ “điện trường”, để tìm khóa hợp với lớp của em.", "Find courses", "Type a subject or topic, like “electric field”, to find courses for your grade."),
    G(".res", "Kết quả tìm", "Bấm Xem để đọc giới thiệu khóa trước khi học.", "Search result", "Tap View to read about the course first."),
    G(".side", "Bắt đầu khóa", "Bấm Bắt đầu học, Mentor sẽ tự xếp khóa này vào lịch của em.", "Start the course", "Press Start and Mentor fits this course into your plan."),
    G(".lessons", "Các bài trong khóa", "Biểu tượng cho biết bài có video, bài đọc hay câu hỏi.", "Lessons", "Icons show whether a lesson has video, reading or questions."),
    // ask
    G("#micBtn", "Nói thay vì gõ", "Bấm micro rồi nói, chữ sẽ hiện ra trong ô. Bấm Xong khi nói hết.", "Talk instead of typing", "Tap the mic and speak; your words appear in the box. Tap Done when you finish."),
    G("[data-cam]", "Chụp bài", "Chụp một bài tập thật rõ, Mentor đọc đề rồi giải từng bước.", "Snap an exercise", "Take a clear photo of one exercise; Mentor reads it and solves it step by step."),
    G("[data-pick]", "Ảnh có sẵn", "Chọn ảnh bài tập em đã chụp từ trước.", "From photos", "Pick a photo of an exercise you took earlier."),
    G("#sendBtn", "Gửi", "Gửi câu hỏi cho Mentor.", "Send", "Sends your question to Mentor."),
    G("#composer", "Ô hỏi Mentor", "Gõ câu hỏi rồi bấm nút tím để gửi. Hỏi bài hay hỏi nên học gì đều được.", "Ask Mentor", "Type a question and press the purple button. Ask about homework or what to learn.", "hs-08"),
    G(".sug", "Khóa gợi ý", "Bấm vào để xem khóa có những bài gì. Bấm Thêm để đưa khóa vào danh sách học của em.", "Suggested course", "Tap to see what's inside. Tap Add to put it in your courses."),
    G("#sheet", "Nội dung khóa", "Cây này cho thấy khóa có những chương, bài nào. Bấm mũi tên để mở từng bài.", "Course outline", "This tree shows the chapters and lessons. Tap an arrow to open one."),
    G(".starter", "Gợi ý câu hỏi", "Chưa biết hỏi gì thì bấm một gợi ý để bắt đầu.", "Starter", "Not sure what to ask? Tap one to begin."),
    G(".steps", "Lời giải từng bước", "Đọc lần lượt từng bước. Bước cuối để em tự làm trước, cần thì bấm Xem bước cuối.", "Step by step", "Read one step at a time. Try the last step yourself first."),
    G(".viewfinder", "Khung chụp", "Đưa một bài vào trong khung rồi bấm nút tròn để chụp.", "Camera frame", "Fit one exercise in the frame and press the round button."),
    // progress
    G("#addBtn", "Thêm mục tiêu", "Viết điều em muốn đạt, chọn hạn nếu có. Mentor sẽ tự xếp lịch cho mục tiêu đó.", "Add a goal", "Write what you want to reach and pick a deadline if you like. Mentor plans for it."),
    G("#mpBtn", "Chọn hạn", "Chọn tháng em muốn đạt mục tiêu. Không chọn cũng được.", "Deadline", "Pick the month you want to reach it by. It's optional."),
    G(".goal .chip, .goal .for", "Khóa của mục tiêu", "Đây là các khóa giúp em đạt mục tiêu này. Bấm để học.", "Courses for this goal", "These courses get you to this goal. Tap one to study."),
    G(".goal", "Mục tiêu", "Thanh tím là phần đã xong. Nhãn bên phải cho biết em đang đúng nhịp hay hơi chậm, Mentor tự thêm buổi khi cần.", "Goal", "The purple bar is what's done. The tag says if you're on track; Mentor adds sessions when needed."),
    G(".week", "Lịch tuần", "Mentor tự xếp và tự dời lịch khi em bỏ buổi. Ô viền tím là hôm nay.", "This week", "Mentor plans the week and moves sessions you miss. The purple box is today."),
    // practice
    G(".quick", "Luyện nhanh", "Mentor chọn sẵn câu hỏi cho hôm nay. Bấm Bắt đầu là làm.", "Quick practice", "Mentor picked today's questions. Press Start."),
    G(".opt", "Chọn đáp án", "Bấm vào đáp án em chọn. Sai thì Mentor chỉ ra chỗ nhầm ngay.", "Pick an answer", "Tap your answer. If it's wrong, Mentor shows the slip right away."),
    G(".feedback, #fb", "Vì sao sai", "Đọc chỗ nhầm để lần sau không mắc lại.", "Why it's wrong", "Read the slip so it doesn't happen again."),
    G(".result", "Kết quả", "Điểm của lần luyện này. Câu sai sẽ được làm lại vào buổi sau.", "Result", "Your score. Missed questions come back next session."),
    // lessons
    G("#baskets", "Chọn giỏ", "Chạm vào giỏ có đúng số quả. Bấm loa để nghe lại câu hỏi.", "Pick a basket", "Tap the basket with the right number. Tap the speaker to hear it again."),
    G(".speak", "Nút loa", "Chạm để nghe đọc to.", "Speaker", "Tap to hear it read aloud."),
    G("#video, .video, #poster, .poster", "Video bài học", "Bấm nút phát để xem. Video ngắn và có phụ đề.", "Lesson video", "Press play. Videos are short and captioned.", "hs-0"),
    G(".read, .prose", "Bài đọc", "Phần chữ ngắn gọn, có công thức và ví dụ. Đọc xong thì làm câu hỏi.", "Reading", "Short text with formulas and examples. Then answer the questions."),
    G("#plot", "Đồ thị", "Đồ thị cho thấy niềm tin thay đổi thế nào sau khi có dữ liệu.", "Plot", "How belief changes once data comes in."),
    G("#quiz", "Câu hỏi", "Trả lời để xem em hiểu bài chưa. Sai thì có giải thích ngay.", "Questions", "Check you understood. Wrong answers get an explanation."),
    G(".outline, .toc", "Mục lục", "Các bài trong khóa. Dấu tích là bài em đã học xong.", "Contents", "Lessons in the course. Ticks mark the ones you've finished.", "hs-0"),
    // login + first run
    G(".role", "Chọn vai trò", "Chạm hình học sinh hoặc giáo viên. Vai trò phải khớp với tài khoản.", "Pick your role", "Tap student or teacher. It must match your account.", "hs-00"),
    G("#accPill, #acc", "Tài khoản", "Nhập tên tài khoản trường hoặc thầy cô đưa cho em.", "Account", "Enter the account your school or teacher gave you."),
    G("#pwPill, #pw", "Mật khẩu", "Nhập mật khẩu. Bấm hình con mắt để xem lại.", "Password", "Enter your password. Tap the eye to check it."),
    G("#login", "Đăng nhập", "Bấm sau khi đã chọn vai trò và điền đủ.", "Log in", "Press after picking a role and filling both boxes."),
    G(".age", "Chọn lớp", "Chạm vào hình giống em nhất. Mentor sẽ chỉnh chữ, hình và bài cho hợp.", "Your grade", "Tap the picture closest to you. Mentor adjusts text, pictures and lessons."),
    G(".lang", "Ngôn ngữ", "Chạm để chọn tiếng Việt hoặc tiếng Anh.", "Language", "Tap to choose Vietnamese or English."),
    // teacher
    G("#drop", "Thả tài liệu", "Kéo ảnh chụp sách, PDF, slide hay video vào đây. Gửi xong có thể đóng app, khóa soạn xong sẽ tự hiện.", "Drop your material", "Drag book photos, PDFs, slides or videos here. You can close the app; the course appears when it's ready."),
    G(".list .row", "Khóa của bạn", "Nhãn màu cho biết khóa đang được soạn, cần bạn xem hay đã xuất bản.", "Your courses", "The coloured tag shows if a course is being prepared, needs you, or is published.", "gv-01"),
    G(".bad", "Trang chưa đọc được", "Ảnh này mờ hoặc tối. Bấm Chụp lại để gửi lại đúng trang đó.", "Unreadable page", "This photo is blurry or dark. Tap Retake to resend that page."),
    G("#outline", "Cấu trúc khóa", "Sửa thẳng ở đây: đổi tên, kéo để đổi thứ tự, xóa hoặc thêm bài.", "Course structure", "Edit right here: rename, drag to reorder, delete or add lessons."),
    G("#go", "Soạn nội dung", "Bấm khi đã ưng cấu trúc. Mentor soạn xong sẽ báo bạn.", "Write the lessons", "Press when the structure looks right. Mentor tells you when it's done."),
    G("#composer", "Nhắn Mentor", "Gõ điều cần sửa rồi gửi. Mentor làm theo luôn, không hỏi lại.", "Message Mentor", "Type what to change. Mentor just does it.", "gv-02"),
    G(".vbar, #vcmt", "Nhận xét video", "Tua tới đoạn cần sửa rồi bấm Nhận xét tại giây đó.", "Comment on the video", "Scrub to the part to fix, then comment at that second.", "gv-03"),
    G("#figimg", "Nhận xét hình", "Bấm vào chỗ chưa đúng trên hình để cắm ghim và ghi nhận xét.", "Comment on a figure", "Click the wrong spot on the figure to pin a comment."),
    G(".panel", "Nhận xét của bạn", "Mentor sửa theo từng nhận xét. Xong thì nhãn đổi thành Đã sửa.", "Your comments", "Mentor fixes each one; the tag turns to Fixed.", "gv-03"),
    G("#pub, #pub2", "Xuất bản", "Đưa bản này tới học sinh. Ai đang học bản cũ vẫn giữ tiến độ.", "Publish", "Sends this version to students. Anyone mid-course keeps their progress."),
    G(".version", "Phiên bản", "Học sinh đang học bản cũ vẫn học tiếp bản cũ. Bản sửa chỉ đến học sinh mới.", "Versions", "Students on the old version keep it; edits go to new students."),
    G("#paper, .lesson-body", "Nội dung bài", "Bôi đen câu chưa ưng rồi bấm Nhận xét. Mentor sửa luôn.", "Lesson text", "Select a sentence you don't like and comment. Mentor fixes it.", "gv-03"),
    // everywhere
    G("[data-settings]", "Cài đặt", "Đổi lớp, ngôn ngữ, nền sáng tối. Muốn yên tĩnh thì chọn Tạm im lặng, Mentor sẽ không nhắc trong lúc đó.", "Settings", "Change grade, language and theme. Pick Quiet for a while and Mentor won't remind you."),
  ];
  const pageGuides = () => GUIDES.filter((g) => !g.page || PAGE.indexOf(g.page) === 0);

  // ---------------------------------------------------------------- first visit of a page
  // The first time someone opens a page, Mực walks them through its main parts once (3 at most), then leaves them be.
  // A step is the `sel` of a GUIDES entry or its own G(); parts missing or hidden right now are skipped.
  const adult = () => root.dataset.age === "dai-hoc" || PAGE.indexOf("gv-") === 0;
  const HELLO = "hello";
  const hello = () => adult()
    ? { vi: { t: "Chào bạn, mình là Mực!", d: "Lần đầu bạn mở một trang, mình sẽ chỉ nhanh vài chỗ chính. Sau đó cần gì cứ bấm vào mình." }, en: { t: "Hi, I'm Mực!", d: "The first time you open a page I'll point out its main parts. After that, tap me whenever you need help." } }
    : { vi: { t: "Chào em, mình là Mực!", d: "Lần đầu em mở một trang, mình sẽ chỉ nhanh vài chỗ chính. Sau đó cần gì cứ bấm vào mình." }, en: { t: "Hi, I'm Mực!", d: "The first time you open a page I'll point out its main parts. After that, tap me whenever you need help." } };
  const TOURS = {
    "hs-00-dang-nhap": [".role", "#accPill, #acc"],
    "hs-01-bat-dau": [".lang", ".age"],
    "hs-02-trang-chu": [HELLO, 'a.tile[href*="khoa-hoc"]', "[data-settings]"],
    "hs-02b-khoa-hoc": [".today", ".kid-tile", ".course", ".search"],
    "hs-02c-khoa-sap-co": [G(".tree", "Nội dung khóa", "Các chương và bài của khóa. Khóa chưa mở nhưng em xem trước được.", "What's inside", "The chapters and lessons. The course isn't open yet, but you can look ahead."), ".side"],
    "hs-03-tim-khoa-hoc": [".search", ".side", ".lessons"],
    "hs-04-khoa-hoc-tieu-hoc": ["#baskets", ".speak"],
    "hs-05-khoa-hoc-thpt": ["#video, .video, #poster, .poster", ".outline, .toc", "#quiz"],
    "hs-06-khoa-hoc-dai-hoc": [".read, .prose", "#plot", "#quiz"],
    "hs-07-luyen-tap": [".quick", ".opt", ".result"],
    "hs-08-hoi-bai": ["#composer", "[data-cam]", ".starter"],
    "hs-10-tien-bo": [".goal", ".week", "#addBtn"],
    "hs-11-nghien-cuu": [
      G(".rtabs", "Bốn chương", "Đọc, Lịch, Thí nghiệm và Đề tài. Chấm tím là có paper mới, chấm cam là sắp tới hạn nộp.", "Four chapters", "Read, Schedule, Experiments and Topic. A purple dot means new papers, an orange one a deadline coming up."),
      G(".sform", "Tìm paper", "Gõ chủ đề, tên bài hoặc tác giả. Kết quả hiện ngay trong chương Đọc.", "Find papers", "Type a topic, a title or an author. Results show up in the Read chapter."),
      G(".depth-btn", "Tìm sâu đến đâu", "Nhanh chỉ tìm trên arXiv. Kỹ và Sâu tìm thêm Semantic Scholar và Asta, cần key của bạn.", "How deep", "Quick searches arXiv only. Thorough and Deep add Semantic Scholar and Asta, with your own key."),
    ],
    "hs-12-doc-paper": [
      G(".mine", "Tóm tắt của bạn", "Viết tóm tắt bằng lời của bạn trước. Mentor chỉ góp ý sau khi bạn viết.", "Your summary", "Write a summary in your own words first. Mentor only gives feedback after you write."),
      G(".composer-wrap", "Hỏi về paper", "Câu trả lời kèm đoạn trích nguyên văn. Không thấy đoạn nào thì Mentor nói thẳng.", "Ask about the paper", "Answers come with quoted passages. If nothing is found, Mentor says so."),
      G(".rel", "Bài liên quan", "Bài trích dẫn paper này và bài paper này trích dẫn.", "Related papers", "Papers citing this one and papers it cites."),
    ],
    "gv-01-gui-bai": ["#drop", ".list .row"],
    "gv-02-cau-truc": ["#outline", ".bad", "#go"],
    "gv-03-duyet-noi-dung": ["#paper, .lesson-body", ".panel", "#pub, #pub2"],
  };
  const firstVisible = (sel) => Array.from(document.querySelectorAll(sel)).find((x) => visible(x) && !x.closest(".mock-bar"));
  function tourSteps() {
    const out = [];
    for (const s of TOURS[PAGE] || []) {
      if (out.length >= 3) break;
      if (s === HELLO) { out.push({ el: null, g: hello() }); continue; }
      const g = typeof s === "string" ? GUIDES.find((x) => x.sel === s) : s;
      const n = g && firstVisible(g.sel);
      if (n && !out.some((o) => o.el && (o.el.contains(n) || n.contains(o.el)))) out.push({ el: n, g });
    }
    return out;
  }

  // ---------------------------------------------------------------- figure (original character, no third-party likeness)
  const SVG =
    '<svg class="m-svg" viewBox="0 0 80 100" aria-hidden="true" focusable="false">' +
    '<defs><linearGradient id="mGrad" x1="0" y1="0" x2=".35" y2="1"><stop offset="0" style="stop-color:var(--m-a)"/><stop offset="1" style="stop-color:var(--m-b)"/></linearGradient></defs>' +
    '<ellipse class="m-shadow" cx="40" cy="97" rx="20" ry="3" fill="rgba(0,0,0,.16)"/>' +
    '<g class="m-legL"><rect x="28.5" y="76" width="5.5" height="14" rx="2.75" fill="var(--m-b)"/><ellipse cx="30" cy="92" rx="6.8" ry="3.8" fill="var(--m-shoe)"/></g>' +
    '<g class="m-legR"><rect x="46" y="76" width="5.5" height="14" rx="2.75" fill="var(--m-b)"/><ellipse cx="50" cy="92" rx="6.8" ry="3.8" fill="var(--m-shoe)"/></g>' +
    '<g class="m-armL"><path d="M17 58 Q9 62 8 70" stroke="var(--m-b)" stroke-width="5" fill="none" stroke-linecap="round"/><circle cx="8" cy="71" r="3.7" fill="var(--m-b)"/></g>' +
    '<g class="m-body"><path d="M40 4 C47 18 68 33 68 56 A28 28 0 0 1 12 56 C12 33 33 18 40 4 Z" fill="url(#mGrad)"/>' +
    '<ellipse cx="28" cy="35" rx="4.5" ry="8.5" fill="#fff" opacity=".38" transform="rotate(28 28 35)"/><circle cx="25" cy="25" r="1.8" fill="#fff" opacity=".45"/></g>' +
    '<g class="m-eyes"><ellipse cx="31" cy="50" rx="7" ry="8" fill="#fff"/><ellipse cx="49" cy="50" rx="7" ry="8" fill="#fff"/>' +
    '<g class="m-pupils"><circle cx="32" cy="51" r="4.1" fill="#1F1B3A"/><circle cx="50" cy="51" r="4.1" fill="#1F1B3A"/>' +
    '<circle cx="33.6" cy="49.2" r="1.5" fill="#fff"/><circle cx="51.6" cy="49.2" r="1.5" fill="#fff"/></g></g>' +
    '<ellipse cx="22.5" cy="61" rx="4.6" ry="2.8" fill="#FF8FB1" opacity=".8"/><ellipse cx="57.5" cy="61" rx="4.6" ry="2.8" fill="#FF8FB1" opacity=".8"/>' +
    '<path class="m-mouth-smile" d="M35 63 Q40 68.5 45 63" stroke="#1F1B3A" stroke-width="2.4" fill="none" stroke-linecap="round"/>' +
    '<ellipse class="m-mouth-open" cx="40" cy="65.2" rx="3.7" ry="3.3" fill="#3A1830"/>' +
    '<g class="m-armR"><path d="M63 58 Q71 55 73 48" stroke="var(--m-b)" stroke-width="5" fill="none" stroke-linecap="round"/>' +
    '<g transform="rotate(-24 74.5 40)"><rect x="72" y="28" width="5" height="16" rx="1" fill="#FFD84D"/><rect x="72" y="25.5" width="5" height="4" rx="1.3" fill="#FF8FB1"/>' +
    '<rect x="72" y="29.2" width="5" height="1.4" fill="#C9C3D9"/><path d="M72 44 L74.5 49.5 L77 44 Z" fill="#F2C9A0"/><path d="M73.7 47.6 L74.5 49.5 L75.3 47.6 Z" fill="#1F1B3A"/></g>' +
    '<circle cx="73" cy="47.5" r="3.7" fill="var(--m-b)"/></g>' +
    "</svg>";

  // ---------------------------------------------------------------- state
  let el, pos = { x: 0, y: 0 };
  let bubble = null, tail = null, spot = null, catcher = null, hinted = null;
  let current = null; // { kind: 'help'|'explain'|'say', render(), close() }
  let busy = false, drag = null, lastFocus = null, idleTimers = [];

  const vw = () => document.documentElement.clientWidth;
  const vh = () => window.innerHeight;
  const size = () => ({ w: el.offsetWidth, h: el.offsetHeight });
  const place = (x, y) => { pos = { x, y }; el.style.left = Math.round(x) + "px"; el.style.top = Math.round(y) + "px"; };
  const clampPos = (x, y) => {
    const { w, h } = size();
    return { x: Math.min(Math.max(8, x), vw() - w - 8), y: Math.min(Math.max(8, y), vh() - h - 8) };
  };
  const rectOf = () => ({ left: pos.x, top: pos.y, right: pos.x + size().w, bottom: pos.y + size().h, width: size().w, height: size().h });
  const hit = (a, b, pad) => !(a.right + pad <= b.left || b.right + pad <= a.left || a.bottom + pad <= b.top || b.bottom + pad <= a.top);
  const visible = (n) => {
    if (!n || n.closest("[hidden]")) return false;
    const r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  const AVOID = '.mascot-dock, .topbar, .lesson-top, .composer-wrap, .mock-bar, .bottomnav, .set-pop:not([hidden]), .btn-primary, .sheet, .toast, a[href], button:not(.mascot), input, textarea, select, [role="button"], [tabindex="0"]';
  function avoidRects() {
    const out = [];
    document.querySelectorAll(AVOID).forEach((n) => {
      if (n.closest(".mascot, .m-bubble")) return;
      if (!visible(n)) return;
      const r = n.getBoundingClientRect();
      if (r.bottom < 0 || r.top > vh() || r.right < 0 || r.left > vw()) return;
      out.push(r);
    });
    return out;
  }
  function topLimit() {
    let t = 8;
    document.querySelectorAll(".mock-bar, .topbar, .lesson-top").forEach((n) => {
      const r = n.getBoundingClientRect();
      if (visible(n) && r.bottom > t && r.top < 140) t = r.bottom;
    });
    return t + 10;
  }
  function candidates() {
    const { w, h } = size(), m = 14, out = [];
    const top = topLimit(), bottom = vh() - h - m;
    for (let y = bottom; y >= top; y -= 26) { out.push({ x: vw() - w - m, y }); out.push({ x: m, y }); }
    for (let x = m; x <= vw() - w - m; x += 34) out.push({ x, y: bottom });
    return out;
  }
  function freeSpots(exclude) {
    const av = avoidRects();
    if (exclude) av.push(exclude);
    const { w, h } = size();
    return candidates().filter((c) => {
      const r = { left: c.x, top: c.y, right: c.x + w, bottom: c.y + h };
      return !av.some((a) => hit(r, a, 6));
    });
  }
  function defaultSpot() {
    const { w, h } = size();
    const free = freeSpots();
    if (free.length) {
      free.sort((a, b) => (vw() - a.x) + (vh() - a.y) - ((vw() - b.x) + (vh() - b.y)));
      return free[0];
    }
    const cw = document.querySelector(".composer-wrap");
    if (cw && visible(cw)) return clampPos(vw() - w - 14, cw.getBoundingClientRect().top - h - 10);
    return clampPos(vw() - w - 14, vh() - h - 14);
  }
  function randomSpot(exclude) {
    const free = freeSpots(exclude).filter((c) => Math.hypot(c.x - pos.x, c.y - pos.y) > 110);
    if (!free.length) return defaultSpot();
    return free[Math.floor(Math.random() * free.length)];
  }
  function savePos() { store.set("pos-" + PAGE, JSON.stringify({ fx: pos.x / vw(), fy: pos.y / vh() })); }
  function restorePos() {
    try {
      const s = JSON.parse(store.get("pos-" + PAGE) || "null");
      if (s && isFinite(s.fx) && isFinite(s.fy)) {
        const p = clampPos(s.fx * vw(), s.fy * vh());
        const { w, h } = size();
        const r = { left: p.x, top: p.y, right: p.x + w, bottom: p.y + h };
        if (!avoidRects().some((a) => hit(r, a, 4))) return p;
      }
    } catch (e) {}
    return defaultSpot();
  }

  // ---------------------------------------------------------------- motion
  let dustTimer = null;
  function startDust(dx) {
    stopDust();
    dustTimer = setInterval(() => {
      const r = el.getBoundingClientRect();
      const d = document.createElement("i");
      d.className = "m-dust";
      d.style.left = r.left + r.width / 2 - 5 + (dx > 0 ? -10 : 10) + "px";
      d.style.top = r.bottom - 9 + "px";
      d.style.setProperty("--dx", (dx > 0 ? -12 : 12) + "px");
      document.body.appendChild(d);
      setTimeout(() => d.remove(), 650);
    }, 110);
  }
  function stopDust() { if (dustTimer) clearInterval(dustTimer); dustTimer = null; }

  async function moveTo(dest, mode) {
    const from = { ...pos };
    const to = clampPos(dest.x, dest.y);
    const dx = to.x - from.x, dy = to.y - from.y, dist = Math.hypot(dx, dy);
    if (dist < 2) return;
    if (RM.matches) {
      el.style.opacity = "0";
      await settle(el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140 }), 180);
      place(to.x, to.y);
      el.style.opacity = "";
      await settle(el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160 }), 200);
      return;
    }
    if (Math.abs(dx) > 4) el.classList.toggle("face-left", dx < 0);
    const run = mode === "run";
    const duration = run ? Math.min(2000, Math.max(520, dist / 0.5)) : 440;
    const arc = run ? -Math.min(70, dist * 0.18) : -Math.min(46, 18 + dist * 0.08);
    el.classList.add(run ? "is-running" : "is-hopping");
    if (run) startDust(dx);
    place(to.x, to.y);
    const a = el.animate(
      [
        { transform: `translate(${-dx}px, ${-dy}px)` },
        { transform: `translate(${-dx / 2}px, ${-dy / 2 + arc}px)`, offset: 0.5 },
        { transform: "translate(0, 0)" },
      ],
      { duration, easing: run ? "cubic-bezier(.35,.1,.3,1)" : "cubic-bezier(.3,.7,.4,1)" }
    );
    await settle(a, duration + 120);
    stopDust();
    el.classList.remove("is-running", "is-hopping");
    const fig = el.querySelector(".m-fig");
    fig.animate([{ transform: "scale(1.12, .86)" }, { transform: "scale(.96, 1.05)" }, { transform: "none" }], { duration: 260, easing: "ease-out" });
  }

  // ---------------------------------------------------------------- bubbles
  function removeBubble() {
    if (bubble) bubble.remove();
    if (tail) tail.remove();
    bubble = tail = null;
  }
  function placeBubble(avoid) {
    if (!bubble) return;
    const m = 12, gap = 34, W = vw(), H = vh();
    const bw = bubble.offsetWidth, bh = bubble.offsetHeight;
    const a = rectOf(), cx = a.left + a.width / 2, cy = a.top + a.height / 2;
    const clampX = (x) => Math.min(Math.max(m, x), W - bw - m);
    const clampY = (y) => Math.min(Math.max(m, y), H - bh - m);
    const opts = [
      { side: "above", x: clampX(cx - bw * 0.75), y: a.top - bh - gap },
      { side: "left", x: a.left - bw - gap, y: clampY(cy - bh * 0.7) },
      { side: "right", x: a.right + gap, y: clampY(cy - bh * 0.7) },
      { side: "below", x: clampX(cx - bw * 0.75), y: a.bottom + gap },
    ];
    const fits = (o) => o.x >= m && o.y >= m && o.x + bw <= W - m && o.y + bh <= H - m;
    const overlap = (o) => {
      if (!avoid) return 0;
      const w = Math.max(0, Math.min(o.x + bw, avoid.right) - Math.max(o.x, avoid.left));
      const h = Math.max(0, Math.min(o.y + bh, avoid.bottom) - Math.max(o.y, avoid.top));
      return w * h;
    };
    let best = null;
    opts.filter(fits).forEach((o) => { const s = overlap(o); if (!best || s < best.s) best = { ...o, s }; });
    if (!best) best = { side: "above", x: clampX(cx - bw / 2), y: clampY(a.top - bh - gap) };
    bubble.style.left = best.x + "px";
    bubble.style.top = best.y + "px";
    const t = { above: [cx - 23, a.top - 28], below: [cx - 23, a.bottom + 4], left: [a.left - 40, cy - 22], right: [a.right - 6, cy - 22] }[best.side];
    tail.style.left = Math.min(Math.max(4, t[0]), W - 50) + "px";
    tail.style.top = Math.min(Math.max(4, t[1]), H - 28) + "px";
  }
  function showBubble(html, avoid) {
    removeBubble();
    bubble = document.createElement("div");
    bubble.className = "m-bubble";
    bubble.setAttribute("role", "dialog");
    bubble.setAttribute("aria-label", tr("Mực nói", "Mực says"));
    bubble.innerHTML = html;
    tail = document.createElement("div");
    tail.className = "m-tail";
    tail.setAttribute("aria-hidden", "true");
    tail.innerHTML = "<i></i><i></i><i></i>";
    document.body.appendChild(tail);
    document.body.appendChild(bubble);
    placeBubble(avoid);
  }
  function talk(text) {
    el.classList.add("is-talking");
    clearTimeout(talk.t);
    talk.t = setTimeout(() => el.classList.remove("is-talking"), Math.min(4200, Math.max(1200, text.length * 45)));
  }
  function speak(text) {
    if (root.dataset.age !== "tieu-hoc" || !("speechSynthesis" in window)) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = isEn() ? "en-US" : "vi-VN";
      const v = speechSynthesis.getVoices().find((x) => x.lang && x.lang.toLowerCase().startsWith(isEn() ? "en" : "vi"));
      if (v) u.voice = v;
      u.rate = 0.95;
      speechSynthesis.speak(u);
    } catch (e) {}
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // help bubble: one tap on Mực
  function picks() {
    const seen = new Set(), out = [];
    for (const g of pageGuides()) {
      if (out.length >= 4) break;
      const n = Array.from(document.querySelectorAll(g.sel)).find((x) => visible(x) && !x.closest(".mock-bar"));
      if (!n || seen.has(n) || Array.from(seen).some((s) => s.contains(n) || n.contains(s))) continue;
      seen.add(n);
      out.push({ g, n });
    }
    return out;
  }
  function openHelp() {
    closeAll(false);
    const list = picks();
    const render = () => {
      const chips = (TOURS[PAGE] ? `<button type="button" class="m-replay" data-replay>${tr("Chỉ lại trang này", "Show me this page again")}</button>` : "") +
        list.map((p, i) => `<button type="button" data-pick-i="${i}">${esc(p.g[isEn() ? "en" : "vi"].t)}</button>`).join("");
      showBubble(
        `<p class="m-say">${tr("Cần mình chỉ chỗ nào? Nhấn giữ rồi kéo mình đến đó nhé!", "Need help with something? Hold and drag me there!")}</p>` +
          (chips ? `<div class="m-chips" role="group" aria-label="${tr("Hoặc chọn nhanh", "Or pick one")}">${chips}</div>` : "")
      );
      bubble.querySelectorAll("[data-pick-i]").forEach((b) =>
        b.addEventListener("click", () => {
          const p = list[Number(b.dataset.pickI)];
          closeAll(false);
          explain({ kind: "guide", el: p.n, g: p.g });
        })
      );
      const rp = bubble.querySelector("[data-replay]");
      if (rp) rp.addEventListener("click", () => { closeAll(false); startTour(); });
    };
    render();
    talk(tr("Cần mình chỉ chỗ nào? Nhấn giữ rồi kéo mình đến đó nhé!", "Need help with something? Hold and drag me there!"));
    el.classList.add("is-waving");
    el.setAttribute("aria-expanded", "true");
    current = { kind: "help", render, close: () => { removeBubble(); el.classList.remove("is-waving", "is-talking"); el.setAttribute("aria-expanded", "false"); } };
  }
  function say(textVi, textEn, ms) {
    closeAll(false);
    const render = () => showBubble(`<p class="m-say">${esc(tr(textVi, textEn))}</p>`);
    render();
    talk(tr(textVi, textEn));
    el.classList.add("is-waving");
    current = { kind: "say", render, close: () => { removeBubble(); el.classList.remove("is-waving", "is-talking"); } };
    if (ms) setTimeout(() => { if (current && current.kind === "say") closeAll(false); }, ms);
  }

  // ---------------------------------------------------------------- resolve what Mực was dropped on
  function labelOf(n) {
    const t = n.getAttribute("aria-label") || (n.innerText || "").trim().replace(/\s+/g, " ") || n.getAttribute("placeholder") || n.getAttribute("title") || n.value || "";
    return t.length > 42 ? t.slice(0, 40).trim() + "…" : t;
  }
  function resolve(t) {
    if (!t || t === document.documentElement || t === document.body) return { kind: "empty" };
    if (t.closest(".mock-bar")) return { kind: "mock" };
    if (t.closest(".mascot, .m-bubble, .m-tail")) return { kind: "empty" };
    let best = null;
    const consider = (m, g) => {
      if (!m || m === document.body || m.closest(".mock-bar")) return;
      if (!best || (best.el !== m && best.el.contains(m))) best = { el: m, g };
    };
    consider(t.closest("[data-guide]"), null);
    for (const g of pageGuides()) consider(t.closest(g.sel), g);
    if (best) {
      if (!best.g) {
        const n = best.el, nm = labelOf(n);
        best.g = { vi: { t: n.dataset.guideTitle || nm, d: n.dataset.guide }, en: { t: n.dataset.guideTitleEn || n.dataset.guideTitle || nm, d: n.dataset.guideEn || n.dataset.guide } };
      }
      return { kind: "guide", el: best.el, g: best.g };
    }
    const f = t.closest('button, a[href], input, textarea, select, summary, label, [role="button"], [role="radio"]');
    if (f && visible(f)) {
      const nm = labelOf(f) || tr("nút này", "this control");
      return { kind: "guide", el: f, g: { vi: { t: nm, d: `Đây là “${nm}”. Bấm vào để dùng.` }, en: { t: nm, d: `This is “${nm}”. Tap it to use it.` } } };
    }
    return { kind: "empty" };
  }

  // ---------------------------------------------------------------- explain a feature, then run off
  function standBeside(r) {
    const { w, h } = size(), m = 10, W = vw(), H = vh();
    const room = { right: W - r.right, left: r.left, below: H - r.bottom, above: r.top - topLimit() };
    const cy = Math.min(Math.max(r.top + r.height / 2 - h / 2, topLimit()), H - h - m);
    const cx = Math.min(Math.max(r.left + r.width / 2 - w / 2, m), W - w - m);
    const order = Object.keys(room).sort((a, b) => room[b] - room[a]);
    for (const side of order) {
      if (side === "right" && room.right >= w + 2 * m) return { x: r.right + m, y: cy };
      if (side === "left" && room.left >= w + 2 * m) return { x: r.left - w - m, y: cy };
      if (side === "below" && room.below >= h + 2 * m) return { x: cx, y: r.bottom + m };
      if (side === "above" && room.above >= h + 2 * m) return { x: cx, y: r.top - h - m };
    }
    return clampPos(r.right - w - m, r.bottom - h - m); // huge target: stand inside its corner
  }
  function clipToView(r, pad) {
    const left = Math.max(4, r.left - pad), top = Math.max(4, r.top - pad);
    const right = Math.min(vw() - 4, r.right + pad), bottom = Math.min(vh() - 4, r.bottom + pad);
    return { left, top, right, bottom, width: right - left, height: bottom - top };
  }

  async function explain(res) {
    busy = true;
    if (!tour || tour.i === 0) lastFocus = document.activeElement && document.activeElement !== document.body ? document.activeElement : el;
    if (!res.el && res.kind === "tour") {
      // a step about Mực itself (the hello): wave where it stands
      makeCatcher();
      el.classList.add("is-waving");
      openExplain(rectOf(), res.g);
      return;
    }
    if (res.kind === "mock" || res.kind === "empty") {
      const vi = res.kind === "mock" ? "Dải này chỉ để xem thử, không thuộc app." : "Chỗ này chưa có gì để hướng dẫn. Thử kéo mình vào một nút hoặc một ô nhé.";
      const en = res.kind === "mock" ? "That strip is only for reviewing, it isn't part of the app." : "Nothing to explain here. Try dragging me onto a button or a box.";
      if (res.kind === "mock") await moveTo(defaultSpot(), "hop");
      openExplain(null, { vi: { t: "", d: vi }, en: { t: "", d: en } });
      return;
    }
    const target = res.el;
    let r = target.getBoundingClientRect();
    if (r.top < topLimit() || r.bottom > vh()) {
      target.scrollIntoView({ block: "center", behavior: RM.matches ? "auto" : "smooth" });
      await wait(RM.matches ? 30 : 450);
      r = target.getBoundingClientRect();
    }
    const vr = clipToView(r, 8);
    spot = document.createElement("div");
    spot.className = "m-spot";
    Object.assign(spot.style, { left: vr.left + "px", top: vr.top + "px", width: vr.width + "px", height: vr.height + "px" });
    makeCatcher();
    document.body.appendChild(spot);
    await moveTo(standBeside(vr), "hop");
    const me = rectOf();
    el.classList.toggle("face-left", vr.left + vr.width / 2 < me.left + me.width / 2);
    el.classList.add("is-pointing");
    openExplain(vr, res.g);
  }
  // A clear layer over the page while Mực explains. Alone, a tap or a scroll ends the explanation. In a tour the only
  // way on is the button ("Hiểu rồi, tiếp"): taps and scrolls are swallowed and the bubble gives a little nudge instead.
  function makeCatcher() {
    catcher = document.createElement("div");
    catcher.className = "m-catch";
    catcher.addEventListener("pointerdown", (e) => { e.preventDefault(); if (tour) nudge(); else closeExplain(); });
    catcher.addEventListener("wheel", (e) => { e.preventDefault(); if (tour) nudge(); else closeExplain(); }, { passive: false });
    catcher.addEventListener("touchmove", (e) => e.preventDefault(), { passive: false });
    document.body.appendChild(catcher);
  }
  function nudge() {
    if (!bubble) return;
    bubble.classList.remove("m-nudge");
    void bubble.offsetWidth;
    bubble.classList.add("m-nudge");
    const ok = bubble.querySelector(".m-ok");
    if (ok) ok.focus({ preventScroll: true });
  }
  // the page stays put during a tour, so the highlight never drifts off its part (programmatic scrolling still works)
  function lockScroll(on) {
    const s = root.style;
    if (on) {
      if (window.innerWidth > root.clientWidth) s.scrollbarGutter = "stable"; // keep the bar's room: nothing shifts sideways
      s.overflow = "hidden";
    } else {
      s.overflow = "";
      s.scrollbarGutter = "";
    }
  }
  function openExplain(avoid, g) {
    const t = tour, n = t ? t.steps.length : 0, last = !t || t.i >= n - 1;
    const render = () => {
      const c = g[isEn() ? "en" : "vi"];
      const count = n > 1 ? `<span class="m-n">${t.i + 1}/${n}</span>` : "";
      const ok = `<button type="button" class="m-ok">${last ? tr("Hiểu rồi", "Got it") : tr("Hiểu rồi, tiếp", "Got it, next")}</button>`;
      showBubble(
        (c.t ? `<p class="m-t">${esc(c.t)}${count}</p>` : "") + `<p class="m-d">${esc(c.d)}</p>` +
          (t && !last ? `<div class="m-acts"><button type="button" class="m-skip">${tr("Bỏ qua", "Skip")}</button>${ok}</div>` : ok),
        avoid
      );
      bubble.querySelector(".m-ok").addEventListener("click", last ? closeExplain : nextStep);
      const sk = bubble.querySelector(".m-skip");
      if (sk) sk.addEventListener("click", closeExplain);
    };
    render();
    const c = g[isEn() ? "en" : "vi"];
    talk(c.d);
    speak((c.t ? c.t + ". " : "") + c.d);
    current = { kind: "explain", render, avoid, close: () => {} };
    bubble.querySelector(".m-ok").focus({ preventScroll: true });
  }
  function teardownExplain() {
    current = null;
    removeBubble();
    if (spot) spot.remove();
    if (catcher) catcher.remove();
    spot = catcher = null;
    el.classList.remove("is-pointing", "is-talking", "is-waving");
    try { speechSynthesis.cancel(); } catch (e) {}
  }
  function closeExplain() {
    if (!current || current.kind !== "explain") return;
    const avoid = current.avoid;
    teardownExplain();
    return wrapUp(avoid);
  }
  async function wrapUp(avoid) {
    const t = tour;
    tour = null;
    lockScroll(false);
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
    if (t && Math.abs(window.scrollY - t.y) > 4) {
      // the tour scrolled to show its parts: put the page back where the person left it
      window.scrollTo({ top: t.y, behavior: RM.matches ? "auto" : "smooth" });
      await wait(RM.matches ? 30 : 420);
      avoid = null;
    }
    await wait(RM.matches ? 0 : 160);
    await moveTo(randomSpot(avoid), "run");
    savePos();
    busy = false;
  }

  // ---------------------------------------------------------------- tour
  let tour = null; // { steps: [{ el, g }], i, y }
  function startTour() {
    const steps = tourSteps();
    if (!steps.length) return false;
    closeAll(false);
    tour = { steps, i: 0, y: window.scrollY };
    lockScroll(true);
    explain({ kind: "tour", el: tour.steps[0].el, g: tour.steps[0].g });
    return true;
  }
  function nextStep() {
    if (!tour) return;
    teardownExplain();
    let s;
    do s = tour.steps[++tour.i]; while (s && s.el && !visible(s.el));
    if (!s) { wrapUp(null); return; }
    explain({ kind: "tour", el: s.el, g: s.g });
  }
  function closeAll(andRun) {
    if (current && current.kind === "explain") { if (andRun) closeExplain(); else { teardownExplain(); tour = null; lockScroll(false); busy = false; } return; }
    if (current) current.close();
    current = null;
  }

  // ---------------------------------------------------------------- pointer: tap vs hold-and-drag
  function setHint(n) {
    if (hinted === n) return;
    if (hinted) hinted.classList.remove("m-hint");
    hinted = n;
    if (hinted) hinted.classList.add("m-hint");
  }
  function underPointer(x, y) {
    el.style.pointerEvents = "none";
    const t = document.elementFromPoint(x, y);
    el.style.pointerEvents = "";
    return t;
  }
  function beginDrag() {
    if (!drag || drag.on) return;
    drag.on = true;
    clearTimeout(drag.hold);
    closeAll(false);
    el.classList.remove("is-waving");
    el.classList.add("is-dragging");
  }
  function onDown(e) {
    if (e.button !== 0 || busy) return;
    e.preventDefault();
    drag = { sx: e.clientX, sy: e.clientY, t: performance.now(), ox: e.clientX - pos.x, oy: e.clientY - pos.y, on: false, moved: 0, id: e.pointerId };
    try { el.setPointerCapture(e.pointerId); } catch (err) {}
    drag.hold = setTimeout(beginDrag, 250);
  }
  function onMove(e) {
    if (!drag) return;
    drag.moved = Math.max(drag.moved, Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy));
    if (!drag.on && drag.moved > 6) beginDrag();
    if (!drag.on) return;
    const p = clampPos(e.clientX - drag.ox, e.clientY - drag.oy);
    place(p.x, p.y);
    const res = resolve(underPointer(e.clientX, e.clientY));
    setHint(res.kind === "guide" ? res.el : null);
  }
  function onUp(e) {
    if (!drag) return;
    const d = drag;
    drag = null;
    clearTimeout(d.hold);
    try { el.releasePointerCapture(d.id); } catch (err) {}
    if (d.on) {
      el.classList.remove("is-dragging");
      setHint(null);
      if (d.moved < 6) return; // held without moving: just put down
      explain(resolve(underPointer(e.clientX, e.clientY)));
      return;
    }
    if (performance.now() - d.t < 250 && d.moved < 6) toggleHelp();
  }
  function onCancel() {
    if (!drag) return;
    clearTimeout(drag.hold);
    drag = null;
    el.classList.remove("is-dragging");
    setHint(null);
  }
  function toggleHelp() {
    if (current && current.kind === "help") closeAll(false);
    else openHelp();
  }

  // ---------------------------------------------------------------- idle life
  function idleLoop() {
    const blink = () => {
      el.classList.add("blink");
      setTimeout(() => el.classList.remove("blink"), 140);
      idleTimers[0] = setTimeout(blink, 2600 + Math.random() * 3200);
    };
    const look = () => {
      const p = el.querySelector(".m-pupils");
      if (!busy && !drag && !current) {
        p.style.transform = `translate(${(Math.random() * 3 - 1.5).toFixed(1)}px, ${(Math.random() * 2 - 1).toFixed(1)}px)`;
        setTimeout(() => { p.style.transform = ""; }, 1300);
      }
      idleTimers[1] = setTimeout(look, 6000 + Math.random() * 5000);
    };
    idleTimers[0] = setTimeout(blink, 1800);
    idleTimers[1] = setTimeout(look, 4000);
  }

  // ---------------------------------------------------------------- init
  function init() {
    el = document.createElement("button");
    el.type = "button";
    el.className = "mascot";
    el.setAttribute("aria-label", tr("Mực, trợ lý hướng dẫn", "Mực, your guide"));
    el.setAttribute("aria-expanded", "false");
    el.innerHTML = '<span class="m-flip"><span class="m-fig">' + SVG + "</span></span>";
    document.body.appendChild(el);
    const p = restorePos();
    place(p.x, p.y);
    el.animate([{ opacity: 0, transform: "translateY(16px) scale(.8)" }, { opacity: 1, transform: "none" }], { duration: RM.matches ? 1 : 420, easing: "cubic-bezier(.2,.9,.3,1.3)" });

    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onCancel);
    el.addEventListener("lostpointercapture", (e) => { if (drag && drag.on) onUp(e); });
    el.addEventListener("click", (e) => e.preventDefault());
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleHelp(); }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !current) return;
      if (current.kind === "explain") closeExplain();
      else { closeAll(false); el.focus({ preventScroll: true }); }
    });
    document.addEventListener("pointerdown", (e) => {
      if (!current || current.kind === "explain") return;
      if (e.target.closest(".mascot, .m-bubble")) return;
      closeAll(false);
    }, true);
    document.addEventListener("mock:change", (e) => {
      const k = e.detail && e.detail.key;
      if (k === "lang") {
        el.setAttribute("aria-label", tr("Mực, trợ lý hướng dẫn", "Mực, your guide"));
        if (current && current.render) current.render();
      }
      if (k === "age") requestAnimationFrame(() => { const q = clampPos(pos.x, pos.y); place(q.x, q.y); });
    });
    let redo = null;
    window.addEventListener("resize", () => {
      if (tour) {
        // window resized or phone turned mid-tour: show the same step again, laid out for the new size
        clearTimeout(redo);
        redo = setTimeout(() => {
          if (!tour || !current || current.kind !== "explain") return;
          teardownExplain();
          const s = tour.steps[tour.i];
          explain({ kind: "tour", el: s.el, g: s.g });
        }, 180);
      } else if (current && current.kind === "explain") closeAll(false);
      const q = clampPos(pos.x, pos.y);
      place(q.x, q.y);
      if (bubble) placeBubble(current && current.avoid);
    });
    idleLoop();

    // first visit of this page: walk through it once, as soon as the person isn't busy (typing, a menu open, dragging Mực)
    if (TOURS[PAGE] && !store.get("seen-" + PAGE)) {
      let tries = 0;
      const free = () => {
        const a = document.activeElement;
        const typing = a && (a.matches("input, textarea, select, [contenteditable]") || a.isContentEditable);
        const open = document.querySelector('.set-pop:not([hidden]), .depth-pop:not([hidden]), .sheet.open, [role="dialog"]:not([hidden]):not(.m-bubble)');
        return !current && !drag && !busy && !typing && !open && document.visibilityState === "visible";
      };
      const attempt = () => {
        if (store.get("seen-" + PAGE)) return;
        if (!free()) { if (++tries < 20) setTimeout(attempt, 1500); return; }
        if (startTour()) store.set("seen-" + PAGE, "1");
      };
      setTimeout(attempt, 1100);
    }
    // Settings > "Xem lại hướng dẫn": forget every page seen, and start over on this one
    document.addEventListener("mascot:replay", () => {
      try { Object.keys(localStorage).filter((k) => k.indexOf("mentor-mascot-seen-") === 0).forEach((k) => localStorage.removeItem(k)); } catch (e) {}
      setTimeout(() => { if (startTour()) store.set("seen-" + PAGE, "1"); }, 250);
    });
    // reviewers only: see this page as a brand-new user
    const bar = document.querySelector(".mock-bar");
    if (bar && TOURS[PAGE]) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "mock-fresh";
      b.textContent = "Xem như người mới";
      b.addEventListener("click", () => {
        try { Object.keys(localStorage).filter((k) => k.indexOf("mentor-mascot-") === 0).forEach((k) => localStorage.removeItem(k)); } catch (e) {}
        window.scrollTo(0, 0);
        location.reload();
      });
      bar.appendChild(b);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
  else setTimeout(init, 0);
})();
