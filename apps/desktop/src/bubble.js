// The floating Mentor bubble. Click toggles the chat panel, drag moves it (the shell snaps it to the
// nearest screen edge on release), right-click opens a small menu. All window work happens in Rust.
// The tile is the mascot (<mentor-mascot>, mascot.js); its state comes from the shell.
(() => {
  const invoke = window.__TAURI__.core.invoke;
  const bubble = document.getElementById("bubble");
  const badge = document.getElementById("badge");
  const mascot = document.getElementById("mascot");
  const DRAG_THRESHOLD = 4; // px before a press becomes a drag
  const ONE_SHOT = new Set(["wave", "celebrate"]);

  // ---------------------------------------------------------------- mascot

  let mascotReady = false;
  let pendingOnce = null;
  let baseState = "idle"; // what the shell wants when no one-shot is playing
  let playing = null; // the one-shot in progress, if any
  let lastOneShot = null; // one-shot hint already played for the current shell state

  function applyBase() {
    if (mascotReady && !playing && mascot.state !== baseState) mascot.state = baseState;
  }

  /** One-shot move (`wave`, `celebrate`) via el.play(), then back to the shell's state. Never while
   *  calm (the shell also never sends one then). */
  function playOnce(state) {
    if (!ONE_SHOT.has(state) || baseState === "calm") return;
    if (!mascotReady) {
      pendingOnce = state; // played once the element is defined
      return;
    }
    playing = state;
    mascot.play(state).then(
      (done) => {
        // Another state cut it short: that state already stands.
        if (playing === state) playing = null;
        if (!done || !done.interrupted) applyBase();
      },
      () => {
        playing = null;
        applyBase();
      },
    );
  }
  window.mentorMascotOnce = playOnce;

  // The element upgrades once mascot.js has run; without it the "M" glyph stays.
  if (window.customElements) {
    customElements.whenDefined("mentor-mascot").then(() => {
      mascotReady = true;
      document.body.classList.add("has-mascot");
      mascot.state = baseState;
      // Hello on app start (the shell creates this page once per launch).
      playOnce(pendingOnce || (baseState === "idle" ? "wave" : null));
      pendingOnce = null;
    });
  }

  // ---------------------------------------------------------------- state from the shell

  /** Called by the shell (WebviewWindow::eval) and on load. */
  window.mentorSetState = ({
    unread = 0,
    open = false,
    side = "right",
    signedIn = true,
    mascot: mascotState = "idle",
  } = {}) => {
    // Signed out ("always show" mode): outline look, no badge; a click opens the panel's login page.
    if (!signedIn) unread = 0;
    badge.hidden = unread <= 0;
    badge.textContent = unread > 9 ? "9+" : String(unread);
    bubble.classList.toggle("open", open);
    bubble.classList.toggle("signed-out", !signedIn);
    bubble.setAttribute("aria-expanded", String(open));
    // Speech-tail corner and badge follow the screen edge the shell snapped the bubble to.
    const left = side === "left";
    document.body.dataset.side = left ? "left" : "right";
    mascot.setAttribute("tail", left ? "left" : "right");
    const wanted = typeof mascotState === "string" ? mascotState : "idle";
    if (ONE_SHOT.has(wanted)) {
      // A nudge hinting `wave` (check-in) or `celebrate`: play it once when it starts, then rest.
      baseState = "idle";
      if (lastOneShot !== wanted) {
        lastOneShot = wanted;
        playOnce(wanted);
      }
    } else {
      lastOneShot = null;
      baseState = wanted;
      // A one-shot gives way to anything that is not idle (thinking, calm, a happy nudge).
      if (playing && baseState !== "idle") playing = null;
      applyBase();
    }
    if (!signedIn && !open) {
      const label = "Mentor: chưa đăng nhập — bấm để đăng nhập";
      bubble.setAttribute("aria-label", `${label} (Ctrl+Alt+M)`);
      bubble.title = `${label} · Ctrl+Alt+M`;
      return;
    }
    const action = open ? "Thu gọn Mentor" : "Mở Mentor";
    const news = unread > 0 ? `, ${unread} tin mới` : "";
    bubble.setAttribute("aria-label", `${action}${news} (Ctrl+Alt+M)`);
    bubble.title = `${action} · Ctrl+Alt+M`;
  };

  // ---------------------------------------------------------------- pointer and keyboard

  let press = null; // { id, x, y, dragging }
  let frame = 0;

  bubble.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    press = { id: e.pointerId, x: e.screenX, y: e.screenY, dragging: false };
    bubble.setPointerCapture(e.pointerId);
  });

  bubble.addEventListener("pointermove", (e) => {
    if (!press || e.pointerId !== press.id) return;
    if (!press.dragging) {
      if (Math.hypot(e.screenX - press.x, e.screenY - press.y) < DRAG_THRESHOLD) return;
      press.dragging = true;
      bubble.classList.add("dragging");
      void invoke("bubble_drag_start");
    }
    // The shell follows the cursor itself (physical pixels, any monitor DPI); just ask once per frame.
    if (!frame) {
      frame = requestAnimationFrame(() => {
        frame = 0;
        void invoke("bubble_drag_move");
      });
    }
  });

  function endPress(e, cancelled) {
    if (!press || e.pointerId !== press.id) return;
    const wasDrag = press.dragging;
    press = null;
    bubble.classList.remove("dragging");
    if (frame) {
      cancelAnimationFrame(frame);
      frame = 0;
    }
    if (wasDrag) void invoke("bubble_drag_end");
    else if (!cancelled) void invoke("bubble_click");
  }
  bubble.addEventListener("pointerup", (e) => endPress(e, false));
  bubble.addEventListener("pointercancel", (e) => endPress(e, true));
  bubble.addEventListener("lostpointercapture", (e) => endPress(e, true));

  bubble.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      void invoke("bubble_click");
    }
  });

  window.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    void invoke("bubble_menu");
  });

  invoke("bubble_state").then(window.mentorSetState, () => {});
})();
