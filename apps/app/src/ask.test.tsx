import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { askBody, SseParser, streamAsk, toAskEvent, type AskCard, type AskEvent } from "./api/ask";
import { askReducer, initialAsk, type AiTurn, type AskState, type MeTurn } from "./lib/askState";
import { canRecord, pickMime, RecorderError, startRecording } from "./lib/recorder";
import { fitWithin } from "./lib/image";
import { screenKey } from "./components/Guide";

// ------------------------------------------------------------------ SSE parser

const STREAM = 'event: thread\ndata: {"thread_id":"t1"}\n\nevent: answer\ndata: {"text":"Chào em"}\n\n: keep-alive\n\nevent: done\ndata: {"thread_id":"t1"}\n\n';

function parseAll(chunks: string[]) {
  const p = new SseParser();
  const out = chunks.flatMap((c) => p.push(c));
  return [...out, ...p.end()];
}

describe("SseParser", () => {
  it("parses whole events and skips comments", () => {
    const m = parseAll([STREAM]);
    expect(m.map((x) => x.event)).toEqual(["thread", "answer", "done"]);
    expect(JSON.parse(m[1].data)).toEqual({ text: "Chào em" });
  });

  it("gives the same result when the stream is cut at every possible byte boundary", () => {
    const whole = parseAll([STREAM]);
    for (let i = 1; i < STREAM.length; i++) expect(parseAll([STREAM.slice(0, i), STREAM.slice(i)])).toEqual(whole);
  });

  it("copes with one character per chunk", () => {
    expect(parseAll(STREAM.split(""))).toEqual(parseAll([STREAM]));
  });

  it("handles CRLF, even when the CR and the LF arrive in different chunks", () => {
    const crlf = STREAM.replace(/\n/g, "\r\n");
    expect(parseAll([crlf])).toEqual(parseAll([STREAM]));
    for (let i = 1; i < crlf.length; i++) expect(parseAll([crlf.slice(0, i), crlf.slice(i)])).toEqual(parseAll([STREAM]));
  });

  it("joins multi-line data and strips one leading space only", () => {
    const m = parseAll(["event: answer\ndata: a\ndata:  b\n\n"]);
    expect(m).toEqual([{ event: "answer", data: "a\n b" }]);
  });

  it("flushes an event the stream ended in the middle of, and ignores an empty one", () => {
    expect(parseAll(["event: done\ndata: {}"])).toEqual([{ event: "done", data: "{}" }]);
    expect(parseAll(["event: done\n\n\n"])).toEqual([]);
  });

  it("toAskEvent drops unknown events and bad JSON", () => {
    expect(toAskEvent({ event: "wat", data: "{}" })).toBeNull();
    expect(toAskEvent({ event: "answer", data: "{nope" })).toBeNull();
    expect(toAskEvent({ event: "answer", data: '{"text":"x"}' })).toEqual({ event: "answer", data: { text: "x" } });
  });
});

describe("streamAsk", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("reads events from a real (non-mock) stream, with UTF-8 split across chunks", async () => {
    vi.stubEnv("VITE_API_MOCK", "0");
    const bytes = new TextEncoder().encode('event: answer\ndata: {"text":"Điện trường"}\n\nevent: done\ndata: {}\n\n');
    const cut = 30; // inside a multi-byte character
    const res = new Response(
      new ReadableStream({
        start(c) {
          c.enqueue(bytes.slice(0, cut));
          c.enqueue(bytes.slice(cut));
          c.close();
        },
      }),
    );
    const fetchMock = vi.fn().mockResolvedValue(res);
    vi.stubGlobal("fetch", fetchMock);
    const got: AskEvent[] = [];
    await streamAsk("tok", { text: "hi", lang: "vi", thread_id: "t1" }, (e) => got.push(e));
    expect(got).toEqual([
      { event: "answer", data: { text: "Điện trường" } },
      { event: "done", data: {} },
    ]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/ask$/);
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(JSON.parse(init.body)).toEqual({ text: "hi", thread_id: "t1", lang: "vi" });
    vi.unstubAllEnvs();
  });

  it("maps HTTP errors to AskError codes and aborts cleanly", async () => {
    vi.stubEnv("VITE_API_MOCK", "0");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error: "thread_not_found" } }), { status: 404 })));
    await expect(streamAsk("t", { lang: "vi", text: "x" }, () => undefined)).rejects.toMatchObject({ status: 404, code: "thread_not_found" });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(streamAsk("t", { lang: "vi", text: "x" }, () => undefined)).rejects.toMatchObject({ code: "network" });

    const ac = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_u: string, init: RequestInit) => new Promise((_r, rej) => init.signal?.addEventListener("abort", () => rej(new DOMException("a", "AbortError"))))));
    const p = streamAsk("t", { lang: "vi", text: "x" }, () => undefined, ac.signal);
    ac.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
    vi.unstubAllEnvs();
  });

  it("sends images and audio as multipart", () => {
    const img = new Blob(["x"], { type: "image/jpeg" });
    const { body, headers } = askBody({ lang: "en", image: img, thread_id: "t9" });
    expect(headers).toEqual({});
    const f = body as FormData;
    expect(f.get("lang")).toBe("en");
    expect(f.get("thread_id")).toBe("t9");
    expect((f.get("image") as File).name).toBe("photo.jpg");
    const a = askBody({ lang: "vi", audio: new Blob(["y"], { type: "audio/ogg;codecs=opus" }) }).body as FormData;
    expect((a.get("audio") as File).name).toBe("voice.ogg");
  });
});

// ------------------------------------------------------------------ reducer

const ev = (e: AskEvent) => ({ type: "event", ev: e }) as const;
const ai = (s: AskState, i = s.turns.length - 1) => s.turns[i] as AiTurn;
const started = (me: Omit<MeTurn, "id" | "role"> = { text: "hi" }) => askReducer(initialAsk, { type: "send", me });

describe("ask reducer", () => {
  it("send adds the learner's turn and an open answer", () => {
    const s = started();
    expect(s.turns.map((t) => t.role)).toEqual(["me", "ai"]);
    expect(ai(s).open).toBe(true);
    expect(s.target).toBe(1);
  });

  it("thread, status, answer, done", () => {
    let s = started();
    s = askReducer(s, ev({ event: "thread", data: { thread_id: "t1" } }));
    expect(s.threadId).toBe("t1");
    s = askReducer(s, ev({ event: "status", data: { stage: "reading" } }));
    expect(ai(s).stage).toBe("reading");
    s = askReducer(s, ev({ event: "answer", data: { text: "Ok" } }));
    expect(ai(s)).toMatchObject({ answer: "Ok", stage: null });
    s = askReducer(s, ev({ event: "done", data: {} }));
    expect(ai(s).open).toBe(false);
    expect(s.target).toBe(-1);
    // events after done go nowhere
    expect(askReducer(s, ev({ event: "answer", data: { text: "late" } }))).toBe(s);
  });

  it("transcript fills the voice message", () => {
    let s = started({ audio: true });
    s = askReducer(s, ev({ event: "transcript", data: { text: "Em muốn học điện" } }));
    expect((s.turns[0] as MeTurn).text).toBe("Em muốn học điện");
  });

  it("courses keep cards, all-ages flag and start_with", () => {
    const card = { course_id: "c1", title: "T", enrolled: false } as AskCard;
    const s = askReducer(started(), ev({ event: "courses", data: { items: [card], suggested_all_ages: true, start_with: { course_id: "c1", lesson_id: "l1" } } }));
    expect(ai(s).courses).toEqual({ items: [card], suggestedAllAges: true, startWith: { course_id: "c1", lesson_id: "l1" } });
  });

  it("a bad quality check marks the photo; an ok one does not", () => {
    const withPhoto = started({ photo: "blob:x" });
    expect((askReducer(withPhoto, ev({ event: "quality", data: { ok: false, reasons: ["too_dark"] } })).turns[0] as MeTurn).badPhoto).toBe(true);
    expect((askReducer(withPhoto, ev({ event: "quality", data: { ok: true } })).turns[0] as MeTurn).badPhoto).toBeUndefined();
  });

  it("retake message, choices, problem, solution", () => {
    let s = started({ photo: "blob:x" });
    s = askReducer(s, ev({ event: "message", data: { kind: "retake", text: "Tối quá", where: "nửa dưới", tips: ["a", "b", "c"], offer_readable: true } }));
    expect(ai(s).message).toMatchObject({ kind: "retake", where: "nửa dưới", offerReadable: true });
    s = askReducer(s, ev({ event: "choices", data: { problems: [{ id: "p1", label: "Bài 3", text: "x" }], reason: "partial" } }));
    expect(ai(s).choices?.reason).toBe("partial");
    s = askReducer(s, ev({ event: "problem", data: { id: "p1", label: "Bài 3", text: "x" } }));
    s = askReducer(s, ev({ event: "solution", data: { problem_id: "p1", steps: [{ title: "a", md: "b" }], last_step_withheld: true, tip: "mẹo" } }));
    expect(ai(s).solution).toMatchObject({ problemId: "p1", lastStepWithheld: true, tip: "mẹo" });
  });

  it("last_step lands in the solution turn without adding turns (in place)", () => {
    let s = started();
    s = askReducer(s, ev({ event: "solution", data: { problem_id: "p1", steps: [{ title: "a", md: "b" }], last_step_withheld: true } }));
    s = askReducer(s, ev({ event: "done", data: {} }));
    const n = s.turns.length;
    s = askReducer(s, { type: "send", inPlace: true });
    expect(s.turns.length).toBe(n);
    expect(ai(s).open).toBe(true);
    s = askReducer(s, ev({ event: "last_step", data: { step: { title: "z", md: "y" } } }));
    expect(ai(s).lastStep).toEqual({ title: "z", md: "y" });
    // a missing last step is a note, not an error
    s = askReducer(s, { type: "send", inPlace: true });
    s = askReducer(s, ev({ event: "message", data: { kind: "no_last_step", text: "Chưa có" } }));
    expect(ai(s).note).toBe("Chưa có");
    expect(ai(s).message).toBeUndefined();
  });

  it("similar, error and a new solution reset the follow-ups", () => {
    let s = started();
    s = askReducer(s, ev({ event: "similar", data: { items: [{ problem_md: "p", answer_md: "a" }] } }));
    expect(ai(s).similar).toHaveLength(1);
    s = askReducer(s, ev({ event: "solution", data: { problem_id: "p", steps: [], last_step_withheld: false } }));
    expect(ai(s).similar).toBeUndefined();
    s = askReducer(s, ev({ event: "error", data: { code: "model_unavailable" } }));
    expect(ai(s).error?.code).toBe("model_unavailable");
  });

  it("fail and cancel close the turn; an empty cancelled turn says so", () => {
    expect(ai(askReducer(started(), { type: "fail", code: "network" }))).toMatchObject({ open: false, error: { code: "network" } });
    const c = askReducer(started(), { type: "cancel" });
    expect(ai(c)).toMatchObject({ open: false, cancelled: true });
    expect(c.target).toBe(-1);
    const part = askReducer(started(), ev({ event: "answer", data: { text: "half" } }));
    expect(ai(askReducer(part, { type: "cancel" })).cancelled).toBe(false);
  });
});

// ------------------------------------------------------------------ recorder

class FakeRecorder {
  static types = ["audio/webm"];
  static isTypeSupported = (t: string) => FakeRecorder.types.includes(t);
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["abc"], { type: "audio/webm" }) });
    this.onstop?.();
  }
}

function mockMedia(getUserMedia: () => Promise<unknown>) {
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
}

describe("recorder", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "mediaDevices");
  });

  it("is unsupported without MediaRecorder or getUserMedia", async () => {
    expect(canRecord()).toBe(false);
    await expect(startRecording()).rejects.toMatchObject({ code: "unsupported" });
  });

  it("maps a permission refusal to denied, a missing device to unsupported, anything else to failed", async () => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    for (const [name, code] of [["NotAllowedError", "denied"], ["SecurityError", "denied"], ["NotFoundError", "unsupported"], ["AbortError", "failed"]] as const) {
      mockMedia(() => Promise.reject(new DOMException("x", name)));
      const err = await startRecording().catch((e) => e);
      expect(err).toBeInstanceOf(RecorderError);
      expect(err.code).toBe(code);
    }
  });

  it("records, returns the audio and releases the microphone", async () => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    const track = { stop: vi.fn() };
    mockMedia(() => Promise.resolve({ getTracks: () => [track] }));
    const r = await startRecording();
    const blob = await r.stop();
    expect(blob.size).toBe(3);
    expect(blob.type).toBe("audio/webm");
    expect(track.stop).toHaveBeenCalled();
  });

  it("cancel throws the audio away and still releases the microphone", async () => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    const track = { stop: vi.fn() };
    mockMedia(() => Promise.resolve({ getTracks: () => [track] }));
    const r = await startRecording();
    r.cancel();
    expect(track.stop).toHaveBeenCalled();
  });

  it("stops by itself after the maximum time", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    mockMedia(() => Promise.resolve({ getTracks: () => [{ stop: () => undefined }] }));
    const auto = vi.fn();
    await startRecording({ maxMs: 1000, onAutoStop: auto });
    vi.advanceTimersByTime(1001);
    expect(auto).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("picks the first supported container", () => {
    expect(pickMime({ isTypeSupported: (t) => t === "audio/mp4" })).toBe("audio/mp4");
    expect(pickMime({ isTypeSupported: () => false })).toBeUndefined();
  });
});

describe("helpers", () => {
  it("fitWithin keeps the aspect ratio and never upsizes", () => {
    expect(fitWithin(4000, 3000, 1600)).toEqual({ width: 1600, height: 1200 });
    expect(fitWithin(800, 600, 1600)).toEqual({ width: 800, height: 600 });
    expect(fitWithin(1000, 4000, 1600)).toEqual({ width: 400, height: 1600 });
  });

  it("screenKey maps routes to the guide area of the screen", () => {
    expect(screenKey("/hoi-dap")).toBe("ask");
    expect(screenKey("/khoa-hoc")).toBe("courses");
    expect(screenKey("/khoa-hoc/abc")).toBe("course-tree");
    expect(screenKey("/khoa-hoc/abc/hoc")).toBe("player-progress");
    expect(screenKey("/")).toBeUndefined();
  });
});

// ------------------------------------------------------------------ "+ Thêm" on a course card

const enroll = vi.fn();
vi.mock("./lib/enrollCourse", () => ({ enrollCourse: (...a: unknown[]) => enroll(...a) }));
vi.mock("./state/auth", () => ({ useAuth: () => ({ token: "tok", user: { id: "u1", age_band: "g10_12" } }) }));
vi.mock("./screens/courses/common", () => ({
  CourseCover: () => null,
  LangTag: ({ lang }: { lang: string }) => <span className="tag">{lang}</span>,
  MediaIcons: () => null,
  formatMinutes: () => "1 giờ",
}));

import { CourseCards, useAddCourse } from "./screens/ask/Courses";

const card = (over: Partial<AskCard> = {}): AskCard => ({
  course_id: "c1",
  title: "Vật lí 11: Điện trường",
  cover_sha256: "0",
  description_short: "Lực điện và đường sức.",
  language: "vi",
  lessons_count: 7,
  est_minutes: 120,
  tree: [],
  enrolled: false,
  first_lesson: { lesson_id: "l1", title: "Bài 1" },
  ...over,
});

function Harness({ items, onAdded, onFailed }: { items: AskCard[]; onAdded(c: AskCard): void; onFailed(): void }) {
  const adder = useAddCourse(onAdded, onFailed);
  return (
    <MemoryRouter>
      <CourseCards items={items} startWith={{ course_id: "c1" }} suggestedAllAges={false} adder={adder} onOpen={() => undefined} />
    </MemoryRouter>
  );
}

describe("course card + Thêm", () => {
  afterEach(() => enroll.mockReset());

  it("enrolls once, then shows Đã thêm and cannot be pressed again", async () => {
    await i18n.changeLanguage("vi");
    enroll.mockResolvedValue({ course_id: "c1", pinned_version: 1 });
    const onAdded = vi.fn();
    const ui = userEvent.setup();
    render(<Harness items={[card(), card({ course_id: "c2", title: "Hai", enrolled: true })]} onAdded={onAdded} onFailed={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Đã thêm: Hai/ })).toBeDisabled();
    await ui.click(screen.getByRole("button", { name: /Thêm: Vật lí 11/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Đã thêm: Vật lí 11/ })).toBeDisabled());
    expect(enroll).toHaveBeenCalledTimes(1);
    expect(enroll).toHaveBeenCalledWith("tok", "u1", "c1");
    expect(onAdded).toHaveBeenCalledWith(expect.objectContaining({ course_id: "c1" }));
  });

  it("a coming-soon course shows Sắp có and cannot be added", async () => {
    await i18n.changeLanguage("vi");
    render(<Harness items={[card({ course_id: "ph-x", title: "Toán 2", status: "coming_soon", first_lesson: null })]} onAdded={vi.fn()} onFailed={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Sắp có: Toán 2/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Thêm: / })).toBeNull();
    expect(enroll).not.toHaveBeenCalled();
  });

  it("a failed enrollment reports it and lets the learner try again", async () => {
    await i18n.changeLanguage("vi");
    enroll.mockRejectedValueOnce(new Error("net")).mockResolvedValueOnce({});
    const onFailed = vi.fn();
    const ui = userEvent.setup();
    render(<Harness items={[card()]} onAdded={vi.fn()} onFailed={onFailed} />);
    await ui.click(screen.getByRole("button", { name: /Thêm: / }));
    await waitFor(() => expect(onFailed).toHaveBeenCalled());
    const again = await screen.findByRole("button", { name: /Thêm: / });
    expect(again).toBeEnabled();
    await ui.click(again);
    await waitFor(() => expect(screen.getByRole("button", { name: /Đã thêm: / })).toBeDisabled());
  });

  it("marks the suggested starting course", async () => {
    await i18n.changeLanguage("vi");
    render(<Harness items={[card()]} onAdded={vi.fn()} onFailed={vi.fn()} />);
    expect(screen.getByText("Bắt đầu từ đây")).toBeInTheDocument();
  });
});

import { AiBubble, solveProgress, SOLVE_STAGES, type AiHandlers } from "./screens/ask/Turns";

describe("solve progress bar", () => {
  it("eases towards each stage's end and never reaches it", () => {
    const r = SOLVE_STAGES.photo.reading;
    expect(solveProgress(r, 0)).toBe(0);
    expect(solveProgress(r, r.ms)).toBeGreaterThan(35);
    expect(solveProgress(r, 10 * r.ms)).toBeLessThan(40.01);
    expect(solveProgress(SOLVE_STAGES.photo.solving, 0)).toBe(40);
    expect(solveProgress(SOLVE_STAGES.photo.solving, 60_000)).toBeLessThan(95.01);
  });

  it("shows step 1/2 then 2/2 for a photo, and no step count for a typed problem", async () => {
    await i18n.changeLanguage("vi");
    const h = { adder: {} } as unknown as AiHandlers;
    const turn = (stage: AiTurn["stage"]): AiTurn => ({ id: 1, role: "ai", stage, open: true });
    const { rerender } = render(<AiBubble turn={turn("reading")} latest busy lang="vi" h={h} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveTextContent("Đang đọc đề…");
    expect(bar).toHaveTextContent("1/2");
    rerender(<AiBubble turn={turn("solving")} latest busy lang="vi" h={h} />);
    expect(screen.getByRole("progressbar")).toHaveTextContent("2/2");
    expect(Number(screen.getByRole("progressbar").getAttribute("aria-valuenow"))).toBeGreaterThanOrEqual(40);
    rerender(<AiBubble turn={turn(null)} latest={false} busy={false} lang="vi" h={h} />);
    expect(screen.queryByRole("progressbar")).toBeNull();
    render(<AiBubble turn={{ id: 2, role: "ai", stage: "solving", open: true }} latest busy lang="vi" h={h} />);
    expect(screen.getByRole("progressbar")).not.toHaveTextContent("/2");
  });
});
