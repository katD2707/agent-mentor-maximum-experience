/** English names for the course subjects (shown when the interface is English); unknown subjects keep their name. */
const EN: Record<string, string> = {
  "Toán": "Math", "Tiếng Việt": "Vietnamese", "Tự nhiên và Xã hội": "Nature and Society", "Khoa học": "Science",
  "Lịch sử và Địa lí": "History and Geography", "Tin học": "Informatics", "Công nghệ": "Technology", "Đạo đức": "Ethics",
  "Tiếng Anh": "English", "Ngữ văn": "Literature", "Khoa học tự nhiên": "Natural Science", "Vật lí": "Physics",
  "Hóa học": "Chemistry", "Sinh học": "Biology", "Lịch sử": "History", "Địa lí": "Geography", "GDCD": "Civic Education",
  "Giáo dục kinh tế và pháp luật": "Economics and Law", "Ôn thi": "Exam prep", "Kĩ năng": "Study skills",
  "Giải tích": "Calculus", "Đại số tuyến tính": "Linear Algebra", "Xác suất thống kê": "Probability and Statistics",
  "Lập trình Python": "Python", "Cấu trúc dữ liệu": "Data Structures", "Lập trình": "Programming", "Cơ sở dữ liệu": "Databases",
  "Mạng máy tính": "Networks", "Hệ điều hành": "Operating Systems", "Kinh tế vi mô": "Microeconomics",
  "Kinh tế vĩ mô": "Macroeconomics", "Vật lí đại cương": "General Physics", "Hóa học đại cương": "General Chemistry",
  "Toán rời rạc": "Discrete Math", "Phương pháp nghiên cứu": "Research Methods", "Kế toán": "Accounting",
};

export function subjectName(subject: string, lang: string): string {
  return lang.startsWith("en") ? (EN[subject] ?? subject) : subject;
}
