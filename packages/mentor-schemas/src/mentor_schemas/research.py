"""Nghiên cứu (Research) contracts, REQUIREMENTS-PLAN 3.11 and CONTRACTS.md section 15.

Wire shapes of `/api/research/*`. University band only. Mirrored by `apps/app/src/api/research-types.ts`: field
names are identical on both sides and in CONTRACTS.md section 15. Not re-exported from `mentor_schemas/__init__.py`
(same as `course.py`): `from mentor_schemas.research import ...`.

Conventions
- Dates are `YYYY-MM-DD`, times `HH:MM`, instants ISO 8601 with offset (`+07:00`, local `Asia/Ho_Chi_Minh`).
- Text Mentor writes for the learner (`reason`, feedback rows, answers) is one string in the user's language at the
  time it was written. Lines built by code (hub status line) carry `_vi` and `_en` like section 12.
- API keys (`asta`, `s2`) are never part of any response model.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------- limits (the server enforces, the app may show)
READING_LIST_LIMIT = 5  # active (status new or reading) entries
SUGGESTIONS_PER_WEEK = 10
SUGGESTIONS_FEATURED = 5
REVIEW_MAX_PAPERS = 8
REVIEW_MAX_FOLLOWUPS = 3
SUMMARY_MIN_CHARS = 20
SEARCH_PAGE_SIZE = 10
RELATED_MAX_ITEMS = 20
UPCOMING_MAX_ITEMS = 6
EXPERIMENTS_IN_OVERVIEW = 5

# Behaviour events the research endpoints record themselves into `behaviour_events` (section 12). The app never sends them.
RESEARCH_EVENT_FIELDS: dict[str, tuple[str, ...]] = {
    "paper_opened": ("paper_id",),
    "paper_read": ("paper_id",),
    "summary_written": ("paper_id", "chars"),
    "experiment_logged": ("experiment_id", "status"),
}
RESEARCH_EVENT_KINDS = tuple(RESEARCH_EVENT_FIELDS)

PaperSource = Literal["asta", "s2", "arxiv"]  # the source whose card is shown (priority asta > s2 > arxiv)
SourceName = Literal["asta", "s2"]  # sources that need the user's own key
ReadStatus = Literal["new", "reading", "read"]
EntryOrigin = Literal["search", "suggestion", "link", "pdf", "related"]
FulltextState = Literal["none", "indexing", "ready"]
FeedbackKind = Literal["right", "inaccurate", "missing"]
ExperimentStatus = Literal["running", "done", "failed", "cancelled"]
MeetingStatus = Literal["scheduled", "done", "cancelled"]
DeadlineKind = Literal["submission", "other"]
JobKind = Literal["review", "discovery"]
JobStatus = Literal["queued", "running", "done", "failed"]
ReviewStage = Literal["searching", "reading"]
SourceStatusName = Literal["ok", "not_connected", "skipped", "failed"]
SearchDepth = Literal["quick", "thorough", "deep"]
SuggestionStatus = Literal["pending", "accepted", "dismissed"]
NotFoundReason = Literal["no_passage", "no_fulltext"]
MissingField = Literal["commit", "seed"]

Date = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Clock = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Instant = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LiveLine(_M):
    line_vi: str
    line_en: str


# ---------------------------------------------------------------- profile and source keys
class ResearchProfile(_M):
    """GET and PUT /research/profile. Empty `title` = nothing set yet (first-open state)."""

    title: str = Field(default="", max_length=300)
    question: str = Field(default="", max_length=300)
    keywords: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=8)
    advisor_name: str = Field(default="", max_length=100)
    asta_connected: bool = False
    s2_connected: bool = False
    updated_at: Instant | None = None


class ResearchProfileInput(_M):
    """PUT body, only present fields change. A `title` without `question` and `keywords` makes Mentor derive both
    (a question and 3-5 English keywords) and start a discovery job."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    question: str | None = Field(default=None, max_length=300)
    keywords: list[Annotated[str, Field(min_length=1, max_length=40)]] | None = Field(default=None, max_length=8)
    advisor_name: str | None = Field(default=None, max_length=100)


class SourceKeysStatus(_M):
    """GET /research/source-keys, and the response of PUT and DELETE. arXiv is always on and not listed."""

    asta_connected: bool
    s2_connected: bool


class SourceKeyInput(_M):
    key: str = Field(min_length=8, max_length=200)


# ---------------------------------------------------------------- papers and search
class PaperCard(_M):
    """One paper as search, suggestions and related lists show it. `key` is the dedupe key:
    `arxiv:<id without version>`, else `doi:<lower-case doi>`, else `s2:<paperId>`."""

    key: str
    source: PaperSource
    title: str
    authors: list[str] = Field(default_factory=list, max_length=5)
    year: int | None = None
    venue: str | None = None
    arxiv_id: str | None = None
    doi: str | None = None
    s2_id: str | None = None
    url: str = ""
    excerpt: str = ""  # first sentences of the abstract, <= 240 chars; empty when the source gave no abstract
    tldr: str | None = None  # Semantic Scholar only, English
    snippet: str | None = None  # Asta full-text snippet for the query, search results only
    citation_count: int | None = None  # null = unknown (arXiv-only cards never have it)
    has_pdf: bool = False
    in_reading_list: bool = False
    paper_id: str | None = None  # our id when the paper is already stored


class SearchSourceStatus(_M):
    source: PaperSource
    status: SourceStatusName  # not_connected: no key; skipped: has a key but the chosen depth leaves it out; failed: bad or expired key, rate limit or outage (skipped)


class SearchResponse(_M):
    query: str
    page: int
    page_size: int
    has_more: bool
    sources: list[SearchSourceStatus]
    results: list[PaperCard]


class ReadingEntry(_M):
    id: str  # paper id, used in every `/research/papers/{id}` path
    paper: PaperCard
    status: ReadStatus
    reason: str  # one line: why this paper matters for the thesis
    origin: EntryOrigin
    new_this_week: bool  # status new and added within 7 days: the UI says "Mới", otherwise "Chưa đọc"
    minutes_spent: int = 0
    added_at: Instant
    opened_at: Instant | None = None
    read_at: Instant | None = None


class ReadingList(_M):
    """Active entries (new, reading) plus entries read in the last 14 days. At most 5 are active."""

    limit: int = READING_LIST_LIMIT
    active_count: int
    items: list[ReadingEntry]


class AddPaperRequest(_M):
    """POST /research/reading-list: exactly one of `card` (from search or related), `link` (URL or DOI) or `upload_path`."""

    card: PaperCard | None = None
    link: str | None = Field(default=None, max_length=500)
    upload_path: str | None = None  # `path` returned by POST /uploads (a PDF)
    reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _one(self) -> AddPaperRequest:
        if sum(x is not None for x in (self.card, self.link, self.upload_path)) != 1:
            raise ValueError("give exactly one of card, link, upload_path")
        return self


class StatusInput(_M):
    status: ReadStatus


# ---------------------------------------------------------------- paper reader (hs-12)
class FeedbackRow(_M):
    kind: FeedbackKind
    text: str


class PaperFeedback(_M):
    rows: list[FeedbackRow]
    for_thesis: str | None = None  # the "Với luận văn của bạn" note
    created_at: Instant


class PaperNote(_M):
    my_summary: str | None = None
    summary_updated_at: Instant | None = None
    feedback: PaperFeedback | None = None  # null until requested; dropped when the summary changes


class SummaryInput(_M):
    text: str = Field(min_length=SUMMARY_MIN_CHARS, max_length=4000)


class PaperDetail(_M):
    entry: ReadingEntry
    abstract: str = ""
    pdf_url: str | None = None
    fulltext: FulltextState = "none"  # whether paper questions can be answered from the paper's own text
    thesis_tag: str | None = None  # e.g. "Mục 3 của bạn"
    note: PaperNote
    qa_count: int = 0


class AskInput(_M):
    text: str = Field(min_length=1, max_length=500)
    lang: Literal["vi", "en"] | None = None


class QaCitation(_M):
    section: str  # "Mục 4.1, Dữ liệu"
    snippet: str
    url: str | None = None


class CourseRef(_M):
    course_id: str
    lesson_id: str | None = None
    title: str
    deep_link: str


class PaperQA(_M):
    id: str
    question: str
    answer: str  # when `found` is false: an honest "not found" sentence
    found: bool
    not_found_reason: NotFoundReason | None = None
    citations: list[QaCitation] = Field(default_factory=list)
    course_hint: CourseRef | None = None
    created_at: Instant


class RelatedList(_M):
    count: int  # total known to the source, `items` is cut to 20
    items: list[PaperCard]


class RelatedPapers(_M):
    """GET /research/papers/{id}/related. No key: `available` false, empty lists."""

    available: bool
    reason: Literal["no_source_key"] | None = None
    sources: list[SourceName] = Field(default_factory=list)
    partial: bool = False  # a connected source failed, lists may be short
    citing: RelatedList
    cited: RelatedList


# ---------------------------------------------------------------- quick review and discovery jobs
class ReviewRequest(_M):
    query: str = Field(min_length=1, max_length=300)
    year_min: int | None = None
    followups: list[str] = Field(default_factory=list, max_length=REVIEW_MAX_FOLLOWUPS)


class ReviewRow(_M):
    """What the model read from one abstract. `null` = the abstract does not say ("Abstract không nêu")."""

    key: str
    problem: str | None = None
    method: str | None = None
    data: str | None = None
    result: str | None = None


class SearchRun(_M):
    query: str
    count: int


class ReviewResult(_M):
    query: str
    papers: list[PaperCard] = Field(max_length=REVIEW_MAX_PAPERS)
    matrix: list[ReviewRow]
    followups: list[str] = Field(default_factory=list, max_length=REVIEW_MAX_FOLLOWUPS)
    searches: list[SearchRun] = Field(default_factory=list)
    coverage: str = ""
    caveat_vi: str = "Chỉ dựa trên abstract, chưa đủ để kết luận. Đọc toàn văn trước khi trích dẫn."
    caveat_en: str = "Based on abstracts only, not enough to draw a conclusion. Read the full text before citing."


class JobProgress(_M):
    stage: ReviewStage
    total: int = 0
    done: int = 0


class DiscoveryResult(_M):
    status: Literal["papers_found", "papers_not_found"]
    queries: list[str] = Field(default_factory=list, max_length=3)
    new_suggestions: int = 0


class ResearchJob(_M):
    id: str
    kind: JobKind
    status: JobStatus
    progress: JobProgress | None = None
    result: ReviewResult | DiscoveryResult | None = None  # non-null only when status is done (null while running and on failure)
    error: Literal["model_unavailable", "search_failed", "internal"] | None = None  # present when failed
    created_at: Instant
    finished_at: Instant | None = None


class JobStarted(_M):
    job_id: str
    status: Literal["queued", "running"]


class DiscoveryStatus(_M):
    state: Literal["idle", "running"]
    last_run_at: Instant | None = None
    last_status: Literal["papers_found", "papers_not_found", "failed", "waiting_model"] | None = None
    next_run_at: Instant | None = None  # next Monday 06:00 local


class Suggestion(_M):
    id: str
    week_of: Date  # the Monday of the discovery run
    paper: PaperCard  # source is always arxiv
    reason: str
    query: str  # the arXiv query that found it
    featured: bool  # the 5 shown on the home screen
    status: SuggestionStatus = "pending"
    created_at: Instant


class SuggestionList(_M):
    week_of: Date | None = None
    items: list[Suggestion]  # pending only, at most 10, featured first
    discovery: DiscoveryStatus


# ---------------------------------------------------------------- deadlines and milestones
class Milestone(_M):
    """A dated item: an external deadline or a thesis milestone. Stored in the `milestones` of the one
    `source: "research"` Goal (section 12), so no table of its own."""

    id: str
    title: str
    due_date: Date
    due_time: Clock | None = None  # Vietnam time; null = no time known
    original_text: str | None = None  # as given, e.g. "23:59 AoE 15/11"
    confirmed: bool  # false when the time is missing or the source was unclear: shown as "Chưa xác nhận"
    kind: DeadlineKind = "other"
    thesis: bool = False  # true = also listed in "Mốc luận văn" and counted in the goal's progress
    done: bool = False
    days_left: int  # calendar days from today, negative when overdue
    planned_sessions: int = 0  # preparation sessions the planner placed
    created_at: Instant


class MilestoneInput(_M):
    """POST /research/deadlines: `text` ("nộp full paper 16/11, 23:59 AoE") or `title` + `due_date`, not both."""

    text: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=200)
    due_date: Date | None = None
    due_time: Clock | None = None
    tz: str | None = Field(default=None, max_length=40)  # "AoE", "UTC", "Asia/Ho_Chi_Minh" (default)
    kind: DeadlineKind | None = None
    thesis: bool | None = None

    @model_validator(mode="after")
    def _one(self) -> MilestoneInput:
        if (self.text is None) == (self.title is None):
            raise ValueError("give text or title")
        if self.title is not None and self.due_date is None:
            raise ValueError("title needs due_date")
        return self


class MilestonePatch(_M):
    title: str | None = Field(default=None, max_length=200)
    due_date: Date | None = None
    due_time: Clock | None = None
    kind: DeadlineKind | None = None
    thesis: bool | None = None
    confirmed: bool | None = None
    done: bool | None = None


# ---------------------------------------------------------------- meetings
class AgendaItem(_M):
    text: str
    done: bool


class Agenda(_M):
    promised: list[AgendaItem] = Field(default_factory=list)  # what was promised last time
    new_results: str = ""  # the learner fills
    open_questions: str = ""  # the learner fills
    drafted_at: Instant | None = None
    edited_at: Instant | None = None


class ActionItem(_M):
    id: str
    text: str
    due_date: Date | None = None
    done: bool = False
    in_plan: bool = False  # true when it became a planner item (needs a due date)


class Meeting(_M):
    id: str
    at: Instant
    title: str = "Họp GVHD"
    status: MeetingStatus = "scheduled"
    agenda: Agenda | None = None  # drafted 2 days before `at`
    notes_md: str | None = None
    action_items: list[ActionItem] = Field(default_factory=list)
    created_at: Instant


class MeetingInput(_M):
    """POST /research/meetings: `text` ("họp GVHD thứ Tư 11/11 14:00") or `at`, not both."""

    text: str | None = Field(default=None, max_length=200)
    at: Instant | None = None
    title: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _one(self) -> MeetingInput:
        if (self.text is None) == (self.at is None):
            raise ValueError("give text or at")
        return self


class MeetingPatch(_M):
    at: Instant | None = None
    title: str | None = Field(default=None, max_length=100)
    status: MeetingStatus | None = None


class AgendaInput(_M):
    new_results: str | None = Field(default=None, max_length=2000)
    open_questions: str | None = Field(default=None, max_length=2000)


class NotesInput(_M):
    notes_md: str = Field(min_length=1, max_length=8000)


class ActionItemPatch(_M):
    text: str | None = Field(default=None, max_length=300)
    due_date: Date | None = None
    done: bool | None = None


# ---------------------------------------------------------------- experiment log
class Experiment(_M):
    id: str  # EXP-yyyy-mm-dd-x
    date: Date
    title: str
    status: ExperimentStatus
    aim: str = ""
    setup: str = ""
    result: str = ""  # the learner's numbers, restated, never interpreted
    user_note: str = ""  # the learner's own comment
    next: str = ""
    commit: str | None = None
    seed: str | None = None
    missing: list[MissingField] = Field(default_factory=list)  # nudges: "commit" and "seed" not recorded yet
    photo_path: str | None = None
    raw_text: str
    structured: bool = True  # false when the model was unavailable and only `raw_text` is kept
    created_at: Instant
    updated_at: Instant


class ExperimentInput(_M):
    text: str = Field(min_length=1, max_length=4000)
    photo_path: str | None = None  # `path` returned by POST /uploads (jpeg, png, webp, heic)


class ExperimentPatch(_M):
    title: str | None = Field(default=None, max_length=200)
    status: ExperimentStatus | None = None
    aim: str | None = Field(default=None, max_length=1000)
    setup: str | None = Field(default=None, max_length=2000)
    result: str | None = Field(default=None, max_length=2000)
    user_note: str | None = Field(default=None, max_length=2000)
    next: str | None = Field(default=None, max_length=1000)
    commit: str | None = Field(default=None, max_length=64)
    seed: str | None = Field(default=None, max_length=32)


class ExperimentList(_M):
    items: list[Experiment]  # newest first
    next_before: str | None = None  # pass as `before` for the next page


# ---------------------------------------------------------------- overview (home screen, hs-11)
class ReadNext(_M):
    """The "Đọc tiếp" hero."""

    paper_id: str
    title: str
    authors_line: str  # "Pham, Okafor, Lindqvist · 2026"
    status: ReadStatus
    minutes_spent: int = 0
    reason: str
    deep_link: str


class UpcomingItem(_M):
    """A meeting or a deadline in "Việc sắp tới", soonest first. The app builds the sub-line from these fields."""

    kind: Literal["meeting", "deadline"]
    id: str
    title: str
    date: Date
    time: Clock | None = None
    days_left: int
    confirmed: bool = True
    agenda_ready: bool | None = None  # meetings
    original_text: str | None = None  # deadlines, e.g. "23:59 AoE 15/11"
    planned_sessions: int = 0  # deadlines


class ResearchOverview(_M):
    """GET /research. One call paints the home screen; the state (empty, topic set, searching, data) is derived:
    `profile.title == ""` empty; `discovery.state == "running"` searching; no entries and no suggestions yet
    after a run = topic set."""

    profile: ResearchProfile
    status_line: LiveLine
    hero: ReadNext | None = None
    upcoming: list[UpcomingItem] = Field(default_factory=list, max_length=UPCOMING_MAX_ITEMS)
    reading_list: ReadingList
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=SUGGESTIONS_FEATURED)  # featured, pending
    milestones: list[Milestone] = Field(default_factory=list)  # thesis milestones, by date
    goal_id: str | None = None  # the research Goal in /goals, for the "Xem trong Tiến độ" link
    experiments: list[Experiment] = Field(default_factory=list, max_length=EXPERIMENTS_IN_OVERVIEW)
    discovery: DiscoveryStatus
