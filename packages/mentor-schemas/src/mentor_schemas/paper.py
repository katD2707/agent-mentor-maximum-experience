"""Exam papers for the Arena ("Đấu trường", CONTRACTS-LANGGA section 2).

A paper is a content file `mentor-content/papers/<id>.json`: a real exam (or a placeholder made from the question bank until
real ones are imported) split into parts of quiz items. The crawl project writes files in this format; see
`mentor-content/papers/README.md`. Items are course `QuizItem`s (same answer keys), text only: no asset files.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mentor_schemas.course import AgeBand, Id, QuizItem

PaperKind = Literal["thpt", "minh-hoa", "dgnl", "cuoi-ky"]
PaperBand = Literal["g10_12", "uni"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaperSource(_Strict):
    name: str  # who published it: "Bộ GD&ĐT", "ĐH Bách khoa", "Mentor (đề mẫu từ ngân hàng câu hỏi)"
    url: str = ""


class PaperPart(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,23}$")]
    title_vi: str
    title_en: str = ""
    type: str = "MIXED"  # informational: SINGLE_CHOICE | TRUE_FALSE_GROUP | SHORT_ANSWER | MIXED
    items: list[QuizItem] = Field(min_length=1)
    # points of one item of this part; None = the paper's `max_score` split evenly over every item
    points_each: float | None = Field(default=None, gt=0)


class Paper(_Strict):
    id: Id
    kind: PaperKind
    band: PaperBand
    chicken: str  # a chicken id of the band (checked by the gateway validator: the list lives there)
    title_vi: str
    title_en: str = ""
    year: int = Field(ge=1990, le=2100)
    minutes: int = Field(ge=1, le=300)
    parts: list[PaperPart] = Field(min_length=1)
    source: PaperSource
    placeholder: bool = False  # true = built from the bank, shown as "Đề mẫu" until a real paper replaces it
    max_score: float = Field(default=10.0, gt=0)
    note_vi: str = ""  # e.g. "Rút gọn: 2 câu Đúng/Sai"
    note_en: str = ""

    @model_validator(mode="after")
    def _unique(self) -> Paper:
        parts = [p.id for p in self.parts]
        if len(parts) != len(set(parts)):
            raise ValueError("duplicate part id")
        items = [q.id for p in self.parts for q in p.items]
        if len(items) != len(set(items)):
            raise ValueError("duplicate item id")
        for p in self.parts:
            for q in p.items:
                if q.stem_audio or q.stem_image or q.tap or any(o.image or o.audio for o in q.options):
                    raise ValueError(f"{q.id}: paper items are text only (no assets)")
        return self

    @property
    def item_count(self) -> int:
        return sum(len(p.items) for p in self.parts)

    def points_of(self, part: PaperPart) -> float:
        return part.points_each if part.points_each is not None else round(self.max_score / self.item_count, 6)


__all__ = ["AgeBand", "Paper", "PaperBand", "PaperKind", "PaperPart", "PaperSource"]
