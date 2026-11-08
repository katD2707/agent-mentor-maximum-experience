import { api, ApiError, type BehaviourEvent, type EventKind } from "../api";

/**
 * Behaviour events (CONTRACTS.md section 12). Every event gets a client id (the server is idempotent on it) and is
 * written to the device before anything is sent, so closing the app or losing the network never loses them. Sending
 * follows the same rules as the progress replay in `enrollments.ts`: one serialized chain, run at start-up, on the
 * `online` event and on a timer; an unacknowledged batch stays queued.
 */
export const BATCH = 500;
export const MAX_QUEUE = 2000;

export interface EventStore {
  read(): BehaviourEvent[];
  write(list: BehaviourEvent[]): void;
}

export function localEventStore(userId: string): EventStore {
  const key = `mentor.events.${userId}`;
  return {
    read() {
      try {
        const raw = localStorage.getItem(key);
        return raw ? (JSON.parse(raw) as BehaviourEvent[]) : [];
      } catch {
        return [];
      }
    },
    write(list) {
      try {
        if (list.length) localStorage.setItem(key, JSON.stringify(list));
        else localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    },
  };
}

let counter = 0;
export function newId(): string {
  const c = globalThis.crypto;
  if (c && "randomUUID" in c) return c.randomUUID();
  counter += 1;
  return `e-${Date.now().toString(36)}-${counter}-${Math.random().toString(36).slice(2, 8)}`;
}

export type Sender = (batch: BehaviourEvent[]) => Promise<unknown>;

/** Whether a failed send should keep the batch: network, auth, rate limit and server errors do; a 400/413/422 would never succeed. */
export function keepAfter(e: unknown): boolean {
  if (!(e instanceof ApiError)) return true;
  if (e.status === 0 || e.status === 401 || e.status === 408 || e.status === 429 || e.status >= 500) return true;
  return false;
}

export class EventLogger {
  private chain: Promise<void> = Promise.resolve();
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private store: EventStore,
    private send: Sender,
    private opts: { now?: () => number; autoFlushAt?: number; flushDelayMs?: number } = {},
  ) {}

  private now() {
    return (this.opts.now ?? Date.now)();
  }

  pending(): number {
    return this.store.read().length;
  }

  log(kind: EventKind, data: Record<string, unknown> = {}, ts?: number): void {
    const list = this.store.read();
    list.push({ id: newId(), kind, ts: new Date(ts ?? this.now()).toISOString(), data });
    this.store.write(list.length > MAX_QUEUE ? list.slice(list.length - MAX_QUEUE) : list);
    if (list.length >= (this.opts.autoFlushAt ?? 20)) void this.flush();
    else this.later();
  }

  /** A short debounce, so a burst of events leaves in one request. */
  private later() {
    if (this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.flush();
    }, this.opts.flushDelayMs ?? 15000);
  }

  stop() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  /** Send what is waiting. Never throws. Calls run one after the other. */
  flush(): Promise<void> {
    this.chain = this.chain.then(() => this.doFlush()).catch(() => undefined);
    return this.chain;
  }

  private async doFlush(): Promise<void> {
    for (;;) {
      const batch = this.store.read().slice(0, BATCH);
      if (!batch.length) return;
      try {
        await this.send(batch);
      } catch (e) {
        if (keepAfter(e)) return;
        // a batch the server refuses as a whole is dropped, or it would block everything behind it
      }
      const sent = new Set(batch.map((b) => b.id));
      this.store.write(this.store.read().filter((x) => !sent.has(x.id)));
    }
  }
}

// ---------------------------------------------------------------- the running logger (one per signed-in student)
let current: EventLogger | null = null;

export function startLogger(token: string, userId: string): EventLogger {
  current?.stop();
  current = new EventLogger(localEventStore(userId), (batch) => api.postEvents(token, batch));
  return current;
}
export function stopLogger() {
  current?.stop();
  current = null;
}
export function logEvent(kind: EventKind, data: Record<string, unknown> = {}): void {
  current?.log(kind, data);
}
export function flushEvents(): Promise<void> {
  return current ? current.flush() : Promise.resolve();
}
