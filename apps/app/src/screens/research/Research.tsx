import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { researchApi, type ResearchOverview } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Settings } from "../../components/Settings";
import { Icon } from "../../components/Icon";
import { EmptyTopic, SavedTopic, TopicCard } from "./Topic";
import { Hero, ReadList } from "./Reading";
import { Milestones, Upcoming } from "./Upcoming";
import { ExperimentLog } from "./Log";
import { Results, SearchBar } from "./Search";
import { errCode } from "./util";
import { ChapterTabs, useChapter, type Chapter, type ChapterDot } from "./Chapters";

type Load = { status: "loading" } | { status: "error"; code: string } | { status: "ready"; data: ResearchOverview };

/** Mentor looks for papers in the background; the overview is read again until it is done. */
const WATCH_MS = 3000;

/** hs-11: the research home, four chapters in tabs (Reading, Schedule, Experiments, Topic). The states are worked out from one GET /research. */
export default function Research() {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [ov, setOv] = useState<Load>({ status: "loading" });
  const [query, setQuery] = useState<string | null>(null);
  const [tab, setTab] = useChapter();
  const search = (q: string | null) => {
    setQuery(q);
    if (q !== null) setTab("read"); // a search always lands on the Reading tab
  };

  const load = useCallback(() => {
    if (!token) return Promise.resolve();
    return researchApi.overview(token).then(
      (data) => setOv({ status: "ready", data }),
      (e) => setOv((o) => (o.status === "ready" ? o : { status: "error", code: errCode(e) })),
    );
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);

  const data = ov.status === "ready" ? ov.data : null;
  const running = data?.discovery.state === "running";
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => void load(), WATCH_MS);
    return () => clearInterval(id);
  }, [running, load]);

  const hasTopic = !!data?.profile.title;
  const hasContent = !!data && (data.reading_list.items.length > 0 || data.suggestions.length > 0 || data.upcoming.length > 0);
  const firstSearch = hasTopic && running && !hasContent;

  return (
    <div className="app rs-page" data-guide="research" data-guide-label={t("hub.research")}>
      <header className="topbar">
        <Link className="icon-btn" to="/" aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="back" />
        </Link>
        <h1 className="page-title">{t("hub.research")}</h1>
        <span className="grow" />
        <Settings />
      </header>
      <main className="main rs-main">
        <div className="rs-wrap">
          {ov.status === "loading" && (
            <p className="muted" role="status">
              …
            </p>
          )}
          {ov.status === "error" && (
            <p className="rs-rempty" role="alert">
              {t(`research.err.${ov.code}`, { defaultValue: t("research.err.unknown") })}{" "}
              <button className="btn-link" type="button" onClick={() => void load()}>
                {t("research.retry")}
              </button>
            </p>
          )}
          {data && !hasTopic && <EmptyTopic onSaved={() => void load()} />}
          {data && hasTopic && firstSearch && query === null && (
            <>
              <SearchBar keywords={data.profile.keywords} value="" onSearch={search} />
              <SavedTopic profile={data.profile} />
            </>
          )}
          {data && hasTopic && !(firstSearch && query === null) && (
            <ChapterTabs
              tab={tab}
              onPick={setTab}
              dots={dots(data, t)}
              panels={{
                read: (
                  <>
                    <SearchBar keywords={data.profile.keywords} value={query ?? ""} onSearch={search} />
                    {query !== null ? (
                      <Results key={query} query={query} onClear={() => setQuery(null)} onSearch={(q) => { search(q); window.scrollTo?.({ top: 0 }); }} onChanged={() => void load()} />
                    ) : (
                      <>
                  {running && (
                    <div className="rs-waiting" role="status">
                      <Icon name="clock" />
                      <span>
                        {t("research.discovery.running")}{" "}
                        <span className="rs-dots" aria-hidden="true">
                          <i />
                          <i />
                          <i />
                        </span>
                      </span>
                    </div>
                  )}
                  {!running && data.discovery.last_status === "waiting_model" && (
                    <div className="rs-waiting" role="status">
                      <Icon name="clock" />
                      <span>{t("research.discovery.waiting")}</span>
                    </div>
                  )}
                        {data.hero && <Hero hero={data.hero} />}
                        <ReadList items={data.reading_list.items} suggestions={data.suggestions} searching={running} onChanged={() => void load()} />
                      </>
                    )}
                  </>
                ),
                schedule: <Upcoming items={data.upcoming} onChanged={() => void load()} />,
                experiments: <ExperimentLog items={data.experiments} onChanged={() => void load()} />,
                topic: (
                  <>
                    <TopicCard profile={data.profile} onChanged={() => void load()} />
                    {data.milestones.length > 0 && <Milestones items={data.milestones} goalId={data.goal_id} />}
                  </>
                ),
              }}
            />
          )}
        </div>
      </main>
    </div>
  );
}

/** A dot on Reading when Mentor has new papers, and on Schedule when a deadline is two weeks away or closer. */
const HOT_DAYS = 14;
function dots(data: ResearchOverview, t: (k: string, o?: Record<string, unknown>) => string): Partial<Record<Chapter, ChapterDot>> {
  const due = data.upcoming.filter((u) => u.kind === "deadline" && u.days_left >= 0 && u.days_left <= HOT_DAYS).sort((a, b) => a.days_left - b.days_left)[0];
  return {
    read: data.suggestions.length > 0 ? { kind: "new", label: t("research.tabs.newPapers", { count: data.suggestions.length }) } : null,
    schedule: due ? { kind: "hot", label: t("research.tabs.dueSoon", { count: due.days_left }) } : null,
  };
}
