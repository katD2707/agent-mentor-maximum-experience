import type { CourseLevel, TeacherCourseSummary, TeacherVersion } from "../../api/teacher";
import { LOWER, subjectsFor, UNI, UPPER } from "../subjects";

/** The labels of a course (gv labels step). `bac` is the screen's two-way pick; the gateway stores the four bands. */
export type Bac = "pt" | "dh";
export type Band = "g1_5" | "g6_9" | "g10_12" | "uni";
export interface Labels {
  bac: Bac | null;
  chicken: string | null;
  /** school grade 1-12, or the university year 1-4 */
  grade: number | null;
  difficulty: CourseLevel | null;
}
export type LabelField = keyof Labels;
export const FIELDS: readonly LabelField[] = ["bac", "chicken", "grade", "difficulty"];

export const bandOfGrade = (g: number): Band => (g <= 5 ? "g1_5" : g <= 9 ? "g6_9" : "g10_12");
export const bacOfBand = (b: string | null | undefined): Bac | null => (b === "uni" ? "dh" : b === "g1_5" || b === "g6_9" || b === "g10_12" ? "pt" : null);
/** The band to send: university, else the one of the grade. */
export const bandOf = (l: Labels): Band | null => (l.bac === "dh" ? "uni" : l.bac === "pt" && l.grade ? bandOfGrade(l.grade) : null);
export const gradesFor = (bac: Bac | null): number[] => (bac === "dh" ? [1, 2, 3, 4] : [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);

const strip = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();

/** Words in a course title or subject that point at a chicken (school); first match wins. */
const KEYWORDS: [RegExp, string][] = [
  [/\b(toan|math)/, "toan"],
  [/\b(vat li|vat ly|physics)\b/, "li"],
  [/\b(hoa|hoa hoc|chemistry)\b/, "hoa"],
  [/\b(sinh|sinh hoc|biology)\b/, "sinh"],
  [/\b(van|ngu van|tieng viet|literature)\b/, "van"],
  [/\b(anh|tieng anh|english)\b/, "anh"],
  [/\b(lich su|su)\b/, "su"],
  [/\b(dia li|dia ly|dia)\b/, "dia"],
  [/\b(tin hoc|tin)\b/, "tin"],
  [/\b(cong nghe)\b/, "cn"],
  [/\b(khoa hoc|tu nhien)\b/, "khoahoc"],
];
const UNI_KEYWORDS: [RegExp, string][] = [
  [/he dieu hanh|kien truc may|mang may tinh|vi xu ly/, "ktmt"],
  [/lap trinh|hoc may|machine learning|cau truc du lieu/, "khmt"],
  [/co so du lieu|he thong thong tin/, "httt"],
  [/khoa hoc du lieu|khai pha/, "khdl"],
  [/xac suat|thong ke|giai tich|dai so|toan/, "toanhoc"],
  [/vat li|vat ly/, "vatli"],
  [/hoa hoc|hoa dai cuong/, "hoahoc"],
  [/kinh te|vi mo|vi mo/, "kinhte"],
  [/ke toan|kiem toan/, "ketoan"],
  [/tieng anh|ngon ngu anh/, "nna"],
];

export interface GuessInput {
  title: string;
  subject?: string | null;
  age_band?: string | null;
  level_suggested?: CourseLevel | null;
  /** what students see (latest published) */
  level?: CourseLevel | null;
  /** chicken / band / grade the gateway saved for the working version (open draft, else latest published) */
  saved?: { chicken?: string | null; band?: string | null; grade?: number | null } | null;
  versions?: TeacherVersion[];
}

/** The version the gateway's saved labels belong to: the open draft, else the latest one. */
const workingVersion = (vs: TeacherVersion[] | undefined): number | null => {
  if (!vs?.length) return null;
  const open = vs.filter((v) => v.status !== "published");
  return Math.max(...(open.length ? open : vs).map((v) => v.version));
};

/**
 * What Mentor pre-fills: the saved labels of the version first, then what it read from the files (subject, age band), then
 * the title ("Vật lí 11: ..."). A field it cannot decide stays null: the screen marks it "Cần chọn".
 */
export function guessLabels(c: GuessInput, version: number | null): Labels {
  const v = c.versions?.find((x) => x.version === version) ?? c.versions?.[c.versions.length - 1];
  const server = v && v.version === workingVersion(c.versions) ? c.saved : null;
  const saved = v?.labels || server ? { ...(server ?? {}), ...(v?.labels ?? {}) } : null;
  const text = strip(`${c.subject ?? ""} ${c.title}`);
  const gm = /\b(?:lop|nam|grade|year)?\s*(\d{1,2})\b/.exec(strip(c.title));
  const titleGrade = gm && +gm[1] >= 1 && +gm[1] <= 12 ? +gm[1] : null;
  let bac: Bac | null = bacOfBand(saved?.band) ?? bacOfBand(c.age_band);
  if (!bac && titleGrade) bac = "pt";
  const grade = saved?.grade ?? (bac === "dh" ? (titleGrade && titleGrade <= 4 ? titleGrade : null) : titleGrade);
  let chicken: string | null = saved?.chicken ?? null;
  if (!chicken) {
    for (const [re, id] of bac === "dh" ? UNI_KEYWORDS : KEYWORDS) {
      if (re.test(text)) {
        chicken = id;
        break;
      }
    }
  }
  // a published version's difficulty is the one students already see
  const difficulty = v?.level_confirmed ?? (v?.status === "published" ? c.level : null) ?? v?.level_suggested ?? c.level_suggested ?? null;
  const out: Labels = { bac, chicken, grade, difficulty };
  return fixChicken(out);
}

/** Lí/Hóa/Sinh only exist from grade 10; below it the same lessons are Khoa học. Keeps a chicken valid for the stage. */
export function fixChicken(l: Labels): Labels {
  if (!l.chicken) return l;
  const list = l.bac === "dh" ? UNI : l.grade ? subjectsFor(l.grade >= 10 ? "g10_12" : "g6_9") : [...LOWER, ...UPPER];
  if (list.some((s) => s.id === l.chicken)) return l;
  return { ...l, chicken: null };
}

/** Fields that still need the teacher's pick. */
export const missingFields = (l: Labels): LabelField[] => FIELDS.filter((f) => l[f] === null);
export const labelsComplete = (l: Labels): boolean => missingFields(l).length === 0;

/** The one-line hint under the grade when the chicken and the grade do not fit. */
export function gradeWarning(l: Labels): "low" | "high" | null {
  if (l.bac !== "pt" || !l.grade || !l.chicken) return null;
  if (l.grade < 10 && ["li", "hoa", "sinh"].includes(l.chicken)) return "low";
  if (l.grade >= 10 && l.chicken === "khoahoc") return "high";
  return null;
}

/** The body of PUT .../labels. */
export function labelsBody(l: Labels): { chicken: string; band: Band; level: number; difficulty: CourseLevel } | null {
  const band = bandOf(l);
  if (!band || !l.chicken || !l.grade || !l.difficulty) return null;
  return { chicken: l.chicken, band, level: l.grade, difficulty: l.difficulty };
}

/** Publishing waits for the course's difficulty to be confirmed (the gateway answers 409 level_unconfirmed otherwise). */
export const canPublish = (course: Pick<TeacherCourseSummary, "level" | "level_confirmed" | "versions">, version: number): boolean => {
  const v = course.versions.find((x) => x.version === version);
  return (v?.level_confirmed ?? (v?.status === "published" ? course.level : null) ?? null) !== null;
};
