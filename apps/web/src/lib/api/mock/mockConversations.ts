/** Mock of CONTRACTS 10.5 conversations: list/create/rename/delete/search and per-conversation transcripts. */
import { ApiError } from "../client";
import type { ArchivedFilter, ChatHistoryEntry, Conversation, ConversationHit, ConversationPatch } from "../../types";
import { fold, snippetAround } from "../../text";

const KEY = "mentor-mock-conversations-v1";

interface Store {
  next: number;
  list: Conversation[];
  history: Record<string, ChatHistoryEntry[]>;
}

type Storage_ = Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;

export class MockConversations {
  private s: Store = { next: 1, list: [], history: {} };

  constructor(
    private readonly storage: Storage_,
    private readonly now: () => number,
  ) {
    try {
      const raw = storage?.getItem(KEY);
      if (raw) this.s = JSON.parse(raw) as Store;
    } catch {
      // ignore corrupt state
    }
  }

  private save() {
    try {
      this.storage?.setItem(KEY, JSON.stringify(this.s));
    } catch {
      // ignore
    }
  }

  list(archived: ArchivedFilter = "false"): Conversation[] {
    const keep = (c: Conversation) => archived === "all" || (archived === "true") === Boolean(c.archived);
    return structuredClone(
      this.s.list.filter(keep).sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? "")),
    );
  }

  create(body: { title?: string; subject?: string | null } = {}): Conversation {
    const ts = new Date(this.now()).toISOString();
    const id = `c-${this.s.next++}`;
    const c: Conversation = { id, title: (body.title ?? "").trim() || "Cuộc trò chuyện mới", subject: body.subject ?? null, created_at: ts, updated_at: ts };
    this.s.list.push(c);
    this.s.history[id] = [];
    this.save();
    return structuredClone(c);
  }

  private find(id: string): Conversation {
    const c = this.s.list.find((x) => x.id === id);
    if (!c) throw new ApiError(404, "Không tìm thấy cuộc trò chuyện.");
    return c;
  }

  update(id: string, patch: ConversationPatch): Conversation {
    const c = this.find(id);
    if (patch.archived !== undefined) c.archived = patch.archived;
    if (patch.title !== undefined) {
      const t = patch.title.trim();
      if (!t) throw new ApiError(422, "Tên cuộc trò chuyện không được để trống.");
      c.title = t.slice(0, 80);
    }
    if (patch.subject !== undefined) c.subject = patch.subject;
    this.save();
    return structuredClone(c);
  }

  remove(id: string) {
    this.find(id);
    this.s.list = this.s.list.filter((x) => x.id !== id);
    delete this.s.history[id];
    this.save();
  }

  history(id: string): ChatHistoryEntry[] {
    this.find(id);
    return structuredClone(this.s.history[id] ?? []);
  }

  append(id: string, entry: ChatHistoryEntry) {
    const c = this.s.list.find((x) => x.id === id);
    if (!c) return;
    (this.s.history[id] ??= []).push(entry);
    c.updated_at = new Date(this.now()).toISOString();
    this.save();
  }

  /** Searches conversations; `mainEntries` are today's main-chat items (conversation_id null). */
  search(q: string, mainEntries: ChatHistoryEntry[]): ConversationHit[] {
    const f = fold(q);
    if (!f) return [];
    const hits: ConversationHit[] = [];
    const scan = (id: string | null, title: string, entries: ChatHistoryEntry[]) => {
      for (const e of entries) {
        if (e.role === "card" || !e.text || !fold(e.text).includes(f)) continue;
        hits.push({ conversation_id: id, title, ts: e.ts, role: e.role, snippet: snippetAround(e.text, q) });
      }
    };
    scan(null, "Trò chuyện hằng ngày", mainEntries);
    for (const c of this.s.list) scan(c.id, c.title, this.s.history[c.id] ?? []);
    return hits.sort((a, b) => (b.ts ?? "").localeCompare(a.ts ?? "")).slice(0, 30);
  }
}
