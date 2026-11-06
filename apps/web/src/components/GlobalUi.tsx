"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { getApi } from "@/lib/api";
import { requestMessageFocus, setActiveConversation } from "@/lib/conversationNav";
import { OPEN_SEARCH_EVENT, OPEN_SHORTCUTS_EVENT } from "@/lib/conversationNav";
import { formatDate, localDateStamp } from "@/lib/format";
import { isTypingTarget, shortcutSections, subscribeShortcuts } from "@/lib/shortcuts";
import type { ConversationHit } from "@/lib/types";
import { Highlight } from "./Highlight";
import { Icon } from "./Icon";
import { errorText } from "./ui";

/** A native <dialog> that opens/closes with `open`, closes on Esc and backdrop click, and returns focus. */
function Modal({ open, onClose, label, children, className = "" }: { open: boolean; onClose: () => void; label: string; children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className={`dialog ${className}`}
      aria-label={label}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      {open && children}
    </dialog>
  );
}

export { Modal };

const MIN_QUERY = 2;

export function SearchDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState("");
  const [result, setResult] = useState<{ query: string; hits: ConversationHit[] | null; error: unknown }>({ query: "", hits: null, error: null });
  const inputId = useId();
  const query = q.trim();
  const short = query.length < MIN_QUERY;
  const current = !short && result.query === query;
  const hits = current ? result.hits : null;
  const error = current ? result.error : null;
  const busy = !short && !current;

  useEffect(() => {
    if (!open || query.length < MIN_QUERY) return;
    let alive = true;
    const t = window.setTimeout(() => {
      getApi()
        .searchConversations(query)
        .then(
          (r) => alive && setResult({ query, hits: r, error: null }),
          (e: unknown) => alive && setResult({ query, hits: null, error: e }),
        );
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [query, open]);

  function pick(h: ConversationHit) {
    setActiveConversation(h.conversation_id);
    // Named chats load their whole history; the main chat shows today only, so older days open the history dialog.
    if (h.ts) requestMessageFocus({ ts: h.ts, date: !h.conversation_id && h.date && h.date !== localDateStamp() ? h.date : null });
    onClose();
    if (!pathname.startsWith("/chat") && !pathname.startsWith("/popup")) router.push("/chat");
  }

  return (
    <Modal open={open} onClose={onClose} label="Tìm trong các cuộc trò chuyện" className="dialog-wide">
      <div className="search-box">
        <Icon name="research" size={18} />
        <label htmlFor={inputId} className="sr-only">
          Tìm trong các cuộc trò chuyện
        </label>
        <input
          id={inputId}
          className="input"
          type="search"
          autoFocus
          autoComplete="off"
          placeholder="Tìm trong các cuộc trò chuyện (không cần gõ dấu)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Đóng tìm kiếm">
          <Icon name="close" size={16} />
        </button>
      </div>
      <div className="search-results" aria-live="polite" aria-busy={busy}>
        {short && <p className="hint">Gõ ít nhất {MIN_QUERY} ký tự. Ví dụ “phuong trinh” cũng tìm được “phương trình”.</p>}
        {error != null && <p className="alert alert-error">{errorText(error)}</p>}
        {hits && hits.length === 0 && !busy && <p className="hint">Không thấy kết quả nào cho “{q.trim()}”.</p>}
        {hits && hits.length > 0 && (
          <ul className="hit-list">
            {hits.map((h, i) => (
              <li key={`${h.conversation_id}-${h.ts}-${i}`}>
                <button type="button" className="hit-row" onClick={() => pick(h)}>
                  <span className="hit-title">
                    {h.title || (h.conversation_id ? "Cuộc trò chuyện" : "Trò chuyện hằng ngày")}
                    {h.ts && <span className="faint"> · {formatDate(h.ts)}</span>}
                    {h.role && <span className="faint"> · {h.role === "user" ? "Bạn" : "Mentor"}</span>}
                  </span>
                  <span className="hit-snippet">
                    <Highlight text={h.snippet} query={q} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}

export function ShortcutsOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  useSyncExternalStore(subscribeShortcuts, () => 0, () => 0);
  const sections = shortcutSections(pathname);
  return (
    <Modal open={open} onClose={onClose} label="Phím tắt">
      <h2>Phím tắt</h2>
      {sections.map((s) => (
        <section key={s.title} aria-label={s.title} style={{ marginBottom: 12 }}>
          <h3 style={{ fontSize: "0.95rem" }}>{s.title}</h3>
          <dl className="kbd-list">
            {s.list.map((k) => (
              <div key={k.keys + k.description}>
                <dt>
                  <kbd>{k.keys}</kbd>
                </dt>
                <dd>{k.description}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn" onClick={onClose}>
          Đóng
        </button>
      </div>
    </Modal>
  );
}

/** Global keys (Ctrl+K search, F1 / ? shortcut overlay) plus the two dialogs. Mounted once per shell and in the pop-up. */
export function GlobalUi() {
  const [search, setSearch] = useState(false);
  const [help, setHelp] = useState(false);
  const closeSearch = useCallback(() => setSearch(false), []);
  const closeHelp = useCallback(() => setHelp(false), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setHelp(false);
        setSearch(true);
      } else if (e.key === "F1" || (e.key === "?" && !e.ctrlKey && !e.metaKey && !isTypingTarget(e.target))) {
        e.preventDefault();
        setSearch(false);
        setHelp((v) => !v);
      }
    };
    const openSearch = () => setSearch(true);
    const openHelp = () => setHelp(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_SEARCH_EVENT, openSearch);
    window.addEventListener(OPEN_SHORTCUTS_EVENT, openHelp);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_SEARCH_EVENT, openSearch);
      window.removeEventListener(OPEN_SHORTCUTS_EVENT, openHelp);
    };
  }, []);

  return (
    <>
      <SearchDialog open={search} onClose={closeSearch} />
      <ShortcutsOverlay open={help} onClose={closeHelp} />
    </>
  );
}
