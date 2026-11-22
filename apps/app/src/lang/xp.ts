/**
 * One small bus for the XP any call paid (a lesson's progress PUT, a practice answer / fix / finish, a study-room finish).
 * The calls that pay emit here; whoever cares listens (the lesson's end screen; the village, which shows a level-up once
 * the student comes back to it). Nothing here touches the network.
 */
export interface XpGain {
  chicken: string;
  source: string;
  amount: number;
  level_up: boolean;
}
/** What the calls send: `level_up` may be missing. */
export type XpIn = Omit<XpGain, "level_up"> & { level_up?: boolean };

type XpListener = (xp: XpGain[], ref: string) => void;
const listeners = new Set<XpListener>();
const waiting = new Set<string>();

/** `ref` says where it came from (a course id for lessons, else the session or focus id); listeners may filter on it. */
export function emitXp(xp: XpIn[] | undefined, ref = ""): void {
  if (!xp?.length) return;
  const list = xp.map((x) => ({ ...x, level_up: !!x.level_up }));
  for (const x of list) if (x.level_up) waiting.add(x.chicken);
  listeners.forEach((cb) => cb(list, ref));
}

export function onXp(cb: XpListener): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Chickens that levelled up since the village last looked (read once, then forgotten). */
export function takeLevelUps(): string[] {
  const out = [...waiting];
  waiting.clear();
  return out;
}
