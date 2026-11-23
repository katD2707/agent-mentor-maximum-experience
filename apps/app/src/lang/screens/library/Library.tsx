import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { NotesShelf } from "./NotesShelf";
import { ResearchBody, type LibMood } from "./research/Research";
import { PaperReader, type PaperMood } from "./research/Paper";
import { SettingsSourcesRow } from "./research/Sources";
import { lg, type Chicken } from "../../api";
import { artFile, chickenName, subjectOf } from "../../subjects";
import "../../styles/fonts";
import "../../styles/lang.css";
import "../../styles/library.css";

// the Library's gear holds only the paper-source keys; the general settings live on the village gear (one place each)
const SourcesSheet = lazy(() =>
  import("../village/Sheets").then((m) => ({
    default: function SourcesSheet({ title, onClose }: { title: string; onClose(): void }) {
      return (
        <m.Sheet id="lg-lib-sources" title={title} onClose={onClose}>
          <SettingsSourcesRow onOpen={onClose} />
        </m.Sheet>
      );
    },
  })),
);
const base = import.meta.env.BASE_URL;

/** The research half of the Library (papers, schedule, experiments) is for the university band; the notes shelf is for everyone from grade 6. */
function useBand() {
  const { user } = useAuth();
  const band = user?.age_band ?? null;
  return { uni: band === "uni", kid: band === "g1_5" };
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
  const band = useAuth().user?.age_band;
  const [settings, setSettings] = useState(false);
  // before the village answers (or with no chicken at all) the host is the band's own first chicken, never a university one for a school student
  const home = band === "uni" || !band ? "khmt" : "toan";
  const name = chicken ? (lang === "en" ? chicken.name_en : chicken.name_vi) : chickenName(home, lang);
  const art = chicken ? artFile(chicken.art, 3) : artFile(subjectOf(home)?.art ?? home, 3);
  return (
    <div className="lg lg-back lg-lib" data-age={band ?? "uni"}>
      <div className="lg-lib-wrap">
        <div className="lg-lib-hud">
          <Link className="lg-lib-rb" to={back} replace={back === "/"} aria-label={backLabel}>
            <Icon name="back" />
          </Link>
          <span className="lg-lib-grow" />
          {band === "uni" && (
            <button className="lg-lib-rb" type="button" onClick={() => setSettings(true)} aria-label={t("lg.lib.settings")}>
              <Icon name="gear" />
            </button>
          )}
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
          <SourcesSheet title={t("research.sources.row")} onClose={() => setSettings(false)} />
        </Suspense>
      )}
    </div>
  );
}

/** lg-10 Thư viện: the search, the reading list, the schedule, the experiment log and the topic of the research area (uni), and the notes shelf (grade 6 and up). */
export function Library() {
  const { t } = useTranslation();
  const { uni, kid } = useBand();
  const [mood, setMood] = useState<LibMood | null>(null);
  const onMood = useCallback((m: LibMood | null) => setMood((o) => (o?.key === m?.key && o?.n === m?.n && o?.what === m?.what ? o : m)), []);
  const bubble = kid
    ? t("lg.lib.kidLocked")
    : !uni
      ? t("lg.lib.bubbleNotes")
      : !mood
        ? t("lg.lib.loadingOverview")
        : mood.key === "dataDue"
          ? t("lg.lib.bubble.dataDue", { n: mood.n ?? 0, what: mood.what ?? "" })
          : t(`lg.lib.bubble.${mood.key}`);
  return (
    <Frame back="/" backLabel={t("lg.lib.back")} bubble={bubble}>
      {!kid && <NotesShelf />}
      {uni && <ResearchBody onMood={onMood} />}
      {!kid && !uni && <p className="lg-notes-quiet">{t("lg.lib.researchLocked")}</p>}
    </Frame>
  );
}

/** lg-10 Bàn đọc: one paper. You write your own summary first; only then the chicken's comments. */
export function LibraryPaper() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const { uni } = useBand();
  const [mood, setMood] = useState<PaperMood>("write");
  return (
    <Frame desk back="/thu-vien" backLabel={t("lg.lib.backLib")} bubble={uni ? t(`lg.lib.bubble.${mood === "write" ? "write" : mood === "feedback" ? "feedback" : "ask"}`) : t("lg.lib.researchLocked")}>
      {uni ? <PaperReader id={id} onMood={setMood} /> : <p className="lg-notes-quiet">{t("lg.lib.researchLocked")}</p>}
    </Frame>
  );
}
