"use client";

import { useCallback, useEffect, useState } from "react";
import { getApi } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { SUBJECT_NAMES } from "@/lib/practice/progress";
import type { Conversation } from "@/lib/types";
import { Modal } from "../GlobalUi";
import { Icon } from "../Icon";
import { useToast } from "../toast";
import { ConfirmDialog, errorText } from "../ui";

const SUBJECT_OPTIONS = ["math", "physics", "english"] as const;

export function subjectTag(id: string | null | undefined): string | null {
  return id ? (SUBJECT_NAMES[id] ?? id) : null;
}

/** Create a conversation and make it active. Shared by the button, Ctrl+N and the dialog. */
export async function createConversation(): Promise<Conversation> {
  return getApi().createConversation({});
}

export function ConversationsDialog({
  open,
  onClose,
  activeId,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  activeId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const toast = useToast();
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"active" | "archived">("active");

  const load = useCallback(() => {
    getApi()
      .listConversations(view === "archived" ? "true" : "false")
      .then(
        (r) => {
          setItems(r);
          setError(null);
        },
        (e: unknown) => setError(e),
      );
  }, [view]);

  /** Archived chats leave the list but keep their history; sending a message in one brings it back. */
  async function setArchived(c: Conversation, archived: boolean) {
    try {
      await getApi().updateConversation(c.id, { archived });
      setItems((l) => l?.filter((x) => x.id !== c.id) ?? l);
      if (archived && activeId === c.id) onSelect(null);
      toast(archived ? `Đã lưu trữ “${c.title}”.` : `Đã đưa “${c.title}” trở lại danh sách.`, "ok");
    } catch (e) {
      toast(errorText(e), "error");
    }
  }

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  async function add() {
    setBusy(true);
    try {
      const c = await createConversation();
      onSelect(c.id);
      onClose();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveName(c: Conversation) {
    const title = draft.trim();
    if (!title || title === c.title) {
      setRenaming(null);
      return;
    }
    try {
      const u = await getApi().updateConversation(c.id, { title });
      setItems((l) => l?.map((x) => (x.id === c.id ? u : x)) ?? l);
      setRenaming(null);
    } catch (e) {
      toast(errorText(e), "error");
    }
  }

  async function setSubject(c: Conversation, subject: string) {
    try {
      const u = await getApi().updateConversation(c.id, { subject: subject || null });
      setItems((l) => l?.map((x) => (x.id === c.id ? u : x)) ?? l);
    } catch (e) {
      toast(errorText(e), "error");
    }
  }

  async function remove() {
    if (!deleting) return;
    setBusy(true);
    try {
      await getApi().deleteConversation(deleting.id);
      if (activeId === deleting.id) onSelect(null);
      setItems((l) => l?.filter((x) => x.id !== deleting.id) ?? l);
      toast("Đã xoá cuộc trò chuyện.", "ok");
      setDeleting(null);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Modal open={open && !deleting} onClose={onClose} label="Các cuộc trò chuyện" className="dialog-wide">
        <div className="card-header">
          <h2>Các cuộc trò chuyện</h2>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => void add()} disabled={busy}>
            <Icon name="edit" size={16} /> Cuộc trò chuyện mới
          </button>
        </div>
        <div className="tabs" role="tablist" aria-label="Danh sách" style={{ marginBottom: 10 }}>
          {(["active", "archived"] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              onClick={() => {
                if (v === view) return;
                setItems(null);
                setView(v);
              }}
            >
              {v === "active" ? "Đang dùng" : "Đã lưu trữ"}
            </button>
          ))}
        </div>
        {error != null && <p className="alert alert-error">{errorText(error)}</p>}
        <ul className="conv-list">
          {view === "active" && (
            <li data-active={activeId === null}>
              <button
                type="button"
                className="conv-main"
                aria-current={activeId === null ? "true" : undefined}
                onClick={() => {
                  onSelect(null);
                  onClose();
                }}
              >
                <strong>Trò chuyện hằng ngày</strong>
                <span className="hint">Cuộc trò chuyện chính, theo từng ngày</span>
              </button>
            </li>
          )}
          {items === null && error == null && <li className="hint">Đang tải…</li>}
          {items?.length === 0 && view === "active" && (
            <li className="hint">Chưa có cuộc trò chuyện riêng nào. Tạo một cái để tách chủ đề, ví dụ “Ôn hàm số”.</li>
          )}
          {items?.length === 0 && view === "archived" && (
            <li className="hint">Chưa lưu trữ cuộc trò chuyện nào. Lưu trữ để gọn danh sách mà vẫn giữ lịch sử.</li>
          )}
          {items?.map((c) => (
            <li key={c.id} data-active={activeId === c.id}>
              {renaming === c.id ? (
                <form
                  className="row"
                  style={{ flex: 1 }}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void saveName(c);
                  }}
                >
                  <label className="sr-only" htmlFor={`rn-${c.id}`}>
                    Tên cuộc trò chuyện
                  </label>
                  <input id={`rn-${c.id}`} className="input" autoFocus maxLength={80} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Escape" && (e.stopPropagation(), setRenaming(null))} />
                  <button type="submit" className="btn btn-sm btn-primary">
                    Lưu
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => setRenaming(null)}>
                    Huỷ
                  </button>
                </form>
              ) : (
                <>
                  <button
                    type="button"
                    className="conv-main"
                    aria-current={activeId === c.id ? "true" : undefined}
                    onClick={() => {
                      onSelect(c.id);
                      onClose();
                    }}
                  >
                    <strong>{c.title}</strong>
                    <span className="hint">
                      {subjectTag(c.subject) && <span className="badge">{subjectTag(c.subject)}</span>}{" "}
                      {c.updated_at ? formatDate(c.updated_at) : ""}
                    </span>
                  </button>
                  <label className="sr-only" htmlFor={`sub-${c.id}`}>
                    Môn của “{c.title}”
                  </label>
                  <select id={`sub-${c.id}`} className="select conv-subject" value={c.subject ?? ""} onChange={(e) => void setSubject(c, e.target.value)}>
                    <option value="">Không gắn môn</option>
                    {SUBJECT_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {SUBJECT_NAMES[s]}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn btn-ghost btn-icon btn-sm"
                    aria-label={`Đổi tên “${c.title}”`}
                    onClick={() => {
                      setRenaming(c.id);
                      setDraft(c.title);
                    }}
                  >
                    <Icon name="edit" size={16} />
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => void setArchived(c, view === "active")}>
                    {view === "active" ? "Lưu trữ" : "Khôi phục"}
                    <span className="sr-only"> “{c.title}”</span>
                  </button>
                  <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={`Xoá “${c.title}”`} onClick={() => setDeleting(c)}>
                    <Icon name="trash" size={16} />
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}>
          <button type="button" className="btn" onClick={onClose}>
            Đóng
          </button>
        </div>
      </Modal>
      <ConfirmDialog
        open={deleting !== null}
        title="Xoá cuộc trò chuyện này?"
        confirmLabel="Xoá"
        danger
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setDeleting(null)}
      >
        “{deleting?.title}” và các tin nhắn trong đó sẽ bị xoá. Việc này không hoàn tác được.
      </ConfirmDialog>
    </>
  );
}
