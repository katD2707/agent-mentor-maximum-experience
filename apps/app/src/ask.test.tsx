import { afterEach, describe, expect, it, vi } from "vitest";
import { askBody, SseParser, streamAsk, toAskEvent, type AskEvent } from "./api/ask";
import { canRecord, pickMime, RecorderError, startRecording } from "./lib/recorder";
import { fitWithin } from "./lib/image";

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
});
