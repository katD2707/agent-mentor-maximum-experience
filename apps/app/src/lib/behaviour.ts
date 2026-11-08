import { api, ApiError, type Lang, type RemindersResponse, type User } from "../api";
import { flushEvents, logEvent, startLogger, stopLogger } from "./events";
import { FocusTracker } from "./focus";
import { localFiredStore, ReminderScheduler, type LocalNotification } from "./reminders";
import { hasPushSubscription, isTauri, nativeOnOpen, nativeShow, registerWorker, webOnOpen, webShow, type OpenReminder } from "./platform";
import { flushOutbox } from "./enrollments";

/**
 * Everything the app does in the background for a signed-in student: the behaviour logger (events, focus accounting),
 * and the reminders (fetch, schedule, show, report). One instance per session; `App` starts and stops it.
 */
export const REMIND_KEY = "mentor.reminders";
const PULL_EVERY_MS = 10 * 60000;

export const remindersEnabled = (): boolean => {
  try {
    return localStorage.getItem(REMIND_KEY) !== "off";
  } catch {
    return true;
  }
};

export interface Background {
  stop(): void;
  /** quiet mode changed in Settings: apply it now */
  setQuiet(until: string | null): void;
  /** the user tapped a reminder (desktop toast, web notification or a tab opened by it) */
  opened(id: string): void;
  /** fetch /reminders again (after the plan may have changed) */
  refresh(): Promise<void>;
}

let running: Background | null = null;
/** For screens that change the plan (a new goal): ask the running background to re-read the reminders. */
export const refreshReminders = (): Promise<void> => running?.refresh() ?? Promise.resolve();

export function startBackground(opts: { token: string; user: User; lang: () => Lang; open: (o: OpenReminder) => void }): Background {
  const { token, user } = opts;
  startLogger(token, user.id);
  let breakAfter = 0;

  const scheduler = new ReminderScheduler({
    lang: opts.lang,
    enabled: remindersEnabled,
    store: localFiredStore(user.id),
    notify: (n: LocalNotification) => (isTauri() ? nativeShow(n) : webShow(n)),
    report: async (id, outcome) => {
      try {
        await api.reminderOutcome(token, id, outcome);
      } catch (e) {
        if (e instanceof ApiError && e.code === "not_found") return; // the plan was rebuilt: nothing to report to
        // offline: the behaviour queue carries it to the server when the network is back
        logEvent("reminder_outcome", { reminder_id: id, outcome, at: new Date().toISOString() });
      }
    },
  });
  scheduler.setQuietUntil(user.quiet_until);
  scheduler.restore();

  const focus = new FocusTracker({
    emit: (kind, data) => logEvent(kind, data),
    breakAfterMin: () => breakAfter,
    onBreakDue: (m) => scheduler.breakDue(m),
  });

  // ---- reminders: fetch, then schedule locally (or leave it to Web Push when this browser is subscribed)
  const pull = async () => {
    try {
      const r: RemindersResponse = await api.getReminders(token);
      breakAfter = r.break_after_minutes;
      const pushed = !isTauri() && (await hasPushSubscription());
      scheduler.sync(pushed ? { ...r, reminders: [] } : r);
    } catch {
      /* offline: what is already scheduled stays */
    }
  };

  // ---- behaviour events
  logEvent("app_open");
  const flushAll = () => {
    void flushEvents();
    void flushOutbox(token, user.id);
  };
  const onInput = () => focus.touch();
  const onVisible = () => {
    const v = document.visibilityState === "visible";
    focus.setVisible(v);
    if (v) void pull();
  };
  const onHide = () => {
    focus.end();
    void flushEvents();
  };
  const inputs = ["pointerdown", "keydown", "wheel", "touchstart", "scroll"] as const;
  inputs.forEach((e) => window.addEventListener(e, onInput, { passive: true, capture: true }));
  document.addEventListener("timeupdate", onInput, true); // a playing video is focus too
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("pagehide", onHide);
  window.addEventListener("online", flushAll);
  window.addEventListener("online", pull);
  focus.setVisible(document.visibilityState === "visible");

  const sampler = setInterval(() => focus.sample(), 1000);
  const puller = setInterval(pull, PULL_EVERY_MS);
  const flusher = setInterval(() => void flushEvents(), 60000);
  void pull();
  void flushEvents();

  // ---- a tapped notification (desktop: Rust event; web: service worker message)
  let unlistenNative: (() => void) | null = null;
  let dead = false;
  if (isTauri()) {
    void nativeOnOpen(opts.open).then((u) => (dead ? u() : (unlistenNative = u)));
  } else {
    void registerWorker();
  }
  const unlistenWeb = isTauri() ? () => undefined : webOnOpen(opts.open);

  const bg: Background = {
    stop() {
      dead = true;
      focus.end();
      scheduler.dispose();
      clearInterval(sampler);
      clearInterval(puller);
      clearInterval(flusher);
      inputs.forEach((e) => window.removeEventListener(e, onInput, true));
      document.removeEventListener("timeupdate", onInput, true);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("online", flushAll);
      window.removeEventListener("online", pull);
      unlistenNative?.();
      unlistenWeb();
      if (running === bg) running = null;
      void flushEvents().finally(() => {
        if (!running) stopLogger(); // signed out; a new session would have replaced the logger already
      });
    },
    setQuiet(until) {
      scheduler.setQuietUntil(until);
      if (!until || Date.parse(until) <= Date.now()) void pull(); // quiet ended or cleared: bring the dropped ones back
    },
    opened: (id) => scheduler.opened(id),
    refresh: pull,
  };
  running = bg;
  return bg;
}
