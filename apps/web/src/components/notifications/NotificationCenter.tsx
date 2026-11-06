"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";
import type { ChatNotification } from "@/lib/chat/reducer";
import { formatTime } from "@/lib/format";
import { sanitizeMascot } from "@/lib/mascot";
import { FADE, SPRING, useReducedMotion } from "@/lib/motion";
import { primaryActionId } from "@/lib/nudges";
import { Icon } from "../Icon";
import { Mascot } from "../Mascot";

/** Notification list in the chat side panel: new items slide in, removed ones collapse, the rest glide up. */
export function NotificationCenter({
  notifications,
  quiet,
  quietRange,
  busyId,
  focusId = null,
  onAction,
  onDismiss,
  onMarkRead,
}: {
  notifications: ChatNotification[];
  quiet: boolean;
  quietRange: [string, string] | null;
  /** Notification whose action is in flight (its buttons are disabled). */
  busyId: string | null;
  /** Server id to scroll to and focus (a push click). */
  focusId?: string | null;
  onAction: (n: ChatNotification, action: string) => void;
  onDismiss: (id: string) => void;
  onMarkRead: () => void;
}) {
  const reduce = useReducedMotion();
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (!focusId) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-server-id="${CSS.escape(focusId)}"]`);
    if (!el) return;
    el.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
    el.focus({ preventScroll: true });
  }, [focusId, notifications, reduce]);
  return (
    <section aria-labelledby="nt-heading">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 id="nt-heading" style={{ margin: 0 }}>
          Thông báo
        </h2>
        {notifications.some((n) => !n.read) && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onMarkRead}>
            Đánh dấu đã đọc
          </button>
        )}
      </div>
      {quiet && quietRange && (
        <p className="quiet-note">
          <Icon name="moon" size={14} />
          <span>
            Giờ yên lặng ({quietRange[0]}–{quietRange[1]}): thông báo chỉ nằm ở đây, không bật lên.
          </span>
        </p>
      )}
      {notifications.length === 0 ? (
        <p className="hint">Chưa có thông báo. Khi mentor nhắc bạn điều gì, nó sẽ hiện ở đây.</p>
      ) : (
        <ul className="notif-list" style={{ marginTop: 8 }} ref={listRef}>
          <AnimatePresence initial={false}>
            {notifications.map((n) => {
              const actions = n.handled ? [] : (n.actions ?? []);
              const primary = primaryActionId(actions);
              return (
                <motion.li
                  key={n.id}
                  layout={reduce ? false : "position"}
                  data-read={n.read}
                  data-server-id={n.serverId}
                  data-focus={focusId !== null && n.serverId === focusId ? true : undefined}
                  tabIndex={-1}
                  initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={reduce ? { opacity: 0, transition: FADE } : { opacity: 0, x: 16, transition: { duration: 0.16 } }}
                  transition={reduce ? FADE : SPRING}
                >
                  {n.title || n.mascot ? <Mascot state={sanitizeMascot(n.mascot)} size={26} /> : <span className="notif-dot" aria-hidden="true" />}
                  <div className="notif-main">
                    {n.title && <strong className="notif-title">{n.title}</strong>}
                    <span className="notif-text">{n.body || n.text}</span>
                    {n.bundled ? <span className="notif-bundled">và {n.bundled} lời nhắc khác</span> : null}
                    <span className="faint notif-time">
                      {formatTime(n.createdAt)}
                      {n.handled && ` · ${labelFor(n, n.handled)}`}
                    </span>
                    {actions.length > 0 && (
                      <div className="notif-actions">
                        {actions.map((a) => (
                          <button
                            key={a.id}
                            type="button"
                            className={`btn btn-sm ${a.id === primary ? "btn-primary" : ""}`}
                            disabled={busyId === n.id}
                            onClick={() => onAction(n, a.id)}
                          >
                            {a.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="Xoá thông báo" onClick={() => onDismiss(n.id)}>
                    <Icon name="close" size={12} />
                  </button>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}
    </section>
  );
}

function labelFor(n: ChatNotification, action: string): string {
  return n.actions?.find((a) => a.id === action)?.label ?? "đã xử lý";
}
