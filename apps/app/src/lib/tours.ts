/** Window event that asks the chicken guide to show the tours again (Settings > "Xem lại từ đầu"). */
export const REPLAY_EVENT = "mentor:tour-replay";

// ---- which screens this person has already been walked through (per account, on this device)
const storeKey = (uid: string | null) => `mentor.tour.seen.${uid ?? "guest"}`;
function seenList(uid: string | null): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(storeKey(uid)) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}
function saveSeen(uid: string | null, list: string[]) {
  try {
    if (list.length) localStorage.setItem(storeKey(uid), JSON.stringify(list));
    else localStorage.removeItem(storeKey(uid));
  } catch {
    /* private mode: tours just show again next time */
  }
}
export const hasSeen = (uid: string | null, screen: string) => seenList(uid).includes(screen);
export function markSeen(uid: string | null, screen: string, seen = true) {
  const list = seenList(uid).filter((s) => s !== screen);
  saveSeen(uid, seen ? [...list, screen] : list);
}
/** Forget every screen seen, so each tour shows again the next time its screen opens. */
export const resetSeen = (uid: string | null) => saveSeen(uid, []);
