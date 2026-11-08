import type { Lang, Reminder, RemindersResponse } from "../api";

/**
 * Reminders on the device (CONTRACTS.md section 12). The gateway plans them; the device schedules every
 * `status: "scheduled"` one with `at` in the future, cancels the ones now `cancelled` or `skipped_quiet`, and drops
 * anything before `quiet_until`. Quiet mode set in Settings applies at once (`setQuietUntil`), not at the next fetch.
 * A reminder that is shown and not opened within 30 minutes is reported `ignored`; a tap is reported `opened`.
 */
export const IGNORE_AFTER_MS = 30 * 60000;
const KEEP_FIRED_MS = 3 * 24 * 3600000;
/** setTimeout cannot take more than ~24.8 days; a reminder is never planned that far ahead anyway */
const MAX_DELAY = 2 ** 31 - 1;

export interface LocalNotification {
  id: string;
  kind: Reminder["kind"];
  title: string;
  body: string;
  deepLink: string;
}

export interface FiredEntry {
  firedAt: number;
  done: boolean;
}
export interface FiredStore {
  read(): Record<string, FiredEntry>;
  write(v: Record<string, FiredEntry>): void;
}

export function localFiredStore(userId: string): FiredStore {
  const key = `mentor.reminders.fired.${userId}`;
  return {
    read() {
      try {
        const raw = localStorage.getItem(key);
        return raw ? (JSON.parse(raw) as Record<string, FiredEntry>) : {};
      } catch {
        return {};
      }
    },
    write(v) {
      try {
        if (Object.keys(v).length) localStorage.setItem(key, JSON.stringify(v));
        else localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    },
  };
}

export interface SchedulerDeps {
  notify(n: LocalNotification): void | Promise<void>;
  report(id: string, outcome: "opened" | "ignored"): void | Promise<unknown>;
  lang(): Lang;
  /** false when the user turned reminders off in Settings */
  enabled?(): boolean;
  now?(): number;
  store?: FiredStore;
}

const BREAK_TEXT = {
  vi: (n: number) => `Em học liền ${n} phút rồi. Nghỉ chút đi, Mentor đã lưu chỗ em đang học.`,
  en: (n: number) => `You've studied ${n} minutes straight. Take a break, Mentor saved your place.`,
};

export class ReminderScheduler {
  private timers = new Map<string, { at: number; timer: ReturnType<typeof setTimeout>; r: Reminder }>();
  private ignoreTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private quietUntil = 0;
  private fired: Record<string, FiredEntry>;

  constructor(private d: SchedulerDeps) {
    this.fired = d.store?.read() ?? {};
  }

  private now() {
    return (this.d.now ?? Date.now)();
  }
  private persist() {
    this.d.store?.write(this.fired);
  }

  scheduledIds(): string[] {
    return [...this.timers.keys()];
  }

  /** Quiet mode from Settings (or from the server): reminders due before it are dropped now. */
  setQuietUntil(iso: string | null) {
    const t = iso ? Date.parse(iso) : 0;
    this.quietUntil = Number.isFinite(t) ? t : 0;
    for (const [id, s] of this.timers) {
      if (s.at < this.quietUntil) this.drop(id);
    }
  }

  private drop(id: string) {
    const s = this.timers.get(id);
    if (s) clearTimeout(s.timer);
    this.timers.delete(id);
  }

  /** Apply a GET /reminders answer. */
  sync(resp: RemindersResponse) {
    const serverQuiet = resp.quiet_until ? Date.parse(resp.quiet_until) : 0;
    if (Number.isFinite(serverQuiet)) this.quietUntil = Math.max(this.quietUntil, serverQuiet);
    const wanted = new Set<string>();
    for (const r of resp.reminders) {
      if (r.status !== "scheduled" || r.outcome || this.fired[r.id]) continue;
      const at = Date.parse(r.at);
      if (!Number.isFinite(at) || at <= this.now() || at < this.quietUntil) continue;
      if (at - this.now() > MAX_DELAY) continue;
      wanted.add(r.id);
      const have = this.timers.get(r.id);
      if (have && have.at === at) {
        have.r = r;
        continue;
      }
      this.drop(r.id);
      const timer = setTimeout(() => this.fire(r.id), at - this.now());
      this.timers.set(r.id, { at, timer, r });
    }
    // everything we hold that the server no longer lists as scheduled (replaced by a new plan, quiet, ...)
    for (const id of [...this.timers.keys()]) if (!wanted.has(id)) this.drop(id);
  }

  private fire(id: string) {
    const s = this.timers.get(id);
    this.timers.delete(id);
    if (!s) return;
    if (this.d.enabled && !this.d.enabled()) return;
    if (this.quietUntil > this.now()) return;
    this.show(s.r.id, s.r.kind, s.r.deep_link, this.d.lang() === "en" ? s.r.text_en : s.r.text_vi);
  }

  private show(id: string, kind: Reminder["kind"], deepLink: string, body: string) {
    this.fired[id] = { firedAt: this.now(), done: false };
    this.persist();
    void Promise.resolve(this.d.notify({ id, kind, title: "Mentor", body, deepLink })).catch(() => undefined);
    this.watchIgnored(id, IGNORE_AFTER_MS);
  }

  private watchIgnored(id: string, ms: number) {
    if (id.startsWith("local-")) return; // device-made reminders are not the server's to know
    clearTimeout(this.ignoreTimers.get(id));
    this.ignoreTimers.set(
      id,
      setTimeout(() => this.finish(id, "ignored"), ms),
    );
  }

  private finish(id: string, outcome: "opened" | "ignored") {
    clearTimeout(this.ignoreTimers.get(id));
    this.ignoreTimers.delete(id);
    const e = this.fired[id];
    if (e?.done) return;
    this.fired[id] = { firedAt: e?.firedAt ?? this.now(), done: true };
    this.persist();
    if (!id.startsWith("local-")) void Promise.resolve(this.d.report(id, outcome)).catch(() => undefined);
  }

  /** The user tapped the notification. */
  opened(id: string) {
    this.finish(id, "opened");
  }

  /**
   * After a restart: reminders shown earlier and never answered are `ignored` once their 30 minutes are over; the
   * rest keep waiting for the remaining time. Old entries are forgotten.
   */
  restore() {
    const now = this.now();
    for (const [id, e] of Object.entries(this.fired)) {
      if (now - e.firedAt > KEEP_FIRED_MS) delete this.fired[id];
      else if (!e.done) {
        const left = e.firedAt + IGNORE_AFTER_MS - now;
        if (left <= 0) this.finish(id, "ignored");
        else this.watchIgnored(id, left);
      }
    }
    this.persist();
  }

  /** "Take a break" after `minutes` of continuous focus, computed on the device. */
  breakDue(minutes: number) {
    if (this.d.enabled && !this.d.enabled()) return;
    if (this.quietUntil > this.now()) return;
    const lang = this.d.lang();
    this.show(`local-break-${this.now()}`, "break", "/", BREAK_TEXT[lang](Math.round(minutes)));
  }

  dispose() {
    for (const id of [...this.timers.keys()]) this.drop(id);
    for (const t of this.ignoreTimers.values()) clearTimeout(t);
    this.ignoreTimers.clear();
  }
}
