import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../state/auth";
import { subjectOf, artFile } from "../../subjects";
import "../../styles/fonts";
import "../../styles/lang.css";
import "../../styles/arena.css";

export const base = import.meta.env.BASE_URL;

export function useLang(): "vi" | "en" {
  const { i18n } = useTranslation();
  return i18n.language === "en" ? "en" : "vi";
}

/** Picture of a chicken standing ready (the battle pose exists for the three exam subjects). */
export function chickenPic(chicken: string, pose: "dung" | "body" = "dung"): string {
  const art = subjectOf(chicken)?.art ?? chicken;
  if (pose === "dung" && ["toan", "van", "anh"].includes(art)) return `${base}ga/${art}-dung.webp`;
  return `${base}ga/${artFile(art, 3)}`;
}

/** The wooden board over the blurred village that every Arena, test and runner screen sits on. */
export function Shell({ title, children, pr, busy }: { title: ReactNode; children: ReactNode; pr?: boolean; busy?: boolean }) {
  const { user } = useAuth();
  return (
    <div className={`lg lg-back lg-ar${pr ? " lg-pr practice-run" : ""}`} data-age={user?.age_band ?? "g10_12"} aria-busy={busy || undefined}>
      <div className="lg-stage">
        <section className="lg-board wide" aria-labelledby="ar-title">
          <h1 className="lg-ribbon-t" id="ar-title">
            {title}
          </h1>
          {children}
        </section>
      </div>
    </div>
  );
}

/** The score as the mockup prints it: one decimal, comma in Vietnamese. */
export const f1 = (x: number, lang: "vi" | "en"): string => {
  const s = (Math.round(x * 10) / 10).toFixed(1);
  return lang === "vi" ? s.replace(".", ",") : s;
};
