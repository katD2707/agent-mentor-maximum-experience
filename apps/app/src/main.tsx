import "@fontsource/lexend/vietnamese-400.css";
import "@fontsource/lexend/vietnamese-500.css";
import "@fontsource/lexend/vietnamese-600.css";
import "@fontsource/lexend/vietnamese-700.css";
import "@fontsource/lexend/latin-400.css";
import "@fontsource/lexend/latin-500.css";
import "@fontsource/lexend/latin-600.css";
import "@fontsource/lexend/latin-700.css";
import "@fontsource/literata/vietnamese-400.css";
import "@fontsource/literata/vietnamese-600.css";
import "@fontsource/literata/latin-400.css";
import "@fontsource/literata/latin-600.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/screens.css";
import "./styles/courses.css";
import "./styles/practice.css";
import "./styles/research.css";
import "./styles/dark.css";
import "./i18n";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { installRipple } from "./lib/ripple";
import { isTauri, registerWorker } from "./lib/platform";
import { initApiBase } from "./api/http";

installRipple();
// web: register at launch so a new build is noticed (and the offline shell cached), not only after notifications are enabled
if (!isTauri() && import.meta.env.PROD) void registerWorker();

const rootEl = document.getElementById("root")!;

/** Plain splash while the desktop shell starts the local gateway (nothing else can run before its address is known). */
function splash(text: string, retry = false) {
  rootEl.replaceChildren();
  const box = document.createElement("div");
  box.setAttribute("style", "min-height:100vh;display:grid;place-content:center;gap:16px;text-align:center;font:600 1.1rem Lexend,system-ui,sans-serif;color:#5a3a1c;background:#f6ecd8");
  box.setAttribute("role", "status");
  box.textContent = text;
  if (retry) {
    const b = document.createElement("button");
    b.textContent = "Thử lại";
    b.setAttribute("style", "font:inherit;padding:10px 24px;border-radius:14px;border:2px solid #165c32;background:#36a862;color:#fff;cursor:pointer");
    b.onclick = () => location.reload();
    box.append(b);
  }
  rootEl.append(box);
}

async function start() {
  if (isTauri()) {
    splash("Đang mở Mentor…");
    try {
      await initApiBase();
    } catch {
      splash("Mentor chưa mở được. Em đóng ứng dụng rồi mở lại nhé.", true);
      return;
    }
  }
  createRoot(rootEl).render(
    <StrictMode>
      <HashRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </HashRouter>
    </StrictMode>,
  );
}

void start();
