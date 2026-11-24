import files from "./gaFiles.json";

/**
 * Which chicken pictures exist under `ga/` (written by `node scripts/sync-ga-assets.mjs`): the costume stills (`<art>-1` chick,
 * `<art>-2` young, `<art>` grown, `<art>-4` master, `<art>-gian` angry) and the animated stand (`-dung`) and jump (`-nhay`), which only
 * some chickens have. A picture that is not there falls back to the grown one, so nothing ever points at a missing file.
 */
const M = files as { still: string[]; dung: string[]; nhay: string[] };
const sets = { still: new Set(M.still), dung: new Set(M.dung), nhay: new Set(M.nhay) };

export const hasGa = (kind: "still" | "dung" | "nhay", name: string): boolean => sets[kind].has(name);

/**
 * The picture name for a growth stage: `<art>-1`, `<art>-2`, `<art>` (stage 3), `<art>-4`; an angry chicken shows `<art>-gian`, which is
 * drawn grown, so it stands for every stage. Falls back to `<art>`.
 */
export function stageName(art: string, stage: number, angry = false): string {
  if (angry && hasGa("still", `${art}-gian`)) return `${art}-gian`;
  const n = stage <= 1 ? `${art}-1` : stage === 2 ? `${art}-2` : stage >= 4 ? `${art}-4` : art;
  return n !== art && !hasGa("still", n) ? art : n;
}
