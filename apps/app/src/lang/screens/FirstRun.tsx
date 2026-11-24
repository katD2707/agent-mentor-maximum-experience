import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AgeBand, Lang } from "../../api";
import { BIRTH_YEAR_MAX, BIRTH_YEAR_MIN, bandForBirthYear } from "../../lib/age";
import { useAuth } from "../../state/auth";
import { setLang } from "../../i18n";
import { Icon } from "../../components/Icon";
import { speak } from "../../lib/speak";
import { lg, type MarketChicken } from "../api";
import { subjectsFor } from "../subjects";
import { ChickenGuide } from "../guide/ChickenGuide";
import { chickenSrc, cropVars, isAnimated, reducedMotion } from "../chickenArt";
import { artFile } from "../subjects";
import "../styles/fonts";
import "../styles/lang.css";

const base = import.meta.env.BASE_URL;
const BANDS: AgeBand[] = ["g1_5", "g6_9", "g10_12", "uni"];
const YEARS = Array.from({ length: BIRTH_YEAR_MAX - BIRTH_YEAR_MIN + 1 }, (_, i) => String(BIRTH_YEAR_MAX - i));
export const MAX_PICK = 3;

type Step = "lang" | "year" | "who" | "ga";
const ORDER: Step[] = ["lang", "year", "who", "ga"];

/** The four small figures of the birth-year step (kid with scarf, middle schooler, áo dài, university hoodie). */
function Figure({ band, on }: { band: AgeBand; on: boolean }) {
  const cls = on ? "on" : undefined;
  const ground = <ellipse cx="60" cy="162" rx="34" ry="5" fill="#5f8f45" opacity=".5" />;
  if (band === "g1_5")
    return (
      <svg viewBox="0 0 120 170" className={cls}>
        {ground}
        <rect x="30" y="92" width="20" height="34" rx="6" fill="#2F6FB5" />
        <rect x="47" y="128" width="10" height="30" rx="4" fill="#25305C" />
        <rect x="63" y="128" width="10" height="30" rx="4" fill="#25305C" />
        <rect x="42" y="88" width="36" height="44" rx="10" fill="#fff" stroke="#CFCAEB" strokeWidth="2" />
        <path d="M50 90 L60 108 L70 90 Z" fill="#E5484D" />
        <circle cx="60" cy="68" r="20" fill="#F4C9A1" />
        <path d="M40 66 C40 48 80 46 80 64 C72 58 52 58 40 66 Z" fill="#2B2321" />
        <circle cx="53" cy="70" r="2.4" fill="#2B2321" />
        <circle cx="67" cy="70" r="2.4" fill="#2B2321" />
        <path d="M54 78 Q60 83 66 78" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
      </svg>
    );
  if (band === "g6_9")
    return (
      <svg viewBox="0 0 120 170" className={cls}>
        {ground}
        <rect x="46" y="112" width="12" height="46" rx="4" fill="#25305C" />
        <rect x="62" y="112" width="12" height="46" rx="4" fill="#25305C" />
        <rect x="40" y="64" width="40" height="54" rx="10" fill="#fff" stroke="#CFCAEB" strokeWidth="2" />
        <path d="M52 66 L60 78 L68 66" stroke="#CFCAEB" strokeWidth="2" fill="none" />
        <rect x="70" y="86" width="22" height="28" rx="3" fill="#FFB020" transform="rotate(-8 81 100)" />
        <circle cx="60" cy="44" r="18" fill="#E9B98E" />
        <path d="M42 42 C42 24 78 22 78 42 L74 36 C66 32 52 32 44 38 Z" fill="#2B2321" />
        <circle cx="54" cy="46" r="2.2" fill="#2B2321" />
        <circle cx="66" cy="46" r="2.2" fill="#2B2321" />
        <path d="M55 53 Q60 57 65 53" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
      </svg>
    );
  if (band === "g10_12")
    return (
      <svg viewBox="0 0 120 170" className={cls}>
        {ground}
        <path d="M44 100 L40 158 L80 158 L76 100 Z" fill="#F3F1FA" stroke="#CFCAEB" strokeWidth="2" />
        <path d="M44 52 C40 80 40 120 46 150 L74 150 C80 120 80 80 76 52 Z" fill="#fff" stroke="#CFCAEB" strokeWidth="2" />
        <path d="M60 52 L60 150" stroke="#E6E3F4" strokeWidth="2" />
        <path d="M40 34 C38 60 40 84 44 96 L50 60 Z" fill="#2B2321" />
        <path d="M80 34 C82 60 80 84 76 96 L70 60 Z" fill="#2B2321" />
        <circle cx="60" cy="34" r="17" fill="#F2C49B" />
        <path d="M42 34 C42 14 78 14 78 34 C70 26 50 26 42 34 Z" fill="#2B2321" />
        <circle cx="54" cy="36" r="2.2" fill="#2B2321" />
        <circle cx="66" cy="36" r="2.2" fill="#2B2321" />
        <path d="M55 43 Q60 47 65 43" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
      </svg>
    );
  return (
    <svg viewBox="0 0 120 170" className={cls}>
      {ground}
      <rect x="45" y="106" width="13" height="52" rx="4" fill="#3B3F4A" />
      <rect x="62" y="106" width="13" height="52" rx="4" fill="#3B3F4A" />
      <rect x="36" y="50" width="48" height="62" rx="14" fill="#4B2EBF" />
      <path d="M48 52 Q60 64 72 52" stroke="#3A2299" strokeWidth="3" fill="none" />
      <rect x="30" y="84" width="40" height="26" rx="3" fill="#C9CCD6" />
      <rect x="33" y="87" width="34" height="18" rx="2" fill="#E9EDF5" />
      <circle cx="60" cy="30" r="17" fill="#D9A47C" />
      <path d="M43 28 C44 10 78 10 77 28 L72 22 C64 18 52 19 46 24 Z" fill="#2B2321" />
      <rect x="49" y="28" width="9" height="6" rx="2" fill="none" stroke="#2B2321" strokeWidth="1.6" />
      <rect x="62" y="28" width="9" height="6" rx="2" fill="none" stroke="#2B2321" strokeWidth="1.6" />
      <path d="M58 31 h4" stroke="#2B2321" strokeWidth="1.6" />
      <path d="M55 40 Q60 43 65 40" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/**
 * First run (mockups/lg-02): language, birth year (set once, then locked), boy or girl, then up to three chickens. More
 * chickens come later from the Chợ gà in the village. A step that is already done (language, year, character) is skipped.
 */
export function LgFirstRun() {
  const { t, i18n } = useTranslation();
  const { user, token, updateMe } = useAuth();
  const nav = useNavigate();
  const lang: Lang = i18n.language === "en" ? "en" : "vi";
  // the language picked on the login screen counts: it is asked once, not again
  const storedLang = (() => {
    try {
      const v = localStorage.getItem("mentor.lang");
      return v === "vi" || v === "en" ? v : null;
    } catch {
      return null;
    }
  })();
  const initial: Step = !user?.language && !storedLang ? "lang" : user?.birth_year == null ? "year" : !user?.avatar ? "who" : "ga";
  const [step, setStep] = useState<Step>(initial);
  const [year, setYear] = useState(user?.birth_year != null ? String(user.birth_year) : "");
  const [kid, setKid] = useState<"nam" | "nu">(user?.avatar ?? "nam");
  const [picked, setPicked] = useState<string[]>([]);
  const [market, setMarket] = useState<MarketChicken[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const locked = user?.birth_year != null;
  const band: AgeBand | null = year ? bandForBirthYear(Number(year)) : (user?.age_band ?? null);

  // the list of chickens of this person's level (with course counts and what is already owned)
  useEffect(() => {
    if (step !== "ga" || !token) return;
    let alive = true;
    lg.getMarket(token).then(
      (m) => alive && setMarket(m.chickens),
      () => alive && setMarket(subjectsFor(user?.age_band).map((s) => ({ id: s.id, name_vi: `Gà ${s.vi}`, name_en: `${s.en} chicken`, art: s.art, courses: 0, owned: false }))),
    );
    return () => {
      alive = false;
    };
  }, [step, token, user?.age_band]);

  const list = useMemo(() => (market ?? []).filter((m) => !m.owned), [market]);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < MAX_PICK ? [...p, id] : p));
  const name = (m: { name_vi: string; name_en: string }) => (lang === "en" ? m.name_en : m.name_vi);
  const speakQ = () => speak(t("lg.first.yearTitle"), lang);

  const run = async (fn: () => Promise<void>, next?: Step) => {
    setFailed(false);
    setBusy(true);
    try {
      await fn();
      if (next) {
        setStep(next);
        window.scrollTo?.(0, 0);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!user?.language && storedLang && token) void updateMe({ language: storedLang }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const chooseLang = (l: Lang) => {
    setLang(l);
    void run(() => updateMe({ language: l }), user?.birth_year == null ? "year" : !user?.avatar ? "who" : "ga");
  };
  const done = () =>
    run(async () => {
      if (!token) return;
      for (const id of picked) {
        try {
          await lg.takeChicken(token, id);
        } catch (e) {
          // already owned (409) is fine; anything else stops here
          if (!(e instanceof Object && "status" in e && (e as { status: number }).status === 409)) throw e;
        }
      }
      nav("/", { replace: true });
    });

  const cta = () => {
    if (step === "year") return void run(() => (locked ? Promise.resolve() : updateMe({ birth_year: Number(year) })), !user?.avatar ? "who" : "ga");
    if (step === "who") return void run(() => updateMe({ avatar: kid }), "ga");
    if (step === "ga") return void done();
  };
  const ctaLabel = step === "ga" ? (picked.length === 0 ? t("lg.first.pickAtLeast") : t("lg.first.enter")) : t("lg.first.next");
  const ctaOff = busy || (step === "year" && !band) || (step === "ga" && picked.length === 0);
  const back = step === "ga" && !!user && ORDER.indexOf(step) > 0 ? "who" : null;

  return (
    <div className="lg lg-back" data-age={band ?? "g10_12"}>
      <main className="lg-first">
        {step === "lang" && (
          <section className="lg-board" aria-labelledby="lg-t0">
            <h1 className="lg-ribbon-t" id="lg-t0">
              Xin chào · Hello
            </h1>
            <p className="lg-lead">Chọn ngôn ngữ · Pick a language</p>
            <div className="lg-langs">
              <button className="lg-lang" type="button" disabled={busy} onClick={() => chooseLang("vi")}>
                <span className="hello">Xin chào</span>
                <span className="name">Tiếng Việt</span>
              </button>
              <button className="lg-lang" type="button" disabled={busy} onClick={() => chooseLang("en")}>
                <span className="hello">Hello</span>
                <span className="name">English</span>
              </button>
            </div>
            {failed && <p className="lg-lead">{t("first.saveFailed")}</p>}
          </section>
        )}

        {step === "year" && (
          <section className="lg-board" aria-labelledby="lg-t3">
            <h1 className="lg-ribbon-t" id="lg-t3">
              {t("lg.first.yearTitle")}
            </h1>
            <p className="lg-lead">{t("lg.first.yearLead")}</p>
            <div className="lg-q">
              <button className="lg-speak" type="button" onClick={speakQ}>
                <Icon name="volume" />
                <span>{t("lg.first.readAloud")}</span>
              </button>
            </div>
            <div className="lg-figs" data-pick={band ?? undefined} aria-hidden="true">
              {BANDS.map((b) => (
                <Figure key={b} band={b} on={b === band} />
              ))}
            </div>
            <div className="lg-pickyear">
              <select className="lg-year" aria-label={t("first.yearLabel")} value={year} disabled={locked} onChange={(e) => setYear(e.target.value)}>
                <option value="" disabled>
                  {t("first.yearLabel")}
                </option>
                {YEARS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            <p className="lg-level" aria-live="polite">
              {band && year ? t(`first.level.${band}`) : ""}
            </p>
            {failed && <p className="lg-lead">{t("first.saveFailed")}</p>}
          </section>
        )}

        {step === "who" && (
          <section className="lg-board" aria-labelledby="lg-t1">
            <h1 className="lg-ribbon-t" id="lg-t1">
              {t("lg.first.whoTitle")}
            </h1>
            <p className="lg-lead">{t("lg.first.whoLead")}</p>
            <div className="lg-who">
              {(["nam", "nu"] as const).map((k) => (
                <button key={k} className="lg-pick" type="button" aria-pressed={kid === k} onClick={() => setKid(k)}>
                  <img src={`${base}ga/hs-${k}.webp`} alt="" />
                  <b>{t(`lg.first.${k}`)}</b>
                  <span className="lg-tick" aria-hidden="true">
                    <Icon name="check" />
                  </span>
                </button>
              ))}
            </div>
            {failed && <p className="lg-lead">{t("first.saveFailed")}</p>}
          </section>
        )}

        {step === "ga" && (
          <section className="lg-board wide" aria-labelledby="lg-t2">
            <h1 className="lg-ribbon-t" id="lg-t2">
              {t("lg.first.gaTitle")}
            </h1>
            <p className="lg-lead">{t("lg.first.gaLead")}</p>
            <div className="lg-perches" id="lg-perches">
              {[0, 1, 2].map((k) => {
                const m = list.find((x) => x.id === picked[k]);
                return m ? (
                  <div className="lg-perch on" key={k}>
                    <img className={isAnimated(m.art, 3) || reducedMotion() ? undefined : "ga-bob"} src={chickenSrc(m.art, 3, "stand", reducedMotion())} alt="" />
                    <small>{name(m)}</small>
                  </div>
                ) : (
                  <div className="lg-perch" key={k}>
                    <span>{k + 1}</span>
                  </div>
                );
              })}
            </div>
            <p className="lg-count" aria-live="polite">
              {t("lg.first.count", { n: picked.length, max: MAX_PICK })}
            </p>
            <div className={"lg-grid" + (picked.length === MAX_PICK ? " full" : "")}>
              {list.map((m) => (
                <button key={m.id} className="lg-ga" type="button" aria-pressed={picked.includes(m.id)} onClick={() => toggle(m.id)}>
                  <span className="pic">
                    <img src={`${base}ga/${artFile(m.art, 3)}`} alt="" className="ga-crop" style={cropVars(m.art, 3)} />
                  </span>
                  <b>{name(m)}</b>
                  <small>{t("lg.first.courses", { count: m.courses })}</small>
                  <span className="lg-tick" aria-hidden="true">
                    <Icon name="check" />
                  </span>
                </button>
              ))}
            </div>
            {failed && <p className="lg-lead">{t("first.saveFailed")}</p>}
          </section>
        )}
      </main>

      {step !== "lang" && (
        <div className="lg-foot">
          <div className="lg-row">
            {back && (
              <button className="lg-btn-back" type="button" onClick={() => setStep(back)}>
                {t("lg.first.back")}
              </button>
            )}
            <button className="lg-cta" type="button" disabled={ctaOff} onClick={cta}>
              {ctaLabel}
            </button>
          </div>
          {step === "ga" && <p>{t("lg.first.hint")}</p>}
        </div>
      )}
      <ChickenGuide screen="first" />
    </div>
  );
}
