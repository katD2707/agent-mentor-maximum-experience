import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, type Goal, type Lang, type Theme, type WeekPlan } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { UpdateRow } from "../../../components/UpdateRow";
import { SettingsSourcesRow } from "../library/research/Sources";
import { setLang } from "../../../i18n";
import { isQuiet, quietCustom, quietUntil, type QuietPick } from "../../../lib/quiet";
import { enableWebNotifications, isTauri, notifyState, type NotifyState } from "../../../lib/platform";
import { REMIND_KEY, refreshReminders } from "../../../lib/behaviour";
import { REPLAY_EVENT } from "../../../lib/tours";
import { resolveDeepLink } from "../../../lib/deeplink";
import { APP_VERSION } from "../../../lib/version";
import { lg, type Chicken, type MarketChicken, type NewsItem, type Village } from "../../api";
import { artFile, chickenName } from "../../subjects";
import { cropVars } from "../../chickenArt";

const base = import.meta.env.BASE_URL;

/** One wooden board in the middle of the screen (shared by the market, the notice board, the week and the settings). */
export function Sheet({ id, title, onClose, children, wide }: { id: string; title: string; onClose(): void; children: ReactNode; wide?: boolean }) {
  const { t } = useTranslation();
  const x = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    x.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <>
      <div className="lg-scrim" onClick={onClose} />
      <section className={"lg-sheet" + (wide ? " wide" : "")} role="dialog" aria-modal="true" aria-labelledby={id}>
        <div className="lg-sheet-h">
          <h2 id={id}>{title}</h2>
          <span className="grow" />
          <button ref={x} className="lg-sheet-x" type="button" onClick={onClose} aria-label={t("lg.close")}>
            <Icon name="x" />
          </button>
        </div>
        {children}
      </section>
    </>
  );
}

// ---------------------------------------------------------------- Chợ gà
/** The market: take more chickens (one per subject, free). */
export function MarketSheet({ onClose, onTaken, owned }: { onClose(): void; onTaken(c: Chicken): void; owned: string[] }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const lang = i18n.language === "en" ? "en" : "vi";
  const [list, setList] = useState<MarketChicken[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    lg.getMarket(token).then(
      (m) => alive && setList(m.chickens),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [token]);

  const take = async (id: string) => {
    if (!token || busy) return;
    setBusy(id);
    setFailed(false);
    try {
      const c = await lg.takeChicken(token, id);
      setList((l) => l?.map((m) => (m.id === id ? { ...m, owned: true } : m)) ?? l);
      onTaken(c);
    } catch (e) {
      // already owned (409): the card just turns to "yours"
      if (e instanceof Object && "status" in e && (e as { status: number }).status === 409) setList((l) => l?.map((m) => (m.id === id ? { ...m, owned: true } : m)) ?? l);
      else setFailed(true);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Sheet id="lg-s-mk" title={t("lg.market.title")} onClose={onClose}>
      <p className="lg-lead2">{t("lg.market.lead")}</p>
      {failed && <p className="lg-note" role="alert">{t("lg.market.failed")}</p>}
      <div className="lg-shop">
        {(list ?? []).map((m) => {
          const mine = m.owned || owned.includes(m.id);
          return (
            <div key={m.id} className={"lg-gcard" + (mine ? " mine" : "")}>
              <span className="pic">
                <img src={`${base}ga/${m.art}.png`} alt="" className="ga-crop" style={cropVars(m.art, 3, { fill: 0.74, pad: 0.14 })} />
              </span>
              <b>{lang === "en" ? m.name_en : m.name_vi}</b>
              <small>{t("lg.first.courses", { count: m.courses })}</small>
              {mine ? (
                <span className="have">✓ {t("lg.market.have")}</span>
              ) : (
                <button type="button" className="lg-take" data-take={m.id} disabled={busy !== null} onClick={() => void take(m.id)}>
                  {t("lg.market.take")}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------- Bảng tin
export function NewsSheet({ news, onClose }: { news: NewsItem[]; onClose(): void }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "en" ? "en" : "vi";
  return (
    <Sheet id="lg-s-news" title={t("lg.place.news")} onClose={onClose}>
      <div className="lg-feed" aria-live="polite">
        {news.length === 0 && <p>{t("lg.news.empty")}</p>}
        {news.map((n) => (
          <p key={n.id}>
            {n.chicken && <b>{chickenName(n.chicken, lang)}</b>}
            <span>{lang === "en" ? n.text_en || n.text_vi : n.text_vi}</span>
          </p>
        ))}
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------- Tuần này
/** The week from the ring: seven days planned by Mentor, the goals, and the way to the full progress screen. */
export function WeekSheet({ onClose }: { onClose(): void }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const lang = i18n.language === "en" ? "en" : "vi";
  const [plan, setPlan] = useState<WeekPlan | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.getWeekPlan(token).then((p) => alive && setPlan(p), () => undefined);
    api.listGoals(token).then((g) => alive && setGoals(g), () => undefined);
    return () => {
      alive = false;
    };
  }, [token]);

  const wd = t("settings.weekdays", { returnObjects: true }) as unknown as string[]; // CN, T2 ... T7
  const names = [wd[1], wd[2], wd[3], wd[4], wd[5], wd[6], wd[0]];
  const days = plan ? plan.days.slice(0, 7) : [];
  return (
    <Sheet id="lg-s-prog" title={t("lg.week.title")} onClose={onClose}>
      {plan ? (
        <div className="lg-days" aria-label={t("lg.week.aria")}>
          {days.map((d, i) => {
            const its = plan.items.filter((x) => x.date === d && x.kind !== "break");
            const done = its.length > 0 && its.every((x) => x.done);
            const now = d === plan.today;
            const next = its.find((x) => !x.done);
            const cls = "lg-day" + (done ? " ok" : "") + (now ? " now" : "");
            const inner = (
              <>
                <b>{names[i]}</b>
                {done ? <Icon name="check" /> : its.length ? <span>{(lang === "en" ? its[0].title_en : its[0].label) || its[0].label}</span> : <span>{t("lg.week.rest")}</span>}
                {done && <span className="lg-vh">{t("lg.week.done")}</span>}
              </>
            );
            // a day with a session still to do opens that session (it comes back to the village)
            return next && d >= plan.today ? (
              <Link key={d} className={cls} to={resolveDeepLink(next.deep_link).to} state={{ back: "/" }} aria-label={`${names[i]}: ${next.label}`}>
                {inner}
              </Link>
            ) : (
              <div key={d} className={cls}>
                {inner}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="lg-lead2">{t("lg.loading")}</p>
      )}
      {plan && (lang === "en" ? plan.note_en : plan.note_vi) && <p className="lg-lead2">{lang === "en" ? plan.note_en : plan.note_vi}</p>}
      <div>
        {goals.slice(0, 4).map((g) => (
          <div className="lg-goal" key={g.id}>
            <div className="lg-goal-top">
              <b>{g.title}</b>
              <span className={"lg-gtag" + (g.status === "on_track" ? " ok" : "")}>{t(`lg.week.status.${g.status}`)}</span>
            </div>
            <span className="lg-gbar" aria-hidden="true">
              <i style={{ width: `${Math.min(100, g.progress_pct)}%` }} />
            </span>
          </div>
        ))}
      </div>
      <Link className="lg-reply" to="/tien-do" state={{ back: "/" }}>
        <Icon name="chart" />
        <span>{t("lg.week.full")}</span>
      </Link>
    </Sheet>
  );
}

// ---------------------------------------------------------------- Cài đặt
const PICKS: QuietPick[] = ["30", "60", "120", "tomorrow", "week"];
const THEMES: Theme[] = ["system", "light", "dark"];
const PICK_KEY = "mentor.quietPick";
const read = (k: string): string | null => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
const write = (k: string, v: string) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* ignore */
  }
};
const hm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

/** Every row of the old settings popover: language, theme, reminders, notifications, quiet mode, tips, update, sign out. */
export function SettingsSheet({ onClose }: { onClose(): void }) {
  const { t } = useTranslation();
  const { user, token, updateMe, setQuiet, logout } = useAuth();
  const [notify, setNotify] = useState<NotifyState>(() => notifyState());
  const [customOpen, setCustomOpen] = useState(false);
  const [day, setDay] = useState(0);
  const [mins, setMins] = useState(21 * 60);
  const [pick, setPick] = useState(() => read(PICK_KEY) ?? "");
  const [reminders, setReminders] = useState(() => read(REMIND_KEY) !== "off");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);
  const gear = useRef<HTMLButtonElement>(null);
  if (!user) return null;
  const quiet = isQuiet(user.quiet_until, now);
  const swallow = (p: Promise<unknown>) => void p.catch(() => undefined);
  const when = (iso: string) => {
    const d = new Date(iso);
    const days = t("settings.weekdays", { returnObjects: true }) as unknown as string[];
    const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    return d.toDateString() === new Date().toDateString() ? time : `${time} ${days[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`;
  };
  const startQuiet = (p: string, until: string) => {
    setPick(p);
    write(PICK_KEY, p);
    swallow(setQuiet(until));
  };
  const chooseLang = (l: Lang) => {
    setLang(l);
    swallow(updateMe({ language: l }));
  };

  return (
    <Sheet id="lg-s-set" title={t("settings.title")} onClose={onClose}>
      <div className="lg-set">
        {user.birth_year !== null && (
          <div className="lg-srow">
            <span className="lg-slabel">{t("settings.birthYear")}</span>
            <span>{user.birth_year}</span>
          </div>
        )}
        <div className="lg-srow">
          <span className="lg-slabel">{t("settings.language")}</span>
          <span className="lg-chips">
            <button type="button" aria-pressed={user.language === "vi"} onClick={() => chooseLang("vi")}>
              Tiếng Việt
            </button>
            <button type="button" aria-pressed={user.language === "en"} onClick={() => chooseLang("en")}>
              English
            </button>
          </span>
        </div>
        <div className="lg-srow">
          <span className="lg-slabel">{t("settings.theme")}</span>
          <span className="lg-chips">
            {THEMES.map((th) => (
              <button key={th} type="button" aria-pressed={user.theme === th} onClick={() => swallow(updateMe({ theme: th }))}>
                {t(`settings.themeOptions.${th}`)}
              </button>
            ))}
          </span>
        </div>
        <SettingsSourcesRow returnTo={gear} onOpen={onClose} />
        <div className="lg-srow sw">
          <span className="lg-slabel">{t("settings.reminders")}</span>
          <button
            className="lg-switch"
            type="button"
            role="switch"
            aria-checked={reminders}
            aria-label={t("settings.reminders")}
            onClick={() => {
              setReminders(!reminders);
              write(REMIND_KEY, reminders ? "off" : "on");
              void refreshReminders();
            }}
          />
        </div>
        {!isTauri() && reminders && notify !== "unsupported" && (
          <div className="lg-srow">
            <span className="lg-slabel">{t("settings.notify")}</span>
            {notify === "granted" ? (
              <span>{t("settings.notifyOn")}</span>
            ) : notify === "denied" ? (
              <span>{t("settings.notifyDenied")}</span>
            ) : (
              <button
                className="lg-chipbtn"
                type="button"
                onClick={() =>
                  token &&
                  void enableWebNotifications(
                    () => api.vapidPublicKey(token),
                    (sub) => api.pushSubscribe(token, sub),
                  ).then((st) => {
                    setNotify(st);
                    void refreshReminders();
                  })
                }
              >
                {t("settings.notifyEnable")}
              </button>
            )}
          </div>
        )}
        <div className="lg-srow">
          <span className="lg-slabel">{t("settings.quiet")}</span>
          <span className="lg-chips">
            {PICKS.map((p) => (
              <button
                key={p}
                type="button"
                data-quiet={p}
                aria-pressed={quiet && pick === p}
                onClick={() => {
                  setCustomOpen(false);
                  startQuiet(p, quietUntil(p));
                }}
              >
                {t(`settings.quietOptions.${p}`)}
              </button>
            ))}
            <button type="button" data-quiet="custom" aria-pressed={quiet && pick === "custom"} onClick={() => setCustomOpen(true)}>
              {t("settings.quietOptions.custom")}
            </button>
          </span>
          {customOpen && (
            <span className="lg-qc">
              <span className="lg-chips">
                {[0, 1, 2].map((d) => (
                  <button key={d} type="button" aria-pressed={day === d} onClick={() => setDay(d)}>
                    {t(["settings.today", "settings.tomorrow", "settings.dayAfter"][d])}
                  </button>
                ))}
              </span>
              <span className="lg-chips">
                <button type="button" aria-label={t("settings.earlier")} onClick={() => setMins((m) => (m - 30 + 1440) % 1440)}>
                  −
                </button>
                <output aria-live="polite">{hm(mins)}</output>
                <button type="button" aria-label={t("settings.later")} onClick={() => setMins((m) => (m + 30) % 1440)}>
                  +
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const until = quietCustom(day, mins);
                    if (until) {
                      startQuiet("custom", until);
                      setCustomOpen(false);
                    }
                  }}
                >
                  {t("settings.set")}
                </button>
              </span>
            </span>
          )}
          {quiet && user.quiet_until && (
            <span className="lg-chips">
              <span>{t("settings.quietUntil", { when: when(user.quiet_until) })}</span>
              <button
                type="button"
                onClick={() => {
                  setPick("");
                  write(PICK_KEY, "");
                  swallow(setQuiet(null));
                }}
              >
                {t("settings.turnOn")}
              </button>
            </span>
          )}
        </div>
        <div className="lg-srow">
          <span className="lg-slabel">{t("lg.settings.tips")}</span>
          <span>
            <button
              type="button"
              className="lg-chipbtn"
              onClick={() => {
                onClose();
                window.dispatchEvent(new Event(REPLAY_EVENT));
              }}
            >
              {t("settings.tipsReplay")}
            </button>
          </span>
        </div>
        <UpdateRow />
        <p className="lg-sfoot">
          <span>{t("settings.version", { version: APP_VERSION })}</span>
          <button type="button" onClick={() => void logout()}>
            {t("settings.logout")}
          </button>
        </p>
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------- list view
/** The same village as a plain list (keyboard, screen readers, small screens): chickens and places. */
export function ListView({ village, uni, onMarket, onClose }: { village: Village; uni: boolean; onMarket(): void; onClose(): void }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "en" ? "en" : "vi";
  const speaker = village.speaker;
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);
  const places: { to?: string; title: string; sub: string; run?: () => void }[] = [
    { to: "/dau-truong", title: t("lg.place.arena"), sub: t("lg.list.arena") },
    { title: t("lg.market.title"), sub: t("lg.list.market"), run: onMarket },
    { to: "/phong-tu-hoc", title: t("lg.place.study"), sub: t("lg.list.study") },
    { to: "/tien-do", title: t("lg.list.progress"), sub: t("lg.list.progressSub") },
    ...(uni ? [{ to: "/thu-vien", title: t("lg.place.library"), sub: t("lg.list.library") }] : []),
  ];
  return (
    <aside className="lg-listv" id="lg-listv" aria-label={t("lg.list.aria")}>
      <h2>{t("lg.list.mine")}</h2>
      <ul>
        {village.chickens.map((c) => (
          <li key={c.id}>
            <Link to={`/chuong/${c.id}`} state={{ back: "/" }}>
              <img src={`${base}ga/${artFile(c.art, c.stage)}`} alt="" />
              <span>
                <b>
                  {lang === "en" ? c.name_en : c.name_vi} · {t("lg.level")} {c.level}
                </b>
                <small>{speaker?.chicken === c.id ? (lang === "en" ? speaker.line_en || speaker.line_vi : speaker.line_vi) : c.done_today ? t("lg.list.doneToday") : t("lg.list.nothing")}</small>
              </span>
              <Icon name="next" />
            </Link>
          </li>
        ))}
      </ul>
      <h2>{t("lg.list.goTo")}</h2>
      <ul>
        {places.map((p) => (
          <li key={p.title}>
            {p.to ? (
              <Link to={p.to} state={{ back: "/" }}>
                <span />
                <span>
                  <b>{p.title}</b>
                  <small>{p.sub}</small>
                </span>
                <Icon name="next" />
              </Link>
            ) : (
              <button type="button" onClick={p.run}>
                <span />
                <span>
                  <b>{p.title}</b>
                  <small>{p.sub}</small>
                </span>
                <Icon name="next" />
              </button>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
