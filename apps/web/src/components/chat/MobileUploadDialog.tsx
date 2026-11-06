"use client";

import { useEffect, useRef, useState } from "react";
import { getApi } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { ChatAttachment, MobileToken, TreeEntry } from "@/lib/types";
import { QrCode } from "../QrCode";
import { errorText } from "../ui";
import { guessMime } from "./useUploads";

/**
 * Shows a QR for POST /uploads/mobile-token and watches inbox/ for files that arrive
 * from the phone, so they can be attached to the next message.
 */
export function MobileUploadDialog({ open, onClose, onAttach }: { open: boolean; onClose: () => void; onAttach: (a: ChatAttachment) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [token, setToken] = useState<MobileToken | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [arrived, setArrived] = useState<TreeEntry[]>([]);
  const baseline = useRef<Set<string> | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    baseline.current = null;
    (async () => {
      try {
        const [t, tree] = await Promise.all([getApi().createMobileToken(), getApi().getTree("inbox")]);
        if (!alive) return;
        baseline.current = new Set(tree.map((e) => e.path));
        setToken(t);
        setArrived([]);
        setError(null);
      } catch (e) {
        if (alive) setError(errorText(e));
      }
    })();
    const poll = setInterval(async () => {
      if (!baseline.current) return;
      try {
        const tree = await getApi().getTree("inbox");
        const fresh = tree.filter((e) => e.type === "file" && !baseline.current!.has(e.path));
        if (alive && fresh.length) setArrived(fresh);
      } catch {
        // ignore transient errors
      }
    }, 3000);
    return () => {
      alive = false;
      clearInterval(poll);
    };
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby="mobile-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <h2 id="mobile-title">Tải ảnh từ điện thoại</h2>
      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}
      {token ? (
        <div className="qr-box">
          <QrCode value={token.upload_url} label="Mã QR mở trang tải lên trên điện thoại" />
          <p className="hint" style={{ margin: 0 }}>
            Quét mã bằng camera điện thoại, chụp bài làm hoặc chọn ảnh rồi gửi. Mã hết hạn lúc {formatTime(token.expires_at)}.
          </p>
          <a href={token.upload_url} target="_blank" rel="noopener noreferrer" className="hint" style={{ overflowWrap: "anywhere" }}>
            {token.upload_url}
          </a>
        </div>
      ) : (
        !error && <p className="muted">Đang tạo mã…</p>
      )}
      <div aria-live="polite" style={{ marginTop: 12 }}>
        {arrived.length > 0 && (
          <>
            <div className="field-label">Tệp vừa nhận</div>
            <ul className="notif-list" style={{ marginTop: 6 }}>
              {arrived.map((f) => (
                <li key={f.path}>
                  <span className="spacer" style={{ overflowWrap: "anywhere" }}>
                    {f.path}
                  </span>
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={() => onAttach({ path: f.path, mime_type: guessMime(f.path) })}
                  >
                    Đính kèm
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
        <button type="button" className="btn" onClick={onClose}>
          Đóng
        </button>
      </div>
    </dialog>
  );
}
