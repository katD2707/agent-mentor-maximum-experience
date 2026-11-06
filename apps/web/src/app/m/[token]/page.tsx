"use client";

import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { getApi } from "@/lib/api";
import { errorText } from "@/components/ui";

/**
 * Phone upload page opened from the QR code (no session; the token authorises
 * POST /m/{token}). The gateway's upload_url should point here.
 */
export default function MobileUploadPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      const paths: string[] = [];
      for (const f of files) paths.push((await getApi().mobileUpload(token, f, f.name)).path);
      setDone((d) => [...d, ...paths]);
      setFiles([]);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <main className="auth-card card">
        <h1>Gửi ảnh cho mentor</h1>
        <p className="muted">Chụp bài làm, đề bài hoặc chọn ảnh có sẵn. Tệp sẽ được đưa vào hộp thư đến của bạn.</p>
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}
        {done.length > 0 && (
          <div className="alert alert-ok" role="status">
            Đã gửi {done.length} tệp. Quay lại máy tính để tiếp tục trò chuyện, hoặc gửi thêm.
          </div>
        )}
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="mfile">Chọn hoặc chụp ảnh</label>
            <input
              id="mfile"
              className="input"
              type="file"
              accept="image/*,application/pdf"
              capture="environment"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            {files.length > 0 && <span className="hint">Đã chọn {files.length} tệp</span>}
          </div>
          <button type="submit" className="btn btn-primary" disabled={busy || files.length === 0} style={{ width: "100%" }}>
            {busy ? "Đang gửi…" : "Gửi"}
          </button>
        </form>
      </main>
    </div>
  );
}
