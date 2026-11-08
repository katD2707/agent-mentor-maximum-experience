// Nghiên cứu (Research): wire types of `/api/research/*`, CONTRACTS.md section 15.
// Mirror of packages/mentor-schemas/src/mentor_schemas/research.py: keep names identical. University band only.
// Dates are YYYY-MM-DD, times HH:MM (Vietnam time), instants ISO 8601 with offset (+07:00).

export const READING_LIST_LIMIT = 5;
export const SUGGESTIONS_PER_WEEK = 10;
export const SUGGESTIONS_FEATURED = 5;
export const REVIEW_MAX_PAPERS = 8;
export const REVIEW_MAX_FOLLOWUPS = 3;
export const SUMMARY_MIN_CHARS = 20;
export const SEARCH_PAGE_SIZE = 10;
export const RELATED_MAX_ITEMS = 20;
export const UPCOMING_MAX_ITEMS = 6;
export const EXPERIMENTS_IN_OVERVIEW = 5;

/** Recorded by the server into behaviour_events; the app never sends these. */
export type ResearchEventKind = "paper_opened" | "paper_read" | "summary_written" | "experiment_logged";

export type PaperSource = "asta" | "s2" | "arxiv";
export type SourceName = "asta" | "s2";
export type ReadStatus = "new" | "reading" | "read";
export type EntryOrigin = "search" | "suggestion" | "link" | "pdf" | "related";
export type FulltextState = "none" | "indexing" | "ready";
export type FeedbackKind = "right" | "inaccurate" | "missing";
export type ExperimentStatus = "running" | "done" | "failed" | "cancelled";
export type MeetingStatus = "scheduled" | "done" | "cancelled";
export type DeadlineKind = "submission" | "other";
export type JobKind = "review" | "discovery";
export type JobStatus = "queued" | "running" | "done" | "failed";
export type ReviewStage = "searching" | "reading";
/** skipped: has a key, but the chosen search depth leaves the source out */
export type SourceStatusName = "ok" | "not_connected" | "skipped" | "failed";
export type SearchDepth = "quick" | "thorough" | "deep";
export type SuggestionStatus = "pending" | "accepted" | "dismissed";
export type NotFoundReason = "no_passage" | "no_fulltext";
export type MissingField = "commit" | "seed";

/** Machine codes of `{"error": code}` bodies the research endpoints add to section 5's. */
export type ResearchErrorCode =
  | "not_university"
  | "invalid_key"
  | "source_unreachable"
  | "unknown_source"
  | "empty_query"
  | "reading_list_full"
  | "paper_not_found"
  | "paper_unresolved"
  | "bad_paper_ref"
  | "suggestion_not_found"
  | "summary_required"
  | "model_unavailable"
  | "no_fulltext"
  | "job_running"
  | "job_not_found"
  | "rate_limited"
  | "empty_title"
  | "bad_keywords"
  | "deadline_unparsed"
  | "deadline_not_found"
  | "meeting_unparsed"
  | "meeting_not_found"
  | "action_not_found"
  | "experiment_not_found"
  | "upload_not_found";

export interface LiveLine {
  line_vi: string;
  line_en: string;
}

// ---- profile and source keys
export interface ResearchProfile {
  title: string;
  question: string;
  keywords: string[];
  advisor_name: string;
  asta_connected: boolean;
  s2_connected: boolean;
  updated_at: string | null;
}

export interface ResearchProfileInput {
  title?: string;
  question?: string;
  keywords?: string[];
  advisor_name?: string;
}

export interface SourceKeysStatus {
  asta_connected: boolean;
  s2_connected: boolean;
}

export interface SourceKeyInput {
  key: string;
}

// ---- papers and search
export interface PaperCard {
  key: string;
  source: PaperSource;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  arxiv_id: string | null;
  doi: string | null;
  s2_id: string | null;
  url: string;
  excerpt: string;
  tldr: string | null;
  snippet: string | null;
  citation_count: number | null;
  has_pdf: boolean;
  in_reading_list: boolean;
  paper_id: string | null;
}

export interface SearchSourceStatus {
  source: PaperSource;
  status: SourceStatusName;
}

export interface SearchParams {
  q: string;
  /** keep papers from this year on (5 years back = this year - 4, this year = this year) */
  year_min?: number;
  pdf?: boolean;
  page?: number;
  /** quick = arXiv, thorough = + Semantic Scholar, deep = + Asta; none = every source with a key */
  depth?: SearchDepth;
}

export interface SearchResponse {
  query: string;
  page: number;
  page_size: number;
  has_more: boolean;
  sources: SearchSourceStatus[];
  results: PaperCard[];
}

export interface ReadingEntry {
  id: string;
  paper: PaperCard;
  status: ReadStatus;
  reason: string;
  origin: EntryOrigin;
  new_this_week: boolean;
  minutes_spent: number;
  added_at: string;
  opened_at: string | null;
  read_at: string | null;
}

export interface ReadingList {
  limit: number;
  active_count: number;
  items: ReadingEntry[];
}

/** Exactly one of card, link, upload_path. */
export interface AddPaperRequest {
  card?: PaperCard;
  link?: string;
  upload_path?: string;
  reason?: string;
}

export interface StatusInput {
  status: ReadStatus;
}

// ---- paper reader
export interface FeedbackRow {
  kind: FeedbackKind;
  text: string;
}

export interface PaperFeedback {
  rows: FeedbackRow[];
  for_thesis: string | null;
  created_at: string;
}

export interface PaperNote {
  my_summary: string | null;
  summary_updated_at: string | null;
  feedback: PaperFeedback | null;
}

export interface SummaryInput {
  text: string;
}

export interface PaperDetail {
  entry: ReadingEntry;
  abstract: string;
  pdf_url: string | null;
  fulltext: FulltextState;
  thesis_tag: string | null;
  note: PaperNote;
  qa_count: number;
}

export interface AskInput {
  text: string;
  lang?: "vi" | "en";
}

export interface QaCitation {
  section: string;
  snippet: string;
  url: string | null;
}

export interface CourseRef {
  course_id: string;
  lesson_id: string | null;
  title: string;
  deep_link: string;
}

export interface PaperQA {
  id: string;
  question: string;
  answer: string;
  found: boolean;
  not_found_reason: NotFoundReason | null;
  citations: QaCitation[];
  course_hint: CourseRef | null;
  created_at: string;
}

/** SSE of POST /research/papers/{id}/ask: `status`, `qa`, `error`, `done`. */
export type PaperAskEvent =
  | { event: "status"; data: { stage: "searching" | "reading" } }
  | { event: "qa"; data: PaperQA }
  | { event: "error"; data: { code: "model_unavailable" | "internal"; message: string } }
  | { event: "done"; data: { qa_id: string | null } };

export interface RelatedList {
  count: number;
  items: PaperCard[];
}

export interface RelatedPapers {
  available: boolean;
  reason: "no_source_key" | null;
  sources: SourceName[];
  partial: boolean;
  citing: RelatedList;
  cited: RelatedList;
}

// ---- quick review and discovery jobs
export interface ReviewRequest {
  query: string;
  year_min?: number;
  followups?: string[];
}

export interface ReviewRow {
  key: string;
  problem: string | null;
  method: string | null;
  data: string | null;
  result: string | null;
}

export interface SearchRun {
  query: string;
  count: number;
}

export interface ReviewResult {
  query: string;
  papers: PaperCard[];
  matrix: ReviewRow[];
  followups: string[];
  searches: SearchRun[];
  coverage: string;
  caveat_vi: string;
  caveat_en: string;
}

export interface JobProgress {
  stage: ReviewStage;
  total: number;
  done: number;
}

export interface DiscoveryResult {
  status: "papers_found" | "papers_not_found";
  queries: string[];
  new_suggestions: number;
}

export interface ResearchJob {
  id: string;
  kind: JobKind;
  status: JobStatus;
  progress: JobProgress | null;
  result: ReviewResult | DiscoveryResult | null;
  error: "model_unavailable" | "search_failed" | "internal" | null;
  created_at: string;
  finished_at: string | null;
}

export interface JobStarted {
  job_id: string;
  status: "queued" | "running";
}

export interface DiscoveryStatus {
  state: "idle" | "running";
  last_run_at: string | null;
  last_status: "papers_found" | "papers_not_found" | "failed" | "waiting_model" | null;
  next_run_at: string | null;
}

export interface Suggestion {
  id: string;
  week_of: string;
  paper: PaperCard;
  reason: string;
  query: string;
  featured: boolean;
  status: SuggestionStatus;
  created_at: string;
}

export interface SuggestionList {
  week_of: string | null;
  items: Suggestion[];
  discovery: DiscoveryStatus;
}

// ---- deadlines and milestones
export interface Milestone {
  id: string;
  title: string;
  due_date: string;
  due_time: string | null;
  original_text: string | null;
  confirmed: boolean;
  kind: DeadlineKind;
  thesis: boolean;
  done: boolean;
  days_left: number;
  planned_sessions: number;
  created_at: string;
}

/** Either `text`, or `title` + `due_date`. */
export interface MilestoneInput {
  text?: string;
  title?: string;
  due_date?: string;
  due_time?: string;
  /** "AoE", "UTC", "Asia/Ho_Chi_Minh" (default) */
  tz?: string;
  kind?: DeadlineKind;
  thesis?: boolean;
}

export interface MilestonePatch {
  title?: string;
  due_date?: string;
  due_time?: string;
  kind?: DeadlineKind;
  thesis?: boolean;
  confirmed?: boolean;
  done?: boolean;
}

/** Additive fields on section 12's Goal (apps/app/src/api/planner.ts) and on PlanItem and Reminder kinds. */
export interface ResearchGoalExtras {
  source: "learning" | "research";
  /** research goal only, otherwise [] */
  milestones: Milestone[];
}
export type ResearchPlanItemKind = "research";
export type ResearchReminderKind = "research";

// ---- meetings
export interface AgendaItem {
  text: string;
  done: boolean;
}

export interface Agenda {
  promised: AgendaItem[];
  new_results: string;
  open_questions: string;
  drafted_at: string | null;
  edited_at: string | null;
}

export interface ActionItem {
  id: string;
  text: string;
  due_date: string | null;
  done: boolean;
  in_plan: boolean;
}

export interface Meeting {
  id: string;
  at: string;
  title: string;
  status: MeetingStatus;
  agenda: Agenda | null;
  notes_md: string | null;
  action_items: ActionItem[];
  created_at: string;
}

/** Either `text` or `at`. */
export interface MeetingInput {
  text?: string;
  at?: string;
  title?: string;
}

export interface MeetingPatch {
  at?: string;
  title?: string;
  status?: MeetingStatus;
}

export interface AgendaInput {
  new_results?: string;
  open_questions?: string;
}

export interface NotesInput {
  notes_md: string;
}

export interface ActionItemPatch {
  text?: string;
  due_date?: string;
  done?: boolean;
}

// ---- experiment log
export interface Experiment {
  id: string;
  date: string;
  title: string;
  status: ExperimentStatus;
  aim: string;
  setup: string;
  result: string;
  user_note: string;
  next: string;
  commit: string | null;
  seed: string | null;
  missing: MissingField[];
  photo_path: string | null;
  raw_text: string;
  structured: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExperimentInput {
  text: string;
  photo_path?: string;
}

export interface ExperimentPatch {
  title?: string;
  status?: ExperimentStatus;
  aim?: string;
  setup?: string;
  result?: string;
  user_note?: string;
  next?: string;
  commit?: string;
  seed?: string;
}

export interface ExperimentList {
  items: Experiment[];
  next_before: string | null;
}

// ---- overview
export interface ReadNext {
  paper_id: string;
  title: string;
  authors_line: string;
  status: ReadStatus;
  minutes_spent: number;
  reason: string;
  deep_link: string;
}

export interface UpcomingItem {
  kind: "meeting" | "deadline";
  id: string;
  title: string;
  date: string;
  time: string | null;
  days_left: number;
  confirmed: boolean;
  agenda_ready: boolean | null;
  original_text: string | null;
  planned_sessions: number;
}

export interface ResearchOverview {
  profile: ResearchProfile;
  status_line: LiveLine;
  hero: ReadNext | null;
  upcoming: UpcomingItem[];
  reading_list: ReadingList;
  suggestions: Suggestion[];
  milestones: Milestone[];
  goal_id: string | null;
  experiments: Experiment[];
  discovery: DiscoveryStatus;
}
