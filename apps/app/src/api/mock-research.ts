import { ResearchError } from "./research-error";
import type { ResearchApi, PaperAskBody } from "./research";
import type {
  ActionItem,
  Agenda,
  DiscoveryStatus,
  Experiment,
  JobProgress,
  LiveLine,
  Meeting,
  Milestone,
  PaperAskEvent,
  PaperCard,
  SearchDepth,
  PaperFeedback,
  PaperNote,
  PaperQA,
  ReadingEntry,
  ReadStatus,
  RelatedPapers,
  ResearchJob,
  ResearchProfile,
  ResearchOverview,
  ReviewResult,
  ReviewRow,
  SourceName,
  Suggestion,
  UpcomingItem,
} from "./research-types";

/**
 * In-browser mock of CONTRACTS.md section 15 (VITE_API_MOCK=1) with the sample data of the mockups.
 * State lives in memory (the connected-source flags and the scenario also in localStorage).
 * Scenario "full" (default), "empty" (no topic yet) or "searching" (full, with Mentor looking for papers).
 */
const SCENARIO_KEY = "mentor.mock.research.scenario";
const SOURCES_KEY = "mentor.mock.research.sources";

const delay = (ms = 90) => new Promise((r) => setTimeout(r, ms));
const pad = (n: number) => String(n).padStart(2, "0");
const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (n: number, base = new Date()) => {
  const d = new Date(base);
  d.setDate(d.getDate() + n);
  return d;
};
const daysUntil = (date: string) => Math.round((new Date(`${date}T00:00:00`).getTime() - new Date(`${ymd(new Date())}T00:00:00`).getTime()) / 86400000);
const iso = (d: Date) => `${ymd(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:00+07:00`;
const en = () => {
  try {
    return localStorage.getItem("mentor.lang") === "en";
  } catch {
    return false;
  }
};
const tr = (vi: string, e: string) => (en() ? e : vi);

// ---------------------------------------------------------------- sample papers
interface Sample {
  id: string; // arXiv id, or "" for a paper only Semantic Scholar knows
  doi?: string;
  au: string[];
  y: number;
  venue: string;
  cites: number;
  pdf: boolean;
  s2only?: boolean;
  t: string;
  abs: string;
  tldr?: string;
  snip?: string;
}

const SAMPLES: Sample[] = [
  { id: "2603.01234", au: ["Haddad", "Nguyen"], y: 2026, venue: "Digital Discovery", cites: 6, pdf: true, t: "Learning Formation Energies from Fewer Than Five Thousand Crystal Structures",
    abs: "Formation energy models usually need tens of thousands of labelled structures. We train an equivariant network on fewer than five thousand and evaluate it on a held-out split, with and without augmentation of the training set.",
    tldr: "An equivariant network that predicts formation energy from fewer than 5,000 structures.", snip: "…with 3,000 training structures the equivariant model reaches a mean absolute error of 0.047 eV/atom on the held-out split…" },
  { id: "2507.04411", au: ["Moreau", "Abdi"], y: 2025, venue: "NeurIPS Workshop", cites: 2, pdf: true, t: "Sample-Efficient Graph Networks for Inorganic Stability Prediction",
    abs: "We study how a pretraining stage affects graph networks that predict inorganic stability when only a few thousand labelled structures are available, and ablate each component of the pipeline.",
    snip: "…ablating the pretraining stage raises the error by 18% when fewer than 5,000 labelled structures are available…" },
  { id: "2601.08832", au: ["Pham", "Okafor", "Lindqvist"], y: 2026, venue: "Journal of Computational Materials", cites: 14, pdf: true, t: "Equivariant Message Passing for Formation Energy Prediction in Inorganic Crystals",
    abs: "We propose an E(3)-equivariant message passing network that predicts formation energies of inorganic crystals directly from atomic positions and species. On 90,211 structures from a public materials database, the model reduces mean absolute error by 18% over a strong invariant baseline, and by 7% when trained on 3,000 structures. We also report calibrated uncertainty estimates and analyse failure cases on structures far from equilibrium.",
    tldr: "An equivariant message passing network. Cuts MAE by 18% against the baseline, and by 7% with only 3,000 structures." },
  { id: "2602.11975", au: ["Reyes", "Chen"], y: 2026, venue: "arXiv", cites: 3, pdf: true, t: "Data-Efficient Crystal Graph Networks with Pretrained Atomic Embeddings",
    abs: "We show that atom embeddings pretrained on large unlabelled structure sets let crystal graph networks reach chemical accuracy on formation energy with only a few hundred labelled samples, and we release the embeddings for 89 elements." },
  { id: "2405.09317", au: ["Marchetti", "Dang"], y: 2024, venue: "Digital Discovery", cites: 47, pdf: true, t: "Ensembles and Evidential Learning for Uncertainty in Crystal Property Prediction",
    abs: "Uncertainty estimates matter most when training data is scarce. We compare deep ensembles and evidential regression on five crystal property benchmarks of different sizes and report calibration as well as accuracy." },
  { id: "2209.05471", au: ["Lund", "Abara"], y: 2022, venue: "ACM Computing Surveys", cites: 312, pdf: true, t: "Message Passing Networks for Materials Property Prediction: A Survey",
    abs: "We survey graph network architectures for materials property prediction, group them by how they encode geometry, and compare their reported accuracy in a table organised by training set size.",
    tldr: "A survey of graph network architectures for materials, with a comparison table by data size." },
  { id: "2108.07720", au: ["Silva", "Ng"], y: 2021, venue: "arXiv preprint", cites: 175, pdf: true, t: "Transfer Learning for Formation Energy with Limited Labels",
    abs: "Formation energy labels are expensive to compute. We study transfer from a model trained on a large dataset to small target sets, freezing the structure encoder and retraining only the readout layers." },
  { id: "2604.02210", au: ["Sørensen", "Le"], y: 2026, venue: "arXiv", cites: 0, pdf: true, t: "Transfer Learning from Large Atomistic Models to Low-Data Targets",
    abs: "We adapt large pretrained atomistic models to target datasets with fewer than one thousand structures, and compare full fine-tuning, adapter layers and a linear probe on the frozen features." },
  { id: "", doi: "10.1021/acs.chemmater.5c00412", au: ["Okonkwo", "Bauer", "Tanaka"], y: 2025, venue: "Chemistry of Materials", cites: 58, pdf: false, s2only: true, t: "Learning Formation Energies from a Few Hundred Structures with Graph Contrastive Pretraining",
    abs: "We pretrain a graph encoder with a contrastive objective on unlabelled structures, then fine-tune it with very few energy labels.",
    tldr: "Contrastive pretraining on unlabelled structures, then fine-tuning with very few energy labels." },
  // papers on the reading list, not in the search sample above
  { id: "2511.03321", au: ["Tran", "Weiss"], y: 2025, venue: "arXiv", cites: 21, pdf: true, t: "Calibrated Uncertainty for Graph Neural Network Property Predictors",
    abs: "Graph networks for property prediction are often overconfident. We recalibrate ensemble predictions on a validation split and show better coverage on five crystal property benchmarks." },
  { id: "2603.05512", au: ["Haddad", "Nguyen", "Kim"], y: 2026, venue: "arXiv", cites: 1, pdf: true, t: "A Benchmark of Data-Efficient Learning on Small Materials Datasets",
    abs: "We benchmark transfer, pretraining and active learning on materials datasets of a few thousand samples, with a shared evaluation protocol and released splits." },
  { id: "2605.01877", au: ["Ito", "Vo"], y: 2026, venue: "arXiv", cites: 0, pdf: false, t: "Active Learning Loops for Perovskite Stability Screening",
    abs: "We run active learning loops that pick which perovskite compositions to compute next, and compare acquisition rules on a stability screening task." },
];
const SEARCHABLE = SAMPLES.slice(0, 9);

const REV: Record<string, { vi: (string | null)[]; en: (string | null)[] }> = {
  "2603.01234": { vi: ["Dự đoán năng lượng hình thành khi chỉ có dưới 5.000 cấu trúc", "Mạng tương đẳng, có tăng cường dữ liệu huấn luyện", "Dưới 5.000 cấu trúc; một tập giữ lại để kiểm tra", null], en: ["Predict formation energy with under 5,000 structures", "Equivariant network, with training-set augmentation", "Under 5,000 structures; a held-out split", null] },
  "2507.04411": { vi: ["Dự đoán độ bền vô cơ khi ít nhãn", "Mạng đồ thị có bước tiền huấn luyện, bỏ từng thành phần để so", "Vài nghìn cấu trúc có nhãn", null], en: ["Predict inorganic stability with few labels", "Graph network with a pretraining stage, ablating each part", "A few thousand labelled structures", null] },
  "2601.08832": { vi: ["Năng lượng hình thành của tinh thể vô cơ", "Truyền thông điệp tương đẳng", "Huấn luyện đủ và bản chỉ 3.000 cấu trúc", "MAE giảm 18% so với baseline, 7% với 3.000 cấu trúc"], en: ["Formation energy of inorganic crystals", "Equivariant message passing", "Full training set and a 3,000-structure subset", "MAE down 18% vs baseline, 7% at 3,000 structures"] },
  "2602.11975": { vi: ["Đạt độ chính xác hóa học khi chỉ có vài trăm nhãn", "Embedding nguyên tử tiền huấn luyện, gắn vào mạng đồ thị tinh thể", "Bộ cấu trúc không nhãn lớn; vài trăm mẫu có nhãn", "Đạt độ chính xác hóa học; công bố embedding cho 89 nguyên tố"], en: ["Reach chemical accuracy with a few hundred labels", "Pretrained atom embeddings in a crystal graph network", "Large unlabelled set; a few hundred labelled samples", "Chemical accuracy; embeddings released for 89 elements"] },
  "2405.09317": { vi: ["Ước lượng bất định khi dữ liệu ít", "So ensemble sâu với hồi quy evidential", "Năm benchmark tính chất tinh thể, nhiều cỡ", "Báo cả độ hiệu chuẩn lẫn độ chính xác"], en: ["Uncertainty estimates when data is scarce", "Deep ensembles vs evidential regression", "Five crystal property benchmarks of different sizes", "Reports calibration and accuracy"] },
  "2209.05471": { vi: ["Tổng quan mạng truyền thông điệp cho vật liệu", "Khảo sát, nhóm theo cách mã hóa hình học", "Số liệu đã công bố, xếp theo cỡ tập huấn luyện", "Bảng so sánh theo cỡ dữ liệu; không có thí nghiệm mới"], en: ["Overview of message passing networks for materials", "Survey, grouped by how geometry is encoded", "Published results, by training set size", "A comparison table by data size; no new experiments"] },
  "2108.07720": { vi: ["Nhãn năng lượng hình thành đắt", "Chuyển giao: đóng băng encoder, huấn luyện lại lớp đọc", "Mô hình huấn luyện trên tập lớn, chuyển sang tập đích nhỏ", null], en: ["Formation energy labels are expensive", "Transfer: freeze the encoder, retrain the readout", "Model trained on a large set, moved to small targets", null] },
  "2604.02210": { vi: ["Chuyển mô hình nguyên tử lớn sang tập dưới 1.000 cấu trúc", "So tinh chỉnh toàn bộ, adapter và linear probe", "Tập đích dưới 1.000 cấu trúc", null], en: ["Adapt large atomistic models to sets under 1,000 structures", "Full fine-tuning vs adapters vs linear probe", "Target sets under 1,000 structures", null] },
};
const FOLLOW = ["equivariant graph network small dataset", "contrastive pretraining crystal structures", "uncertainty calibration materials property prediction"];

const keyOf = (s: Sample) => (s.id ? `arxiv:${s.id}` : `doi:${s.doi}`);
const paperIdOf = (s: Sample) => `p-${s.id || s.doi!.replace(/\W+/g, "-")}`;
const sampleById = (pid: string) => SAMPLES.find((s) => paperIdOf(s) === pid);

// ---------------------------------------------------------------- store
interface Store {
  profile: ResearchProfile;
  asta: boolean;
  s2: boolean;
  entries: { sampleId: string; status: ReadStatus; reason: string; origin: ReadingEntry["origin"]; minutes: number; newThisWeek: boolean; addedAt: string; openedAt: string | null; readAt: string | null }[];
  removed: Set<string>;
  suggestions: Suggestion[];
  discoveryUntil: number;
  notes: Record<string, PaperNote>;
  qa: Record<string, PaperQA[]>;
  experiments: Experiment[];
  meetings: Meeting[];
  milestones: Milestone[];
  jobs: Map<string, { kind: "review" | "discovery"; req?: { query: string; year_min?: number; followups?: string[] }; polls: number; created: string }>;
  seq: number;
}

let store: Store | null = null;
const scenario = () => {
  try {
    return localStorage.getItem(SCENARIO_KEY) || "full";
  } catch {
    return "full";
  }
};
const savedSources = (): { asta: boolean; s2: boolean } => {
  try {
    const j = JSON.parse(localStorage.getItem(SOURCES_KEY) || "{}") as { asta?: boolean; s2?: boolean };
    return { asta: !!j.asta, s2: !!j.s2 };
  } catch {
    return { asta: false, s2: false };
  }
};
const saveSources = (s: Store) => {
  try {
    localStorage.setItem(SOURCES_KEY, JSON.stringify({ asta: s.asta, s2: s.s2 }));
  } catch {
    /* ignore */
  }
};

const TOPIC_VI = "Mạng nơ-ron đồ thị dự đoán năng lượng hình thành của vật liệu tinh thể khi chỉ có vài nghìn mẫu.";
const TOPIC_EN = "Graph neural networks that predict the formation energy of crystalline materials with only a few thousand samples.";
const KEYWORDS = ["graph neural network", "formation energy", "crystal structure", "small data", "uncertainty"];

function mkExperiment(id: string, daysAgo: number, title: string, status: Experiment["status"], result: string, extra: Partial<Experiment> = {}): Experiment {
  const d = addDays(-daysAgo);
  return {
    id, date: ymd(d), title, status, aim: "", setup: "", result, user_note: "", next: "", commit: null, seed: null, missing: [], photo_path: null, raw_text: result, structured: true,
    created_at: iso(d), updated_at: iso(d), ...extra,
  };
}

function seedStore(): Store {
  const sc = scenario();
  const src = savedSources();
  const empty = sc === "empty";
  const now = new Date();
  const profile: ResearchProfile = empty
    ? { title: "", question: "", keywords: [], advisor_name: "", asta_connected: src.asta, s2_connected: src.s2, updated_at: null }
    : { title: tr(TOPIC_VI, TOPIC_EN), question: tr(TOPIC_VI, TOPIC_EN), keywords: [...KEYWORDS], advisor_name: "", asta_connected: src.asta, s2_connected: src.s2, updated_at: iso(addDays(-20)) };
  const at = (n: number, h: number, m = 0) => {
    const d = addDays(n);
    d.setHours(h, m, 0, 0);
    return d;
  };
  const meetingAt = at(4, 14);
  const entries: Store["entries"] = empty
    ? []
    : [
        { sampleId: "2601.08832", status: "reading", reason: "Dùng cùng bộ dữ liệu với chương 3 của bạn.", origin: "suggestion", minutes: 25, newThisWeek: false, addedAt: iso(addDays(-8)), openedAt: iso(addDays(-1)), readAt: null },
        { sampleId: "2511.03321", status: "new", reason: "Trích dẫn paper bạn đọc tuần trước, đúng từ khóa “uncertainty”.", origin: "suggestion", minutes: 0, newThisWeek: true, addedAt: iso(addDays(-2)), openedAt: null, readAt: null },
        { sampleId: "2604.02210", status: "read", reason: "Ghi chú của bạn đã lưu.", origin: "search", minutes: 40, newThisWeek: false, addedAt: iso(addDays(-12)), openedAt: iso(addDays(-9)), readAt: iso(addDays(-8)) },
      ];
  const sug = (id: string, sampleId: string, reason: string, query: string): Suggestion => ({
    id, week_of: ymd(addDays(-((now.getDay() + 6) % 7))), paper: card(SAMPLES.find((s) => s.id === sampleId)!, "arxiv", false), reason, query, featured: true, status: "pending", created_at: iso(addDays(-1)),
  });
  const s: Store = {
    profile,
    asta: src.asta,
    s2: src.s2,
    entries,
    removed: new Set(),
    suggestions: empty ? [] : [sug("sg-1", "2603.05512", "Khớp từ khóa small data: so sánh các phương pháp trên vài nghìn mẫu, giống thiết lập của bạn.", "small data materials"), sug("sg-2", "2605.01877", "Một cách khác để làm việc với ít dữ liệu, nên lướt qua.", "small data materials")],
    discoveryUntil: sc === "searching" ? Date.now() + 3_600_000 : 0,
    notes: empty ? {} : { "p-2604.02210": { my_summary: "Bài so sánh ba cách chuyển mô hình lớn sang tập nhỏ: tinh chỉnh toàn bộ, adapter và linear probe.", summary_updated_at: iso(addDays(-8)), feedback: null } },
    qa: {},
    experiments: empty
      ? []
      : [
          mkExperiment("EXP-" + ymd(addDays(-2)) + "-a", 2, tr("Baseline mạng đồ thị trên bộ 3.200 mẫu", "Baseline graph network on 3,200 samples"), "done",
            tr("MAE 0,061 eV/nguyên tử, seed 3.", "MAE 0.061 eV/atom, seed 3."), { seed: "3", missing: ["commit"], user_note: tr("Gần số của paper dù dữ liệu ít hơn nhiều.", "Close to the paper's number, with far less data.") }),
          mkExperiment("EXP-" + ymd(addDays(-4)) + "-a", 4, tr("Thêm nhiễu vào vị trí nguyên tử", "Add noise to atom positions"), "failed",
            tr("Loss phân kỳ sau epoch 12.", "Loss diverged after epoch 12."), { user_note: tr("Learning rate 3e-3 có thể quá cao.", "Learning rate 3e-3 may be too high."), next: tr("Thử 1e-3.", "Try 1e-3."), commit: "a3f9c21", seed: "3" }),
        ],
    meetings: empty
      ? []
      : [
          {
            id: "mt-1", at: iso(meetingAt), title: tr("Họp GVHD", "Advisor meeting"), status: "scheduled",
            agenda: { promised: [{ text: tr("Chạy lại baseline trên bộ dữ liệu B", "Rerun the baseline on dataset B"), done: true }, { text: tr("Viết xong mục 3.2 (mới được nửa)", "Finish section 3.2 (about half done)"), done: false }], new_results: "", open_questions: "", drafted_at: iso(addDays(-1)), edited_at: null },
            notes_md: null, action_items: [], created_at: iso(addDays(-6)),
          },
        ],
    milestones: empty
      ? []
      : [
          ms("ms-0", tr("Xong chương 2, tổng quan tài liệu", "Chapter 2, literature review, done"), -23, "other", true, true, null, null, 0),
          ms("ms-1", tr("Nộp full paper hội nghị", "Submit the conference full paper"), 9, "submission", true, true, "18:59", "23:59 AoE 15/11", 2),
          ms("ms-2", tr("Bản nháp chương 3", "Draft of chapter 3"), 38, "other", true, true, null, null, 0),
          ms("ms-3", tr("Gửi GVHD toàn bộ bản nháp", "Send the whole draft to your advisor"), 113, "other", true, true, null, null, 0),
          ms("ms-4", tr("Báo cáo tiến độ cho khoa", "Progress report to the department"), 24, "other", false, false, null, null, 0),
        ],
    jobs: new Map(),
    seq: 10,
  };
  return s;
}

function ms(id: string, title: string, inDays: number, kind: Milestone["kind"], thesis: boolean, confirmed: boolean, time: string | null, original: string | null, sessions: number, done = false): Milestone {
  const d = addDays(inDays);
  return { id, title, due_date: ymd(d), due_time: time, original_text: original, confirmed, kind, thesis, done: done || inDays < 0, days_left: inDays, planned_sessions: sessions, created_at: iso(addDays(-30)) };
}

const S = (): Store => (store ??= seedStore());

/** Tests and the visual check start from a clean mock: `scenario` "full" | "empty" | "searching". */
export function resetMockResearch(sc?: "full" | "empty" | "searching") {
  try {
    if (sc) localStorage.setItem(SCENARIO_KEY, sc);
    else localStorage.removeItem(SCENARIO_KEY);
  } catch {
    /* ignore */
  }
  store = null;
}
/** Polling rounds a mock job needs before it is done (the app polls every 1.5 s). */
export const mockJobPolls = { review: 2, discovery: 1 };

// ---------------------------------------------------------------- cards
function card(s: Sample, source: "asta" | "s2" | "arxiv", inList: boolean): PaperCard {
  const arxiv = source === "arxiv";
  return {
    key: keyOf(s), source, title: s.t, authors: s.au, year: s.y, venue: arxiv ? null : s.venue, arxiv_id: s.id || null, doi: s.doi ?? null, s2_id: source === "arxiv" ? null : `s2-${s.id || "x"}`,
    url: s.id ? `https://arxiv.org/abs/${s.id}` : `https://doi.org/${s.doi}`, excerpt: s.abs.length > 240 ? s.abs.slice(0, 237).trimEnd() + "…" : s.abs,
    tldr: source === "s2" ? (s.tldr ?? null) : null, snippet: source === "asta" ? (s.snip ?? null) : null, citation_count: arxiv ? null : s.cites, has_pdf: s.pdf,
    in_reading_list: inList, paper_id: inList ? paperIdOf(s) : null,
  };
}
const inList = (s: Sample) => S().entries.some((e) => e.sampleId === s.id && !S().removed.has(e.sampleId));
const sampleCard = (s: Sample, source: "asta" | "s2" | "arxiv" = "arxiv") => card(s, source, inList(s));

function entryOf(e: Store["entries"][number]): ReadingEntry {
  const s = SAMPLES.find((x) => x.id === e.sampleId)!;
  return { id: paperIdOf(s), paper: sampleCard(s), status: e.status, reason: e.reason, origin: e.origin, new_this_week: e.newThisWeek, minutes_spent: e.minutes, added_at: e.addedAt, opened_at: e.openedAt, read_at: e.readAt };
}
const activeEntries = () => S().entries.filter((e) => !S().removed.has(e.sampleId));
const entryById = (id: string) => {
  const s = sampleById(id);
  const e = s && activeEntries().find((x) => x.sampleId === s.id);
  if (!s || !e) throw new ResearchError(404, "paper_not_found");
  return { s, e };
};
const readingList = () => {
  const items = activeEntries().map(entryOf);
  return { limit: 5, active_count: items.filter((i) => i.status !== "read").length, items };
};

// ---------------------------------------------------------------- derived views
const authorsLine = (s: Sample) => `${s.au.join(", ")} · ${s.y}`;
const nextMilestones = () => S().milestones.filter((m) => !m.done);

function statusLine(): LiveLine {
  const st = S();
  if (!st.profile.title) return { line_vi: "Đặt đề tài của bạn", line_en: "Set your topic" };
  const when = (n: number): [string, string] => (n === 0 ? ["hôm nay", "today"] : n === 1 ? ["ngày mai", "tomorrow"] : [`còn ${n} ngày`, `in ${n} days`]);
  const open = nextMilestones().filter((m) => m.confirmed && m.days_left >= 0 && m.days_left <= 30).sort((a, b) => a.days_left - b.days_left)[0];
  const parts: [string, string][] = [];
  if (open) {
    const [w_vi, w_en] = when(open.days_left);
    parts.push(open.kind === "submission" ? [`Hạn nộp bài ${w_vi}`, `Paper due ${w_en}`] : [`Hạn gần nhất ${w_vi}`, `Next deadline ${w_en}`]);
  }
  const k = st.suggestions.filter((x) => x.status === "pending" && x.featured).length + activeEntries().filter((e) => e.status === "new" && e.newThisWeek).length;
  if (k > 0) parts.push([`${k} paper mới`, `${k} new papers`]);
  if (!parts.length) return { line_vi: "Chưa có gì mới", line_en: "Nothing new" };
  return { line_vi: parts.map((p) => p[0]).join(", "), line_en: parts.map((p) => p[1]).join(", ") };
}

/** The hub line for the "Nghiên cứu" tile (`GET /today` hub.research), for the mock planner. */
export const mockResearchLine = (): LiveLine => statusLine();

/** The research goal (`Goal` with source "research"), for the mock planner's GET /goals. */
export function mockResearchGoal() {
  const st = S();
  const thesis = st.milestones.filter((m) => m.thesis);
  if (!thesis.length) return null;
  const done = thesis.filter((m) => m.done).length;
  const last = [...thesis].sort((a, b) => (a.due_date < b.due_date ? 1 : -1))[0];
  return {
    id: "res-thesis", title: st.profile.title, kind: "student" as const, deadline: last.due_date, progress_pct: Math.round((done / thesis.length) * 100), status: "on_track" as const,
    line_vi: `Xong ${done}/${thesis.length} mốc luận văn.`, line_en: `${done} of ${thesis.length} thesis milestones done.`, course_ids: [] as string[], courses: [] as { id: string; title: string; subject: string }[],
    required_min_per_day: null, created_at: iso(addDays(-30)), source: "research" as const, milestones: thesis,
  };
}

const discoveryStatus = (): DiscoveryStatus => ({ state: S().discoveryUntil > Date.now() ? "running" : "idle", last_run_at: iso(addDays(-1)), last_status: "papers_found", next_run_at: iso(addDays(3)) });

function upcoming(): UpcomingItem[] {
  const st = S();
  const out: UpcomingItem[] = [];
  for (const m of st.meetings.filter((x) => x.status === "scheduled")) {
    const d = new Date(m.at);
    out.push({ kind: "meeting", id: m.id, title: m.title, date: ymd(d), time: `${pad(d.getHours())}:${pad(d.getMinutes())}`, days_left: daysUntil(ymd(d)), confirmed: true, agenda_ready: !!m.agenda, original_text: null, planned_sessions: 0 });
  }
  for (const m of nextMilestones().filter((x) => x.days_left <= 30))
    out.push({ kind: "deadline", id: m.id, title: m.title, date: m.due_date, time: m.due_time, days_left: m.days_left, confirmed: m.confirmed, agenda_ready: null, original_text: m.original_text, planned_sessions: m.planned_sessions });
  return out.sort((a, b) => (a.date < b.date ? -1 : 1)).slice(0, 6);
}

function overview(): ResearchOverview {
  const st = S();
  const list = readingList();
  const reading = list.items.filter((i) => i.status === "reading").sort((a, b) => ((a.opened_at ?? "") < (b.opened_at ?? "") ? 1 : -1))[0] ?? list.items.find((i) => i.status === "new");
  const s = reading && sampleById(reading.id);
  const soon = nextMilestones().find((m) => m.kind === "submission" && m.days_left <= 14 && m.days_left >= 0);
  return {
    profile: { ...st.profile, asta_connected: st.asta, s2_connected: st.s2 },
    status_line: statusLine(),
    hero: reading && s ? { paper_id: reading.id, title: s.t, authors_line: authorsLine(s), status: reading.status, minutes_spent: reading.minutes_spent, reason: soon ? tr(`Bài full paper của bạn còn ${soon.days_left} ngày nữa đến hạn, và mục 3 của bài so sánh với paper này.`, `Your full paper is due in ${soon.days_left} days, and section 3 of it compares against this one.`) : reading.reason, deep_link: `/nghien-cuu/paper/${reading.id}` } : null,
    upcoming: upcoming(),
    reading_list: list,
    suggestions: st.suggestions.filter((x) => x.status === "pending"),
    milestones: st.milestones.filter((m) => m.thesis).sort((a, b) => (a.due_date < b.due_date ? -1 : 1)),
    goal_id: st.milestones.some((m) => m.thesis) ? "res-thesis" : null,
    experiments: st.experiments.slice(0, 5),
    discovery: discoveryStatus(),
  };
}

// ---------------------------------------------------------------- search and review
const rank = { asta: 0, s2: 1, arxiv: 2 } as const;
function runSearch(q: string, yearMin?: number, pdf?: boolean, page = 1, depth?: SearchDepth) {
  if (!q.trim()) throw new ResearchError(422, "empty_query");
  const keys = S();
  const st = { asta: keys.asta && (!depth || depth === "deep"), s2: keys.s2 && depth !== "quick" };
  const stat = (has: boolean, used: boolean) => (used ? ("ok" as const) : has ? ("skipped" as const) : ("not_connected" as const));
  const rows: PaperCard[] = [];
  for (const s of SEARCHABLE) {
    const source: "asta" | "s2" | "arxiv" | null = st.asta && s.snip ? "asta" : st.s2 ? "s2" : s.s2only ? null : "arxiv";
    if (!source) continue;
    if (yearMin && s.y < yearMin) continue;
    if (pdf && !s.pdf) continue;
    rows.push(sampleCard(s, source));
  }
  rows.sort((a, b) => rank[a.source] - rank[b.source]);
  const size = 10;
  const slice = rows.slice((page - 1) * size, page * size);
  return {
    query: q, page, page_size: size, has_more: rows.length > page * size, results: slice,
    sources: [
      { source: "asta" as const, status: stat(keys.asta, st.asta) },
      { source: "s2" as const, status: stat(keys.s2, st.s2) },
      { source: "arxiv" as const, status: "ok" as const },
    ],
  };
}

function reviewResult(query: string, yearMin?: number): ReviewResult {
  const found = SEARCHABLE.filter((s) => s.id && (!yearMin || s.y >= yearMin)).slice(0, 8);
  const L = en() ? "en" : "vi";
  const matrix: ReviewRow[] = found.map((s) => {
    const c = REV[s.id]?.[L] ?? [null, null, null, null];
    return { key: keyOf(s), problem: c[0], method: c[1], data: c[2], result: c[3] };
  });
  return {
    query, papers: found.map((s) => sampleCard(s, "arxiv")), matrix, followups: FOLLOW, searches: [{ query, count: found.length }, ...FOLLOW.slice(0, 2).map((f) => ({ query: f, count: 3 }))],
    coverage: `${found.length}`, caveat_vi: "Chỉ dựa trên abstract, chưa đủ để kết luận. Đọc toàn văn trước khi trích dẫn.", caveat_en: "Based on abstracts only, not enough to draw a conclusion. Read the full text before citing.",
  };
}

// ---------------------------------------------------------------- paper pages
const THREAD_FEEDBACK = () => ({
  rows: [
    { kind: "right" as const, text: tr("Một mạng truyền thông điệp bất biến theo phép quay để dự đoán năng lượng hình thành, có thêm phần độ bất định.", "An equivariant message passing network for formation energy, with an uncertainty part.") },
    { kind: "inaccurate" as const, text: tr("Bạn viết hơn 18%. Bài đạt 18% trên toàn bộ dữ liệu, còn với 3.000 cấu trúc chỉ là 7%. Bạn muốn nói trường hợp nào?", "You wrote 18% better. The paper gets 18% on the full set but only 7% with 3,000 structures. Which one do you mean?") },
    { kind: "missing" as const, text: tr("Mô hình giả định cấu trúc đã được tối ưu (mục 2.1). Giả định này có ảnh hưởng tới cách bạn so sánh không?", "The model assumes relaxed structures (section 2.1). Does that affect how you compare against it?") },
  ],
  for_thesis: tr("họ dùng 90.000 mẫu, bạn có 3.200. Khoảng cách này có thể nên nằm trong mục 3.2 của bạn.", "they use 90,000 samples and you have 3,200. This gap may belong in your section 3.2."),
  created_at: iso(new Date()),
});

function relatedFor(s: Sample): RelatedPapers {
  const st = S();
  if (!st.s2 && !st.asta) return { available: false, reason: "no_source_key", sources: [], partial: false, citing: { count: 0, items: [] }, cited: { count: 0, items: [] } };
  const by = (ids: string[], src: "s2" | "asta") => ids.map((id) => sampleCard(SAMPLES.find((x) => x.id === id)!, src));
  return {
    available: true, reason: null, sources: [st.s2 ? "s2" : "asta"], partial: false,
    citing: { count: s.cites, items: by(["2511.03321", "2602.11975", "2603.05512"], st.s2 ? "s2" : "asta") },
    cited: { count: 38, items: by(["2209.05471", "2108.07720", "2405.09317"], st.s2 ? "s2" : "asta") },
  };
}

function answerFor(pid: string, question: string): PaperQA {
  const s = sampleById(pid)!;
  const base = { id: `qa-${S().seq++}`, question, created_at: iso(new Date()) };
  if (!s.pdf) return { ...base, answer: tr("Mình chưa có chữ của bài này. Thêm PDF hoặc key Asta để mình đọc được.", "I do not have the text of this paper yet. Add the PDF or an Asta key so I can read it."), found: false, not_found_reason: "no_fulltext", citations: [], course_hint: null };
  if (/seed|lệch chuẩn|độ lệch|std|standard deviation/i.test(question))
    return { ...base, answer: tr("Mình không tìm thấy đoạn nào nói về điều này trong paper. Có thể nó nằm ở phụ lục, phần mình chưa đọc được.", "I could not find a passage about this in the paper. It may be in the appendix, which I cannot see."), found: false, not_found_reason: "no_passage", citations: [], course_hint: null };
  if (/bất định|uncertain|ensemble/i.test(question))
    return {
      ...base, answer: tr("Họ gộp 5 mô hình cùng kiến trúc rồi hiệu chỉnh độ lệch chuẩn bằng một hệ số học trên tập kiểm định.", "They combine 5 models of the same architecture and recalibrate the standard deviation with one scale factor learned on the validation set."), found: true, not_found_reason: null,
      citations: [{ section: tr("Mục 5, Độ bất định", "Section 5, Uncertainty"), snippet: "An ensemble of five models is recalibrated on the validation split with a single scale factor.", url: `https://arxiv.org/pdf/${s.id}#page=7` }],
      course_hint: { course_id: "bayes", lesson_id: null, title: tr("Xác suất thống kê: Suy luận Bayes", "Probability and Statistics: Bayesian inference"), deep_link: "/khoa-hoc/bayes" },
    };
  return {
    ...base, answer: tr("Huấn luyện trên 90.211 cấu trúc từ một cơ sở dữ liệu vật liệu công khai, chia 80/10/10 theo công thức hóa học, nên cùng một hợp chất không nằm vừa ở train vừa ở test.", "Trained on 90,211 structures from a public materials database, split 80/10/10 by composition, so the same compound never sits in both train and test."), found: true, not_found_reason: null,
    citations: [{ section: tr("Mục 4.1, Dữ liệu", "Section 4.1, Data"), snippet: "We split by composition so that polymorphs of the same compound never appear on both sides of the split.", url: `https://arxiv.org/pdf/${s.id}#page=5` }], course_hint: null,
  };
}

/** The mock of POST /research/papers/{id}/ask: status, qa, done, with short pauses. */
export async function mockPaperAsk(paperId: string, input: PaperAskBody, onEvent: (e: PaperAskEvent) => void, signal?: AbortSignal): Promise<void> {
  entryById(paperId);
  const wait = (ms: number) =>
    new Promise<void>((res, rej) => {
      const t = setTimeout(res, ms);
      signal?.addEventListener("abort", () => (clearTimeout(t), rej(new DOMException("aborted", "AbortError"))), { once: true });
    });
  onEvent({ event: "status", data: { stage: "searching" } });
  await wait(220);
  onEvent({ event: "status", data: { stage: "reading" } });
  await wait(260);
  const text = "text" in input ? input.text : tr("(giọng nói)", "(voice)");
  const qa = answerFor(paperId, text);
  (S().qa[paperId] ??= []).push(qa);
  onEvent({ event: "qa", data: qa });
  onEvent({ event: "done", data: { qa_id: qa.id } });
}

// ---------------------------------------------------------------- parsing (the server's job; a small version here)
function parseWhen(text: string): { date: string; time: string | null; aoe: boolean; original: string | null } | null {
  const m = /(\d{1,2})\/(\d{1,2})(?:\/(\d{4}))?/.exec(text);
  if (!m) return null;
  const now = new Date();
  let year = m[3] ? Number(m[3]) : now.getFullYear();
  let d = new Date(year, Number(m[2]) - 1, Number(m[1]));
  if (!m[3] && d < new Date(now.getFullYear(), now.getMonth(), now.getDate())) {
    year += 1;
    d = new Date(year, Number(m[2]) - 1, Number(m[1]));
  }
  const t = /(\d{1,2}):(\d{2})/.exec(text);
  const aoe = /aoe/i.test(text);
  let time: string | null = null;
  let original: string | null = null;
  if (t) {
    time = `${pad(Number(t[1]))}:${t[2]}`;
    if (aoe) {
      original = `${time} AoE ${pad(Number(m[1]))}/${pad(Number(m[2]))}`;
      const vn = new Date(d.getFullYear(), d.getMonth(), d.getDate(), Number(t[1]) + 19, Number(t[2]));
      d = new Date(vn.getFullYear(), vn.getMonth(), vn.getDate());
      time = `${pad(vn.getHours())}:${pad(vn.getMinutes())}`;
    }
  }
  return { date: ymd(d), time, aoe, original };
}

// ---------------------------------------------------------------- the api
const flushJob = (id: string): ResearchJob => {
  const st = S();
  const j = st.jobs.get(id);
  if (!j) throw new ResearchError(404, "job_not_found");
  j.polls += 1;
  const need = mockJobPolls[j.kind];
  const base = { id, kind: j.kind, created_at: j.created, finished_at: null as string | null };
  if (j.polls <= need) {
    const progress: JobProgress = j.polls === 1 ? { stage: "searching", total: 8, done: 0 } : { stage: "reading", total: 8, done: Math.min(7, j.polls * 3) };
    return { ...base, status: "running", progress: j.kind === "review" ? progress : null, result: null, error: null };
  }
  if (j.kind === "discovery") return { ...base, status: "done", progress: null, result: { status: "papers_found", queries: ["small data materials"], new_suggestions: st.suggestions.filter((x) => x.status === "pending").length }, error: null, finished_at: iso(new Date()) };
  return { ...base, status: "done", progress: null, result: reviewResult(j.req!.query, j.req!.year_min), error: null, finished_at: iso(new Date()) };
};

const findMeeting = (id: string) => {
  const m = S().meetings.find((x) => x.id === id);
  if (!m) throw new ResearchError(404, "meeting_not_found");
  return m;
};
const newJob = (kind: "review" | "discovery", req?: { query: string; year_min?: number; followups?: string[] }) => {
  const st = S();
  const id = `job-${st.seq++}`;
  st.jobs.set(id, { kind, req, polls: 0, created: iso(new Date()) });
  return { job_id: id, status: "running" as const };
};

export const mockResearchApi: ResearchApi = {
  async overview() {
    await delay();
    const st = S();
    // a topic set a moment ago: Mentor "looks" for a few seconds, then the first suggestions appear
    const o = overview();
    if (st.discoveryUntil && st.discoveryUntil <= Date.now() && st.profile.title && st.suggestions.length === 0 && st.entries.length === 0) {
      const mk = (sid: string, reason: string): Suggestion => ({ id: `sg-${st.seq++}`, week_of: ymd(new Date()), paper: card(SAMPLES.find((x) => x.id === sid)!, "arxiv", false), reason, query: "first", featured: true, status: "pending", created_at: iso(new Date()) });
      st.suggestions = [mk("2603.01234", tr("Khớp từ khóa formation energy.", "Matches the keyword formation energy.")), mk("2601.08832", tr("Khớp từ khóa graph neural network.", "Matches the keyword graph neural network.")), mk("2511.03321", tr("Khớp từ khóa uncertainty.", "Matches the keyword uncertainty."))];
      return overview();
    }
    return o;
  },
  async getProfile() {
    await delay();
    return { ...S().profile, asta_connected: S().asta, s2_connected: S().s2 };
  },
  async putProfile(_t, body) {
    await delay();
    const st = S();
    if (body.title !== undefined) {
      if (!body.title.trim()) throw new ResearchError(422, "empty_title");
      const title = body.title.trim();
      st.profile.title = title;
      st.profile.question = title.endsWith(".") ? title : title + ".";
      st.profile.keywords = title.split(/\s+/).filter((w) => w.length > 3).slice(0, 5);
      if (!st.profile.keywords.length) st.profile.keywords = [title.slice(0, 20)];
      st.discoveryUntil = Date.now() + 3500;
    }
    if (body.keywords !== undefined) {
      if (body.keywords.length < 1 || body.keywords.length > 8) throw new ResearchError(422, "bad_keywords");
      st.profile.keywords = body.keywords;
    }
    if (body.question !== undefined) st.profile.question = body.question;
    if (body.advisor_name !== undefined) st.profile.advisor_name = body.advisor_name;
    st.profile.updated_at = iso(new Date());
    return { ...st.profile, asta_connected: st.asta, s2_connected: st.s2 };
  },
  async sourceKeys() {
    await delay();
    return { asta_connected: S().asta, s2_connected: S().s2 };
  },
  async putSourceKey(_t, source: SourceName, key) {
    await delay(700);
    if (/bad/i.test(key)) throw new ResearchError(422, "invalid_key");
    const st = S();
    if (source === "asta") st.asta = true;
    else st.s2 = true;
    saveSources(st);
    return { asta_connected: st.asta, s2_connected: st.s2 };
  },
  async deleteSourceKey(_t, source: SourceName) {
    await delay();
    const st = S();
    if (source === "asta") st.asta = false;
    else st.s2 = false;
    saveSources(st);
    return { asta_connected: st.asta, s2_connected: st.s2 };
  },
  async search(_t, p) {
    await delay(220);
    return runSearch(p.q, p.year_min, p.pdf, p.page, p.depth);
  },
  async related(_t, id) {
    await delay();
    return relatedFor(entryById(id).s);
  },
  async startReview(_t, body) {
    await delay();
    return newJob("review", body);
  },
  async getJob(_t, id) {
    await delay(60);
    return flushJob(id);
  },
  async startDiscovery() {
    await delay();
    if (!S().profile.title) throw new ResearchError(422, "empty_title");
    return newJob("discovery");
  },
  async suggestions() {
    await delay();
    return { week_of: S().suggestions[0]?.week_of ?? null, items: S().suggestions.filter((x) => x.status === "pending"), discovery: discoveryStatus() };
  },
  async acceptSuggestion(_t, id) {
    await delay();
    const st = S();
    const sg = st.suggestions.find((x) => x.id === id && x.status === "pending");
    if (!sg) throw new ResearchError(404, "suggestion_not_found");
    if (readingList().active_count >= 5) throw new ResearchError(409, "reading_list_full");
    sg.status = "accepted";
    const s = SAMPLES.find((x) => x.id === sg.paper.arxiv_id)!;
    st.removed.delete(s.id);
    const e = { sampleId: s.id, status: "new" as const, reason: sg.reason, origin: "suggestion" as const, minutes: 0, newThisWeek: true, addedAt: iso(new Date()), openedAt: null, readAt: null };
    st.entries = st.entries.filter((x) => x.sampleId !== s.id).concat(e);
    return entryOf(e);
  },
  async dismissSuggestion(_t, id) {
    await delay();
    const sg = S().suggestions.find((x) => x.id === id && x.status === "pending");
    if (!sg) throw new ResearchError(404, "suggestion_not_found");
    sg.status = "dismissed";
  },
  async readingList() {
    await delay();
    return readingList();
  },
  async addPaper(_t, body) {
    await delay();
    const st = S();
    let s: Sample | undefined;
    if (body.card) s = SAMPLES.find((x) => keyOf(x) === body.card!.key);
    else if (body.link) {
      const link = body.link.trim();
      s = SAMPLES.find((x) => (x.id && link.includes(x.id)) || (x.doi && link.toLowerCase().includes(x.doi.toLowerCase())));
      if (!s && !/^(https?:\/\/|10\.\d{4,})/i.test(link)) throw new ResearchError(422, "bad_paper_ref");
      if (!s) throw new ResearchError(422, "paper_unresolved");
    } else if (body.upload_path) s = SAMPLES[10];
    if (!s) throw new ResearchError(422, "bad_paper_ref");
    const had = activeEntries().find((e) => e.sampleId === s!.id);
    if (had) return entryOf(had);
    if (readingList().active_count >= 5) throw new ResearchError(409, "reading_list_full");
    st.removed.delete(s.id);
    const e = { sampleId: s.id, status: "new" as const, reason: body.reason ?? tr("Bạn tự thêm vào danh sách.", "You added this one yourself."), origin: (body.card ? "search" : body.link ? "link" : "pdf") as ReadingEntry["origin"], minutes: 0, newThisWeek: true, addedAt: iso(new Date()), openedAt: null, readAt: null };
    st.entries = st.entries.filter((x) => x.sampleId !== s!.id).concat(e);
    if (!st.profile.title) {
      st.profile.title = s.t;
      st.profile.keywords = s.t.split(/\s+/).filter((w) => w.length > 4).slice(0, 4);
    }
    return entryOf(e);
  },
  async removePaper(_t, id) {
    await delay();
    const { s } = entryById(id);
    S().removed.add(s.id);
  },
  async setStatus(_t, id, status) {
    await delay();
    const { e } = entryById(id);
    if (e.status === "read" && status !== "read" && readingList().active_count >= 5) throw new ResearchError(409, "reading_list_full");
    e.status = status;
    e.readAt = status === "read" ? iso(new Date()) : null;
    if (status === "reading") e.openedAt = iso(new Date());
    return entryOf(e);
  },
  async paper(_t, id) {
    await delay();
    const { s, e } = entryById(id);
    if (e.status === "new") {
      e.status = "reading";
      e.openedAt = iso(new Date());
    }
    const note = S().notes[id] ?? { my_summary: null, summary_updated_at: null, feedback: null };
    return {
      entry: entryOf(e), abstract: s.abs, pdf_url: s.pdf ? `https://arxiv.org/pdf/${s.id}` : null, fulltext: s.pdf ? "ready" : "none", thesis_tag: s.id === "2601.08832" ? tr("Mục 3 của bạn", "Section 3 of yours") : null,
      note, qa_count: (S().qa[id] ?? []).length,
    };
  },
  async putSummary(_t, id, text) {
    await delay();
    entryById(id);
    if (text.trim().length < 20) throw new ResearchError(422, "summary_too_short");
    const prev = S().notes[id];
    const note: PaperNote = { my_summary: text.trim(), summary_updated_at: iso(new Date()), feedback: prev && prev.my_summary === text.trim() ? prev.feedback : null };
    S().notes[id] = note;
    return note;
  },
  async feedback(_t, id) {
    await delay(500);
    entryById(id);
    const note = S().notes[id];
    if (!note?.my_summary) throw new ResearchError(409, "summary_required");
    if (note.feedback) return note.feedback;
    const fb: PaperFeedback = THREAD_FEEDBACK();
    note.feedback = fb;
    return fb;
  },
  async qa(_t, id) {
    await delay();
    entryById(id);
    return S().qa[id] ?? [];
  },
  async experiments() {
    await delay();
    return { items: S().experiments, next_before: null };
  },
  async createExperiment(_t, body) {
    await delay(500);
    const st = S();
    const today = ymd(new Date());
    const n = st.experiments.filter((x) => x.id.startsWith(`EXP-${today}`)).length;
    const text = body.text.trim();
    const commit = /commit\s+([0-9a-f]{6,40})/i.exec(text)?.[1] ?? null;
    const seed = /seed\s*[:=]?\s*(\d+)/i.exec(text)?.[1] ?? null;
    const failed = /lỗi|thất bại|phân kỳ|diverg|fail|crash/i.test(text);
    const x: Experiment = {
      id: `EXP-${today}-${String.fromCharCode(97 + (n % 26))}`, date: today, title: text.length > 60 ? text.slice(0, 57).trimEnd() + "…" : text, status: failed ? "failed" : "done", aim: "", setup: "", result: text, user_note: "", next: "",
      commit, seed, missing: [...(commit ? [] : (["commit"] as const)), ...(seed ? [] : (["seed"] as const))], photo_path: body.photo_path ?? null, raw_text: text, structured: true, created_at: iso(new Date()), updated_at: iso(new Date()),
    };
    st.experiments.unshift(x);
    return x;
  },
  async patchExperiment(_t, id, body) {
    await delay();
    const x = S().experiments.find((e) => e.id === id);
    if (!x) throw new ResearchError(404, "experiment_not_found");
    Object.assign(x, body);
    x.missing = x.missing.filter((m) => !(m === "commit" && body.commit) && !(m === "seed" && body.seed));
    return x;
  },
  async upload(_t, file) {
    await delay(200);
    return { path: `inbox/mock-${S().seq++}`, mime_type: file.type || "application/octet-stream" };
  },
  async meetings(_t, status = "scheduled") {
    await delay();
    return S().meetings.filter((m) => status === "all" || (status === "scheduled" ? m.status === "scheduled" : m.status === "done"));
  },
  async nextMeeting() {
    await delay();
    return S().meetings.find((m) => m.status === "scheduled") ?? null;
  },
  async createMeeting(_t, body) {
    await delay();
    const st = S();
    let at: Date;
    if (body.at) at = new Date(body.at);
    else {
      const w = body.text ? parseWhen(body.text) : null;
      if (!w) throw new ResearchError(422, "meeting_unparsed");
      at = new Date(`${w.date}T${w.time ?? "09:00"}:00`);
    }
    const m: Meeting = { id: `mt-${st.seq++}`, at: iso(at), title: body.title ?? tr("Họp GVHD", "Advisor meeting"), status: "scheduled", agenda: null, notes_md: null, action_items: [], created_at: iso(new Date()) };
    st.meetings.push(m);
    st.meetings.sort((a, b) => (a.at < b.at ? -1 : 1));
    return m;
  },
  async putAgenda(_t, id, body) {
    await delay();
    const m = findMeeting(id);
    const a: Agenda = m.agenda ?? { promised: [], new_results: "", open_questions: "", drafted_at: null, edited_at: null };
    if (body.new_results !== undefined) a.new_results = body.new_results;
    if (body.open_questions !== undefined) a.open_questions = body.open_questions;
    a.edited_at = iso(new Date());
    m.agenda = a;
    return m;
  },
  async draftAgenda(_t, id) {
    await delay(400);
    const m = findMeeting(id);
    m.agenda = m.agenda ?? { promised: [], new_results: "", open_questions: "", drafted_at: null, edited_at: null };
    m.agenda.drafted_at = iso(new Date());
    return m;
  },
  async putNotes(_t, id, notes) {
    await delay();
    const m = findMeeting(id);
    m.status = "done";
    m.notes_md = notes;
    const lines = notes.split(/\n+/).map((l) => l.replace(/^[-*\d.)\s]+/, "").trim()).filter(Boolean);
    m.action_items = lines.map((text, i): ActionItem => {
      const w = /trước (?:thứ )?(\w+)|(\d{1,2}\/\d{1,2})/i.exec(text);
      const date = w?.[2] ? parseWhen(w[2])?.date ?? null : null;
      return { id: `ai-${m.id}-${i}`, text, due_date: date, done: false, in_plan: !!date };
    });
    return m;
  },
  async patchAction(_t, mid, aid, body) {
    await delay();
    const m = findMeeting(mid);
    const a = m.action_items.find((x) => x.id === aid);
    if (!a) throw new ResearchError(404, "action_not_found");
    Object.assign(a, body);
    return m;
  },
  async deadlines(_t, includeDone) {
    await delay();
    return S().milestones.filter((m) => includeDone || !m.done);
  },
  async createDeadline(_t, body) {
    await delay(300);
    const st = S();
    let title = body.title ?? "";
    let date = body.due_date ?? null;
    let time = body.due_time ?? null;
    let original: string | null = null;
    if (body.text !== undefined) {
      const w = parseWhen(body.text);
      if (!w) throw new ResearchError(422, "deadline_unparsed");
      date = w.date;
      time = w.time;
      original = w.original;
      title = body.text.replace(/\d{1,2}:\d{2}/g, "").replace(/aoe/gi, "").replace(/\d{1,2}\/\d{1,2}(\/\d{4})?/g, "").replace(/[,]/g, " ").replace(/\s+/g, " ").trim();
      title = title ? title[0].toUpperCase() + title.slice(1) : tr("Hạn mới", "New deadline");
    }
    if (!date) throw new ResearchError(422, "deadline_unparsed");
    const days = daysUntil(date);
    const m: Milestone = { id: `ms-${st.seq++}`, title, due_date: date, due_time: time, original_text: original, confirmed: !!time, kind: body.kind ?? (/nộp|submi/i.test(title) ? "submission" : "other"), thesis: !!body.thesis, done: false, days_left: days, planned_sessions: time && days <= 14 ? 2 : 0, created_at: iso(new Date()) };
    st.milestones.push(m);
    return m;
  },
  async patchDeadline(_t, id, body) {
    await delay();
    const m = S().milestones.find((x) => x.id === id);
    if (!m) throw new ResearchError(404, "deadline_not_found");
    Object.assign(m, body);
    if (body.due_date) m.days_left = daysUntil(body.due_date);
    return m;
  },
  async deleteDeadline(_t, id) {
    await delay();
    const st = S();
    if (!st.milestones.some((m) => m.id === id)) throw new ResearchError(404, "deadline_not_found");
    st.milestones = st.milestones.filter((m) => m.id !== id);
  },
};
