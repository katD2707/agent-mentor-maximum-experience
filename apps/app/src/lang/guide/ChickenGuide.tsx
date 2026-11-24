import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../state/auth";
import { hasSeen, markSeen, resetSeen, REPLAY_EVENT } from "../../lib/tours";
import { artFile, chickenName, subjectOf } from "../subjects";
import { hasGa } from "../gaFiles";
import { createGuide, resetToured, ROAMING, type GuideHandle } from "./guide";
import "../styles/guide.css";

/** The picture of the guide chicken: its costume, animated where it has an animated stand, else the grown still. */
export function guideImage(chicken: string): string {
  const base = import.meta.env.BASE_URL;
  const reduced = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const art = subjectOf(chicken)?.art ?? chicken;
  if (!reduced && hasGa("dung", art)) return `${base}ga/${art}-dung.webp`;
  return `${base}ga/${artFile(art, 3)}`;
}

/** Local key of the first-visit tour of a screen (shared with Settings > "Xem lại từ đầu"). */
export const tourKey = (screen: string) => `lg-${screen}`;

/**
 * The chicken guide on a screen (replaces the old Mực). Mount it once per screen with its key (login, first, village).
 * Settings > "Xem lại từ đầu" fires `mentor:tour-replay`: every tour is forgotten and this screen's runs again.
 */
export function ChickenGuide({ screen, chicken = "toan" }: { screen: string; chicken?: string }) {
  const { i18n } = useTranslation();
  const { user } = useAuth();
  const lang = i18n.language === "en" ? "en" : "vi";
  const adult = user?.age_band === "uni" || user?.role === "teacher";
  const live = useRef<{ lang: "vi" | "en"; adult: boolean; kid: boolean; uid: string | null }>({ lang, adult, kid: user?.age_band === "g1_5", uid: user?.id ?? null });
  live.current = { lang, adult, kid: user?.age_band === "g1_5", uid: user?.id ?? null };
  const handle = useRef<GuideHandle | null>(null);

  useEffect(() => {
    const g = createGuide({
      screen,
      name: chickenName(chicken, live.current.lang),
      image: guideImage(chicken),
      lang: () => live.current.lang,
      adult: () => live.current.adult,
      kid: () => live.current.kid,
      seen: () => hasSeen(live.current.uid, tourKey(screen)),
      markSeen: () => markSeen(live.current.uid, tourKey(screen)),
    });
    handle.current = g;
    const replay = () => {
      resetSeen(live.current.uid);
      resetToured();
      markSeen(live.current.uid, tourKey(screen));
      setTimeout(() => g.startTour(), 250); // let a closing sheet go first
    };
    window.addEventListener(REPLAY_EVENT, replay);
    return () => {
      window.removeEventListener(REPLAY_EVENT, replay);
      g.destroy();
      handle.current = null;
    };
  }, [screen, chicken]);

  useEffect(() => handle.current?.refresh(), [lang]);

  // parked screens: leave room under the content for the corner dock
  const parked = !ROAMING.has(screen);
  useEffect(() => {
    if (!parked) return;
    document.body.classList.add("cg-parked");
    return () => document.body.classList.remove("cg-parked");
  }, [parked]);

  return parked ? null : (
    <>
      <div className="cg-bar" aria-hidden="true" />
      <div className="cg-dock" aria-hidden="true" />
    </>
  );
}
