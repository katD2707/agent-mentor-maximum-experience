import type { ActorsData, Layout } from "./geometry";

export * from "./geometry";
export { VillageEngine, Actor, type ActorSpec, type EngineOptions } from "./village";

/** Folder of the village files (public/ga/lang), with a trailing slash. */
export const villageBase = (): string => `${import.meta.env.BASE_URL}ga/lang/`;

/** layout.json (the map) and actors.json (the sprite sheets), fetched when the village opens. */
export function loadVillageData(base = villageBase()): Promise<{ layout: Layout; sheets: ActorsData | null }> {
  // the map never changes while the app is open: coming back to the village does not fetch it again
  const hit = cache.get(base);
  if (hit) return hit;
  const p = fetchVillageData(base);
  cache.set(base, p);
  p.catch(() => cache.delete(base));
  return p;
}
const cache = new Map<string, Promise<{ layout: Layout; sheets: ActorsData | null }>>();

async function fetchVillageData(base: string): Promise<{ layout: Layout; sheets: ActorsData | null }> {
  const [layout, sheets] = await Promise.all([
    fetch(`${base}layout.json`).then((r) => {
      if (!r.ok) throw new Error("layout");
      return r.json() as Promise<Layout>;
    }),
    fetch(`${base}actors/actors.json`)
      .then((r) => (r.ok ? (r.json() as Promise<ActorsData>) : null))
      .catch(() => null),
  ]);
  return { layout, sheets };
}
