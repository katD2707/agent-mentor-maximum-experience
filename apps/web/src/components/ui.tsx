"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { isApiError } from "@/lib/api";
import type { MascotState } from "@/lib/types";
import { Mascot } from "./Mascot";

/**
 * Loading state. In content areas a skeleton holds the layout (no jump when content lands); full screen keeps a
 * small spinner with a visible label, since there is no layout to predict yet. Both announce `label`.
 */
export function Loading({ full = false, label = "Đang tải…", lines = 3 }: { full?: boolean; label?: string; lines?: number }) {
  if (full) {
    return (
      <div className="center-screen">
        <div className="row muted" role="status" aria-live="polite" style={{ padding: 16 }}>
          <span className="spinner" aria-hidden="true" /> {label}
        </div>
      </div>
    );
  }
  const widths = ["92%", "78%", "56%", "84%", "64%"];
  return (
    <div className="skeleton" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton-line" style={{ width: widths[i % widths.length] }} aria-hidden="true" />
      ))}
    </div>
  );
}

/** Empty state with the mascot waving once (then resting). */
export function EmptyState({ children, card = false }: { children: ReactNode; card?: boolean }) {
  const [state, setState] = useState<MascotState>("wave");
  return (
    <div className={card ? "card empty empty-state" : "empty empty-state"}>
      <Mascot state={state} size={44} onDone={() => setState("idle")} />
      <div>{children}</div>
    </div>
  );
}

export function errorText(e: unknown): string {
  if (isApiError(e)) {
    if (e.status === 0) return "Không kết nối được tới máy chủ. Kiểm tra mạng rồi thử lại.";
    if (e.status === 401) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
    if (e.status === 403) return e.message && !e.message.startsWith("HTTP") ? e.message : "Bạn không có quyền thực hiện thao tác này.";
    if (e.status === 404) return "Không tìm thấy nội dung.";
    return e.message;
  }
  if (e instanceof Error) return e.message;
  return String(e);
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="alert alert-error" role="alert">
      <div className="row">
        <span className="spacer">{errorText(error)}</span>
        {onRetry && (
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            Thử lại
          </button>
        )}
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  );
}

/** Native <dialog> confirmation with focus trapping and Esc to cancel. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  danger = false,
  busy = false,
  confirmDisabled = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
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
      className="dialog"
      aria-labelledby="dlg-title"
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
    >
      <h2 id="dlg-title">{title}</h2>
      <div style={{ marginBottom: 16 }}>{children}</div>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn" onClick={onCancel} disabled={busy}>
          Huỷ
        </button>
        <button
          type="button"
          className={danger ? "btn btn-danger" : "btn btn-primary"}
          onClick={onConfirm}
          disabled={busy || confirmDisabled}
        >
          {busy ? "Đang xử lý…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
