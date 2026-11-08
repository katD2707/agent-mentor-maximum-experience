import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { AgeBand, Lang } from "../api";
import { BIRTH_YEAR_MAX, BIRTH_YEAR_MIN, bandForBirthYear } from "../lib/age";
import { useAuth } from "../state/auth";
import { setLang } from "../i18n";
import { Icon } from "../components/Icon";
import { AgeArt } from "../components/Illustrations";
import { speak } from "../lib/speak";

const BANDS: AgeBand[] = ["g1_5", "g6_9", "g10_12", "uni"];
const YEARS = Array.from({ length: BIRTH_YEAR_MAX - BIRTH_YEAR_MIN + 1 }, (_, i) => String(BIRTH_YEAR_MAX - i));

/** Shown once: language first, then the birth year. The year decides the picture and the band; neither age nor grade is ever shown. */
export function FirstRun() {
  const { t, i18n } = useTranslation();
  const { user, updateMe } = useAuth();
  const [failed, setFailed] = useState(false);
  const [year, setYear] = useState("");
  const [saving, setSaving] = useState(false);
  const step = user?.language ? "age" : "lang";
  const band = year ? bandForBirthYear(Number(year)) : null;

  const save = async (patch: { language: Lang } | { birth_year: number }) => {
    setFailed(false);
    setSaving(true);
    try {
      await updateMe(patch);
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="first-stage">
      {step === "lang" ? (
        <section className="sheet oli" aria-labelledby="h-lang">
          <h1 id="h-lang" className="sr">
            {t("first.chooseLanguage")}
          </h1>
          <div className="langs">
            <button
              className="lang"
              type="button"
              onClick={() => {
                setLang("vi");
                void save({ language: "vi" });
              }}
            >
              <span className="hello-big">Xin chào</span>
              <span className="name">Tiếng Việt</span>
            </button>
            <button
              className="lang"
              type="button"
              onClick={() => {
                setLang("en");
                void save({ language: "en" });
              }}
            >
              <span className="hello-big">Hello</span>
              <span className="name">English</span>
            </button>
          </div>
          {failed && <p className="muted">{t("first.saveFailed")}</p>}
        </section>
      ) : (
        <section className="sheet oli" aria-labelledby="h-age">
          <div className="q">
            <h1 id="h-age">{t("first.question")}</h1>
            <button className="speak" type="button" aria-label={t("first.readAloud")} onClick={() => speak(t("first.question"), i18n.language)}>
              <Icon name="volume" />
            </button>
          </div>
          <div className="figs" data-pick={band ?? undefined} aria-hidden="true">
            {BANDS.map((b) => (
              <div key={b} className={"fig" + (b === band ? " on" : "")} data-band={b}>
                <AgeArt band={b} />
              </div>
            ))}
          </div>
          <div className="pick">
            <select className="year" aria-label={t("first.yearLabel")} value={year} onChange={(e) => setYear(e.target.value)}>
              <option value="" disabled>
                {t("first.yearLabel")}
              </option>
              {YEARS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
            <button className="go" type="button" disabled={!band || saving} onClick={() => void save({ birth_year: Number(year) })}>
              {t("first.start")}
            </button>
          </div>
          <p className="level" aria-live="polite">
            {band ? t(`first.level.${band}`) : ""}
          </p>
          {failed && <p className="muted">{t("first.saveFailed")}</p>}
        </section>
      )}
    </div>
  );
}
