import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { ResearchBody, type LibMood } from "./research/Research";
import { PaperReader, type PaperMood } from "./research/Paper";
import { lg, type Chicken } from "../../api";
import { artFile, chickenName } from "../../subjects";
import "../../styles/fonts";
import "../../styles/lang.css";
import "../../styles/library.css";

const SettingsSheet = lazy(() => import("../village/Sheets").then((m) => ({ default: m.SettingsSheet })));
const base = import.meta.env.BASE_URL;

/** The Library is for the university band only; anyone else goes back to the village. */
function UniGate({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user?.age_band === "uni" ? <>{children}</> : <Navigate to="/" replace />;
}

/** The student's university chicken: the one that speaks in the village, else the first one they own. */
function useLibraryChicken(): Chicken | null {
  const { token } = useAuth();
  const [c, setC] = useState<Chicken | null>(null);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    lg.getVillage(token).then(
      (v) => alive && setC(v.chickens.find((x) => x.id === v.speaker?.chicken) ?? v.chickens[0] ?? null),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [token]);
  return c;
}

/** The look of lg-10: the village behind, a wooden board, a ribbon, the chicken in its corner, the paper inside. */
function Frame({ desk, back, backLabel, bubble, children }: { desk?: boolean; back: string; backLabel: string; bubble: string; children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "en" ? "en" : "vi";
  const chicken = useLibraryChicken();
  const [settings, setSettings] = useState(false);
  const name = chicken ? (lang === "en" ? chicken.name_en : chicken.name_vi) : chickenName("khmt", lang);
  const art = chicken ? artFile(chicken.art, 3) : "khmt.png";
  return (
    <div className="lg lg-back lg-lib" data-age="uni">
      <div className="lg-lib-wrap">
        <div className="lg-lib-hud">
          <Link className="lg-lib-rb" to={back} replace={back === "/"} aria-label={backLabel}>
            <Icon name="back" />
          </Link>
          <span className="lg-lib-grow" />
          <button className="lg-lib-rb" type="button" onClick={() => setSettings(true)} aria-label={t("lg.lib.settings")}>
            <Icon name="gear" />
          </button>
        </div>
        <main className="lg-lib-board rs-page" data-guide="research" data-guide-label={t("lg.place.library")}>
          <h1 className="lg-lib-ribbon">{desk ? t("lg.lib.desk") : t("lg.lib.title")}</h1>
          <div className="lg-lib-corner">
            <div className="gaf">
              <img src={`${base}ga/${art}`} alt="" />
              <span className="nm">{name}</span>
            </div>
            <div className="bubble" aria-live="polite">
              <p>{bubble}</p>
            </div>
          </div>
          {children}
        </main>
      </div>
      {settings && (
        <Suspense fallback={null}>
          <SettingsSheet onClose={() => setSettings(false)} />
        </Suspense>
      )}
    </div>
  );
}

/** lg-10 Thư viện: the search, the reading list, the schedule, the experiment log and the topic of the research area. */
export function Library() {
  const { t } = useTranslation();
  const [mood, setMood] = useState<LibMood | null>(null);
  const onMood = useCallback((m: LibMood | null) => setMood((o) => (o?.key === m?.key && o?.n === m?.n && o?.what === m?.what ? o : m)), []);
  const bubble = !mood
    ? ""
    : mood.key === "dataDue"
      ? t("lg.lib.bubble.dataDue", { n: mood.n ?? 0, what: mood.what ?? "" })
      : t(`lg.lib.bubble.${mood.key}`);
  return (
    <UniGate>
      <Frame back="/" backLabel={t("lg.lib.back")} bubble={bubble}>
        <ResearchBody onMood={onMood} />
      </Frame>
    </UniGate>
  );
}

/** lg-10 Bàn đọc: one paper. You write your own summary first; only then the chicken's comments. */
export function LibraryPaper() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const [mood, setMood] = useState<PaperMood>("write");
  return (
    <UniGate>
      <Frame desk back="/thu-vien" backLabel={t("lg.lib.backLib")} bubble={t(`lg.lib.bubble.${mood === "write" ? "write" : mood === "feedback" ? "feedback" : "ask"}`)}>
        <PaperReader id={id} onMood={setMood} />
      </Frame>
    </UniGate>
  );
}
