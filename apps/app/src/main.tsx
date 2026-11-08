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
import "./styles/catalog.css";
import "./styles/progress.css";
import "./styles/ask.css";
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

installRipple();
// web: register at launch so a new build is noticed (and the offline shell cached), not only after notifications are enabled
if (!isTauri() && import.meta.env.PROD) void registerWorker();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </HashRouter>
  </StrictMode>,
);
