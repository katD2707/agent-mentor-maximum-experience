"use client";

import { useEffect, useId, useRef, useState } from "react";
import { getApi } from "@/lib/api";
import { historyToMessages } from "@/lib/chat/reducer";
import { scrollToMessage, type MessageFocus } from "@/lib/conversationNav";
import { formatDate, localDateStamp } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, Loading } from "../ui";
import { MessageView } from "./Message";

export function shiftDate(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Read-only transcript of an earlier day from GET /chat/history?date=; `focus` (a search hit) picks the day and message. */
export function HistoryDialog({ open, onClose, focus = null }: { open: boolean; onClose: () => void; focus?: MessageFocus | null }) {
  const ref = useRef<HTMLDialogElement>(null);
  const dateId = useId();
  const today = localDateStamp();
  const [date, setDate] = useState(() => shiftDate(localDateStamp(), -1));
  const [prevFocus, setPrevFocus] = useState(focus);
  if (focus !== prevFocus) {
    setPrevFocus(focus);
    if (focus?.date) setDate(focus.date);
  }

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  // Days that have a transcript (sessions/YYYY-MM-DD/); best effort.
  const days = useAsync(
    () =>
      open
        ? getApi()
            .getTree("sessions")
            .then((t) =>
              t
                .filter((e) => e.type === "dir" && /^sessions\/\d{4}-\d{2}-\d{2}$/.test(e.path))
                .map((e) => e.path.slice("sessions/".length))
                .sort()
                .reverse(),
            )
            .catch(() => [] as string[])
        : Promise.resolve([] as string[]),
    [open],
  );
  const hist = useAsync(() => (open ? getApi().getChatHistory(date) : Promise.resolve(null)), [open, date]);
  const messages = hist.data ? historyToMessages(hist.data, date) : [];

  useEffect(() => {
    if (open && focus && focus.date === date && !hist.loading) scrollToMessage(ref.current, focus.ts);
  }, [open, focus, date, hist.loading, messages.length]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      style={{ maxWidth: "min(720px, calc(100vw - 32px))" }}
      aria-labelledby="hist-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h2 id="hist-title" style={{ margin: 0 }}>
          Trò chuyện ngày {formatDate(date)}
        </h2>
        <button type="button" className="btn btn-sm" onClick={onClose}>
          Đóng
        </button>
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <button type="button" className="btn btn-sm" onClick={() => setDate((d) => shiftDate(d, -1))}>
          ← Ngày trước
        </button>
        <label htmlFor={dateId} className="sr-only">
          Chọn ngày
        </label>
        <input
          id={dateId}
          type="date"
          className="input"
          style={{ width: 170, minHeight: 30, padding: "2px 8px" }}
          value={date}
          max={today}
          onChange={(e) => e.target.value && setDate(e.target.value)}
        />
        <button type="button" className="btn btn-sm" disabled={date >= today} onClick={() => setDate((d) => shiftDate(d, 1))}>
          Ngày sau →
        </button>
      </div>
      {days.data && days.data.length > 0 && (
        <div className="row" style={{ gap: 4, marginBottom: 12 }} aria-label="Các ngày có trò chuyện">
          {days.data.slice(0, 10).map((d) => (
            <button
              key={d}
              type="button"
              className={d === date ? "btn btn-sm btn-primary" : "btn btn-sm btn-ghost"}
              aria-pressed={d === date}
              onClick={() => setDate(d)}
            >
              {formatDate(d).slice(0, 5)}
            </button>
          ))}
        </div>
      )}
      <div style={{ maxHeight: "60vh", overflowY: "auto", display: "flex", flexDirection: "column", gap: 12, padding: 2 }}>
        {hist.error != null && <ErrorBox error={hist.error} onRetry={hist.reload} />}
        {hist.loading && <Loading />}
        {!hist.loading && hist.error == null && messages.length === 0 && <p className="empty">Không có trò chuyện nào trong ngày này.</p>}
        {!hist.loading && messages.map((m) => <MessageView key={m.id} m={m} />)}
      </div>
    </dialog>
  );
}
