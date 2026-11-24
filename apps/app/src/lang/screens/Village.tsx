import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { loadVillageData, villageBase, VillageEngine, type ActorsData, type Layout, type Pt } from "../engine";
import { chickenName } from "../subjects";
import { chickenSrc, jumpSrc, reducedMotion } from "../chickenArt";
import type { Chicken } from "../api";
import { ChickenGuide } from "../guide/ChickenGuide";
import { Tray, type SheetKey } from "./village/Tray";
import { useVillage } from "./village/useVillage";
import { keepVillageReadable } from "./village/labels";
import "../styles/fonts";
import "../styles/lang.css";

const MarketSheet = lazy(() => import("./village/Sheets").then((m) => ({ default: m.MarketSheet })));
const NewsSheet = lazy(() => import("./village/Sheets").then((m) => ({ default: m.NewsSheet })));
const WeekSheet = lazy(() => import("./village/Sheets").then((m) => ({ default: m.WeekSheet })));
const SettingsSheet = lazy(() => import("./village/Sheets").then((m) => ({ default: m.SettingsSheet })));
const ListView = lazy(() => import("./village/Sheets").then((m) => ({ default: m.ListView })));

const base = import.meta.env.BASE_URL;
// where the first chickens like to stand (the rest find an open spot, see VillageEngine.seat)
const SEATS: Pt[] = [[-0.6, 7.2], [4.6, 7.6], [2.8, 3.6], [-3.4, 6.2], [7.2, 5.4], [-5.8, 8.4], [1.4, 9.4], [6.4, 9.0]];

const FireIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-4-1-6 1-10z" />
  </svg>
);

/** Làng gà (mockups/lg-01): the student's home. The chicken speaks first; places open from the painted village. */
export function Village() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const nav = useNavigate();
  const lang: "vi" | "en" = i18n.language === "en" ? "en" : "vi";
  const { village, status, refresh, levelUps, clearLevelUps } = useVillage();
  const [data, setData] = useState<{ layout: Layout; sheets: ActorsData | null } | null>(null);
  const [sheet, setSheet] = useState<SheetKey>("none");
  const [list, setList] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [newsSeen, setNewsSeen] = useState(0);
  const [taken, setTaken] = useState<string[]>([]);
  const engine = useRef<VillageEngine | null>(null);
  const els = useRef(new Map<string, HTMLElement>());
  const tags = useRef(new Map<string, HTMLElement>());
  const refs = {
    scene: useRef<HTMLElement>(null),
    world: useRef<HTMLDivElement>(null),
    bg: useRef<HTMLDivElement>(null),
    occ: useRef<HTMLDivElement>(null),
    fx: useRef<HTMLCanvasElement>(null),
    steam: useRef<HTMLDivElement>(null),
  };
  const opener = useRef<HTMLElement | null>(null);
  // the library holds the photo-notes shelf from grade 6 up; its paper reading stays university-only inside
  const library = !!user && user.age_band !== "g1_5";
  const kidKey = user?.avatar ?? "nam";
  const kidName = user?.display_name ?? "";
  const chickens = village?.chickens ?? [];
  const speakerId = village?.speaker?.chicken ?? chickens[0]?.id ?? null;
  const ids = chickens.map((c) => c.id).join(",");
  const looks = chickens.map((c) => `${c.id}:${c.stage}:${c.angry ? "x" : ""}`).join(",");

  useEffect(() => {
    let alive = true;
    loadVillageData().then(
      (d) => alive && setData(d),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, []);

  // the engine: starts once the picture, the map and the first look at the village are there
  const ready = !!data && !!village;
  useEffect(() => {
    if (!ready || !data || !refs.scene.current || !refs.world.current || !refs.bg.current || !refs.occ.current) return;
    const e = new VillageEngine({
      world: refs.world.current,
      scene: refs.scene.current,
      bgHost: refs.bg.current,
      occHost: refs.occ.current,
      fx: refs.fx.current,
      steam: refs.steam.current,
      layout: data.layout,
      sheets: data.sheets,
      base: villageBase(),
    });
    engine.current = e;
    return () => {
      e.destroy();
      engine.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, data]);

  // readable at any size: no sign cut by the edge, the student's name tag never behind a canopy
  useEffect(() => {
    if (!ready || !refs.world.current || !refs.scene.current || typeof getComputedStyle !== "function") return;
    return keepVillageReadable({ world: refs.world.current, scene: refs.scene.current });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, data]);

  // characters: the student and the chickens
  useEffect(() => {
    const e = engine.current;
    if (!e || !ready) return;
    const kidEl = els.current.get("kid");
    if (kidEl && !e.actors.kid) e.addActor(kidEl, { key: "kid", id: kidKey, kind: "kid", pos: [3.4, 6.4], tag: tags.current.get("kid"), still: `${base}ga/hs-${kidKey}.png` });
    else e.setActorId("kid", kidKey);
    chickens.forEach((c, i) => {
      const el = els.current.get(c.id);
      const stay = c.id === speakerId;
      // the costume of its stage (the angry one when its course is neglected): animated where the art has a stand and a jump, else a still
      const angry = !!c.angry;
      const still = chickenSrc(c.art, c.stage, "stand", reducedMotion(), angry);
      const jump = reducedMotion() ? null : jumpSrc(c.art, c.stage, angry);
      if (el && !e.actors[c.id]) e.addActor(el, { key: c.id, id: c.id, kind: "ga", pos: e.seat(stay ? SEATS[0] : SEATS[(i + 1) % SEATS.length], i), stay, stage: c.stage, still, jump, angry, tag: tags.current.get(c.id) });
      else {
        e.setStay(c.id, stay);
        e.setLook(c.id, still, c.stage, jump, angry);
      }
    });
    for (const k of Object.keys(e.actors)) if (k !== "kid" && !ids.split(",").includes(k)) e.removeActor(k);
    e.placeSigns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, ids, looks, speakerId, kidKey]);

  // a level-up: the chicken jumps, the student waves, a line on the board
  useEffect(() => {
    if (!levelUps.length) return;
    const u = levelUps[0];
    void engine.current?.hop(u.chicken);
    void engine.current?.wave("kid");
    setToast(t("lg.levelUp", { name: chickenName(u.chicken, lang), level: u.level }));
    clearLevelUps();
  }, [levelUps, clearLevelUps, lang, t]);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(id);
  }, [toast]);

  const open = (s: SheetKey, from?: HTMLElement | null) => {
    opener.current = from ?? (document.activeElement as HTMLElement | null);
    setSheet(s);
    if (s === "news") setNewsSeen(village?.news.length ?? 0);
  };
  const close = useCallback(() => {
    setSheet("none");
    setTimeout(() => opener.current?.focus?.({ preventScroll: true }), 0);
  }, []);

  // places: the student runs to the door (a moment at most; a second tap skips it), then the place opens
  const going = useRef(false);
  const go = async (sign: string, run: () => void, lean = true) => {
    const en = engine.current;
    if (going.current) {
      en?.skipWalk();
      return;
    }
    going.current = true;
    try {
      await en?.goPlace(sign, lean);
    } finally {
      going.current = false;
    }
    run();
  };
  const goTo = (sign: string, to: string) => void go(sign, () => nav(to, { state: { back: "/" } }));
  const tapChicken = async (c: Chicken) => {
    await engine.current?.hop(c.id);
    nav(`/chuong/${c.id}`, { state: { back: "/" } });
  };
  const tapGround = (e: React.MouseEvent) => {
    const en = engine.current;
    const w = refs.world.current;
    if (!en || !w || (e.target as HTMLElement).closest("button, a, .lg-say")) return;
    const r = w.getBoundingClientRect();
    const u = (e.clientX - r.left) / r.width;
    const v = (e.clientY - r.top) / r.height;
    if (en.justDragged > performance.now() - 300) return;
    if (en.walkableAt(u, v)) void en.walkToPoint(en.screenToWorld(u, v));
  };
  const setEl = (key: string) => (el: HTMLElement | null) => {
    if (el) els.current.set(key, el);
    else els.current.delete(key);
  };
  const setTag = (key: string) => (el: HTMLElement | null) => {
    if (el) tags.current.set(key, el);
    else tags.current.delete(key);
  };

  if (status === "ready" && village && village.chickens.length === 0) return <Navigate to="/chon-ga" replace />;

  const week = village?.week ?? { done: 0, planned: 0 };
  const streak = village?.streak.days ?? 0;
  const newsN = Math.max(0, (village?.news.length ?? 0) - newsSeen);
  const ringText = user?.age_band === "g1_5" ? t("lg.ring.kid", { count: week.done }) : t("lg.ring.sessions", { done: week.done, planned: week.planned });
  const arc = week.planned ? Math.min(1, week.done / week.planned) * 88 : 0;
  const speakerLine = village?.speaker ? (lang === "en" ? village.speaker.line_en || village.speaker.line_vi : village.speaker.line_vi) : "";

  if (status === "error" && !village)
    return (
      <div className="lg lg-back" data-age={user?.age_band ?? "g10_12"}>
        <div className="lg-stage">
          <section className="lg-board" role="alert">
            <h1 className="lg-ribbon-t">{t("lg.village")}</h1>
            <p className="lg-lead">{t("lg.villageFail")}</p>
            <button className="lg-cta" type="button" onClick={() => void refresh()}>
              {t("lg.retry")}
            </button>
          </section>
        </div>
      </div>
    );

  return (
    <div className="lg lg-village" data-age={user?.age_band ?? "g10_12"} data-kid={kidKey}>
      {!ready && (
        <div className="lg-splash" role="status">
          <img src={`${base}ga/icon-ga.png`} alt="" width="96" height="96" />
          <span>{t("lg.opening")}</span>
        </div>
      )}
      <main className="lg-scene" id="lg-scene" ref={refs.scene} aria-label={t("lg.village")} onClick={tapGround}>
        <div className="lg-world" ref={refs.world} style={{ ["--ratio" as string]: 3.2 }}>
          <div className="lg-sky" aria-hidden="true">
            <i style={{ ["--y" as string]: "8%", ["--w" as string]: "16%", ["--t" as string]: "150s", ["--d" as string]: "-20s" }} />
            <i style={{ ["--y" as string]: "34%", ["--w" as string]: "11%", ["--t" as string]: "120s", ["--d" as string]: "-75s" }} />
            <i style={{ ["--y" as string]: "16%", ["--w" as string]: "20%", ["--t" as string]: "190s", ["--d" as string]: "-130s" }} />
          </div>
          <div className="lg-bg" ref={refs.bg} aria-hidden="true" />
          <div className="lg-cshade" aria-hidden="true">
            <i style={{ ["--y" as string]: "30%", ["--t" as string]: "140s", ["--d" as string]: "-30s" }} />
            <i style={{ ["--y" as string]: "62%", ["--t" as string]: "170s", ["--d" as string]: "-110s" }} />
          </div>
          <canvas className="lg-fx" ref={refs.fx} aria-hidden="true" />
          <div className="lg-steam" ref={refs.steam} aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </div>
          <div ref={refs.occ} style={{ display: "contents" }} aria-hidden="true" />

          <button className="lg-place" type="button" data-sign="arena" onClick={() => goTo("arena", "/dau-truong")}>
            <span className="lg-sign">{t("lg.place.arena")}</span>
          </button>
          {library && (
            <button className="lg-place" type="button" data-sign="library" onClick={() => goTo("library", "/thu-vien")}>
              <span className="lg-sign">{t("lg.place.library")}</span>
            </button>
          )}
          <button className="lg-place" type="button" data-sign="spring" onClick={() => goTo("spring", "/phong-tu-hoc")}>
            <span className="lg-sign">
              {t("lg.place.study1")}
              <br />
              {t("lg.place.study2")}
            </span>
          </button>
          <button className="lg-place" type="button" data-sign="board" aria-label={newsN ? t("lg.news.aria", { count: newsN }) : t("lg.place.news")} onClick={(e) => open("news", e.currentTarget)}>
            <span className="lg-sign">
              {t("lg.place.news")}
              {newsN > 0 && <span className="dot" aria-hidden="true" />}
            </span>
          </button>
          <span className="lg-burnt" data-sign="gate" aria-hidden="true">
            {t("lg.village")}
          </span>

          {village && (
            <div className="lg-actor is-kid" ref={setEl("kid")} aria-label={t("lg.meAria")} data-id="kid">
              <span className="lg-shadow" />
              <span className="lg-spr" />
            </div>
          )}
          {chickens.map((c) => {
            const name = lang === "en" ? c.name_en : c.name_vi;
            const speaker = c.id === speakerId;
            return (
              <div key={c.id} className={"lg-actor ga" + (speaker ? " speaker" : "") + (c.angry ? " angry" : "")} ref={setEl(c.id)} data-id={c.id}>
                <span className="lg-shadow" />
                <span className="lg-spr" />
                <button className="lg-hit" type="button" title={name} aria-label={t("lg.chickenAria", { name, level: c.level, done: c.done_today ? t("lg.doneAria") : "" })} onClick={() => void tapChicken(c)} />
                {speaker && speakerLine && (
                  <span className="lg-say" id="lg-say" role="note">
                    <span>{speakerLine}</span>
                  </span>
                )}
              </div>
            );
          })}
          {/* the student's name tag: one layer over the scenery, hanging under the student */}
          <div className="lg-tags" aria-hidden="true">
            {village && (
              <span className="lg-plate is-kid" ref={setTag("kid")} data-for="kid">
                <span>{kidName}</span>
                {streak > 0 && (
                  <span className="fire">
                    <FireIcon />
                    {streak}
                  </span>
                )}
              </span>
            )}
          </div>
          {/* the chickens' level badges: in the same depth order as the chickens, so scenery in front of a chicken covers its badge too */}
          <div className="lg-tags lg-tags-ga" aria-hidden="true">
            {chickens.map((c) => (
              <span key={c.id} className={"lg-plate ga lg-mini" + (c.stage >= 4 ? " master" : "") + (c.done_today ? " done" : "")} ref={setTag(c.id)} data-for={c.id}>
                <span className="lv">{c.level}</span>
                {c.done_today && <span className="tick">✓</span>}
              </span>
            ))}
          </div>
        </div>
      </main>

      <div className="lg-hud lg-me">
        <span className="face" aria-hidden="true" style={{ backgroundImage: `url(${base}ga/hs-${kidKey}.png)` }} />
        <div>
          <b>{kidName}</b>
          {streak > 0 && (
            <span className="streak">
              <FireIcon />
              <span>{t("lg.streak", { count: streak })}</span>
            </span>
          )}
        </div>
      </div>
      <div className="lg-hud lg-tr">
        <button className="lg-ring" id="lg-ring" type="button" aria-label={t("lg.ring.aria", { done: week.done, planned: week.planned })} onClick={(e) => open("progress", e.currentTarget)}>
          <svg viewBox="0 0 36 36" aria-hidden="true">
            <circle className="trk" cx="18" cy="18" r="14" fill="none" strokeWidth="5" />
            <circle className="val" cx="18" cy="18" r="14" fill="none" strokeWidth="5" strokeDasharray={`${arc} 88`} />
          </svg>
          <span>{ringText}</span>
        </button>
        <button className="lg-rb" type="button" aria-pressed={list} aria-label={t("lg.list.toggle")} onClick={() => setList((l) => !l)}>
          <Icon name="layers" />
        </button>
        <button className="lg-rb" type="button" data-settings aria-label={t("settings.open")} onClick={(e) => open("settings", e.currentTarget)}>
          <Icon name="gear" />
        </button>
      </div>
      {/* the chicken market: one door, the stall icon under the top-right buttons (the new village has no stalls to hang a sign on) */}
      <button className="lg-hud lg-mk" id="lg-market" type="button" aria-label={t("lg.market.aria")} onClick={(e) => open("market", e.currentTarget)}>
        <span className="art" aria-hidden="true">
          <img src={`${base}ga/cho-icon.webp`} alt="" width="88" height="88" />
          <span className="plus">+</span>
        </span>
        <b>{t("lg.market.title")}</b>
      </button>
      {village && <Tray village={village} openSheet={(s) => open(s)} onChanged={() => void refresh()} />}

      <Suspense fallback={null}>
        {list && village && (
          <ListView
            village={village}
            library={library}
            onMarket={() => {
              setList(false);
              open("market");
            }}
            onClose={() => setList(false)}
          />
        )}
        {sheet === "market" && village && (
          <MarketSheet
            onClose={close}
            owned={village.chickens.map((c) => c.id).concat(taken)}
            onTaken={(c) => {
              setTaken((l) => [...l, c.id]);
              setToast(t("lg.market.taken", { name: lang === "en" ? c.name_en : c.name_vi }));
              void refresh();
            }}
          />
        )}
        {sheet === "news" && village && <NewsSheet news={village.news} onClose={close} />}
        {sheet === "progress" && <WeekSheet onClose={close} />}
        {sheet === "settings" && <SettingsSheet onClose={close} />}
      </Suspense>

      {toast && (
        <div className="lg-toast" role="status">
          {toast}
        </div>
      )}
      {village && <ChickenGuide screen="village" chicken={speakerId ?? "toan"} />}
    </div>
  );
}
