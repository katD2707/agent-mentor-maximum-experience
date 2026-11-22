import { hasGa, stageName } from "./gaFiles";

/**
 * Which picture shows a chicken. Each chicken is drawn per growth stage (chick, young, grown; the master shows the grown
 * one). Where a stage has an animated stand and jump (`-dung`, `-nhay`) they are used, else the still. `drawn` = how far the
 * picture is grown (it frames the head in the coop), see mockups/lg-03.
 */
export const drawnStage = (art: string, stage: number): 1 | 2 | 3 => {
  const s = Math.min(Math.max(stage, 1), 3) as 1 | 2 | 3;
  const own = stageName(art, s) !== art; // the stage has a drawing of its own
  return own ? s : 3;
};

export type Pose = "stand" | "jump";

/** Picture URL. `still` (reduced motion) always gives the png. */
export function chickenSrc(art: string, stage: number, pose: Pose = "stand", still = false): string {
  const base = import.meta.env.BASE_URL;
  const name = stageName(art, stage);
  if (still) return `${base}ga/${name}.png`;
  const kind = pose === "jump" ? "nhay" : "dung";
  return hasGa(kind, name) ? `${base}ga/${name}-${kind}.webp` : `${base}ga/${name}.png`;
}

/** The jump drawing of a stage; null when it has none (the screen then keeps the still). */
export function jumpSrc(art: string, stage: number): string | null {
  const name = stageName(art, stage);
  return hasGa("nhay", name) ? `${import.meta.env.BASE_URL}ga/${name}-nhay.webp` : null;
}

export const reducedMotion = (): boolean => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** The age band as the mockups name it (their CSS keys on this). */
export const mockAge = (band: string | null | undefined): "tieu-hoc" | "thcs" | "thpt" | "dai-hoc" => (band === "g1_5" ? "tieu-hoc" : band === "g6_9" ? "thcs" : band === "uni" ? "dai-hoc" : "thpt");

/**
 * The frame of a small sprite (the lesson's speaker): the pictures are 512x512 squares with the bird at the bottom; how much of the
 * frame the bird fills depends on how far it is grown. Returns CSS variables for `.lp-gsp` (image width and bottom offset in
 * widths of the box, and the box height), so every chicken stands as wide as the box.
 */
const BOX: Record<1 | 2 | 3, { bw: number; top: number; bot: number }> = { 1: { bw: 156, top: 279, bot: 432 }, 2: { bw: 155, top: 203, bot: 433 }, 3: { bw: 179, top: 160, bot: 434 } };
export function spriteVars(art: string, stage: number): Record<string, string> {
  const b = BOX[drawnStage(art, stage)];
  const iw = (0.9 * 512) / b.bw;
  const high = ((b.bot - b.top) / 512) * iw;
  return { "--iw": iw.toFixed(3), "--gh": (high + 0.06).toFixed(3), "--bo": (((512 - b.bot) / 512) * iw).toFixed(3) };
}

/**
 * How to crop a chicken picture into a card, a circle or a face, whatever its size: the pictures are 512 squares with the bird at the
 * bottom (top of the head or the "Hi!" bubble at `TOPS[stage]`, feet at 434). Returns CSS variables for `.ga-crop`: the image height
 * in % of the box and its top in % of the box, so the bird fills `fill` of the box height with `pad` above the head and never loses it.
 */
const TOPS: Record<1 | 2 | 3, number> = { 1: 256, 2: 203, 3: 156 };
export function cropVars(art: string, stage: number, opts: { fill?: number; pad?: number } = {}): Record<string, string> {
  const { fill = 0.8, pad = 0.08 } = opts;
  const top = TOPS[drawnStage(art, stage)];
  const span = 434 - top;
  return { "--ih": `${((fill * 512) / span) * 100}%`, "--it": `${(pad - (fill * top) / span) * 100}%` };
}
