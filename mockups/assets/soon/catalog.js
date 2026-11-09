// Mock-only catalog for hs-03: real filtering, sorting, paging over the sample courses.
(function () {
  var root = document.documentElement, host = document.getElementById("cat");
  if (!host) return;
  var PER = 10;
  var en = function () { return root.dataset.lang === "en"; };
  var L = function (vi, e) { return en() ? e : vi; };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (m) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]; }); };

  // accent-insensitive: one output char per input char, so match positions map back to the original text
  function nm(s) {
    var o = "";
    for (var i = 0; i < s.length; i++) {
      var c = s.charAt(i), b = c.normalize("NFD").charAt(0).toLowerCase();
      o += b === "đ" ? "d" : b;
    }
    return o;
  }
  function hl(text, q) {
    var n = nm(text), toks = nm(q).split(" ").filter(Boolean), on = [], i, j;
    if (!toks.length) return esc(text);
    for (i = 0; i < text.length; i++) on.push(false);
    toks.forEach(function (t) { var p = n.indexOf(t); while (p > -1) { for (j = p; j < p + t.length; j++) on[j] = true; p = n.indexOf(t, p + t.length); } });
    var out = "", open = false;
    for (i = 0; i < text.length; i++) {
      if (on[i] && !open) { out += "<mark>"; open = true; }
      if (!on[i] && open) { out += "</mark>"; open = false; }
      out += esc(text.charAt(i));
    }
    return out + (open ? "</mark>" : "");
  }
  function bold(text, q) { return hl(text, q).replace(/<mark>/g, "<b>").replace(/<\/mark>/g, "</b>"); }

  var BANDS = [["tieu-hoc", "Tiểu học", "Primary"], ["thcs", "THCS", "Lower secondary"], ["thpt", "THPT", "Upper secondary"], ["dai-hoc", "Đại học", "University"]];
  var MEDIA = { video: ["Video", "Video"], reading: ["Bài đọc", "Reading"], quiz: ["Câu hỏi", "Questions"], interactive: ["Tương tác", "Interactive"], audio: ["Âm thanh", "Audio"] };
  var DUR = { a: ["Dưới 1 giờ", "Under 1 hour"], b: ["1 đến 3 giờ", "1 to 3 hours"], c: ["Trên 3 giờ", "Over 3 hours"] };
  var STAT = { live: ["Học được ngay", "Available now"], soon: ["Sắp có", "Coming soon"] };
  var LANG = { vi: ["Tiếng Việt", "Vietnamese"], en: ["English", "English"] };
  var LV = { 1: ["Cơ bản", "Basic"], 2: ["Trung bình", "Intermediate"], 3: ["Nâng cao", "Advanced"] };
  var SUBJ = window.SoonPager.subj;

  // ---- data: 3 live courses + every placeholder ----
  var ALL = [
    { k: "live-toan1", t: "Toán 1: Các số đến 10", s: "Toán", te: "Cô Mai", l: "vi", n: 6, m: 45, lv: 1, band: "tieu-hoc", med: ["video", "interactive", "quiz"], img: "assets/courses/so-den-10.jpg", href: "hs-04-khoa-hoc-tieu-hoc.html", st: 412, d: 1003 },
    { k: "live-vatli11", t: "Vật lí 11: Điện trường", s: "Vật lí", te: "Thầy Minh", l: "vi", n: 7, m: 120, lv: 2, band: "thpt", med: ["video", "reading", "quiz"], img: "assets/courses/dien-truong.jpg", href: "hs-05-khoa-hoc-thpt.html", st: 286, d: 1002 },
    { k: "live-bayes", t: "Xác suất thống kê: Suy luận Bayes", s: "Xác suất thống kê", te: "TS. Quang", l: "vi", n: 6, m: 300, lv: 3, band: "dai-hoc", med: ["reading", "quiz"], img: "assets/courses/bayes.jpg", href: "hs-06-khoa-hoc-dai-hoc.html", st: 94, d: 1001 }
  ];
  var i0 = 0;
  BANDS.forEach(function (b) {
    window.SOON_LIST[b[0]].forEach(function (c) {
      ALL.push({ k: c.k, t: c.t, s: c.s, te: c.te, l: c.l, n: c.n, m: c.m, lv: c.lv, band: b[0], soon: true, med: window.SOON_DETAIL[c.k].med, img: "assets/soon/" + c.k + ".webp", href: "hs-02c-khoa-sap-co.html?c=" + c.k, st: 0, d: 500 - i0++ });
    });
  });
  var VOCAB = {};
  ALL.forEach(function (c) {
    c.idx = nm(c.t + " " + c.s + " " + c.te + " " + (c.l === "en" ? "english" : "tieng viet"));
    (c.t + " " + c.s + " " + c.te).split(" ").forEach(function (w) { var k = nm(w.replace(/[:,.()]/g, "")); if (k.length > 1 && !VOCAB[k]) VOCAB[k] = w.replace(/[:,.()]/g, "").toLowerCase(); });
  });
  var durCat = function (m) { return m < 60 ? "a" : m <= 180 ? "b" : "c"; };
  var subjName = function (s) { return L(s, SUBJ[s] || s); };
  var durText = function (m) {
    var h = Math.floor(m / 60), r = m % 60;
    return en() ? (h ? h + " h" : "") + (h && r ? " " : "") + (r ? r + " min" : "") : (h ? h + " giờ" : "") + (h && r ? " " : "") + (r ? r + " phút" : "");
  };

  // ---- state ----
  var KEYS = ["band", "subj", "lang", "lv", "dur", "media", "status", "teacher"];
  var S = { q: "", sort: "rel", dir: "asc", view: "grid", page: 1, F: {}, exp: {} };
  var age = "thpt";
  function resetF(keepBand) {
    var b = keepBand;
    KEYS.forEach(function (k) { S.F[k] = {}; });
    if (b) S.F.band[b] = 1;
  }
  resetF();
  var isKid = function () { return age === "tieu-hoc"; };
  function has(k) { return Object.keys(S.F[k]).length; }
  function val(c, k) {
    switch (k) {
      case "band": return [c.band];
      case "subj": return [c.s];
      case "lang": return [c.l];
      case "lv": return [String(c.lv)];
      case "dur": return [durCat(c.m)];
      case "media": return c.med;
      case "status": return [c.soon ? "soon" : "live"];
      default: return [c.te];
    }
  }
  function passes(c, skip, noQ) {
    for (var i = 0; i < KEYS.length; i++) {
      var k = KEYS[i];
      if (k === skip || !has(k)) continue;
      if (!val(c, k).some(function (v) { return S.F[k][v]; })) return false;
    }
    if (!noQ && S.q) {
      var toks = nm(S.q).split(" ").filter(Boolean);
      if (!toks.every(function (t) { return c.idx.indexOf(t) > -1; })) return false;
    }
    return true;
  }
  function results() {
    var r = ALL.filter(function (c) { return passes(c); });
    var first = nm(S.q).split(" ")[0];
    var rel = function (c) { var t = nm(c.t); return !S.q ? 0 : t.indexOf(first) === 0 ? 0 : t.indexOf(first) > -1 ? 1 : 2; };
    r.forEach(function (c, i) { c.o = i; });
    r.sort(function (a, b) {
      var x = 0;
      if (S.sort === "new") x = b.d - a.d;
      else if (S.sort === "pop") x = b.st - a.st;
      else if (S.sort === "dur") x = (a.m - b.m) * (S.dir === "asc" ? 1 : -1);
      else x = rel(a) - rel(b) || (a.soon ? 1 : 0) - (b.soon ? 1 : 0);
      return x || a.o - b.o;
    });
    return r;
  }
  function facetOpts(k) {
    var counts = {}, order = [];
    ALL.forEach(function (c) {
      if (!passes(c, k)) return;
      val(c, k).forEach(function (v) { counts[v] = (counts[v] || 0) + 1; });
    });
    var vals;
    if (k === "band") vals = BANDS.map(function (b) { return b[0]; });
    else if (k === "lang") vals = ["vi", "en"];
    else if (k === "lv") vals = ["1", "2", "3"];
    else if (k === "dur") vals = ["a", "b", "c"];
    else if (k === "status") vals = ["live", "soon"];
    else {
      var set = {};
      ALL.forEach(function (c) { val(c, k).forEach(function (v) { set[v] = 1; }); });
      vals = Object.keys(set);
      vals.sort(function (a, b) { return (counts[b] || 0) - (counts[a] || 0) || a.localeCompare(b, "vi"); });
    }
    return vals.map(function (v) { return { v: v, n: counts[v] || 0 }; });
  }
  function label(k, v) {
    switch (k) {
      case "band": var b = BANDS.filter(function (x) { return x[0] === v; })[0]; return L(b[1], b[2]);
      case "subj": return subjName(v);
      case "lang": return L(LANG[v][0], LANG[v][1]);
      case "lv": return L(LV[v][0], LV[v][1]);
      case "dur": return L(DUR[v][0], DUR[v][1]);
      case "media": return L(MEDIA[v][0], MEDIA[v][1]);
      case "status": return L(STAT[v][0], STAT[v][1]);
      default: return v;
    }
  }
  var FTITLE = { band: ["Cấp học", "Level"], subj: ["Môn học", "Subject"], lang: ["Ngôn ngữ dạy", "Teaching language"], lv: ["Độ khó", "Difficulty"], dur: ["Thời lượng", "Duration"], media: ["Hình thức", "Format"], status: ["Trạng thái", "Status"], teacher: ["Giáo viên", "Teacher"] };
  var ORDER = ["subj", "band", "lang", "lv", "dur", "media", "status", "teacher"];

  // ---- recents ----
  function recents() { try { var r = JSON.parse(localStorage.getItem("mentor-mock-recent") || "null"); if (r) return r; } catch (e) {} return ["vật lí 12", "python"]; }
  function saveRecents(r) { try { localStorage.setItem("mentor-mock-recent", JSON.stringify(r)); } catch (e) {} }
  function addRecent(q) { q = q.trim(); if (!q) return; var r = recents().filter(function (x) { return x !== q; }); r.unshift(q); saveRecents(r.slice(0, 6)); }
  var POPULAR = ["Toán 12", "IELTS", "Python", "Vật lí", "Hóa học", "Machine learning"];

  // ---- typo hint ----
  function dist(a, b) {
    var p = [], i, j;
    for (j = 0; j <= b.length; j++) p[j] = j;
    for (i = 1; i <= a.length; i++) {
      var prev = p[0]; p[0] = i;
      for (j = 1; j <= b.length; j++) { var t = p[j]; p[j] = Math.min(p[j] + 1, p[j - 1] + 1, prev + (a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1)); prev = t; }
    }
    return p[b.length];
  }
  function suggest(q) {
    var out = [], changed = false;
    nm(q).split(" ").filter(Boolean).forEach(function (t) {
      var words = Object.keys(VOCAB);
      var pre = words.filter(function (w) { return w.indexOf(t) === 0; })[0]; if (pre) { out.push(VOCAB[pre]); return; }
      var best = null, bd = t.length > 4 ? 2 : 1;
      words.forEach(function (w) { var d = dist(t, w); if (d <= bd && (best === null || d < bd)) { best = w; bd = d; } });
      changed = true;
      if (best) out.push(VOCAB[best]);
    });
    var s = out.join(" ");
    return changed && s && nm(s) !== nm(q) ? s : null;
  }

  // ---- skeleton (built once, so the input keeps focus) ----
  host.innerHTML =
    '<div class="sbar" id="sbar"><form class="search" role="search" id="sform"><i data-i="search"></i><input id="q" type="search" autocomplete="off" aria-label="Tìm khóa học" aria-autocomplete="list" aria-controls="ac">' +
    '<button class="mic" type="button" aria-label="Nói để tìm"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/></svg></button></form>' +
    '<button class="fbtn" id="fbtn" type="button"><span id="fbl"></span><b id="fbn"></b></button><div class="ac" id="ac" hidden></div></div>' +
    '<div class="cat" id="catgrid"><aside class="filters" id="filters"></aside><div class="col"><div class="sortbar" id="sortbar"></div><div class="chips" id="chips"></div><div class="kidsubj" id="kidsubj"></div>' +
    '<ul class="grid" id="results"></ul><div id="empty"></div><nav class="pager" id="pager"></nav></div></div><div class="backdrop" id="backdrop" hidden></div>';
  var $ = function (id) { return document.getElementById(id); };
  var q = $("q"), ac = $("ac"), grid = $("catgrid");

  // ---- render ----
  var svgGrid = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/></svg>';
  var svgList = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
  var chevL = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 5.5 8 12l6.5 6.5"/></svg>', chevR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 5.5 16 12l-6.5 6.5"/></svg>';

  function activeCount() {
    var n = 0;
    KEYS.forEach(function (k) { n += has(k); });
    if (has("band") === 1 && S.F.band[age]) n -= 1;
    return n;
  }
  function renderFilters(total) {
    var h = '<div class="fh"><h2>' + L("Bộ lọc", "Filters") + '</h2><button type="button" class="reset" data-act="reset">' + L("Đặt lại", "Reset") + '</button><button type="button" class="x" data-act="close" aria-label="' + L("Đóng", "Close") + '">×</button></div><div class="fbody">';
    ORDER.forEach(function (k) {
      var opts = facetOpts(k), lim = k === "subj" || k === "teacher" ? 6 : 99, shown = [];
      if (k === "teacher" || k === "subj") opts = opts.filter(function (o) { return o.n > 0 || S.F[k][o.v]; });
      var all = !!S.exp[k];
      opts.forEach(function (o, i) { if (all || i < lim || S.F[k][o.v]) shown.push(o); });
      h += '<section class="facet"><h3>' + L(FTITLE[k][0], FTITLE[k][1]) + "</h3>" + (k === "teacher" && all ? '<div class="tlist">' : "");
      shown.forEach(function (o) {
        h += '<label class="fo' + (o.n === 0 && !S.F[k][o.v] ? " zero" : "") + '"><input type="checkbox" data-f="' + k + '" data-v="' + esc(o.v) + '"' + (S.F[k][o.v] ? " checked" : "") + '><span class="fl">' + esc(label(k, o.v)) + '</span><span class="fn">' + o.n + "</span></label>";
      });
      h += (k === "teacher" && all ? "</div>" : "");
      if (opts.length > lim) h += '<button type="button" class="more" data-act="more" data-k="' + k + '">' + (all ? L("Thu gọn", "Show less") : L("Xem thêm", "Show more") + " (" + (opts.length - shown.length) + ")") + "</button>";
      h += "</section>";
    });
    h += '</div><div class="ff"><button type="button" class="btn btn-primary" data-act="close">' + L("Áp dụng", "Apply") + " (" + total + " " + L("kết quả", "results") + ")</button></div>";
    $("filters").innerHTML = h;
  }
  function card(c, kid) {
    var tags = window.SoonPager.tags(c, kid);
    var foot = c.soon ? '<span class="tag">' + L("Sắp có", "Coming soon") + "</span>" : "<span>" + c.st + " " + L("học sinh đang học", "students learning") + "</span>";
    return '<li class="pc" tabindex="-1"><a href="' + c.href + '"><span class="pimg"><img src="' + c.img + '" alt="" loading="lazy"></span><span class="pbody">' +
      "<h3>" + hl(c.t, S.q) + "</h3>" + (kid ? "" : '<span class="pt">' + hl(c.te, S.q) + "</span>") + tags +
      (kid ? "" : '<span class="pm">' + c.n + " " + L("bài", "lessons") + ", " + durText(c.m) + "</span>") + '<span class="pf">' + foot + "</span></span></a></li>";
  }
  function chip(act, attrs, text) { return '<button type="button" class="chip" data-act="' + act + '" ' + attrs + ">" + text + "</button>"; }
  function renderEmpty(res) {
    var el = $("empty"), h = "";
    var few = res.length < 4;
    if (!few) { el.innerHTML = ""; return; }
    var hint = S.q ? suggest(S.q) : null;
    var gains = [];
    KEYS.forEach(function (k) {
      Object.keys(S.F[k]).forEach(function (v) {
        if (k === "band" && v === age && has("band") === 1) return;
        var saved = S.F[k][v]; delete S.F[k][v];
        var n = ALL.filter(function (c) { return passes(c); }).length;
        S.F[k][v] = saved;
        if (n > res.length) gains.push({ k: k, v: v, g: n - res.length });
      });
    });
    gains.sort(function (a, b) { return b.g - a.g; });
    h += '<div class="none">';
    if (!res.length) h += "<h2>" + L("Không có khóa nào khớp", "No course matches") + "</h2>";
    else h += "<h4>" + L("Chỉ có vài khóa khớp", "Only a few courses match") + "</h4>";
    if (hint) h += '<p class="hint">' + L("Có phải bạn muốn tìm: ", "Did you mean: ") + '<button type="button" data-act="q" data-q="' + esc(hint) + '">' + esc(hint) + "</button>?</p>";
    if (gains.length) {
      h += '<div class="chipset">';
      gains.slice(0, 4).forEach(function (g) { h += chip("rm", 'data-f="' + g.k + '" data-v="' + esc(g.v) + '"', L("Bỏ lọc ", "Remove ") + esc(label(g.k, g.v)) + " (+" + g.g + ")"); });
      h += "</div>";
    }
    var subs = {};
    ALL.forEach(function (c) { if (!has("band") || S.F.band[c.band]) subs[c.s] = (subs[c.s] || 0) + 1; });
    var top = Object.keys(subs).filter(function (s) { return !S.F.subj[s]; }).sort(function (a, b) { return subs[b] - subs[a]; }).slice(0, 5);
    h += "<h4>" + L("Môn học liên quan", "Related subjects") + '</h4><div class="chipset">';
    top.forEach(function (s) { h += chip("subj", 'data-v="' + esc(s) + '"', esc(subjName(s))); });
    h += "</div></div>";
    el.innerHTML = h;
  }
  function renderPager(pages) {
    var lo = Math.max(1, Math.min(S.page - 2, pages - 4)), hi = Math.min(pages, lo + 4);
    var h = '<button type="button" data-go="' + (S.page - 1) + '"' + (S.page === 1 ? " disabled" : "") + ' aria-label="' + L("Trang trước", "Previous page") + '">' + chevL + "</button>";
    for (var i = lo; i <= hi; i++) h += '<button type="button" data-go="' + i + '"' + (i === S.page ? ' aria-current="page"' : "") + ' aria-label="' + L("Trang ", "Page ") + i + '">' + i + "</button>";
    h += '<button type="button" data-go="' + (S.page + 1) + '"' + (S.page === pages ? " disabled" : "") + ' aria-label="' + L("Trang sau", "Next page") + '">' + chevR + "</button>";
    $("pager").innerHTML = h;
  }
  function render() {
    var kid = isKid();
    grid.classList.toggle("kid", kid); host.classList.toggle("kid", kid);
    q.placeholder = kid ? L("Tìm khóa học", "Search") : L("Tìm khóa học, môn học, giáo viên", "Search courses, subjects, teachers");
    q.setAttribute("aria-label", L("Tìm khóa học", "Search courses"));
    if (document.activeElement !== q) q.value = S.q;
    $("fbl").textContent = L("Bộ lọc", "Filters");
    $("fbn").textContent = activeCount() || "";
    var res = results(), pages = Math.max(1, Math.ceil(res.length / PER));
    if (S.page > pages) S.page = pages;
    var slice = res.slice((S.page - 1) * PER, S.page * PER);
    var focusId = document.activeElement && document.activeElement.closest("#filters") ? document.activeElement.dataset.f + "|" + document.activeElement.dataset.v : null;
    if (!kid) {
      renderFilters(res.length);
      if (focusId) { var f = $("filters").querySelector('input[data-f="' + focusId.split("|")[0] + '"][data-v="' + focusId.split("|")[1] + '"]'); if (f) f.focus({ preventScroll: true }); }
      var tabs = [["rel", "Liên quan", "Relevant"], ["new", "Mới nhất", "Newest"], ["pop", "Phổ biến", "Popular"], ["dur", "Thời lượng", "Duration"]];
      var h = '<div class="tabs" role="group" aria-label="' + L("Sắp xếp", "Sort") + '">';
      tabs.forEach(function (t) { h += '<button type="button" data-sort="' + t[0] + '" aria-pressed="' + (S.sort === t[0]) + '">' + L(t[1], t[2]) + (t[0] === "dur" ? (S.sort === "dur" && S.dir === "desc" ? " ↓" : " ↑") : "") + "</button>"; });
      h += '</div><div class="sbtm"><span class="count" aria-live="polite">' + res.length + " " + L("khóa", res.length === 1 ? "course" : "courses") + '</span><span class="vt"><button type="button" data-view="grid" aria-pressed="' + (S.view === "grid") + '" aria-label="' + L("Dạng lưới", "Grid") + '">' + svgGrid + '</button><button type="button" data-view="list" aria-pressed="' + (S.view === "list") + '" aria-label="' + L("Dạng danh sách", "List") + '">' + svgList + "</button></span></div>";
      $("sortbar").innerHTML = h;
      var c = "", any = 0;
      KEYS.forEach(function (k) { Object.keys(S.F[k]).forEach(function (v) { any++; c += '<button type="button" class="chip" data-act="rm" data-f="' + k + '" data-v="' + esc(v) + '" aria-label="' + L("Bỏ lọc ", "Remove ") + esc(label(k, v)) + '">' + L(FTITLE[k][0], FTITLE[k][1]) + ": " + esc(label(k, v)) + ' <span class="x" aria-hidden="true">×</span></button>'; }); });
      if (any > 1) c += '<button type="button" class="chip clear" data-act="clear">' + L("Xóa tất cả", "Clear all") + "</button>";
      $("chips").innerHTML = c;
      $("kidsubj").innerHTML = "";
    } else {
      var subs = [], seen = {};
      ALL.forEach(function (x) { if (x.band === "tieu-hoc" && !seen[x.s]) { seen[x.s] = 1; subs.push(x); } });
      var cur = Object.keys(S.F.subj)[0];
      var kh = '<button type="button" class="chip all' + (!cur ? " on" : "") + '" data-act="ksubj" data-v="">' + L("Tất cả", "All") + "</button>";
      subs.forEach(function (x) { kh += '<button type="button" class="chip' + (cur === x.s ? " on" : "") + '" data-act="ksubj" data-v="' + esc(x.s) + '"><img src="' + x.img + '" alt="">' + esc(subjName(x.s)) + "</button>"; });
      $("kidsubj").innerHTML = kh;
    }
    var list = $("results");
    list.className = "grid pager-list" + (!kid && S.view === "list" ? " list" : "");
    list.innerHTML = slice.map(function (x) { return card(x, kid); }).join("");
    renderEmpty(res);
    renderPager(pages);
  }

  // ---- autocomplete ----
  function renderAc() {
    var v = q.value.trim(), h = "";
    if (isKid()) { ac.hidden = true; return; }
    if (!v) {
      var r = recents();
      if (r.length) {
        h += "<h4>" + L("Tìm gần đây", "Recent searches") + "</h4>";
        r.forEach(function (x) { h += '<div class="row"><button type="button" class="it" data-act="q" data-q="' + esc(x) + '"><span>' + esc(x) + '</span></button><button type="button" class="it x" style="flex:none;width:44px;justify-content:center" data-act="delrecent" data-q="' + esc(x) + '" aria-label="' + L("Xóa", "Remove") + " " + esc(x) + '">×</button></div>'; });
      }
      h += "<h4>" + L("Tìm nhiều", "Popular searches") + '</h4><div class="chipset">';
      POPULAR.forEach(function (x) { h += chip("q", 'data-q="' + esc(x) + '"', esc(x)); });
      h += "</div>";
    } else {
      var toks = nm(v).split(" ").filter(Boolean);
      var m = function (s) { var n = nm(s); return toks.every(function (t) { return n.indexOf(t) > -1; }); };
      var cs = ALL.filter(function (c) { return m(c.t); }).slice(0, 4);
      var sj = [], te = [];
      ALL.forEach(function (c) { if (sj.indexOf(c.s) < 0 && m(c.s)) sj.push(c.s); if (te.indexOf(c.te) < 0 && m(c.te)) te.push(c.te); });
      if (cs.length) { h += "<h4>" + L("Khóa học", "Courses") + "</h4>"; cs.forEach(function (c) { h += '<button type="button" class="it" data-act="q" data-q="' + esc(c.t) + '"><span>' + bold(c.t, v) + "</span></button>"; }); }
      if (sj.length) { h += "<h4>" + L("Môn học", "Subjects") + "</h4>"; sj.slice(0, 3).forEach(function (s) { h += '<button type="button" class="it" data-act="subj" data-v="' + esc(s) + '"><span>' + bold(subjName(s), v) + "</span></button>"; }); }
      if (te.length) { h += "<h4>" + L("Giáo viên", "Teachers") + "</h4>"; te.slice(0, 3).forEach(function (t) { h += '<button type="button" class="it" data-act="teacher" data-v="' + esc(t) + '"><span>' + bold(t, v) + "</span></button>"; }); }
      if (!cs.length && !sj.length && !te.length) {
        var hint = suggest(v);
        h += '<p class="hint">' + L("Không có gợi ý nào.", "No suggestions.") + (hint ? " " + L("Có phải bạn muốn tìm: ", "Did you mean: ") + '<button type="button" data-act="q" data-q="' + esc(hint) + '">' + esc(hint) + "</button>?" : "") + "</p>";
      }
    }
    ac.innerHTML = h;
    ac.hidden = false;
  }

  // ---- actions ----
  function scrollFirst() {
    var first = $("results").firstElementChild;
    if (!first) return;
    var y = 0;
    document.querySelectorAll(".mock-bar, .sbar").forEach(function (e) { var p = getComputedStyle(e).position; if (p === "sticky" || p === "fixed") y += e.getBoundingClientRect().height; });
    first.style.scrollMarginTop = y + 12 + "px";
    first.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    first.focus({ preventScroll: true });
  }
  function setQ(v, save) { S.q = v; q.value = v; if (save) addRecent(v); S.page = 1; ac.hidden = true; render(); }
  function sheet(open) { document.body.classList.toggle("sheet", open); $("backdrop").hidden = !open; document.body.style.overflow = open ? "hidden" : ""; if (open) { var x = $("filters").querySelector(".x"); if (x) x.focus(); } else $("fbtn").focus({ preventScroll: true }); }

  document.addEventListener("click", function (e) {
    if (!host.contains(e.target)) return;
    if (!e.target.closest("#sbar")) ac.hidden = true;
    var b = e.target.closest("button, a");
    if (!b) return;
    if (b.id === "fbtn") { sheet(true); return; }
    var go = b.dataset.go, a = b.dataset.act;
    if (go) { if (b.disabled) return; S.page = +go; render(); scrollFirst(); return; }
    if (b.dataset.sort) { var s = b.dataset.sort; if (s === "dur" && S.sort === "dur") S.dir = S.dir === "asc" ? "desc" : "asc"; else S.dir = "asc"; S.sort = s; S.page = 1; render(); return; }
    if (b.dataset.view) { S.view = b.dataset.view; render(); return; }
    if (a === "close") sheet(false);
    else if (a === "reset") { resetF(age); S.q = ""; S.page = 1; render(); }
    else if (a === "clear") { resetF(); S.page = 1; render(); }
    else if (a === "more") { S.exp[b.dataset.k] = !S.exp[b.dataset.k]; render(); }
    else if (a === "rm") { delete S.F[b.dataset.f][b.dataset.v]; S.page = 1; render(); }
    else if (a === "q") setQ(b.dataset.q, true);
    else if (a === "delrecent") { saveRecents(recents().filter(function (x) { return x !== b.dataset.q; })); renderAc(); }
    else if (a === "subj") { S.q = ""; q.value = ""; S.F.subj = {}; S.F.subj[b.dataset.v] = 1; ac.hidden = true; S.page = 1; render(); }
    else if (a === "teacher") { S.q = ""; q.value = ""; S.F.teacher = {}; S.F.teacher[b.dataset.v] = 1; ac.hidden = true; S.page = 1; render(); }
    else if (a === "ksubj") { S.F.subj = {}; if (b.dataset.v) S.F.subj[b.dataset.v] = 1; S.page = 1; render(); }
  });
  host.addEventListener("change", function (e) {
    var t = e.target;
    if (!t.dataset.f) return;
    if (t.checked) S.F[t.dataset.f][t.dataset.v] = 1; else delete S.F[t.dataset.f][t.dataset.v];
    S.page = 1; render();
  });
  q.addEventListener("input", function () { S.q = q.value; S.page = 1; render(); renderAc(); });
  q.addEventListener("focus", renderAc);
  $("sform").addEventListener("submit", function (e) { e.preventDefault(); addRecent(q.value); ac.hidden = true; q.blur(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { if (document.body.classList.contains("sheet")) sheet(false); else ac.hidden = true; } });

  // ---- mock toolbar ----
  function stick() { var b = document.querySelector(".mock-bar"); root.style.setProperty("--stick", (b ? b.getBoundingClientRect().height : 0) + "px"); }
  window.addEventListener("resize", stick);
  document.addEventListener("mock:change", function (e) {
    var k = e.detail.key;
    stick();
    if (k === "age") { age = root.dataset.age; resetF(age); S.page = 1; }
    else if (k === "state") { S.q = e.detail.value === "trong" ? "tích phân bội" : ""; q.value = S.q; S.page = 1; resetF(age); }
    if (k === "age" || k === "state" || k === "lang") { if (document.body.classList.contains("sheet")) sheet(false); render(); }
  });
  document.addEventListener("DOMContentLoaded", function () { stick(); age = root.dataset.age || age; if (!has("band")) resetF(age); render(); });
})();
