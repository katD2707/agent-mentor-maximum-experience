"use client";

import { toast } from "sonner";
import type { ChatNotification } from "@/lib/chat/reducer";
import { sanitizeMascot } from "@/lib/mascot";
import { primaryActionId } from "@/lib/nudges";
import { Icon } from "../Icon";
import { Mascot } from "../Mascot";

/** Rich nudge in a Sonner toast: mascot, title, body and up to three action buttons. Never makes a sound. */
export function NudgeToast({
  n,
  onAction,
  onClose,
}: {
  n: ChatNotification;
  onAction: (action: string) => void;
  onClose: () => void;
}) {
  const actions = n.actions ?? [];
  const primary = primaryActionId(actions);
  const titleId = `nudge-t-${n.id}`;
  return (
    <div className="nudge" role="group" aria-labelledby={titleId}>
      <Mascot state={sanitizeMascot(n.mascot, "idle")} size={40} />
      <div className="nudge-main">
        <p className="nudge-title" id={titleId}>
          {n.title || "Mentor"}
        </p>
        {(n.body || (!n.title && n.text)) && <p className="nudge-body">{n.body || n.text}</p>}
        {n.bundled ? <p className="nudge-bundled">và {n.bundled} lời nhắc khác trong Bảng phụ</p> : null}
        {actions.length > 0 && (
          <div className="nudge-actions">
            {actions.map((a) => (
              <button
                key={a.id}
                type="button"
                className={`btn btn-sm ${a.id === primary ? "btn-primary" : a.id === "snooze_1h" ? "btn-ghost" : ""}`}
                onClick={() => onAction(a.id)}
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <button type="button" className="btn btn-ghost btn-icon btn-sm nudge-close" aria-label="Đóng thông báo" onClick={onClose}>
        <Icon name="close" size={14} />
      </button>
    </div>
  );
}

/** Pops a nudge toast; `onAction` gets the action id and the toast closes itself. */
export function showNudgeToast(n: ChatNotification, onAction: (n: ChatNotification, action: string) => void) {
  const id = `nudge-${n.serverId ?? n.id}`;
  toast.custom(
    (tid) => (
      <NudgeToast
        n={n}
        onAction={(a) => {
          toast.dismiss(tid);
          onAction(n, a);
        }}
        onClose={() => toast.dismiss(tid)}
      />
    ),
    // Actions keep it open longer; it never blocks anything and also lives in the notification centre.
    { id, duration: n.actions?.length ? 12_000 : 7000, unstyled: true, className: "toast-nudge" },
  );
}
