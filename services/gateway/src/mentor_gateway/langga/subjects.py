"""Làng gà taxonomy: chickens (one per subject of a school stage) and the course -> chicken mapping.

The id list, names and `SUBJ2GA` table are fixed in code (CONTRACTS-LANGGA section 1); the app mirrors them in
`src/lang/subjects.ts`. `SUBJ2GA` is the table of `mockups/lg-03-chuong-ga.html`.
"""

import unicodedata
from dataclasses import dataclass


def unaccent(s: str) -> str:  # same as planner.text.unaccent; not imported from there to keep this module cycle-free
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

# stage -> chicken ids (market order)
LOW = ("toan", "van", "anh", "khoahoc", "su", "dia", "cd", "tin", "cn", "nt", "kn")
HIGH = ("toan", "van", "anh", "li", "hoa", "sinh", "su", "dia", "cd", "tin", "cn", "nt", "kn")
UNI = ("khmt", "ktmt", "httt", "khdl", "toanhoc", "vatli", "hoahoc", "kinhte", "ketoan", "nna", "daicuong")
STAGE_OF_BAND = {"g1_5": "low", "g6_9": "low", "g10_12": "high", "uni": "uni"}
STAGE_CHICKENS = {"low": LOW, "high": HIGH, "uni": UNI}
DEFAULT_BAND = "g10_12"  # a student who has not set a birth year yet is shown the high-school list


@dataclass(frozen=True)
class Chicken:
    id: str
    vi: str  # label without "Gà "
    en: str
    art: str  # file under the app's `ga/` assets

    @property
    def name_vi(self) -> str:
        return f"Gà {self.vi}"

    @property
    def name_en(self) -> str:
        return f"{self.en} chicken"


_ART = {"nt": "nghethuat", "kn": "kynang", "toanhoc": "toan", "nna": "anh"}
_LABELS: dict[str, tuple[str, str]] = {
    "toan": ("Toán", "Math"), "van": ("Văn", "Literature"), "anh": ("Anh", "English"), "khoahoc": ("Khoa học", "Science"),
    "su": ("Sử", "History"), "dia": ("Địa", "Geography"), "cd": ("Công dân", "Civics"), "tin": ("Tin", "Informatics"),
    "cn": ("Công nghệ", "Technology"), "nt": ("Nghệ thuật", "Arts"), "kn": ("Kỹ năng", "Skills"),
    "li": ("Lí", "Physics"), "hoa": ("Hóa", "Chemistry"), "sinh": ("Sinh", "Biology"),
    "khmt": ("Khoa học máy tính", "Computer Science"), "ktmt": ("Kỹ thuật máy tính", "Computer Engineering"),
    "httt": ("Hệ thống thông tin", "Information Systems"), "khdl": ("Khoa học dữ liệu", "Data Science"),
    "toanhoc": ("Toán học", "Mathematics"), "vatli": ("Vật lí", "Physics"), "hoahoc": ("Hóa học", "Chemistry"),
    "kinhte": ("Kinh tế", "Economics"), "ketoan": ("Kế toán", "Accounting"), "nna": ("Ngôn ngữ Anh", "English Studies"),
    "daicuong": ("Đại cương", "General studies"),
}
CHICKENS: dict[str, Chicken] = {k: Chicken(k, vi, en, _ART.get(k, k)) for k, (vi, en) in _LABELS.items()}

# subject text of the catalog -> chicken (lg-03 SUBJ2GA)
SUBJ2GA: dict[str, dict[str, str]] = {
    "school": {
        "Toán": "toan", "Tiếng Việt": "van", "Ngữ văn": "van", "Tiếng Anh": "anh", "IELTS": "anh", "SAT": "anh", "English": "anh",
        "Tự nhiên và Xã hội": "khoahoc", "Khoa học": "khoahoc", "Science": "khoahoc", "Khoa học tự nhiên": "khoahoc",
        "Lịch sử và Địa lí": "su", "Lịch sử": "su", "Địa lí": "dia", "Đạo đức": "cd", "GDCD": "cd",
        "Giáo dục kinh tế và pháp luật": "cd", "Tin học": "tin", "Computing": "tin", "Công nghệ": "cn", "Ôn thi": "kn",
        "Kĩ năng": "kn",
    },
    "uni": {
        "Giải tích": "toanhoc", "Đại số tuyến tính": "toanhoc", "Toán rời rạc": "toanhoc", "Linear Algebra": "toanhoc",
        "Xác suất thống kê": "khdl", "Probability": "khdl", "Machine learning": "khdl", "Machine Learning": "khdl",
        "Lập trình Python": "khmt", "Cấu trúc dữ liệu": "khmt", "Lập trình": "khmt", "Computer Science": "khmt",
        "Cơ sở dữ liệu": "httt", "Mạng máy tính": "ktmt", "Hệ điều hành": "ktmt", "Kinh tế vi mô": "kinhte",
        "Kinh tế vĩ mô": "kinhte", "Economics": "kinhte", "Vật lí đại cương": "vatli", "Hóa học đại cương": "hoahoc",
        "Kế toán": "ketoan", "Academic Writing": "nna", "Phương pháp nghiên cứu": "daicuong",
    },
}
# the catalog also has subjects the mockup table lacks; map them by keyword (checked after the exact table, unaccented)
_SCHOOL_WORDS = (
    ("giao duc cong dan", "cd"), ("giao duc kinh te", "cd"), ("dao duc", "cd"), ("khoa hoc tu nhien", "khoahoc"),
    ("lich su va dia", "su"), ("lich su", "su"), ("dia li", "dia"), ("dia ly", "dia"), ("ngu van", "van"),
    ("tieng viet", "van"), ("tieng anh", "anh"), ("english", "anh"), ("ielts", "anh"), ("tin hoc", "tin"),
    ("computing", "tin"), ("coding", "tin"), ("cong nghe", "cn"), ("toan", "toan"), ("khoa hoc", "khoahoc"),
    ("science", "khoahoc"), ("ki nang", "kn"), ("ky nang", "kn"),
)
_UNI_WORDS = (
    ("giai tich", "toanhoc"), ("dai so", "toanhoc"), ("toan", "toanhoc"), ("algebra", "toanhoc"), ("xac suat", "khdl"),
    ("probability", "khdl"), ("machine learning", "khdl"), ("data", "khdl"), ("python", "khmt"), ("cau truc du lieu", "khmt"),
    ("lap trinh", "khmt"), ("computer science", "khmt"), ("co so du lieu", "httt"), ("mang may tinh", "ktmt"),
    ("he dieu hanh", "ktmt"), ("kinh te", "kinhte"), ("economics", "kinhte"), ("vat li", "vatli"), ("hoa hoc", "hoahoc"),
    ("ke toan", "ketoan"), ("academic writing", "nna"), ("english", "nna"), ("tieng anh", "nna"),
)
_SCIENCE10 = {"Vật lí": "li", "Hóa học": "hoa", "Sinh học": "sinh"}


def stage_of(band: str | None) -> str:
    return STAGE_OF_BAND.get(band or DEFAULT_BAND, "high")


def band_or_default(band: str | None) -> str:
    return band if band in STAGE_OF_BAND else DEFAULT_BAND


def chickens_of_band(band: str | None) -> tuple[str, ...]:
    return STAGE_CHICKENS[stage_of(band)]


def valid_for_band(chicken: str, band: str | None) -> bool:
    return chicken in chickens_of_band(band)


def _keyword(table: tuple[tuple[str, str], ...], subject: str) -> str | None:
    folded = unaccent(subject)
    return next((cid for word, cid in table if word in folded), None)


def chicken_of(subject: str, age_band: str | None, explicit: str | None = None) -> str:
    """Chicken of a course from its free-text `subject` and `age_band`. A teacher label (`explicit`) wins when it is a
    chicken of the band. Unknown subjects go to `kn` (school) or `daicuong` (university)."""
    band = band_or_default(age_band)
    if explicit and valid_for_band(explicit, band):
        return explicit
    subject = (subject or "").strip()
    if band == "uni":
        return SUBJ2GA["uni"].get(subject) or _keyword(_UNI_WORDS, subject) or "daicuong"
    if band == "g10_12" and subject in _SCIENCE10:
        return _SCIENCE10[subject]
    if subject in _SCIENCE10:  # below grade 10 physics, chemistry and biology sit in Khoa học
        return "khoahoc"
    found = SUBJ2GA["school"].get(subject) or _keyword(_SCHOOL_WORDS, subject)
    if found is None:
        folded = unaccent(subject)
        if any(k in folded for k in ("vat li", "hoa hoc", "sinh hoc")):
            found = {"vat li": "li", "hoa hoc": "hoa", "sinh hoc": "sinh"}[
                next(k for k in ("vat li", "hoa hoc", "sinh hoc") if k in folded)] if band == "g10_12" else "khoahoc"
    if found == "khoahoc" and band == "g10_12":
        found = "kn"  # no integrated science chicken in grades 10 to 12
    return found or "kn"


def chicken_of_entry(entry, explicit: str | None = None) -> str:
    """For a `CatalogEntry` / `CourseMeta`: its own `chicken` label if valid, else derived."""
    return chicken_of(entry.subject, entry.age_band, explicit or getattr(entry, "chicken", None))


def market_row(cid: str) -> dict:
    c = CHICKENS[cid]
    return {"id": cid, "name_vi": c.name_vi, "name_en": c.name_en, "art": c.art}


# bank subject (practice engine) -> chicken
BANK_SUBJECT = {"math": "toan", "physics": "li", "english": "anh"}


def chicken_of_bank_subject(subject: str, age_band: str | None) -> str | None:
    cid = BANK_SUBJECT.get(subject)
    if cid is None:
        return None
    if band_or_default(age_band) == "uni":
        return {"toan": "toanhoc", "li": "vatli", "anh": "nna"}[cid]
    if cid == "li" and stage_of(age_band) == "low":
        return "khoahoc"
    return cid
