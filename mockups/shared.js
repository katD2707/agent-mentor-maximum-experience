// Mockup helpers: reviewer toolbar state, age / language / theme switching, icons.
// Everything here is mock-only; the real app gets age + language from Settings.
(function () {
  const root = document.documentElement;
  const store = {
    get(k) { try { return localStorage.getItem("mentor-mock-" + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem("mentor-mock-" + k, v); } catch (e) {} },
  };

  // ---- icons (stroke, 24px grid) ----
  const P = {
    camera: '<path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.6l1.4-2h5l1.4 2h1.6A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5z"/><circle cx="12" cy="12.5" r="3.5"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
    book: '<path d="M4 5.5C4 4.7 4.7 4 5.5 4H11v15H5.5A1.5 1.5 0 0 1 4 17.5z"/><path d="M20 5.5c0-.8-.7-1.5-1.5-1.5H13v15h5.5c.8 0 1.5-.7 1.5-1.5z"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6" fill="currentColor"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M5.6 18.4l1.6-1.6M16.8 7.2l1.6-1.6"/>',
    back: '<path d="M15 5l-7 7 7 7"/>',
    next: '<path d="M9 5l7 7-7 7"/>',
    play: '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>',
    volume: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/>',
    file: '<path d="M6 3.5h8l4 4v13H6z"/><path d="M14 3.5v4h4"/>',
    image: '<rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m4 17 5-4.5 4 3.5 3-2.5 4 3.5"/>',
    send: '<path d="M4 12 20 4l-6 16-2.5-6.5z"/><path d="m11.5 13.5 3-3"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
    bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5h4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    chev: '<path d="m7 10 5 5 5-5"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    comment: '<path d="M5 5h14v10H10l-5 4z"/>',
    refresh: '<path d="M19 8a7.5 7.5 0 1 0 .5 6"/><path d="M19.5 3.5V8H15"/>',
    flame: '<path d="M12 21c-3.9 0-6.5-2.6-6.5-6.2 0-3.2 2.3-5.3 3.6-7.2.3 1.6 1 2.6 2 3.2C11.6 7.7 13 5 15.2 3c-.3 2.6.7 4.4 1.8 6 1 1.5 1.5 3 1.5 4.8C18.5 18.4 15.9 21 12 21z"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    chat: '<path d="M4.5 6.5A2.5 2.5 0 0 1 7 4h10a2.5 2.5 0 0 1 2.5 2.5v7A2.5 2.5 0 0 1 17 16h-6l-4.5 4v-4H7a2.5 2.5 0 0 1-2.5-2.5z"/>',
    mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5"/>',
    up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
    chart: '<path d="M4 20h16"/><path d="M7 16v-4M12 16V8M17 16V5"/>',
    user: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"/>',
    lock: '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    flag: '<path d="M6 21V4M6 4h11l-2 4 2 4H6"/>',
    trash: '<path d="M5 7h14M10 7V5h4v2M7 7l1 13h8l1-13"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 2.5 14.4 0 17M12 3.5c-2.5 2.6-2.5 14.4 0 17"/>',
    text: '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
    video: '<rect x="3.5" y="6" width="12" height="12" rx="2"/><path d="m15.5 10.5 5-3v9l-5-3z"/>',
    quiz: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.4"/><circle cx="12" cy="16.6" r=".6" fill="currentColor"/>',
    download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    layers: '<path d="m12 4 8.5 4.5L12 13 3.5 8.5z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5"/>',
  };
  function svg(name, cls) {
    return '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' + (cls ? ' class="' + cls + '"' : "") + ">" + (P[name] || "") + "</svg>";
  }
  window.mentorIcon = svg;

  // ---- age band from the birth year, fixed at first run. The grade moves up on its own each school year
  //      (Vietnamese school year starts in September; grade 1 is the year a child turns 6). ----
  function mentorAge(birthYear, at) {
    const d = at || mentorAge.now();
    const schoolYear = d.getMonth() >= 8 ? d.getFullYear() : d.getFullYear() - 1;
    const grade = schoolYear - birthYear - 5;
    // before grade 1 counts as primary; after grade 12 as university. Worked out in the background, never shown.
    const band = grade <= 5 ? "tieu-hoc" : grade <= 9 ? "thcs" : grade <= 12 ? "thpt" : "dai-hoc";
    return { grade, band };
  }
  // the reviewer can look ahead ("year" in the mock toolbar); the real app uses today's date
  mentorAge.now = () => {
    const y = Number(store.get("previewYear")), d = new Date();
    if (y) d.setFullYear(y);
    return d;
  };
  mentorAge.saved = () => Number(store.get("birthYear")) || null;
  mentorAge.save = (y) => { store.set("birthYear", String(y)); set("age", mentorAge(y).band, true); };
  window.mentorAge = mentorAge;
  function paintIcons(scope) {
    (scope || document).querySelectorAll("i[data-i]").forEach((el) => {
      el.outerHTML = svg(el.dataset.i, el.className);
    });
  }

  // ---- i18n: elements carry data-en; Vietnamese is the source text ----
  function applyLang(lang) {
    document.querySelectorAll("[data-en]").forEach((el) => {
      if (el.dataset.vi === undefined) el.dataset.vi = el.innerHTML;
      el.innerHTML = lang === "en" ? el.dataset.en : el.dataset.vi;
    });
    document.querySelectorAll("[data-en-ph]").forEach((el) => {
      if (el.dataset.viPh === undefined) el.dataset.viPh = el.placeholder;
      el.placeholder = lang === "en" ? el.dataset.enPh : el.dataset.viPh;
    });
    root.lang = lang === "en" ? "en" : "vi";
  }

  // ---- conditional blocks: data-when="age=tieu-hoc|thcs; state=loi" ----
  function applyWhen() {
    if (!root.dataset.app) root.dataset.app = new URLSearchParams(location.search).get("app") || "desktop"; // the update row is desktop-only
    document.querySelectorAll("[data-when]").forEach((el) => {
      const ok = el.dataset.when.split(";").every((cond) => {
        const [k, vals] = cond.trim().split("=");
        return vals.split("|").includes(root.dataset[k]);
      });
      el.hidden = !ok;
    });
  }

  function set(key, value, persist) {
    root.dataset[key] = value;
    if (persist) store.set(key, value);
    document.querySelectorAll('.mock-seg button[data-set^="' + key + ':"], .set-pop button[data-set^="' + key + ':"]').forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.set === key + ":" + value));
    });
    if (key === "lang") applyLang(value);
    applyWhen();
    document.dispatchEvent(new CustomEvent("mock:change", { detail: { key, value } }));
  }
  window.mockSet = set;

  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-set]");
    if (!b) return;
    e.preventDefault();
    const [k, v] = b.dataset.set.split(":");
    set(k, v, k === "age" || k === "lang" || k === "theme");
  });

  // ---- settings: a small top-right button opens this popover (no settings page) ----
  function buildSettings() {
    const btn = document.querySelector("[data-settings]");
    if (!btn) return;
    const pop = document.createElement("div");
    pop.className = "set-pop";
    pop.id = "set-pop";
    pop.setAttribute("data-mascot-avoid", "");
    pop.hidden = true;
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", "Cài đặt");
    const teacher = btn.dataset.settings === "teacher";
    pop.innerHTML =
      (teacher ? "" :
      '<div class="set-row"><span class="set-label" data-en="Born in">Năm sinh</span><span class="set-birth"></span></div>') +
      '<div class="set-row"><span class="set-label" data-en="Language">Ngôn ngữ</span><span class="set-chips">' +
      '<button data-set="lang:vi">Tiếng Việt</button><button data-set="lang:en">English</button></span></div>' +
      '<div class="set-row"><span class="set-label" data-en="Theme">Nền</span><span class="set-chips">' +
      '<button data-set="theme:auto" data-en="Auto">Theo máy</button><button data-set="theme:light" data-en="Light">Sáng</button><button data-set="theme:dark" data-en="Dark">Tối</button></span></div>' +
      (teacher ? "" :
      '<div class="set-row"><span class="set-label" data-en="Study reminders">Nhắc học</span>' +
      '<button class="set-switch" role="switch" aria-checked="true" aria-label="Nhắc học"></button></div>' +
      '<div class="set-row set-quiet"><span class="set-label" data-en="Quiet for">Tạm im lặng</span><span class="set-chips">' +
      '<button data-quiet="30" data-en="30 min">30 phút</button><button data-quiet="60" data-en="1 hour">1 giờ</button>' +
      '<button data-quiet="120" data-en="2 hours">2 giờ</button><button data-quiet="tomorrow" data-en="Until tomorrow">Đến mai</button>' +
      '<button data-quiet="week" data-en="This week">Tuần này</button><button data-quiet="custom" data-en="Custom">Tùy chọn</button></span>' +
      '<span class="quiet-custom" hidden>' +
      '<span class="set-chips qc-days"><button data-qday="0" aria-pressed="true" data-en="Today">Hôm nay</button><button data-qday="1" aria-pressed="false" data-en="Tomorrow">Ngày mai</button><button data-qday="2" aria-pressed="false" data-en="In 2 days">Ngày kia</button></span>' +
      '<span class="qc-time"><button type="button" class="qc-step" data-qstep="-30" aria-label="Sớm hơn 30 phút">−</button><output class="qc-out" aria-live="polite">21:00</output><button type="button" class="qc-step" data-qstep="30" aria-label="Muộn hơn 30 phút">+</button>' +
      '<button type="button" class="quiet-ok" data-en="Set">Đặt</button></span></span>' +
      '<span class="quiet-status" hidden></span></div>') +
      '<div class="set-row set-srcs" data-when="age=dai-hoc"><span class="set-label" data-en="Paper sources">Nguồn tìm paper</span>' +
      '<span class="set-src"><span>arXiv <span data-en="(always on)">(luôn bật)</span></span></span>' +
      '<span class="set-src"><span>Semantic Scholar: <span data-src-state="s2"></span></span><button type="button" class="set-srcbtn" data-src-open="s2" data-src-act="s2"></button></span>' +
      '<span class="set-src"><span>Asta: <span data-src-state="asta"></span></span><button type="button" class="set-srcbtn" data-src-open="asta" data-src-act="asta"></button></span></div>' +
      '<div class="set-row set-upd" data-when="app=desktop"><span class="set-label" data-en="Updates">Cập nhật</span>' +
      '<span class="upd-line"><button type="button" class="set-chip-btn upd-check" data-en="Check for updates">Kiểm tra cập nhật</button><span class="upd-state" role="status" aria-live="polite"></span></span>' +
      '<label class="upd-beta"><span data-en="Try new versions early (beta)">Dùng thử bản mới sớm (beta)</span><button class="set-switch" role="switch" aria-checked="false" aria-label="Beta"></button></label></div>' +
      '<div class="set-row"><span class="set-label" data-en="Mực\'s tips">Hướng dẫn của Mực</span>' +
      '<button type="button" class="set-chip-btn set-replay" data-en="Show them again">Xem lại từ đầu</button></div>' +
      '<p class="set-foot"><span data-en="Mentor 1.4.2, up to date">Mentor 1.4.2, bản mới nhất</span>' +
      '<a href="hs-00-dang-nhap.html" data-en="Log out">Đăng xuất</a></p>';
    document.body.appendChild(pop);
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", "set-pop");
    const place = () => {
      const r = btn.getBoundingClientRect();
      pop.style.top = r.bottom + window.scrollY + 8 + "px";
      pop.style.right = Math.max(12, document.documentElement.clientWidth - r.right) + "px";
    };
    const close = () => { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); };
    pop.querySelector(".set-replay").addEventListener("click", () => {
      close();
      document.dispatchEvent(new CustomEvent("mascot:replay"));
    });
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (pop.hidden) { place(); pop.hidden = false; btn.setAttribute("aria-expanded", "true"); }
      else close();
    });
    // quiet hours, like Teams "pause notifications": a duration or a custom end time
    const quietRow = pop.querySelector(".set-quiet");
    const fmt = (d) => {
      const en = root.lang === "en";
      const days = en ? ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] : ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
      const hm = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
      const sameDay = d.toDateString() === new Date().toDateString();
      return sameDay ? hm : hm + " " + days[d.getDay()] + " " + d.getDate() + "/" + (d.getMonth() + 1);
    };
    const renderQuiet = () => {
      if (!quietRow) return;
      const until = Number(store.get("quietUntil") || 0);
      const on = until > Date.now();
      const st = quietRow.querySelector(".quiet-status");
      st.hidden = !on;
      quietRow.querySelectorAll("[data-quiet]").forEach((b) => b.setAttribute("aria-pressed", String(on && b.dataset.quiet === store.get("quietPick"))));
      if (on) {
        const en = root.lang === "en";
        st.innerHTML = '<span>' + (en ? "Quiet until " : "Im lặng đến ") + fmt(new Date(until)) + '</span><button type="button" class="quiet-off">' + (en ? "Turn back on" : "Bật lại") + "</button>";
      }
      btn.classList.toggle("is-quiet", on);
    };
    const setQuiet = (pick, untilMs) => { store.set("quietUntil", String(untilMs)); store.set("quietPick", pick); renderQuiet(); };
    // update check (desktop): "Checking…", then "up to date" or the version that starts downloading
    const updState = pop.querySelector(".upd-state");
    const updBtn = pop.querySelector(".upd-check");
    if (updBtn) updBtn.addEventListener("click", () => {
      const en = root.lang === "en";
      updBtn.disabled = true;
      updState.textContent = en ? "Checking…" : "Đang kiểm tra…";
      setTimeout(() => {
        updBtn.disabled = false;
        const beta = pop.querySelector(".upd-beta .set-switch").getAttribute("aria-checked") === "true";
        updState.textContent = beta ? (en ? "Downloading 1.5.0-beta…" : "Đang tải bản 1.5.0-beta…") : (en ? "You are on the latest version (1.4.2)" : "Bạn đang dùng bản mới nhất (1.4.2)");
        if (beta) showUpdateNote();
      }, 900);
    });
    // the quiet progress line at the bottom of the window while a version downloads
    function showUpdateNote() {
      if (document.querySelector(".update-note")) return;
      const en = root.lang === "en";
      const n = document.createElement("div");
      n.className = "update-note";
      n.setAttribute("role", "status");
      n.innerHTML = '<span>' + (en ? "Downloading the new version" : "Đang tải bản mới") + ' <b class="upd-pct">0%</b></span><span class="upd-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i></i></span>';
      document.body.appendChild(n);
      let p = 0;
      const tick = setInterval(() => {
        p = Math.min(100, p + 7);
        n.querySelector(".upd-pct").textContent = p + "%";
        n.querySelector("i").style.width = p + "%";
        n.querySelector(".upd-bar").setAttribute("aria-valuenow", String(p));
        if (p === 100) { clearInterval(tick); n.querySelector("span").textContent = en ? "New version ready; it restarts when you are free" : "Bản mới đã sẵn sàng, sẽ khởi động lại khi bạn rảnh"; n.querySelector(".upd-bar").remove(); }
      }, 220);
    }
    if (new URLSearchParams(location.search).get("open") === "update") setTimeout(showUpdateNote, 300);
    pop.addEventListener("click", (e) => {
      const sw = e.target.closest(".set-switch");
      if (sw) sw.setAttribute("aria-checked", sw.getAttribute("aria-checked") === "true" ? "false" : "true");
      const q = e.target.closest("[data-quiet]");
      if (q) {
        const v = q.dataset.quiet, now = new Date();
        const custom = quietRow.querySelector(".quiet-custom");
        custom.hidden = v !== "custom";
        if (v === "custom") { custom.querySelector("[data-qday]").focus(); return; }
        let t;
        if (v === "tomorrow") { t = new Date(now); t.setDate(t.getDate() + 1); t.setHours(7, 0, 0, 0); }
        else if (v === "week") { t = new Date(now); t.setDate(t.getDate() + ((7 - t.getDay()) % 7 || 7)); t.setHours(23, 59, 0, 0); }
        else t = new Date(now.getTime() + Number(v) * 60000);
        setQuiet(v, t.getTime());
      }
      const day = e.target.closest("[data-qday]");
      if (day) quietRow.querySelectorAll("[data-qday]").forEach((b) => b.setAttribute("aria-pressed", String(b === day)));
      const step = e.target.closest("[data-qstep]");
      if (step) {
        const out = quietRow.querySelector(".qc-out");
        const [h, m] = out.textContent.split(":").map(Number);
        const mins = (h * 60 + m + Number(step.dataset.qstep) + 1440) % 1440;
        out.textContent = String(Math.floor(mins / 60)).padStart(2, "0") + ":" + String(mins % 60).padStart(2, "0");
      }
      if (e.target.closest(".quiet-ok")) {
        const d = Number(quietRow.querySelector('[data-qday][aria-pressed="true"]').dataset.qday);
        const [h, m] = quietRow.querySelector(".qc-out").textContent.split(":").map(Number);
        const t = new Date(); t.setDate(t.getDate() + d); t.setHours(h, m, 0, 0);
        if (t.getTime() > Date.now()) { setQuiet("custom", t.getTime()); quietRow.querySelector(".quiet-custom").hidden = true; }
      }
      if (e.target.closest(".quiet-off")) { store.set("quietUntil", "0"); store.set("quietPick", ""); renderQuiet(); }
    });
    // birth year is read-only after the first run
    const birth = pop.querySelector(".set-birth");
    const renderBirth = () => { if (birth) birth.textContent = String(mentorAge.saved() || 2010); };
    document.addEventListener("mock:change", () => { renderQuiet(); renderBirth(); });
    renderQuiet();
    renderBirth();
    document.addEventListener("click", (e) => { if (!pop.contains(e.target)) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !pop.hidden) { close(); btn.focus(); } });
  }

  // ---- Paper sources: arXiv (through DeepTutor) is always on; Semantic Scholar and Asta are optional ----
  // Each optional source has its own key, entered in one shared dialog. Mock only: a key containing "bad" is
  // rejected; nothing real is stored (only the connected flags, one per source).
  const sources = (function () {
    const t = (vi, e) => (root.lang === "en" ? e : vi);
    const DEF = {
      asta: {
        name: "Asta", help: "https://allenai.org/asta",
        descNew: () => t("Tìm sâu hơn trong đoạn trích toàn văn từ Asta của Ai2, bằng key của riêng bạn.", "Deeper search over full-text snippets from Ai2 Asta, using your own key."),
        descOn: () => t("Asta đã được thêm. Mentor tìm ở Asta trước, rồi đến các nguồn còn lại.", "Asta is added. Mentor searches Asta first, then the other sources.")
      },
      s2: {
        name: "Semantic Scholar", help: "https://www.semanticscholar.org/product/api#api-key-form",
        descNew: () => t("Thêm số trích dẫn và TL;DR cho kết quả tìm, bằng key Semantic Scholar của riêng bạn.", "Add citation counts and TL;DRs to search results, using your own Semantic Scholar key."),
        descOn: () => t("Semantic Scholar đã được thêm. Kết quả có số trích dẫn và TL;DR, bài liên quan có cả hai chiều trích dẫn.", "Semantic Scholar is added. Results show citation counts and TL;DRs, and related papers show both citation directions.")
      }
    };
    const ORDER = ["asta", "s2"];
    const on = (id) => store.get(id) === "1";
    // Search depth, picked like a reasoning-effort level: each level adds one source and needs that source's key.
    const LEVELS = [
      { need: null, name: () => t("Nhanh", "Quick"), desc: () => t("arXiv: tên bài, tác giả, abstract. Vài giây.", "arXiv: titles, authors, abstracts. A few seconds.") },
      { need: "s2", name: () => t("Kỹ", "Thorough"), desc: () => t("Thêm Semantic Scholar: số trích dẫn, TL;DR, cả bài ngoài arXiv.", "Adds Semantic Scholar: citation counts, TL;DRs, papers beyond arXiv.") },
      { need: "asta", name: () => t("Sâu", "Deep"), desc: () => t("Thêm Asta: tìm cả trong toàn văn. Chậm hơn.", "Adds Asta: searches inside full texts. Slower.") }
    ];
    const usable = (i) => !LEVELS[i].need || on(LEVELS[i].need);
    function level() {
      let l = Math.min(2, Math.max(0, parseInt(store.get("srcLevel") || "2", 10) || 0));
      while (l > 0 && !usable(l)) l--;
      return l;
    }
    const use = (id) => on(id) && level() >= (id === "asta" ? 2 : 1);
    let pendingLevel = -1, depthPop = null, depthBtn = null;
    const meter = (l) => '<span class="depth-m" aria-hidden="true">' + [0, 1, 2].map((i) => "<i" + (i <= l ? ' class="on"' : "") + "></i>").join("") + "</span>";
    let back, dlg, opener, cur = "s2", mode, busy, value = "", err = "", shown = false, inerted = [];
    function paint() {
      const active = ORDER.filter(on).map((id) => DEF[id].name).concat("arXiv");
      document.querySelectorAll("[data-asta-hint]").forEach((el) => { el.textContent = t("Kết quả từ ", "Results from ") + active.join(" · "); });
      document.querySelectorAll("[data-asta-rel]").forEach((el) => {
        const names = ["s2", "asta"].filter(on).map((id) => DEF[id].name);
        el.textContent = names.length ? t("Từ ", "From ") + names.join(" · ") : "";
      });
      document.querySelectorAll("[data-src-chip]").forEach((el) => {
        const id = el.dataset.srcChip, n = DEF[id].name, c = on(id);
        el.querySelector(".pill").innerHTML = c ? n + " " + svg("check") : svg("plus") + " " + n;
        el.dataset.on = c ? "1" : "0";
        el.setAttribute("aria-label", c ? t(n + " đã thêm, mở cài đặt", n + " added, open settings") : t("Thêm " + n, "Add " + n));
      });
      document.querySelectorAll("[data-src-state]").forEach((el) => { el.textContent = on(el.dataset.srcState) ? t("đã thêm", "added") : t("chưa thêm", "not added"); });
      document.querySelectorAll("[data-src-act]").forEach((el) => {
        const id = el.dataset.srcAct;
        el.textContent = on(id) ? t("Gỡ", "Remove") : t("Thêm", "Add");
        el.setAttribute("aria-label", (on(id) ? t("Gỡ ", "Remove ") : t("Thêm ", "Add ")) + DEF[id].name);
      });
      const m = on("asta") && on("s2") ? "both" : on("asta") ? "asta" : on("s2") ? "s2" : "arxiv";
      document.querySelectorAll("[data-src-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.srcMode === m)));
      root.dataset.srcs = m;
      const lv = level(), L = LEVELS[lv];
      document.querySelectorAll("[data-src-depth]").forEach((b) => {
        b.innerHTML = meter(lv) + '<span class="depth-n">' + L.name() + "</span>" + svg("chev");
        b.setAttribute("aria-label", t("Độ sâu tìm: ", "Search depth: ") + L.name() + ". " + L.desc());
      });
      if (depthPop && !depthPop.hidden) renderDepth();
      document.dispatchEvent(new CustomEvent("sources:change"));
    }
    function toast(msg) {
      const old = document.querySelector(".asta-toast"); if (old) old.remove();
      const el = document.createElement("div");
      el.className = "toast asta-toast"; el.setAttribute("role", "status"); el.textContent = msg;
      document.body.appendChild(el);
      setTimeout(() => el.remove(), 2600);
    }
    function render() {
      const d = DEF[cur], n = d.name, connected = mode === "connected";
      dlg.innerHTML =
        '<div class="asta-head"><h2 id="asta-t">' + (connected ? n : t("Thêm " + n, "Add " + n)) + "</h2>" +
        (connected ? '<button type="button" class="icon-btn asta-x" data-a="close" aria-label="' + t("Đóng", "Close") + '">' + svg("x") + "</button>" : "") + "</div>" +
        '<p id="asta-d" class="asta-desc">' + (connected ? d.descOn() : d.descNew()) + "</p>" +
        (connected ? "" :
          '<div class="asta-fieldwrap"><label for="asta-key" class="set-label">' + t("Key " + n, n + " key") + "</label>" +
          '<div class="asta-field' + (err ? " bad" : "") + '"><input id="asta-key" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="' + t("Dán key vào đây", "Paste your key here") + '"' +
          (err ? ' aria-invalid="true" aria-describedby="asta-e"' : "") + (busy ? " disabled" : "") + ">" +
          '<button type="button" class="asta-eye" data-a="eye" aria-pressed="false" aria-label="' + t("Hiện key", "Show key") + '">' + svg("eye") + "</button></div>" +
          '<p id="asta-e" class="asta-err" role="alert">' + (err ? "<span>" + err + "</span>" : "") + "</p>" +
          '<a class="asta-help" href="' + d.help + '" target="_blank" rel="noopener">' + t("Lấy key ở đâu?", "Where do I get a key?") + "</a></div>") +
        '<div class="asta-actions">' + (connected
          ? '<button type="button" class="btn btn-ghost asta-danger" data-a="remove">' + t("Gỡ " + n, "Remove " + n) + '</button><button type="button" class="btn btn-primary" data-a="change">' + t("Đổi key", "Change key") + "</button>"
          : '<button type="button" class="btn btn-ghost" data-a="close"' + (busy ? " disabled" : "") + ">" + t("Hủy", "Cancel") + '</button><button type="button" class="btn btn-primary" data-a="save" ' + (busy ? 'aria-busy="true" disabled' : "") + ">" + (busy ? '<span class="asta-spin" aria-hidden="true"></span>' + t("Đang kiểm tra", "Checking") : t("Lưu", "Save")) + "</button>") + "</div>";
      const input = dlg.querySelector("#asta-key"); if (input) input.value = value;
    }
    function open(from, o) {
      o = o || {};
      if (!back) {
        back = document.createElement("div"); back.className = "asta-back"; back.hidden = true;
        dlg = document.createElement("div"); dlg.className = "asta-dlg"; dlg.setAttribute("role", "dialog"); dlg.setAttribute("aria-modal", "true");
        dlg.setAttribute("aria-labelledby", "asta-t"); dlg.setAttribute("aria-describedby", "asta-d"); dlg.tabIndex = -1;
        back.appendChild(dlg); document.body.appendChild(back);
        back.addEventListener("mousedown", (e) => { if (e.target === back && !busy) close(); });
        dlg.addEventListener("click", onClick);
        dlg.addEventListener("input", (e) => {
          if (e.target.id !== "asta-key") return;
          value = e.target.value;
          if (err) { err = ""; const pos = e.target.selectionStart, shownTxt = e.target.type; render(); const i = dlg.querySelector("#asta-key"); i.type = shownTxt; i.focus(); i.setSelectionRange(pos, pos); }
        });
        dlg.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.id === "asta-key") { e.preventDefault(); save(); } });
        document.addEventListener("keydown", onKey, true);
      }
      if (!shown) opener = from || document.activeElement;
      cur = o.src || cur;
      mode = o.mode || (on(cur) ? "connected" : "enter"); busy = !!o.busy; value = o.value || ""; err = o.error || "";
      render();
      if (!shown) {
        shown = true; back.hidden = false;
        inerted = [...document.body.children].filter((n) => n !== back && !n.inert);
        inerted.forEach((n) => { n.inert = true; });
      }
      (dlg.querySelector("#asta-key:not([disabled])") || dlg.querySelector(".btn-primary:not([disabled])") || dlg).focus();
    }
    function close(silent) {
      if (!shown) return;
      if (!busy) pendingLevel = -1;
      shown = false; busy = false; back.hidden = true;
      inerted.forEach((n) => { n.inert = false; }); inerted = [];
      if (opener && document.contains(opener) && !silent) opener.focus();
    }
    function onKey(e) {
      if (!shown) return;
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); if (!busy) close(); return; }
      if (e.key !== "Tab") return;
      const f = [...dlg.querySelectorAll("a[href],button,input")].filter((n) => !n.disabled && n.offsetParent !== null);
      if (!f.length) { e.preventDefault(); dlg.focus(); return; }
      const a = f[0], z = f[f.length - 1];
      if (e.shiftKey && (document.activeElement === a || document.activeElement === dlg)) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    }
    function save() {
      if (busy) return;
      const n = DEF[cur].name;
      value = (dlg.querySelector("#asta-key") || {}).value || "";
      if (!value.trim()) { err = t("Dán key " + n + " vào ô trên", "Paste your " + n + " key above"); render(); dlg.querySelector("#asta-key").focus(); return; }
      err = ""; busy = true; render(); dlg.focus();
      setTimeout(() => {
        if (!shown) return;
        busy = false;
        if (/bad/i.test(value)) { err = t("Key không đúng hoặc đã hết hạn", "The key is wrong or has expired"); render(); dlg.querySelector("#asta-key").focus(); return; }
        store.set(cur, "1"); value = "";
        if (pendingLevel >= 0 && LEVELS[pendingLevel].need === cur) store.set("srcLevel", String(pendingLevel));
        pendingLevel = -1; close(); paint(); toast(t("Đã thêm " + n, n + " added"));
      }, 900);
    }
    function onClick(e) {
      const b = e.target.closest("[data-a]"); if (!b) return;
      const a = b.dataset.a;
      if (a === "close") close();
      else if (a === "save") save();
      else if (a === "change") { mode = "enter"; value = ""; err = ""; render(); dlg.querySelector("#asta-key").focus(); }
      else if (a === "remove") { const n = DEF[cur].name; store.set(cur, "0"); close(); paint(); toast(t("Đã gỡ " + n, n + " removed")); }
      else if (a === "eye") {
        const inp = dlg.querySelector("#asta-key"), show = inp.type === "password";
        inp.type = show ? "text" : "password"; b.setAttribute("aria-pressed", String(show));
        b.setAttribute("aria-label", show ? t("Ẩn key", "Hide key") : t("Hiện key", "Show key")); inp.focus();
      }
    }
    function renderDepth() {
      const lv = level();
      depthPop.innerHTML = '<p class="depth-h" id="depth-h">' + t("Tìm sâu đến đâu", "How deep to search") + "</p>" + LEVELS.map((L, i) => {
        const ok = usable(i), sel = i === lv;
        return '<button type="button" role="menuitemradio" class="depth-i" data-depth="' + i + '" aria-checked="' + sel + '"' + (ok ? "" : ' data-locked="1"') + ">" +
          meter(i) + '<span class="depth-t"><b>' + L.name() + "</b><span>" + L.desc() + "</span></span>" +
          (sel ? '<span class="depth-ok">' + svg("check") + "</span>" : ok ? '<span class="depth-ok"></span>' : '<span class="depth-key">' + svg("lock") + t("Cần key", "Needs key") + "</span>") + "</button>";
      }).join("");
    }
    function openDepth(btn) {
      depthBtn = btn;
      if (!depthPop) {
        depthPop = document.createElement("div"); depthPop.className = "depth-pop"; depthPop.setAttribute("role", "menu"); depthPop.hidden = true;
        depthPop.setAttribute("aria-labelledby", "depth-h"); depthPop.setAttribute("data-mascot-avoid", "");
        depthPop.addEventListener("keydown", (e) => {
          const items = [...depthPop.querySelectorAll(".depth-i")], i = items.indexOf(document.activeElement);
          if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus(); }
          else if (e.key === "Home" || e.key === "End") { e.preventDefault(); items[e.key === "Home" ? 0 : items.length - 1].focus(); }
          else if (e.key === "Escape" || e.key === "Tab") { if (e.key === "Escape") e.preventDefault(); closeDepth(e.key === "Escape"); }
        });
      }
      btn.parentElement.appendChild(depthPop);
      renderDepth(); depthPop.hidden = false; btn.setAttribute("aria-expanded", "true");
      (depthPop.querySelector('[aria-checked="true"]') || depthPop.querySelector(".depth-i")).focus();
    }
    function closeDepth(refocus) {
      if (!depthPop || depthPop.hidden) return;
      depthPop.hidden = true;
      if (depthBtn) { depthBtn.setAttribute("aria-expanded", "false"); if (refocus) depthBtn.focus(); }
    }
    document.addEventListener("click", (e) => {
      const db = e.target.closest("[data-src-depth]");
      if (db) { if (depthPop && !depthPop.hidden) closeDepth(true); else openDepth(db); return; }
      const di = e.target.closest("[data-depth]");
      if (di) {
        const i = +di.dataset.depth;
        closeDepth(!di.dataset.locked);
        if (di.dataset.locked) { pendingLevel = i; open(depthBtn, { src: LEVELS[i].need, mode: "enter" }); return; }
        store.set("srcLevel", String(i)); paint(); return;
      }
      if (depthPop && !depthPop.hidden && !depthPop.contains(e.target)) closeDepth(false);
      const c = e.target.closest("[data-src-chip]");
      if (c) { open(c, { src: c.dataset.srcChip }); return; }
      const d = e.target.closest("[data-src-open]");
      if (d) {
        const pop = document.getElementById("set-pop"), gear = document.querySelector("[data-settings]");
        if (pop) { pop.hidden = true; if (gear) gear.setAttribute("aria-expanded", "false"); }
        open(gear || d, { src: d.dataset.srcOpen });
        return;
      }
      const mm = e.target.closest("[data-src-mode]");
      if (mm) {
        const v = mm.dataset.srcMode; close(true);
        store.set("s2", v === "s2" || v === "both" ? "1" : "0"); store.set("asta", v === "asta" || v === "both" ? "1" : "0"); paint(); return;
      }
      const demo = e.target.closest("[data-src-demo]");
      if (demo) {
        const [id, v] = demo.dataset.srcDemo.split(":");
        if (v === "connected") { store.set(id, "1"); paint(); open(demo, { src: id, mode: "connected" }); return; }
        store.set(id, "0"); paint();
        if (v === "empty") open(demo, { src: id, mode: "enter" });
        if (v === "checking") open(demo, { src: id, mode: "enter", busy: true, value: "demo-key-0000" });
        if (v === "invalid") open(demo, { src: id, mode: "enter", value: "bad-demo-key", error: t("Key không đúng hoặc đã hết hạn", "The key is wrong or has expired") });
      }
    }, true);
    document.addEventListener("mock:change", (e) => { if (e.detail.key === "lang") { paint(); if (shown) render(); } });
    return { on, use, level, paint, open };
  })();
  window.mockSources = sources;

  document.addEventListener("DOMContentLoaded", () => {
    buildSettings();
    paintIcons();
    sources.paint();
    const q = new URLSearchParams(location.search);
    const defaults = root.dataset;
    set("lang", q.get("lang") || store.get("lang") || "vi", false);
    // pages built for one age (sample courses) declare data-age-fixed and always win; otherwise the saved
    // birth year decides, recomputed on every launch so the band changes by itself as years pass
    const born = mentorAge.saved();
    set("age", defaults.ageFixed || q.get("age") || (born && mentorAge(born).band) || store.get("age") || defaults.age || "thpt", false);
    // reviewer toolbar "year:2030" looks ahead in time
    document.addEventListener("mock:change", (e) => {
      if (e.detail.key !== "year") return;
      store.set("previewYear", e.detail.value === "now" ? "" : e.detail.value);
      const b = mentorAge.saved();
      if (b && !defaults.ageFixed) set("age", mentorAge(b).band, false);
    });
    set("year", store.get("previewYear") || "now", false);
    set("theme", q.get("theme") || store.get("theme") || "auto", false);
    if (defaults.state) set("state", q.get("state") || defaults.state, false);
    else applyWhen();
    // reviewer shortcut: ?open=settings (or settings-custom) opens the gear popover
    const open = q.get("open");
    if (open && open.startsWith("settings")) {
      const b = document.querySelector("[data-settings]");
      if (b) {
        b.click();
        if (open === "settings-custom") { const c = document.querySelector('[data-quiet="custom"]'); if (c) c.click(); }
      }
    }
  });
})();

// ===================== Motion & effects =====================
(function () {
  const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const COLORS = ["#5A4BC0", "#F0D76E", "#E07A6E", "#5BB592", "#9C8AFF", "#F2A65A"];

  // confetti burst from a point; small for small wins, bigger for big ones
  function burst(x, y, n) {
    if (reduced() || !document.body.animate) return;
    for (let i = 0; i < n; i++) {
      const d = document.createElement("i");
      d.className = "confetti";
      d.style.left = x + "px"; d.style.top = y + "px";
      d.style.background = COLORS[i % COLORS.length];
      document.body.appendChild(d);
      const a = Math.random() * Math.PI * 2, v = 60 + Math.random() * 110;
      const dx = Math.cos(a) * v, dy = Math.sin(a) * v - 70;
      d.animate([
        { transform: "translate(-50%,-50%) rotate(0)", opacity: 1 },
        { transform: `translate(${dx}px, ${dy + 140}px) rotate(${Math.random() * 720 - 360}deg)`, opacity: 0 },
      ], { duration: 900 + Math.random() * 500, easing: "cubic-bezier(.2,.7,.4,1)" }).onfinish = () => d.remove();
    }
  }
  window.mentorConfetti = burst;
  const centerOf = (el) => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };

  function countUp(el) {
    const node = [...el.childNodes].find((c) => c.nodeType === 3 && /\d/.test(c.textContent));
    if (!node) return;
    const m = node.textContent.match(/^(\D*)(\d+)(.*)$/s);
    if (!m) return;
    const target = Number(m[2]), t0 = performance.now(), dur = 900;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      node.textContent = m[1] + Math.round(target * e) + m[3];
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  document.addEventListener("DOMContentLoaded", () => {
    // staggered arrival
    document.querySelectorAll(".main, .courses, .results, .goals, .rows, .grid4, .steps, .kid-shelf, .week, .lessons").forEach((c) => {
      c.classList.add("stagger");
      [...c.children].forEach((ch, i) => ch.style.setProperty("--i", Math.min(i, 12)));
    });
    // highlighter under the one headline that matters
    document.querySelectorAll(".today h2, .quick h2, .hello, .goal.main h3, .result h1").forEach((h) => {
      if (h.querySelector(".marker")) return;
      h.innerHTML = '<span class="marker">' + h.innerHTML + "</span>";
    });
    // numbers count up
    if (!reduced()) document.querySelectorAll(".pct, .score").forEach(countUp);

    // hub squares lean toward the pointer
    document.querySelectorAll(".tile").forEach((t) => {
      t.addEventListener("pointermove", (e) => {
        if (reduced() || e.pointerType !== "mouse") return;
        const r = t.getBoundingClientRect();
        t.style.setProperty("--ry", ((e.clientX - r.left) / r.width - .5) * 8 + "deg");
        t.style.setProperty("--rx", -((e.clientY - r.top) / r.height - .5) * 8 + "deg");
      });
      t.addEventListener("pointerleave", () => { t.style.setProperty("--rx", "0deg"); t.style.setProperty("--ry", "0deg"); });
    });
  });

  // ripple where the finger/mouse lands on a button
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".btn");
    if (!b || reduced()) return;
    const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height) * 2.2;
    const rp = document.createElement("span");
    rp.className = "ripple";
    rp.style.width = rp.style.height = s + "px";
    rp.style.left = e.clientX - r.left - s / 2 + "px";
    rp.style.top = e.clientY - r.top - s / 2 + "px";
    b.appendChild(rp);
    setTimeout(() => rp.remove(), 600);
  });

  // celebrations, checked after the page's own handlers have run
  document.addEventListener("click", (e) => {
    const t = e.target;
    setTimeout(() => {
      const opt = t.closest && t.closest(".opt");
      if (opt && opt.classList.contains("is-right")) return burst(...centerOf(opt), 26);
      const add = t.closest && t.closest("[data-add]");
      if (add && /Đã thêm|Added/.test(add.textContent)) return burst(...centerOf(add), 16);
      const pub = t.closest && t.closest(".btn-primary");
      if (pub && /Xuất bản|Publish/.test(pub.textContent)) return burst(...centerOf(pub), 34);
    }, 0);
  });
  document.addEventListener("submit", (e) => {
    if (e.target.id === "addForm") setTimeout(() => { const g = document.querySelector("#goals li:last-child"); if (g) burst(...centerOf(g), 24); }, 30);
  });
})();

// ===================== Back button =====================
// The top-left back arrow returns to the screen the student actually came from (e.g. a course page opened from
// search goes back to search, with its filters), not to a fixed page. The arrow's href stays as the fallback
// for a page opened directly. Mock-only trail in sessionStorage, because file:// pages get no referrer.
(function () {
  const KEY = "mentor-mock-trail";
  const read = () => { try { return JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch (e) { return []; } };
  const write = (t) => { try { sessionStorage.setItem(KEY, JSON.stringify(t.slice(-30))); } catch (e) {} };
  const page = (u) => u.split("#")[0];
  const here = page(location.href);
  let trail = read();
  if (trail.length > 1 && trail[trail.length - 2] === here) trail.pop();      // arrived by going back
  else if (trail[trail.length - 1] !== here) trail.push(here);                // a new screen
  write(trail);
  document.addEventListener("click", (e) => {
    const a = e.target.closest("header a.icon-btn, .topbar a.icon-btn");
    if (!a || !a.querySelector('svg, i[data-i="back"]') || a.hasAttribute("data-settings")) return;
    if (!a.innerHTML.includes("M15 5l-7 7 7 7") && !a.querySelector('i[data-i="back"]')) return;  // only the back arrow
    const t = read();
    if (t.length < 2) return;                                                  // opened directly: follow the href
    e.preventDefault();
    history.length > 1 ? history.back() : (location.href = t[t.length - 2]);
  }, true);
})();

// phone-width home strip for Mực (see shared.css); only shown at <= 480px
document.addEventListener('DOMContentLoaded', function () {
  ['mascot-bar', 'mascot-dock'].forEach(function (c) { var d = document.createElement('div'); d.className = c; d.setAttribute('aria-hidden', 'true'); document.body.appendChild(d); });
});
