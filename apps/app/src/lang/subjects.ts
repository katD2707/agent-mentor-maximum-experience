import type { AgeBand } from "../api/types";
import { stageName } from "./gaFiles";

/**
 * The chickens (one per subject, or per ngành at university). The id list and names are fixed in code and mirrored by the
 * gateway (`langga/subjects.py`, CONTRACTS-LANGGA.md section 1).
 */
export interface Subject {
  id: string;
  vi: string;
  en: string;
  /** file name (without extension) under `ga/` */
  art: string;
}

const S = (id: string, vi: string, en: string, art = id): Subject => ({ id, vi, en, art });

const TOAN = S("toan", "Toán", "Math");
const VAN = S("van", "Văn", "Literature");
const ANH = S("anh", "Anh", "English");
const SU = S("su", "Sử", "History");
const DIA = S("dia", "Địa", "Geography");
const CD = S("cd", "Công dân", "Civics");
const TIN = S("tin", "Tin", "Informatics");
const CN = S("cn", "Công nghệ", "Technology");
const NT = S("nt", "Nghệ thuật", "Arts", "nghethuat");
const KN = S("kn", "Kỹ năng", "Skills", "kynang");

export const LOWER: Subject[] = [TOAN, VAN, ANH, S("khoahoc", "Khoa học", "Science"), SU, DIA, CD, TIN, CN, NT, KN];
export const UPPER: Subject[] = [TOAN, VAN, ANH, S("li", "Lí", "Physics"), S("hoa", "Hóa", "Chemistry"), S("sinh", "Sinh", "Biology"), SU, DIA, CD, TIN, CN, NT, KN];
export const UNI: Subject[] = [
  S("khmt", "Khoa học máy tính", "Computer Science"),
  S("ktmt", "Kỹ thuật máy tính", "Computer Engineering"),
  S("httt", "Hệ thống thông tin", "Information Systems"),
  S("khdl", "Khoa học dữ liệu", "Data Science"),
  S("toanhoc", "Toán học", "Mathematics", "toan"),
  S("vatli", "Vật lí", "Physics"),
  S("hoahoc", "Hóa học", "Chemistry"),
  S("kinhte", "Kinh tế", "Economics"),
  S("ketoan", "Kế toán", "Accounting"),
  S("nna", "Ngôn ngữ Anh", "English Studies", "anh"),
  S("daicuong", "Đại cương", "General studies"),
];

export const subjectsFor = (band: AgeBand | null | undefined): Subject[] => (band === "uni" ? UNI : band === "g10_12" ? UPPER : LOWER);
export const ALL_SUBJECTS: Subject[] = [...new Map([...LOWER, ...UPPER, ...UNI].map((s) => [s.id, s])).values()];
export const subjectOf = (id: string): Subject | undefined => ALL_SUBJECTS.find((s) => s.id === id);
export const chickenName = (id: string, lang: "vi" | "en"): string => {
  const s = subjectOf(id);
  return s ? (lang === "en" ? `${s.en} chicken` : `Gà ${s.vi}`) : id;
};

/** Chickens with a walking sprite sheet in the village; the others stand and bob. */
export const WALKERS = new Set(["toan", "van", "anh"]);

// ---- levels and XP (CONTRACTS-LANGGA.md "Levels and XP"): 100 XP a level, starts at 1
export const XP_PER_LEVEL = 100;
export const levelOf = (xp: number): number => Math.floor(Math.max(0, xp) / XP_PER_LEVEL) + 1;
export const xpInLevel = (xp: number): number => Math.max(0, xp) % XP_PER_LEVEL;
/** Growth stages (CONTRACTS-LANGGA.md): 1 = chick (lv 1), 2 = young (lv 2-4), 3 = grown (lv 5-9), 4 = master "Cao thủ" (lv 10+). */
export type Stage = 1 | 2 | 3 | 4;
export const STAGE_AT = [1, 2, 5, 10];
export const stageOf = (level: number): Stage => (level >= 10 ? 4 : level >= 5 ? 3 : level >= 2 ? 2 : 1);
/** Picture of a chicken at its growth stage (file under `ga/`). Stage 4 shows the grown drawing; the crown badge marks it. */
export const artFile = (art: string, stage: number): string => `${stageName(art, stage)}.png`;
