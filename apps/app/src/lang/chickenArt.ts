import { hasGa, stageName } from "./gaFiles";

/**
 * Which picture shows a chicken: its costume at the growth stage (chick, young, grown, master with the halo), or the angry one
 * (`<art>-gian`, drawn grown, for every stage). Where a picture has an animated stand and jump (`-dung`, `-nhay`, today Gà Toán) they are
 * used, else the still (the screens give it a CSS bob or hop, see `.ga-bob` and `.ga-hop`). `drawn` = how far the picture is grown (it
 * frames the head in the coop), see mockups/lg-03.
 */
export type Drawn = 1 | 2 | 3 | 4;
export const drawnStage = (art: string, stage: number, angry = false): Drawn => {
  if (angry && hasGa("still", `${art}-gian`)) return 3;
  const s = Math.min(Math.max(stage, 1), 4) as Drawn;
  return stageName(art, s) !== art || s === 3 ? s : 3; // a stage without a drawing of its own shows the grown one
};

export type Pose = "stand" | "jump";

/** Picture URL. `still` (reduced motion) always gives the still. */
export function chickenSrc(art: string, stage: number, pose: Pose = "stand", still = false, angry = false): string {
  const base = import.meta.env.BASE_URL;
  const name = stageName(art, stage, angry);
  if (still) return `${base}ga/${name}.webp`;
  const kind = pose === "jump" ? "nhay" : "dung";
  return hasGa(kind, name) ? `${base}ga/${name}-${kind}.webp` : `${base}ga/${name}.webp`;
}

/** The jump drawing of a stage; null when it has none (the screen then keeps the still and hops it with CSS). */
export function jumpSrc(art: string, stage: number, angry = false): string | null {
  const name = stageName(art, stage, angry);
  return hasGa("nhay", name) ? `${import.meta.env.BASE_URL}ga/${name}-nhay.webp` : null;
}

/** Does the chicken's picture move by itself (an animated stand)? Otherwise a screen gives the still a gentle CSS bob. */
export const isAnimated = (art: string, stage: number, angry = false): boolean => hasGa("dung", stageName(art, stage, angry));

export const reducedMotion = (): boolean => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** The age band as the mockups name it (their CSS keys on this). */
export const mockAge = (band: string | null | undefined): "tieu-hoc" | "thcs" | "thpt" | "dai-hoc" => (band === "g1_5" ? "tieu-hoc" : band === "g6_9" ? "thcs" : band === "uni" ? "dai-hoc" : "thpt");

/**
 * The frame of a small sprite (the lesson's speaker): the pictures are 512x512 squares with the bird at the bottom; how much of the
 * frame the bird fills depends on how far it is grown. Returns CSS variables for `.lp-gsp` (image width and bottom offset in
 * widths of the box, and the box height), so every chicken stands as wide as the box.
 */
const BOX: Record<Drawn, { bw: number; top: number; bot: number }> = { 1: { bw: 166, top: 281, bot: 432 }, 2: { bw: 168, top: 214, bot: 432 }, 3: { bw: 212, top: 168, bot: 432 }, 4: { bw: 233, top: 147, bot: 432 } };
export function spriteVars(art: string, stage: number, angry = false): Record<string, string> {
  const b = BOX[drawnStage(art, stage, angry)];
  const iw = (0.9 * 512) / b.bw;
  const high = ((b.bot - b.top) / 512) * iw;
  return { "--iw": iw.toFixed(3), "--gh": (high + 0.06).toFixed(3), "--bo": (((512 - b.bot) / 512) * iw).toFixed(3) };
}

/**
 * How to crop a chicken picture into a card, a circle or a face, whatever its size: the pictures are 512 squares with the bird at the
 * bottom (top of the head at `TOPS[stage]`, feet at 432; the master's halo reaches the top). Returns CSS variables for `.ga-crop`: the image height
 * in % of the box and its top in % of the box, so the bird fills `fill` of the box height with `pad` above the head and never loses it.
 */
const TOPS: Record<Drawn, number> = { 1: 281, 2: 214, 3: 168, 4: 147 };
/** where the master's halo ends at the top of its picture: a full-figure card (fill <= 1) keeps it, a face crop does not need it */
const HALO_TOP = 22;
export function cropVars(art: string, stage: number, opts: { fill?: number; pad?: number; angry?: boolean } = {}): Record<string, string> {
  const { fill = 0.8, pad = 0.08, angry = false } = opts;
  const d = drawnStage(art, stage, angry);
  const top = d === 4 && fill <= 1 ? HALO_TOP : TOPS[d];
  const span = 432 - top;
  return { "--ih": `${((fill * 512) / span) * 100}%`, "--it": `${(pad - (fill * top) / span) * 100}%` };
}
