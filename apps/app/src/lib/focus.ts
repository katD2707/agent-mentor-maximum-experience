import { newId } from "./events";
import type { EventKind } from "../api";

/**
 * Focus accounting. A second counts only while the page is visible and the user did something (pointer, key, scroll,
 * playing video) within `idleMs` (60 s). Every `tickEveryS` of active time it emits `focus_tick {session, seconds}`;
 * `seconds` is active time since the previous tick, so ticks add up to the real focus time. A session starts at the
 * first active second and ends after `sessionIdleMs` without activity (or `end()` on close). The same clock tells
 * when the learner has studied `breakAfterMin` minutes in a row (a pause of `breakResetMs` starts the count again).
 */
export interface FocusOptions {
  emit(kind: EventKind, data: Record<string, unknown>): void;
  onBreakDue?(minutes: number): void;
  breakAfterMin?: () => number;
  now?: () => number;
  idleMs?: number;
  tickEveryS?: number;
  sessionIdleMs?: number;
  breakResetMs?: number;
}

export class FocusTracker {
  private visible = true;
  private lastInput: number;
  private last: number;
  private lastActive = 0;
  private acc = 0;
  private sessionSeconds = 0;
  private streak = 0;
  session: string | null = null;

  constructor(private o: FocusOptions) {
    this.last = this.lastInput = this.now();
  }

  private now() {
    return (this.o.now ?? Date.now)();
  }

  touch() {
    this.lastInput = this.now();
  }

  setVisible(v: boolean) {
    this.visible = v;
    this.last = this.now(); // time while hidden is never counted
    if (v) this.lastInput = this.now();
  }

  isActive(): boolean {
    return this.visible && this.now() - this.lastInput <= (this.o.idleMs ?? 60000);
  }

  get continuousSeconds() {
    return this.streak;
  }

  /** Call about once a second. */
  sample() {
    const now = this.now();
    const dt = Math.min((now - this.last) / 1000, 5);
    this.last = now;
    if (this.isActive()) {
      if (!this.session) {
        this.session = newId();
        this.sessionSeconds = 0;
        this.o.emit("session_start", { session: this.session });
      }
      this.acc += dt;
      this.sessionSeconds += dt;
      this.streak += dt;
      this.lastActive = now;
      if (this.acc >= (this.o.tickEveryS ?? 30)) this.tick();
      const brk = this.o.breakAfterMin?.() ?? 0;
      if (brk > 0 && this.streak >= brk * 60) {
        this.streak = 0;
        this.o.onBreakDue?.(brk);
      }
      return;
    }
    if (this.lastActive && now - this.lastActive >= (this.o.breakResetMs ?? 3 * 60000)) this.streak = 0;
    if (this.session && now - this.lastActive >= (this.o.sessionIdleMs ?? 10 * 60000)) this.end();
  }

  private tick() {
    const s = Math.round(this.acc);
    if (s > 0 && this.session) this.o.emit("focus_tick", { session: this.session, seconds: s });
    this.acc = Math.max(0, this.acc - s);
  }

  /** The window is closing or the user signed out: send the rest and end the session. */
  end() {
    if (!this.session) return;
    this.tick();
    this.o.emit("session_end", { session: this.session, seconds: Math.round(this.sessionSeconds) });
    this.session = null;
    this.acc = 0;
    this.sessionSeconds = 0;
  }
}
