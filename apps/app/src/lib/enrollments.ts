import { api, ApiError, type Enrollment, type ProgressBody, type QuizResult } from "../api";

/**
 * Local mirror of the learner's enrollments, so the courses list and the player open without a network.
 * The server stays the source of truth: every successful call overwrites the mirror.
 */
const key = (userId: string) => `mentor.enrollments.${userId}`;

export function readMirror(userId: string): Enrollment[] {
  try {
    const raw = localStorage.getItem(key(userId));
    return raw ? (JSON.parse(raw) as Enrollment[]) : [];
  } catch {
    return [];
  }
}

export function writeMirror(userId: string, list: Enrollment[]) {
  try {
    localStorage.setItem(key(userId), JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

export interface EnrollmentsResult {
  list: Enrollment[];
  /** true when the list came from the mirror because the server was unreachable */
  offline: boolean;
}

export async function loadEnrollments(token: string, userId: string): Promise<EnrollmentsResult> {
  if (Object.keys(readOutbox(userId)).length) await flushOutbox(token, userId);
  try {
    const list = await api.listEnrollments(token);
    const merged = overlayOutbox(userId, list);
    writeMirror(userId, merged);
    return { list: merged, offline: false };
  } catch (e) {
    if (e instanceof ApiError && e.code === "unauthorized") throw e;
    return { list: readMirror(userId), offline: true };
  }
}

// ---------------------------------------------------------------- progress outbox
/**
 * Progress that the server has not acknowledged yet, per course: the latest position + completed blocks (a PUT carries
 * the whole state, so the newest wins) and every quiz result (each one is a record of its own). Kept in localStorage so
 * it survives closing the app, and replayed at start-up, on the `online` event and before each list load.
 */
interface OutboxEntry {
  body: ProgressBody;
  quizzes: QuizResult[];
  /** the body itself still has to be sent (it changed since the last acknowledged PUT) */
  dirty: boolean;
}
type Outbox = Record<string, OutboxEntry>;
const outboxKey = (userId: string) => `mentor.outbox.${userId}`;

export function readOutbox(userId: string): Outbox {
  try {
    const raw = localStorage.getItem(outboxKey(userId));
    return raw ? (JSON.parse(raw) as Outbox) : {};
  } catch {
    return {};
  }
}

function writeOutbox(userId: string, box: Outbox) {
  try {
    if (Object.keys(box).length) localStorage.setItem(outboxKey(userId), JSON.stringify(box));
    else localStorage.removeItem(outboxKey(userId));
  } catch {
    /* ignore */
  }
}

/** The server list with unsent progress laid over it, so the UI never shows older progress than the learner made. */
function overlayOutbox(userId: string, list: Enrollment[]): Enrollment[] {
  const box = readOutbox(userId);
  return list.map((e) => {
    const p = box[e.course_id];
    if (!p?.dirty) return e;
    const { lesson_id, block_id, completed_block_ids } = p.body;
    return { ...e, progress: { lesson_id, block_id, completed_block_ids, updated_at: e.progress?.updated_at } };
  });
}

let chain: Promise<void> = Promise.resolve();

/** Send what is waiting in the outbox. Never throws; calls run one after the other. */
export function flushOutbox(token: string, userId: string): Promise<void> {
  chain = chain.then(() => doFlush(token, userId)).catch(() => undefined);
  return chain;
}

async function doFlush(token: string, userId: string): Promise<void> {
  for (const courseId of Object.keys(readOutbox(userId))) {
    const entry = readOutbox(userId)[courseId];
    if (!entry) continue;
    const sent = entry.body;
    const bodies = entry.quizzes.length ? entry.quizzes.map((quiz) => ({ ...sent, quiz })) : entry.dirty ? [sent] : [];
    let ok = 0;
    let gone = false;
    try {
      for (const b of bodies) {
        await api.putProgress(token, courseId, b);
        ok++;
      }
    } catch (e) {
      gone = e instanceof ApiError && e.code === "not_found"; // unenrolled elsewhere: nothing to keep
      if (!gone) {
        // keep what was not acknowledged; a network or auth failure ends this round
        const box = readOutbox(userId);
        if (box[courseId]) box[courseId].quizzes = box[courseId].quizzes.slice(Math.min(ok, entry.quizzes.length));
        writeOutbox(userId, box);
        return;
      }
    }
    const box = readOutbox(userId);
    const cur = box[courseId];
    if (cur) {
      cur.quizzes = cur.quizzes.slice(entry.quizzes.length); // results added during the send stay
      cur.dirty = !gone && JSON.stringify(cur.body) !== JSON.stringify(sent);
      if (!cur.quizzes.length && !cur.dirty) delete box[courseId];
      writeOutbox(userId, box);
    }
  }
}

/**
 * Record progress locally right away (mirror + outbox), then try to send it. A failed PUT is not an error: the
 * outbox keeps it for the next start-up, the `online` event or the next save.
 */
export async function saveProgress(token: string, userId: string, courseId: string, body: ProgressBody): Promise<void> {
  const { quiz, ...state } = body;
  const list = readMirror(userId);
  const e = list.find((x) => x.course_id === courseId);
  if (e) {
    e.progress = { lesson_id: state.lesson_id, block_id: state.block_id, completed_block_ids: state.completed_block_ids, updated_at: new Date().toISOString() };
    writeMirror(userId, list);
  }
  const box = readOutbox(userId);
  const entry = box[courseId] ?? { body: state, quizzes: [], dirty: true };
  entry.body = state;
  entry.dirty = true;
  if (quiz) entry.quizzes.push(quiz);
  box[courseId] = entry;
  writeOutbox(userId, box);
  await flushOutbox(token, userId);
}
