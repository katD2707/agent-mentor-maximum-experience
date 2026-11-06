import type { Report } from "./types";

const key = (id: string) => `mentor-practice-report-${id}`;

/** Keeps the Report from `finish` for the summary page of this tab (sessionStorage; never required). */
export function cacheReport(id: string, report: Report): void {
  try {
    window.sessionStorage.setItem(key(id), JSON.stringify(report));
  } catch {
    // private mode or full: the summary asks the gateway again
  }
}

export function readCachedReport(id: string): Report | null {
  try {
    const raw = window.sessionStorage.getItem(key(id));
    return raw ? (JSON.parse(raw) as Report) : null;
  } catch {
    return null;
  }
}
