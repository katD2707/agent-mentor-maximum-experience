/** Recent course searches, kept on this device per user (never sent anywhere). */
const MAX = 6;
const key = (userId: string) => `mentor.recentSearches.${userId}`;

export function loadRecent(userId: string): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(key(userId)) ?? "[]") as unknown;
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string").slice(0, MAX) : [];
  } catch {
    return [];
  }
}

function save(userId: string, list: string[]): string[] {
  try {
    localStorage.setItem(key(userId), JSON.stringify(list));
  } catch {
    /* private mode: just not remembered */
  }
  return list;
}

export function addRecent(userId: string, q: string): string[] {
  const s = q.trim();
  if (!s) return loadRecent(userId);
  return save(userId, [s, ...loadRecent(userId).filter((x) => x !== s)].slice(0, MAX));
}

export function removeRecent(userId: string, q: string): string[] {
  return save(userId, loadRecent(userId).filter((x) => x !== q));
}
