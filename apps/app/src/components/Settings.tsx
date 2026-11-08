import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../state/auth";
import { Icon } from "./Icon";
import { isQuiet, quietCustom, quietUntil, type QuietPick } from "../lib/quiet";
import { setLang } from "../i18n";
import { api } from "../api";
import type { Lang, Theme } from "../api/types";
import { enableWebNotifications, isTauri, notifyState, type NotifyState } from "../lib/platform";
import { REMIND_KEY as REMIND_STORE, refreshReminders } from "../lib/behaviour";
import { UpdateRow } from "./UpdateRow";
import { SettingsSourcesRow } from "../screens/research/Sources";

const PICKS: QuietPick[] = ["30", "60", "120", "tomorrow", "week"];
const THEMES: Theme[] = ["system", "light", "dark"];
const VERSION = "0.1.0";
const REMIND_KEY = REMIND_STORE;
const PICK_KEY = "mentor.quietPick";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, v: string) {
  try {
    localStorage.setItem(key, v);
  } catch {
    /* ignore */
  }
}

function useNow(ms = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

const hm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

/** Gear button top-right + its popover (no settings page). Behaviour copied from mockups/shared.js. */
export function Settings() {
  const { t } = useTranslation();
  const { user, token, updateMe, setQuiet, logout } = useAuth();
  const [notify, setNotify] = useState<NotifyState>(() => notifyState());
  const [open, setOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [day, setDay] = useState(0);
  const [mins, setMins] = useState(21 * 60);
  const [pick, setPick] = useState(() => read(PICK_KEY) ?? "");
  const [reminders, setReminders] = useState(() => read(REMIND_KEY) !== "off");
  const wrap = useRef<HTMLDivElement>(null);
  const gear = useRef<HTMLButtonElement>(null);
  const now = useNow();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        gear.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;
  const teacher = user.role === "teacher";
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
    <div className="gear-wrap" ref={wrap} data-guide="settings" data-guide-label={t("settings.title")}>
      <button
        ref={gear}
        className={"icon-btn" + (quiet ? " is-quiet" : "")}
        type="button"
        data-settings
        aria-label={t("settings.open")}
        aria-expanded={open}
        aria-controls="set-pop"
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name="gear" />
      </button>
      {open && (
        <div className="set-pop" id="set-pop" data-mascot-avoid role="dialog" aria-label={t("settings.title")}>
          {!teacher && user.birth_year !== null && (
            <div className="set-row">
              <span className="set-label">{t("settings.birthYear")}</span>
              <span className="set-birth">{user.birth_year}</span>
            </div>
          )}
          <div className="set-row">
            <span className="set-label">{t("settings.language")}</span>
            <span className="set-chips">
              <button type="button" aria-pressed={user.language === "vi"} onClick={() => chooseLang("vi")}>
                Tiếng Việt
              </button>
              <button type="button" aria-pressed={user.language === "en"} onClick={() => chooseLang("en")}>
                English
              </button>
            </span>
          </div>
          <div className="set-row">
            <span className="set-label">{t("settings.theme")}</span>
            <span className="set-chips">
              {THEMES.map((th) => (
                <button key={th} type="button" aria-pressed={user.theme === th} onClick={() => swallow(updateMe({ theme: th }))}>
                  {t(`settings.themeOptions.${th}`)}
                </button>
              ))}
            </span>
          </div>
          {!teacher && <SettingsSourcesRow returnTo={gear} onOpen={() => setOpen(false)} />}
          {!teacher && (
            <>
              <div className="set-row has-switch">
                <span className="set-label">{t("settings.reminders")}</span>
                <button
                  className="set-switch"
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
                <div className="set-row">
                  <span className="set-label">{t("settings.notify")}</span>
                  {notify === "granted" ? (
                    <span className="muted small">{t("settings.notifyOn")}</span>
                  ) : notify === "denied" ? (
                    <span className="muted small">{t("settings.notifyDenied")}</span>
                  ) : (
                    <button
                      className="btn btn-ghost"
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
              <div className="set-row">
                <span className="set-label">{t("settings.quiet")}</span>
                <span className="set-chips">
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
                  <span className="quiet-custom">
                    <span className="set-chips">
                      {[0, 1, 2].map((d) => (
                        <button key={d} type="button" aria-pressed={day === d} onClick={() => setDay(d)}>
                          {t(["settings.today", "settings.tomorrow", "settings.dayAfter"][d])}
                        </button>
                      ))}
                    </span>
                    <span className="qc-time">
                      <button type="button" className="qc-step" aria-label={t("settings.earlier")} onClick={() => setMins((m) => (m - 30 + 1440) % 1440)}>
                        −
                      </button>
                      <output className="qc-out" aria-live="polite">
                        {hm(mins)}
                      </output>
                      <button type="button" className="qc-step" aria-label={t("settings.later")} onClick={() => setMins((m) => (m + 30) % 1440)}>
                        +
                      </button>
                      <button
                        type="button"
                        className="quiet-ok"
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
                  <span className="quiet-status">
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
            </>
          )}
          <UpdateRow />
          <p className="set-foot">
            <span>{t("settings.version", { version: VERSION })}</span>
            <button type="button" onClick={() => void logout()}>
              {t("settings.logout")}
            </button>
          </p>
        </div>
      )}
    </div>
  );
}
