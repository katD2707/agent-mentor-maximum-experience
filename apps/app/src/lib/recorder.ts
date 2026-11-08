/** Microphone recording for Hỏi đáp (MediaRecorder). The server turns the audio into text. */

export type RecorderErrorCode = "denied" | "unsupported" | "failed";

export class RecorderError extends Error {
  constructor(public code: RecorderErrorCode) {
    super(code);
    this.name = "RecorderError";
  }
}

export interface Recording {
  /** stop and return the audio; rejects when nothing was recorded */
  stop(): Promise<Blob>;
  /** stop and throw the audio away */
  cancel(): void;
}

/** The sooner a recording stops by itself, the sooner the server (10 MB limit) can answer. */
export const MAX_RECORD_MS = 90_000;

const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export function pickMime(rec: { isTypeSupported?(t: string): boolean } | undefined): string | undefined {
  return TYPES.find((t) => rec?.isTypeSupported?.(t));
}

export const canRecord = (): boolean => typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";

/** Ask for the microphone and start recording. Throws `RecorderError` ("denied" when the user or the system said no). */
export async function startRecording(opts: { maxMs?: number; onAutoStop?: () => void } = {}): Promise<Recording> {
  if (!canRecord()) throw new RecorderError("unsupported");
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    const name = (e as DOMException)?.name;
    throw new RecorderError(name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError" ? "denied" : name === "NotFoundError" ? "unsupported" : "failed");
  }
  const release = () => stream.getTracks().forEach((t) => t.stop());
  let rec: MediaRecorder;
  try {
    const mime = pickMime(MediaRecorder);
    rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
  } catch {
    release();
    throw new RecorderError("failed");
  }
  const chunks: Blob[] = [];
  let discard = false;
  const ended = new Promise<Blob>((resolve, reject) => {
    rec.ondataavailable = (e) => e.data?.size && chunks.push(e.data);
    rec.onerror = () => (release(), reject(new RecorderError("failed")));
    rec.onstop = () => {
      release();
      const blob = new Blob(chunks, { type: rec.mimeType || chunks[0]?.type || "audio/webm" });
      if (discard || !blob.size) reject(new RecorderError("failed"));
      else resolve(blob);
    };
  });
  ended.catch(() => undefined);
  rec.start();
  const timer = setTimeout(() => {
    if (rec.state === "recording") {
      rec.stop();
      opts.onAutoStop?.();
    }
  }, opts.maxMs ?? MAX_RECORD_MS);
  const finish = () => {
    clearTimeout(timer);
    if (rec.state !== "inactive") rec.stop();
    else release();
  };
  return {
    stop() {
      finish();
      return ended;
    },
    cancel() {
      discard = true;
      finish();
    },
  };
}
