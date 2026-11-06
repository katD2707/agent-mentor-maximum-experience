"use client";

/**
 * Optional practice sounds: two short soft tones made with WebAudio (no files). Off unless the learner switched
 * `sounds` on (shared pref, `uiPrefs.ts`); never plays under a crisis context (practice has none) and is silent
 * where audio is unavailable.
 */
import { readSounds } from "../uiPrefs";

export type Cue = "correct" | "wrong" | "complete";

let ctx: AudioContext | null = null;

const TONES: Record<Cue, { f: number; at: number; len: number }[]> = {
  correct: [
    { f: 660, at: 0, len: 0.09 },
    { f: 880, at: 0.09, len: 0.12 },
  ],
  wrong: [{ f: 220, at: 0, len: 0.16 }],
  complete: [
    { f: 523, at: 0, len: 0.1 },
    { f: 659, at: 0.1, len: 0.1 },
    { f: 784, at: 0.2, len: 0.18 },
  ],
};

export function playCue(cue: Cue): void {
  if (typeof window === "undefined" || !readSounds()) return;
  try {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    ctx ??= new AC();
    const c = ctx;
    const now = c.currentTime;
    for (const t of TONES[cue]) {
      const osc = c.createOscillator();
      const gain = c.createGain();
      osc.type = "sine";
      osc.frequency.value = t.f;
      gain.gain.setValueAtTime(0.0001, now + t.at);
      gain.gain.exponentialRampToValueAtTime(0.06, now + t.at + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + t.at + t.len);
      osc.connect(gain).connect(c.destination);
      osc.start(now + t.at);
      osc.stop(now + t.at + t.len + 0.02);
    }
  } catch {
    // autoplay blocked or no audio device: stay silent
  }
}
