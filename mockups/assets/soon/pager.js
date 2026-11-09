// Mock-only: renders the sample catalog in pages of 10 and scrolls to the first item of the new page.
(function () {
  var PER = 10;
  var root = document.documentElement;
  var lang = function () { return root.dataset.lang === "en" ? "en" : "vi"; };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (m) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]; }); };
  function dur(m, en) {
    var h = Math.floor(m / 60), r = m % 60;
    if (en) return (h ? h + " h" : "") + (h && r ? " " : "") + (r ? r + " min" : "");
    return (h ? h + " giờ" : "") + (h && r ? " " : "") + (r ? r + " phút" : "");
  }
  var T = {
    vi: { soon: "Sắp có", prev: "Trang trước", next: "Trang sau", page: "Trang", les: "bài" },
    en: { soon: "Coming soon", prev: "Previous page", next: "Next page", page: "Page", les: "lessons" }
  };
  function href(c) { return "hs-02c-khoa-sap-co.html?c=" + c.k; }
  function meta(c) {
    var en = lang() === "en";
    return esc(c.te) + ", " + c.n + " " + T[lang()].les + ", " + dur(c.m, en);
  }
  function mark(s, q) {
    var lo = s.toLowerCase(), ql = (q || "").toLowerCase(), out = "", i = 0, j;
    if (!q) return esc(s);
    while ((j = lo.indexOf(ql, i)) > -1) { out += esc(s.slice(i, j)) + "<mark>" + esc(s.slice(j, j + q.length)) + "</mark>"; i = j + q.length; }
    return out + esc(s.slice(i));
  }

  // vi / en text; "bi" writes both so shared.js can switch it (used by the course page)
  function tx(l, vi, en) { return l === "bi" ? '<span data-en="' + esc(en) + '">' + esc(vi) + "</span>" : esc(l === "en" ? en : vi); }
  var SUBJ = {
    "Toán": "Math", "Tiếng Việt": "Vietnamese", "Tự nhiên và Xã hội": "Nature and Society", "Khoa học": "Science",
    "Lịch sử và Địa lí": "History and Geography", "Tin học": "Informatics", "Công nghệ": "Technology", "Đạo đức": "Ethics",
    "Tiếng Anh": "English", "Ngữ văn": "Literature", "Khoa học tự nhiên": "Natural Science", "Vật lí": "Physics",
    "Hóa học": "Chemistry", "Sinh học": "Biology", "Lịch sử": "History", "Địa lí": "Geography", "GDCD": "Civic Education",
    "Giáo dục kinh tế và pháp luật": "Economics and Law", "Ôn thi": "Exam prep", "Kĩ năng": "Study skills",
    "Giải tích": "Calculus", "Đại số tuyến tính": "Linear Algebra", "Xác suất thống kê": "Probability and Statistics",
    "Lập trình Python": "Python", "Cấu trúc dữ liệu": "Data Structures", "Lập trình": "Programming", "Cơ sở dữ liệu": "Databases",
    "Mạng máy tính": "Networks", "Hệ điều hành": "Operating Systems", "Kinh tế vi mô": "Microeconomics",
    "Kinh tế vĩ mô": "Macroeconomics", "Vật lí đại cương": "General Physics", "Hóa học đại cương": "General Chemistry",
    "Toán rời rạc": "Discrete Math", "Phương pháp nghiên cứu": "Research Methods", "Kế toán": "Accounting"
  };
  var LV = [["Cơ bản", "Basic"], ["Trung bình", "Intermediate"], ["Nâng cao", "Advanced"]];
  // subject, teaching language, difficulty (bars + word). Kids get subject and level only.
  function tags(c, kid, l) {
    l = l || lang();
    var lv = c.lv || 2, h = '<span class="ctags">';
    h += '<span class="ct ct-sub">' + tx(l, c.s, SUBJ[c.s] || c.s) + "</span>";
    if (!kid) h += c.l === "en" ? '<span class="ct ct-lang ct-en"><b>EN</b> English</span>' : '<span class="ct ct-lang">' + tx(l, "Tiếng Việt", "Vietnamese") + "</span>";
    h += '<span class="ct ct-lv"><span class="bars" aria-hidden="true"><i class="on"></i><i' + (lv > 1 ? ' class="on"' : "") + "></i><i" + (lv > 2 ? ' class="on"' : "") + "></i></span>" + tx(l, LV[lv - 1][0], LV[lv - 1][1]) + "</span>";
    return h + "</span>";
  }

  var build = {
    row: function (c) {
      return '<li tabindex="-1"><a class="course" href="' + href(c) + '"><img class="thumb" src="assets/soon/' + c.k + '.webp" alt="" loading="lazy">' +
        '<span><h3>' + esc(c.t) + '</h3><span class="meta"><span>' + meta(c) + "</span></span>" + tags(c) + "</span>" +
        '<span class="tag">' + T[lang()].soon + "</span></a></li>";
    },
    kid: function (c) {
      return '<a class="kid-tile" tabindex="-1" href="' + href(c) + '"><img class="pic" src="assets/soon/' + c.k + '.webp" alt="" loading="lazy">' +
        "<span>" + esc(c.t) + "</span>" + tags(c, true) + '<span class="tag">' + T[lang()].soon + "</span></a>";
    },
    res: function (c, q) {
      return '<li class="res" tabindex="-1"><span class="thumb"><img src="assets/soon/' + c.k + '.webp" alt=""></span><div>' +
        "<h2>" + mark(c.t, q) + ' <span class="tag">' + T[lang()].soon + "</span></h2>" +
        '<p class="by">' + meta(c) + "</p>" + tags(c) + "</div>" +
        '<a class="btn btn-ghost" href="' + href(c) + '">' + (lang() === "en" ? "View" : "Xem") + "</a></li>";
    }
  };
  function offset() {
    var y = 0;
    document.querySelectorAll(".mock-bar, .topbar").forEach(function (e) {
      var p = getComputedStyle(e).position;
      if (p === "sticky" || p === "fixed") y = Math.max(y, e.getBoundingClientRect().bottom);
    });
    return y + 12;
  }
  function chev(d) { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + (d < 0 ? "M14.5 5.5 8 12l6.5 6.5" : "M9.5 5.5 16 12l-6.5 6.5") + '"/></svg>'; }

  // opts: items, kind (row|kid|res), q, listEl, pagerEl. The pager always shows, even for one page.
  function mount(o) {
    var page = 1;
    var pages = Math.max(1, Math.ceil(o.items.length / PER));
    function render(move) {
      var t = T[lang()], slice = o.items.slice((page - 1) * PER, page * PER);
      o.listEl.classList.add("pager-list");
      o.listEl.innerHTML = slice.map(function (c) { return build[o.kind](c, o.q); }).join("");
      var p = o.pagerEl;
      p.hidden = false;
      p.className = "pager";
      p.setAttribute("aria-label", t.page);
      var lo = Math.max(1, Math.min(page - 2, pages - 4)), hi = Math.min(pages, lo + 4);
      var h = '<button type="button" data-go="' + (page - 1) + '"' + (page === 1 ? " disabled" : "") + ' aria-label="' + t.prev + '">' + chev(-1) + "</button>";
      for (var i = lo; i <= hi; i++) h += '<button type="button" data-go="' + i + '"' + (i === page ? ' aria-current="page"' : "") + ' aria-label="' + t.page + " " + i + '">' + i + "</button>";
      h += '<button type="button" data-go="' + (page + 1) + '"' + (page === pages ? " disabled" : "") + ' aria-label="' + t.next + '">' + chev(1) + "</button>";
      p.innerHTML = h;
      if (move) {
        var first = o.listEl.firstElementChild;
        if (!first) return;
        first.style.scrollMarginTop = offset() + "px";
        var calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        first.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
        first.focus({ preventScroll: true });
      }
    }
    o.pagerEl.onclick = function (e) {
      var b = e.target.closest("button[data-go]");
      if (!b || b.disabled) return;
      page = Math.min(pages, Math.max(1, +b.dataset.go));
      render(true);
    };
    render(false);
    return { rerender: function () { render(false); } };
  }
  window.SoonPager = { mount: mount, PER: PER, tags: tags, subj: SUBJ, build: build };
})();
