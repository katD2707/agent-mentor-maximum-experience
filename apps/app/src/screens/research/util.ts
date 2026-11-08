import type { PaperCard, ReadStatus } from "../../api/research";
import { ResearchError } from "../../api/research-error";

/** The code of a failed research call ("network" when the server could not be reached). */
export const errCode = (e: unknown): string => (e instanceof ResearchError ? e.code : "unknown");

export const byline = (p: Pick<PaperCard, "authors" | "year">) => [p.authors.join(", "), p.year].filter(Boolean).join(" · ");

export const ymdToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** "Thứ Tư / 11 / Th11" for the date block of an event card. */
export function dateBlock(date: string, lang: string): { weekday: string; day: string; month: string } {
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return { weekday: "", day: date, month: "" };
  const en = lang === "en";
  const weekday = d.toLocaleDateString(en ? "en-GB" : "vi-VN", { weekday: en ? "short" : "long" });
  const month = en ? d.toLocaleDateString("en-GB", { month: "short" }) : `Th${d.getMonth() + 1}`;
  return { weekday: weekday.charAt(0).toUpperCase() + weekday.slice(1), day: String(d.getDate()).padStart(2, "0"), month };
}

/** dd/mm */
export const shortDate = (date: string) => {
  const [, m, d] = date.split("-");
  return d && m ? `${d}/${m}` : date;
};

export const STATUS_TAG: Record<ReadStatus, string> = { reading: "tag wait", new: "tag new", read: "tag ok" };

/** Opens a link in the system browser or a new tab. */
export const extProps = { target: "_blank", rel: "noopener noreferrer" } as const;

/** English wants "1 paper" and "2 papers": the singular text sits under `<key>One` (Vietnamese has the same text in both). */
export const pk = (key: string, n: number) => (n === 1 ? `${key}One` : key);
