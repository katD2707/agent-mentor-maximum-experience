import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "@mentor/mentor-mascot/mascot.js";
import type { MentorMascot, MascotLang } from "@mentor/mentor-mascot/mascot";
import { isMock, postGuide } from "../api";
import { useAuth } from "../state/auth";
import { GUIDES, askGuide } from "../lib/guides";
import { REPLAY_EVENT, hasSeen, markSeen, resetSeen, tourScreen, tourSteps } from "../lib/tours";
import { needsFirstRun } from "../lib/gate";

/** Nobody is in the middle of something: not typing, no dialog or menu open, the window in front. */
function free(): boolean {
  const a = document.activeElement as HTMLElement | null;
  if (a && (a.matches("input, textarea, select") || a.isContentEditable)) return false;
  if (document.querySelector('[role="dialog"]:not([hidden]), [role="menu"]:not([hidden]), dialog[open]')) return false;
  return document.visibilityState !== "hidden";
}

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
  const { token, user } = useAuth();
  const lang = i18n.language === "en" ? "en" : "vi";
  const now = useRef({ token, pathname });
  now.current = { token, pathname };
  const uid = user?.id ?? null;
  const adult = user?.role === "teacher" || user?.age_band === "uni";
  const screen = user && user.role === "student" && needsFirstRun(user) ? undefined : tourScreen(pathname, user?.role ?? null);
  const tourNow = useRef<{ screen?: string; uid: string | null; adult: boolean }>({ uid, adult });
  tourNow.current = { screen, uid, adult };

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

  // First visit of a screen: once its parts are on the page and the person isn't busy, Mực walks them through it.
  useEffect(() => {
    const m = ref.current;
    if (!m || !screen || hasSeen(uid, screen)) return;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let gone = false;
    const again = () => {
      if (++tries < 15) timer = setTimeout(attempt, 1000);
    };
    const attempt = async () => {
      if (gone || hasSeen(uid, screen)) return;
      const steps = free() ? tourSteps(screen, adult) : [];
      if (!steps.length) return again();
      markSeen(uid, screen); // seen once it starts, however it ends: never twice
      if ((await m.tour(steps)) === "none" && !gone) {
        markSeen(uid, screen, false); // Mực was busy: try again in a moment
        again();
      }
    };
    timer = setTimeout(attempt, 1200);
    return () => {
      gone = true;
      clearTimeout(timer);
      m.stopTour();
    };
  }, [screen, uid, adult]);

  // "Show me this page again" in Mực's chat, and Settings > "Xem lại từ đầu" (which also forgets every other screen)
  useEffect(() => {
    const m = ref.current;
    if (!m) return;
    const replay = () => {
      const { screen: s, uid: u, adult: a } = tourNow.current;
      const steps = s ? tourSteps(s, a) : [];
      if (!s || !steps.length) return;
      markSeen(u, s);
      void m.tour(steps);
    };
    m.replay = screen ? replay : null;
    const fromSettings = () => {
      resetSeen(tourNow.current.uid);
      setTimeout(replay, 250); // let the settings popover close first
    };
    window.addEventListener(REPLAY_EVENT, fromSettings);
    return () => window.removeEventListener(REPLAY_EVENT, fromSettings);
  }, [screen]);

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
