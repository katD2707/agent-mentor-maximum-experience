"use client";

import { useEffect, useRef, type ComponentProps } from "react";
import { useReducedMotion } from "@/lib/motion";
import { Icon } from "../Icon";
import { NotificationCenter } from "./NotificationCenter";

type CenterProps = Omit<ComponentProps<typeof NotificationCenter>, "onMarkRead">;

/**
 * Bell in the chat header: a badge with the unread count and a popover with the notification list (and its
 * existing actions). Opening marks everything read. Closes on Escape or a click outside.
 */
export function NotificationBell({
  open,
  onOpenChange,
  onMarkRead,
  ...center
}: CenterProps & { open: boolean; onOpenChange: (open: boolean) => void; onMarkRead: () => void }) {
  const reduce = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const unread = center.notifications.filter((n) => !n.read).length;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onOpenChange(false);
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [open, onOpenChange]);

  return (
    <div className="bell-wrap" ref={box}>
      <button
        type="button"
        className="btn btn-ghost btn-icon btn-sm bell-btn"
        aria-expanded={open}
        aria-controls="notif-pop"
        aria-label={unread > 0 ? `Thông báo, ${unread} mới` : "Thông báo"}
        title="Thông báo"
        onClick={() => {
          onOpenChange(!open);
          if (!open) onMarkRead();
        }}
      >
        <span className="bell" data-ring={unread > 0 && !reduce ? true : undefined}>
          <Icon name="bell" size={16} />
        </span>
        {unread > 0 && (
          <span className="bell-badge" aria-hidden="true">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="notif-pop" id="notif-pop" role="dialog" aria-label="Thông báo">
          <NotificationCenter {...center} onMarkRead={onMarkRead} />
        </div>
      )}
    </div>
  );
}
