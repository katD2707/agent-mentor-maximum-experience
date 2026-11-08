/** The app's own version (from package.json at build time) and the check that gates course packs on it. */
declare const __APP_VERSION__: string;
export const APP_VERSION: string = __APP_VERSION__;

const parts = (v: string): number[] => v.replace(/^v/, "").split(/[-+]/)[0]!.split(".").map((n) => Number.parseInt(n, 10) || 0);

/** Compares dotted numeric versions ("0.10.0" > "0.9.2"); a pre-release suffix is ignored. */
export function compareVersions(a: string, b: string): number {
  const x = parts(a);
  const y = parts(b);
  for (let i = 0; i < Math.max(x.length, y.length, 3); i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  return 0;
}

/** True when a pack (or anything else) asks for a newer app than this one. A missing value means "any". */
export const needsNewerApp = (minAppVersion: string | null | undefined, app: string = APP_VERSION): boolean => !!minAppVersion && compareVersions(minAppVersion, app) > 0;
