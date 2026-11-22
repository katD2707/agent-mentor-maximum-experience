import files from "./gaFiles.json";

/**
 * Which chicken pictures exist under `ga/` (written by `node scripts/sync-ga-assets.mjs`): stills (`<art>`, `<art>-1`,
 * `<art>-2`), the animated stand (`-dung`) and jump (`-nhay`). A chicken whose chick or young drawing is not there yet is
 * shown with its grown one, so nothing ever points at a missing file.
 */
const M = files as { still: string[]; dung: string[]; nhay: string[] };
const sets = { still: new Set(M.still), dung: new Set(M.dung), nhay: new Set(M.nhay) };

export const hasGa = (kind: "still" | "dung" | "nhay", name: string): boolean => sets[kind].has(name);

/** The picture name for a growth stage: `<art>-1` (stage 1), `<art>-2` (stage 2), else (3, 4) the grown `<art>`; falls back to `<art>`. */
export function stageName(art: string, stage: number): string {
  const n = stage <= 1 ? `${art}-1` : stage === 2 ? `${art}-2` : art;
  return n !== art && !hasGa("still", n) ? art : n;
}
