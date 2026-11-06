/**
 * The tour's state machine, without React (tourController.test.ts). The provider subscribes to it and renders;
 * every transition is saved on the gateway (`PUT /onboarding`) so the tour never repeats across devices.
 */
import { applyStudyTime, type StudyTimeResult } from "./studyTime";
import { completes, nextStep, resolveStep, tourSteps, type TourSignal, type TourSurface } from "./tour";
import type { Role, Settings, TourPatch, TourState, TourStepId } from "./types";

export interface TourApi {
  updateTour(patch: TourPatch): Promise<TourState>;
  getSettings(): Promise<Settings>;
  putSettings(s: Settings): Promise<Settings>;
}

export interface TourView {
  phase: "idle" | "step" | "finish";
  step: TourStepId | null;
  /** the "ask" step got its message: a short thank-you before moving on */
  ack: boolean;
  /** saving the study time */
  busy: boolean;
  error: string | null;
  /** finish moment: chosen hour (null = no reminders) and whether something will swallow the reminder */
  hour: number | null;
  blockedBy: StudyTimeResult["blockedBy"];
  /** the finish moment may fire confetti and celebrate with the full animation */
  celebrate: boolean;
}

export interface TourDeps {
  api: TourApi;
  role: Role | null;
  surface: TourSurface;
  /** the saved server state after each change (so Me.tour stays current) */
  onState: (t: TourState) => void;
  reducedMotion: () => boolean;
  confetti: () => void;
  errorText: (e: unknown) => string;
  /** ms the "ask" thank-you stays; ms until the finish card closes itself */
  ackMs?: number;
  finishMs?: number;
}

const IDLE: TourView = { phase: "idle", step: null, ack: false, busy: false, error: null, hour: null, blockedBy: null, celebrate: false };

export class TourController {
  private view: TourView = IDLE;
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private deps: TourDeps) {}

  /** Role, surface and the state callback can change after construction. */
  configure(patch: Partial<Pick<TourDeps, "role" | "surface" | "onState">>): void {
    this.deps = { ...this.deps, ...patch };
  }

  subscribe = (cb: () => void): (() => void) => {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  };
  getSnapshot = (): TourView => this.view;

  private set(patch: Partial<TourView>) {
    this.view = { ...this.view, ...patch };
    for (const l of this.listeners) l();
  }

  private clearTimer() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private steps(): TourStepId[] {
    return tourSteps(this.deps.role, this.deps.surface);
  }

  /** Fire and forget: the tour is not worth blocking the learner for a failed save. */
  private save(patch: TourPatch): Promise<void> {
    return this.deps.api.updateTour(patch).then(
      (t) => this.deps.onState(t),
      (e) => console.warn("tour: could not save progress", e),
    );
  }

  /** First start (or replay): the first step of this surface. */
  start(): void {
    this.clearTimer();
    const first = this.steps()[0];
    this.view = { ...IDLE, phase: "step", step: first };
    this.set({});
    void this.save({ step: first });
  }

  /** Replay from Settings: the server forgets completed/skipped first. */
  restart(): void {
    this.clearTimer();
    const first = this.steps()[0];
    this.view = { ...IDLE, phase: "step", step: first };
    this.set({});
    void this.save({ restart: true }).then(() => (first === "welcome" ? undefined : this.save({ step: first })));
  }

  /** Pick up a saved step (nothing is written: the server already has it). */
  resume(saved: TourStepId | null): void {
    const step = resolveStep(this.steps(), saved);
    if (!step) return;
    this.clearTimer();
    this.view = { ...IDLE, phase: "step", step };
    this.set({});
  }

  /** Move on from the current step. After the last one: nothing (the finish moment is entered by chooseHour). */
  advance(): void {
    const step = this.view.step;
    if (this.view.phase !== "step" || !step) return;
    this.clearTimer();
    const next = nextStep(this.steps(), step);
    if (!next) {
      // "Để sau" on the last step: done, nothing changed in the learner's settings
      this.close();
      void this.save({ complete: true });
      return;
    }
    this.set({ step: next, ack: false, error: null });
    void this.save({ step: next });
  }

  /** A screen reported something the learner did. */
  signal(s: TourSignal): void {
    const step = this.view.step;
    if (this.view.phase !== "step" || !step || this.view.ack || !completes(step, s)) return;
    if (step === "ask") {
      this.set({ ack: true });
      this.clearTimer();
      this.timer = setTimeout(() => this.advance(), this.deps.ackMs ?? 1300);
      return;
    }
    this.advance();
  }

  skip(): void {
    if (this.view.phase === "idle") return;
    this.clearTimer();
    this.view = IDLE;
    this.set({});
    void this.save({ skip: true });
  }

  /** The "Giờ học" chips: hour = 19..21, or null for "Không cần nhắc". */
  async chooseHour(hour: number | null): Promise<void> {
    if (this.view.phase !== "step" || this.view.step !== "time" || this.view.busy) return;
    this.set({ busy: true, error: null });
    let blockedBy: StudyTimeResult["blockedBy"] = null;
    try {
      const cur = await this.deps.api.getSettings();
      const out = applyStudyTime(cur, this.deps.role, hour);
      blockedBy = out.blockedBy;
      await this.deps.api.putSettings(out.settings);
    } catch (e) {
      this.set({ busy: false, error: this.deps.errorText(e) });
      return;
    }
    await this.finish(hour, true, blockedBy);
  }

  private async finish(hour: number | null, celebrate: boolean, blockedBy: StudyTimeResult["blockedBy"] = null) {
    this.clearTimer();
    const reduced = this.deps.reducedMotion();
    this.view = { ...IDLE, phase: "finish", hour, blockedBy, celebrate: celebrate && !reduced };
    this.set({});
    if (celebrate && !reduced) this.deps.confetti();
    this.timer = setTimeout(() => this.close(), this.deps.finishMs ?? 6000);
    await this.save({ complete: true });
  }

  /** Close the finish card (the tour is already saved as completed). */
  close(): void {
    this.clearTimer();
    this.view = IDLE;
    this.set({});
  }

  dispose(): void {
    this.clearTimer();
    this.listeners.clear();
  }
}
