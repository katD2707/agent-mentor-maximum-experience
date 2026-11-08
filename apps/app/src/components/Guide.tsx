import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "@mentor/mentor-mascot/mascot.js";
import type { MentorMascot, MascotLang } from "@mentor/mentor-mascot/mascot";
import { isMock, postGuide } from "../api";
import { useAuth } from "../state/auth";
import { GUIDES, askGuide } from "../lib/guides";

/** The guide area (a key of GUIDES) that describes the screen at `pathname`; undefined for the home screen and login. */
export function screenKey(pathname: string): string | undefined {
  if (pathname.startsWith("/khoa-hoc/tim-kiem")) return "course-search";
  if (/^\/khoa-hoc\/[^/]+\/hoc/.test(pathname)) return "player-progress";
  if (/^\/khoa-hoc\/[^/]+/.test(pathname)) return "course-tree";
  if (pathname.startsWith("/khoa-hoc")) return "courses";
  if (pathname.startsWith("/luyen-tap")) return "practice";
  if (pathname.startsWith("/hoi-dap")) return "ask";
  if (pathname.startsWith("/tien-do")) return "progress";
  if (pathname.startsWith("/nghien-cuu/paper/")) return "research-paper";
  if (pathname.startsWith("/nghien-cuu")) return "research";
  return undefined;
}

/** data-guide keys of the areas on screen now (at most 30, the server's limit). */
export function visibleKeys(): string[] {
  const seen = new Set<string>();
  for (const el of document.querySelectorAll<HTMLElement>("[data-guide]")) if (el.dataset.guide) seen.add(el.dataset.guide);
  return [...seen].slice(0, 30);
}

/** Mực, the guide character, on every screen. Signed in, the chat asks POST /guide; the local map answers on the login screen, offline or on an error. */
export function Guide() {
  const ref = useRef<MentorMascot>(null);
  const { i18n } = useTranslation();
  const { pathname } = useLocation();
  const { token } = useAuth();
  const lang = i18n.language === "en" ? "en" : "vi";
  const now = useRef({ token, pathname });
  now.current = { token, pathname };

  useEffect(() => {
    const m = ref.current;
    if (!m) return;
    m.guides = GUIDES;
    m.ask = async (question: string, l: MascotLang) => {
      const { token: tok, pathname: path } = now.current;
      if (tok && !isMock) {
        try {
          return await postGuide(tok, { question: question.slice(0, 300), lang: l, screen: screenKey(path), visible_keys: visibleKeys() });
        } catch {
          /* offline or the server is unhappy: the local map still helps */
        }
      }
      return askGuide(question, l);
    };
  }, []);

  useEffect(() => {
    ref.current?.relocate();
  }, [pathname]);

  return (
    <>
      {/* Phone widths: a slim strip at the bottom is Mực's home (CSS shows it only there). `.mascot-dock` is the invisible
          "keep out" zone above the strip that the mascot's free-spot search avoids, so it never rests on content. */}
      <div className="mascot-bar" aria-hidden="true" />
      <div className="mascot-dock" data-mascot-avoid aria-hidden="true" />
      <mentor-mascot ref={ref} lang={lang} />
    </>
  );
}
