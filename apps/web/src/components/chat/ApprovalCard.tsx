"use client";

import type { ApprovalCardState } from "@/lib/chat/reducer";
import { formatDateTime, formatTime } from "@/lib/format";
import type { ApprovalDecisionValue, ApprovalScope } from "@/lib/types";

const ACTION_LABELS: Record<string, string> = {
  "calendar.create_event": "Tạo sự kiện lịch",
  "calendar.update_event": "Sửa sự kiện lịch",
  "calendar.delete_event": "Xoá sự kiện lịch",
  "zotero.add_item": "Thêm paper vào Zotero",
  "email.send": "Gửi email",
};

const DETAIL_LABELS: Record<string, string> = {
  calendar: "Lịch",
  start: "Bắt đầu",
  end: "Kết thúc",
  title: "Tiêu đề",
  location: "Địa điểm",
  description: "Mô tả",
  nhac_truoc: "Nhắc trước",
  to: "Người nhận",
  subject: "Tiêu đề",
};

function fmtValue(v: unknown): string {
  if (typeof v === "string") {
    if (/^\d{4}-\d{2}-\d{2}T/.test(v)) return formatDateTime(v);
    return v;
  }
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

const STATUS_TEXT: Record<ApprovalCardState["status"], string> = {
  pending: "Đang chờ bạn quyết định",
  approved: "Đã đồng ý",
  denied: "Đã từ chối",
  expired: "Đã hết hạn",
};

export function ApprovalCard({
  card,
  onDecide,
  onDismiss,
}: {
  card: ApprovalCardState;
  onDecide: (id: string, d: ApprovalDecisionValue, s: ApprovalScope) => void;
  onDismiss: (id: string) => void;
}) {
  const a = card.approval;
  const titleId = `ap-${a.approval_id}`;
  const entries = Object.entries(a.details ?? {});
  return (
    <section className="approval" data-status={card.status} aria-labelledby={titleId}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong id={titleId}>{ACTION_LABELS[a.action] ?? a.action}</strong>
        <span className={`badge ${card.status === "pending" ? "badge-warn" : card.status === "approved" ? "badge-ok" : ""}`}>
          {STATUS_TEXT[card.status]}
          {card.status === "approved" && card.scope === "session" ? " (cả phiên)" : ""}
        </span>
      </div>
      <p style={{ margin: "6px 0 0" }}>{a.summary}</p>
      {entries.length > 0 && (
        <dl>
          {entries.map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{DETAIL_LABELS[k] ?? k}</dt>
              <dd>{fmtValue(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {card.status === "pending" ? (
        <>
          <div className="hint">Hết hạn lúc {formatTime(a.expires_at)}</div>
          <div className="actions">
            <button type="button" className="btn btn-primary btn-sm" onClick={() => onDecide(a.approval_id, "approve", "once")}>
              Đồng ý
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onDecide(a.approval_id, "approve", "session")}
              title="Không hỏi lại hành động này trong phiên trò chuyện hiện tại"
            >
              Đồng ý cả phiên
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onDecide(a.approval_id, "deny", "once")}>
              Từ chối
            </button>
          </div>
        </>
      ) : (
        <div className="actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onDismiss(a.approval_id)}>
            Ẩn
          </button>
        </div>
      )}
    </section>
  );
}
