import type { AgeBand } from "../api/types";
import { fold } from "../lib/text";

/**
 * Which chicken a course belongs to: the app-side mirror of the gateway's `chicken_of` (CONTRACTS-LANGGA.md section 1,
 * the SUBJ2GA table of mockups/lg-03). The server stays the authority (`GET /chickens/{id}` lists the courses); this
 * mirror serves the mock layer, redirects from old links and the offline case.
 */
const SCHOOL: Record<string, string> = {
  "Toán": "toan", "Tiếng Việt": "van", "Ngữ văn": "van", "Tiếng Anh": "anh", IELTS: "anh", SAT: "anh", English: "anh",
  "Tự nhiên và Xã hội": "khoahoc", "Khoa học": "khoahoc", Science: "khoahoc", "Khoa học tự nhiên": "khoahoc",
  "Lịch sử và Địa lí": "su", "Lịch sử": "su", "Địa lí": "dia", "Đạo đức": "cd", GDCD: "cd", "Giáo dục kinh tế và pháp luật": "cd",
  "Tin học": "tin", Computing: "tin", "Công nghệ": "cn", "Ôn thi": "kn", "Kĩ năng": "kn",
};
const UNI: Record<string, string> = {
  "Giải tích": "toanhoc", "Đại số tuyến tính": "toanhoc", "Toán rời rạc": "toanhoc", "Linear Algebra": "toanhoc",
  "Xác suất thống kê": "khdl", Probability: "khdl", "Machine learning": "khdl", "Machine Learning": "khdl",
  "Lập trình Python": "khmt", "Cấu trúc dữ liệu": "khmt", "Lập trình": "khmt", "Computer Science": "khmt",
  "Cơ sở dữ liệu": "httt", "Mạng máy tính": "ktmt", "Hệ điều hành": "ktmt", "Kinh tế vi mô": "kinhte", "Kinh tế vĩ mô": "kinhte", Economics: "kinhte",
  "Vật lí đại cương": "vatli", "Hóa học đại cương": "hoahoc", "Kế toán": "ketoan", "Academic Writing": "nna", "Phương pháp nghiên cứu": "daicuong",
};
const SCIENCE: Record<string, string> = { "Vật lí": "li", "Hóa học": "hoa", "Sinh học": "sinh" };
const KEYWORDS: [string, string][] = [["toan", "toan"], ["van", "van"], ["anh", "anh"], ["tin hoc", "tin"], ["lich su", "su"], ["dia li", "dia"]];

export function chickenOfSubject(subject: string, band: AgeBand, explicit?: string | null): string {
  if (explicit) return explicit;
  if (band === "uni") return UNI[subject] ?? "daicuong";
  if (subject in SCIENCE) return band === "g10_12" ? SCIENCE[subject] : "khoahoc";
  const found = SCHOOL[subject];
  if (found) return found === "khoahoc" && band === "g10_12" ? "kn" : found;
  const f = fold(subject);
  if (/vat li|hoa hoc|sinh hoc/.test(f)) return band === "g10_12" ? (f.includes("vat li") ? "li" : f.includes("hoa hoc") ? "hoa" : "sinh") : "khoahoc";
  return KEYWORDS.find(([k]) => f.split(/\s+/).includes(k))?.[1] ?? "kn";
}

/** A course (`CourseDetail`, `CatalogEntry`) carries its own `chicken` label when a teacher set one. */
export function chickenOfCourse(c: { subject: string; age_band: AgeBand; chicken?: string | null }): string {
  return chickenOfSubject(c.subject, c.age_band, c.chicken);
}
