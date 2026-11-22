import type { ActorsData, Layout } from "./geometry";

export * from "./geometry";
export { VillageEngine, Actor, type ActorSpec, type EngineOptions } from "./village";

/** Folder of the village files (public/ga/lang), with a trailing slash. */
export const villageBase = (): string => `${import.meta.env.BASE_URL}ga/lang/`;

/** layout.json (the map) and actors.json (the sprite sheets), fetched when the village opens. */
export async function loadVillageData(base = villageBase()): Promise<{ layout: Layout; sheets: ActorsData | null }> {
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
