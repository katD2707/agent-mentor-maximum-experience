/** Formatting helpers. Learner-facing dates use Asia/Ho_Chi_Minh (CONTRACTS.md). */

export const TZ = "Asia/Ho_Chi_Minh";

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

export function formatDate(iso: string): string {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00+07:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(d);
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** "YYYY-MM-DD" in the learner's time zone. */
export function localDateStamp(d: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

/** ISO string with +07:00 offset, e.g. 2026-10-28T20:31:00+07:00. */
export function isoLocal(d: Date = new Date()): string {
  const shifted = new Date(d.getTime() + 7 * 3600_000);
  return shifted.toISOString().replace(/\.\d{3}Z$/, "+07:00");
}

export function randomId(prefix = ""): string {
  const c = globalThis.crypto;
  const raw =
    c && "randomUUID" in c ? c.randomUUID().replace(/-/g, "") : Math.random().toString(16).slice(2) + Date.now().toString(16);
  return prefix + raw.slice(0, 16);
}

/** FNV-1a based 40-hex digest; stable, not cryptographic. Mock shas only. */
export function fakeSha(text: string): string {
  let out = "";
  for (let seed = 0; seed < 5; seed++) {
    let h = (0x811c9dc5 ^ (seed * 0x9e3779b9)) >>> 0;
    for (let i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    out += h.toString(16).padStart(8, "0");
  }
  return out;
}
