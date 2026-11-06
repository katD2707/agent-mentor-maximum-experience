"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { getApi } from "@/lib/api";
import { REPORT_REASONS } from "@/lib/practice/logic";
import type { ItemReportReason } from "@/lib/practice/types";
import { errorText } from "../ui";
import { useToast } from "../toast";

export interface DialogAction {
  label: string;
  onClick: () => void;
  kind?: "primary" | "default" | "danger";
  /** Gets focus when the dialog opens (the safe choice). */
  autoFocus?: boolean;
  disabled?: boolean;
  hint?: string;
}

/** Native <dialog>: focus trapped by the browser, Esc = `onClose`, backdrop click closes. Content mounts only while open. */
export function PracticeDialog({
  open,
  title,
  onClose,
  actions,
  children,
  wide = false,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  actions?: DialogAction[];
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      const f = d.querySelector<HTMLElement>("[data-autofocus]");
      f?.focus();
    }
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className={wide ? "dialog dialog-wide" : "dialog"}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      {open && (
        <>
          <h2 id={titleId}>{title}</h2>
          <div className="dialog-body">{children}</div>
          {actions && (
            <div className="row dialog-actions">
              {actions.map((a) => (
                <button
                  key={a.label}
                  type="button"
                  className={a.kind === "primary" ? "btn btn-primary" : a.kind === "danger" ? "btn btn-danger" : "btn"}
                  data-autofocus={a.autoFocus ? "" : undefined}
                  disabled={a.disabled}
                  onClick={a.onClick}
                >
                  {a.label}
                  {a.hint && <kbd className="keycap keycap-inline">{a.hint}</kbd>}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </dialog>
  );
}

/** "Báo lỗi câu hỏi": five reasons and a note; only offered once the answer has been shown. */
export function ReportItemDialog({ open, onClose, itemId, sessionId }: { open: boolean; onClose: () => void; itemId: string; sessionId: string }) {
  const toast = useToast();
  const [reason, setReason] = useState<ItemReportReason>("wrong_key");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const noteId = useId();

  async function send() {
    setBusy(true);
    setError(null);
    try {
      await getApi().practice.reportItem(itemId, { session_id: sessionId, reason, note: note.trim() || undefined });
      toast("Đã gửi báo lỗi. Cảm ơn bạn, mentor sẽ xem lại câu này.", "ok");
      setNote("");
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PracticeDialog
      open={open}
      title="Báo lỗi câu hỏi"
      onClose={onClose}
      actions={[
        { label: "Đóng", onClick: onClose, autoFocus: true },
        { label: busy ? "Đang gửi…" : "Gửi báo lỗi", onClick: send, kind: "primary", disabled: busy },
      ]}
    >
      <fieldset>
        <legend>Câu này có vấn đề gì?</legend>
        <div className="choice-grid">
          {REPORT_REASONS.map((r) => (
            <label key={r.id} className="choice">
              <input type="radio" name="reason" checked={reason === r.id} onChange={() => setReason(r.id as ItemReportReason)} />
              <span className="choice-title">{r.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="field">
        <label htmlFor={noteId}>Ghi chú thêm (không bắt buộc)</label>
        <textarea id={noteId} className="textarea" rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}
    </PracticeDialog>
  );
}
