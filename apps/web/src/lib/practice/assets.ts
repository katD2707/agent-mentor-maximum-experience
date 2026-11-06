/** Asset placement helpers (agent-mentor question-schema 5.0: `![](asset:<id>)` tokens). */
import type { ClientItem, PracticeAsset } from "./types";

const TOKEN = /!\[[^\]]*\]\(asset:([A-Za-z0-9_.-]{1,64})\)/g;

/** Ids of the assets a text places with a token. */
export function assetIdsIn(text: string | undefined | null): string[] {
  if (!text) return [];
  return [...text.matchAll(TOKEN)].map((m) => m[1]);
}

/** Ids placed by any field of the item other than the stem (options, statements). */
export function placedElsewhere(item: Pick<ClientItem, "options" | "statements">): Set<string> {
  const ids = new Set<string>();
  for (const o of item.options ?? []) assetIdsIn(o.text).forEach((i) => ids.add(i));
  for (const s of item.statements ?? []) assetIdsIn(s.text).forEach((i) => ids.add(i));
  return ids;
}

/** Assets that render below the stem: not placed by a token in the stem or elsewhere, in the item's order. */
export function unplacedAssets(stem: string, assets: PracticeAsset[], elsewhere: Set<string>): PracticeAsset[] {
  const inStem = new Set(assetIdsIn(stem));
  return assets.filter((a) => !inStem.has(a.id) && !elsewhere.has(a.id));
}

const SHA256 = /^[0-9a-f]{64}$/;

/**
 * URL of a raster asset. The gateway route is not fixed by CONTRACTS 10.3; the web asks for
 * `GET <API_BASE>/practice/assets/<sha256>` (PNG or JPEG, session cookie). Null for a malformed hash.
 */
export function imageUrl(apiBase: string, sha256: string): string | null {
  return SHA256.test(sha256) ? `${apiBase.replace(/\/+$/, "")}/practice/assets/${sha256}` : null;
}
