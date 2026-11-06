// The speech balloon beside the bubble (window "balloon"). The shell drives it:
//   mentorBalloon.render(nudge)  lay out {key, title, body, actions}, report the height (balloon_ready)
//   mentorBalloon.reveal(place)  {key, side, anchorY}: slide out of the bubble, start the 12 s timer
//   mentorBalloon.hide()         go away (an action, ×, timeout, the chat opened, the bubble moved)
// The page reports clicks with balloon_action {key, action} and closing with balloon_close {key}.
// The window never takes focus by itself; once the user clicks into it, it is fully keyboard
// operable (Tab, Enter, Esc).
(() => {
  const invoke = window.__TAURI__.core.invoke;
  const AUTO_HIDE_MS = 12000;
  const RESUME_MIN_MS = 4000; // after hover/focus leaves, at least this long to come back to it
  const PAD_Y = 12 + 20; // card's top and bottom room in the window (balloon.css)

  const body = document.body;
  const card = document.getElementById("card");
  const title = document.getElementById("title");
  const text = document.getElementById("text");
  const actions = document.getElementById("actions");
  const content = document.getElementById("content");
  const close = document.getElementById("close");
  const live = document.getElementById("live");

  let current = null; // the nudge on screen or being laid out
  let busy = false; // a click was sent; ignore more until the next nudge

  // ---------------------------------------------------------------- auto-hide timer

  let timer = 0;
  let deadline = 0;
  let remaining = AUTO_HIDE_MS;
  let hovered = false;
  let focused = false;

  function stopTimer() {
    if (timer) clearTimeout(timer);
    timer = 0;
  }
  function startTimer(ms) {
    stopTimer();
    remaining = ms;
    deadline = Date.now() + ms;
    timer = setTimeout(() => {
      timer = 0;
      if (current && !hovered && !focused) finish("close");
    }, ms);
  }
  function pause() {
    if (!timer) return;
    remaining = Math.max(0, deadline - Date.now());
    stopTimer();
  }
  function resume() {
    if (body.dataset.state !== "in" || hovered || focused || timer) return;
    startTimer(Math.max(remaining, RESUME_MIN_MS));
  }

  body.addEventListener("pointerenter", () => {
    hovered = true;
    pause();
  });
  body.addEventListener("pointerleave", () => {
    hovered = false;
    resume();
  });
  document.addEventListener("focusin", () => {
    focused = true;
    pause();
  });
  document.addEventListener("focusout", (e) => {
    if (e.relatedTarget && card.contains(e.relatedTarget)) return;
    focused = false;
    resume();
  });
  // Window focus goes back to the user's app: the next leave resumes the timer.
  window.addEventListener("blur", () => {
    focused = false;
    resume();
  });

  // ---------------------------------------------------------------- clicks

  function finish(kind, action) {
    if (!current || busy) return;
    busy = true;
    const key = current.key;
    if (kind === "action") void invoke("balloon_action", { key, action });
    else void invoke("balloon_close", { key });
  }

  content.addEventListener("click", () => finish("action", "open"));
  close.addEventListener("click", () => finish("close"));
  actions.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-action]");
    if (b) finish("action", b.dataset.action);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      finish("close");
    }
  });
  window.addEventListener("contextmenu", (e) => e.preventDefault());

  // ---------------------------------------------------------------- driven by the shell

  window.mentorBalloon = {
    render(n) {
      if (!n || typeof n.key !== "string") return;
      const again = current && current.key === n.key && body.dataset.state === "in";
      current = n;
      busy = false;
      title.textContent = n.title || "";
      text.textContent = n.body || "";
      // Name of the message button: the title, else the start of the text.
      content.setAttribute("aria-label", n.title || n.body || "Mentor");
      actions.replaceChildren(
        ...(Array.isArray(n.actions) ? n.actions : []).slice(0, 3).map((a, i) => {
          const b = document.createElement("button");
          b.type = "button";
          b.className = i === 0 ? "action primary" : "action";
          b.dataset.action = String(a.id);
          b.textContent = String(a.label);
          return b;
        }),
      );
      // Updating the one on screen keeps it there; a new one is laid out unseen first.
      if (!again) {
        stopTimer();
        body.dataset.state = "measure";
      }
      requestAnimationFrame(() => {
        if (current !== n) return;
        // Layout height (offsetHeight ignores the entrance scale transform).
        const height = card.offsetHeight + PAD_Y;
        void invoke("balloon_ready", { key: n.key, height });
      });
    },

    reveal({ key, side, anchorY } = {}) {
      if (!current || current.key !== key) return;
      body.dataset.side = side === "left" ? "left" : "right";
      if (Number.isFinite(anchorY)) body.style.setProperty("--anchor-y", `${anchorY}px`);
      const first = body.dataset.state !== "in";
      // Two frames: the "measure" pose is committed before the transition to "in" starts.
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          if (!current || current.key !== key) return;
          body.dataset.state = "in";
        }),
      );
      if (first) {
        hovered = body.matches(":hover");
        startTimer(AUTO_HIDE_MS);
        if (hovered || focused) pause();
        // Read out by screen readers that follow background windows (most announce the toast
        // instead: with a screen reader on, the shell sends toasts).
        live.textContent = "";
        setTimeout(() => {
          live.textContent = [current && current.title, current && current.body]
            .filter(Boolean)
            .join(". ");
        }, 50);
      }
    },

    hide() {
      stopTimer();
      current = null;
      busy = false;
      live.textContent = "";
      if (body.dataset.state === "in" || body.dataset.state === "measure") body.dataset.state = "out";
      if (document.activeElement && document.activeElement !== body) document.activeElement.blur();
    },
  };

  // After the exit transition, drop the old text so nothing stale is read or measured.
  document.getElementById("balloon").addEventListener("transitionend", (e) => {
    if (e.propertyName === "visibility" && body.dataset.state === "out" && !current) {
      body.dataset.state = "idle";
    }
  });
})();
