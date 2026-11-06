"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { getApi, getMock, IS_MOCK } from "@/lib/api";
import { homePath, useDesktopMode } from "@/lib/desktop";
import { formatDateTime } from "@/lib/format";
import { useInterval } from "@/lib/hooks";
import type { Language, ParentLinkStart, ParentLinkState, Role } from "@/lib/types";
import { QrCode } from "@/components/QrCode";
import { useSession } from "@/components/session";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ErrorBox, Loading } from "@/components/ui";
import { HeroMascot } from "@/components/Mascot";

const CODE_KEY = "mentor-parent-code";

function RoleStep() {
  const { me, setMe } = useSession();
  const nameId = useId();
  const langId = useId();
  const [role, setRole] = useState<Role | null>(null);
  const [name, setName] = useState(me?.display_name ?? "");
  const [language, setLanguage] = useState<Language>(me?.language ?? "vi");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!role) return;
    setBusy(true);
    setError(null);
    try {
      setMe(await getApi().completeOnboarding({ role, display_name: name.trim(), language }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = !!role && name.trim().length > 0 && (role !== "thpt" || agree) && !busy;

  return (
    <form onSubmit={submit}>
      <h1>Chào bạn! Mình làm quen nhé</h1>
      <p className="muted">Mentor sẽ điều chỉnh cách đồng hành theo thông tin này. Bạn có thể đổi ngôn ngữ sau trong Cài đặt.</p>
      {error != null && <ErrorBox error={error} />}
      <fieldset>
        <legend>Bạn là</legend>
        <div className="choice-grid">
          <label className="choice">
            <input type="radio" name="role" value="thpt" checked={role === "thpt"} onChange={() => setRole("thpt")} required />
            <span>
              <span className="choice-title">Học sinh THPT</span>
              <br />
              <span className="choice-desc">Ôn tập, kế hoạch học, theo dõi mức độ thành thạo. Cần phụ huynh liên kết.</span>
            </span>
          </label>
          <label className="choice">
            <input type="radio" name="role" value="ncs" checked={role === "ncs"} onChange={() => setRole("ncs")} />
            <span>
              <span className="choice-title">Nghiên cứu sinh / Sinh viên</span>
              <br />
              <span className="choice-desc">Luận văn, đọc paper, họp GVHD, deadline. Không có báo cáo phụ huynh.</span>
            </span>
          </label>
        </div>
      </fieldset>
      <div className="field">
        <label htmlFor={nameId}>Tên hiển thị</label>
        <input
          id={nameId}
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoComplete="nickname"
          required
          maxLength={60}
          placeholder="Ví dụ: Lan Anh"
          aria-describedby={`${nameId}-hint`}
        />
        <span className="hint" id={`${nameId}-hint`}>
          Mentor sẽ gọi bạn bằng tên này.
        </span>
      </div>
      <div className="field">
        <label htmlFor={langId}>Ngôn ngữ mentor dùng khi trò chuyện</label>
        <select id={langId} className="select" value={language} onChange={(e) => setLanguage(e.target.value as Language)}>
          <option value="vi">Tiếng Việt</option>
          <option value="en">English</option>
        </select>
      </div>
      {role === "thpt" && (
        <div className="alert alert-info">
          <p style={{ fontWeight: 600 }}>Điều khoản dành cho học sinh THPT</p>
          <ul style={{ margin: "0 0 8px", paddingLeft: 20 }}>
            <li>Phụ huynh cần liên kết qua Zalo trước khi bạn bắt đầu trò chuyện.</li>
            <li>
              Hai tuần một lần, phụ huynh nhận báo cáo về tiến độ mục tiêu, mức độ đều đặn và xu hướng theo chủ đề.{" "}
              <strong>Không có điểm từng bài, không có nội dung trò chuyện hay nhật ký.</strong>
            </li>
            <li>
              Nếu hệ thống ghi nhận dấu hiệu nguy hiểm nghiêm trọng, phụ huynh nhận một cảnh báo ngắn, không kèm nội dung trò
              chuyện.
            </li>
            <li>Bạn xem được mọi báo cáo đã gửi trong mục “Báo cáo phụ huynh”.</li>
          </ul>
          <label className="row" style={{ alignItems: "flex-start", color: "var(--text)", flexWrap: "nowrap" }}>
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ marginTop: 5 }} />
            <span>Mình đã đọc và đồng ý với các điều trên.</span>
          </label>
        </div>
      )}
      <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
        {busy ? "Đang lưu…" : "Tiếp tục"}
      </button>
    </form>
  );
}

const STATUS_STEPS: { key: ParentLinkState; label: string }[] = [
  { key: "pending", label: "Chờ phụ huynh gửi mã cho bot" },
  { key: "awaiting_consent", label: "Phụ huynh đã gửi mã, chờ phụ huynh đồng ý" },
  { key: "verified", label: "Phụ huynh đã xác nhận" },
];

function readSavedCode(): ParentLinkStart | null {
  try {
    const raw = sessionStorage.getItem(CODE_KEY);
    return raw ? (JSON.parse(raw) as ParentLinkStart) : null;
  } catch {
    return null;
  }
}

function ParentStep() {
  const { refresh, me } = useSession();
  const home = homePath(useDesktopMode());
  const [link, setLink] = useState<ParentLinkStart | null>(null);
  const [status, setStatus] = useState<ParentLinkState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const newCode = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const l = await getApi().startParentLink();
      setLink(l);
      setStatus("pending");
      try {
        sessionStorage.setItem(CODE_KEY, JSON.stringify(l));
      } catch {
        // ignore
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, []);

  // Reuse a still-valid code from this tab; create one only if no consent is in progress.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = await getApi().getParentLink();
        if (!alive) return;
        setStatus(s.status);
        const saved = readSavedCode();
        if (saved && Date.parse(saved.expires_at) > Date.now() && s.status !== "none") setLink(saved);
        else if (s.status === "none" || s.status === "pending") await newCode();
      } catch (e) {
        if (alive) setError(e);
      }
    })();
    return () => {
      alive = false;
    };
  }, [newCode]);

  const verified = status === "verified" || me?.onboarding_state === "active";

  const poll = useCallback(async () => {
    try {
      const s = await getApi().getParentLink();
      setStatus(s.status);
      if (s.status === "verified") {
        try {
          sessionStorage.removeItem(CODE_KEY);
        } catch {
          // ignore
        }
        await refresh();
      }
    } catch {
      // transient; keep polling
    }
  }, [refresh]);

  useInterval(poll, 3000, !verified);

  const devVerify = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await getApi().devVerifyParent();
      await poll();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, [poll]);

  const idx = verified ? 2 : STATUS_STEPS.findIndex((s) => s.key === status);

  return (
    <div>
      <h1>Liên kết với phụ huynh</h1>
      <p className="muted">
        Trò chuyện với mentor sẽ mở khi phụ huynh xác nhận qua Zalo. Mã dùng một lần và hết hạn sau 24 giờ.
      </p>
      {error != null && <ErrorBox error={error} />}

      {!verified && link && (
        <div className="stack">
          <div>
            <div className="field-label" id="code-label">
              Mã liên kết
            </div>
            <div className="code-display" aria-labelledby="code-label">
              {link.link_code}
            </div>
            <div className="hint" style={{ textAlign: "center", marginTop: 4 }}>
              Hết hạn lúc {formatDateTime(link.expires_at)}
            </div>
          </div>
          <div className={link.bot_url ? "grid-2" : undefined} style={{ alignItems: "center" }}>
            {link.bot_url && (
              <div className="qr-box">
                <QrCode value={link.bot_url} label={`Mã QR mở Zalo Bot ${link.bot_name}`} size={168} />
                <span className="hint">Phụ huynh quét bằng Zalo</span>
              </div>
            )}
            <ol style={{ paddingLeft: 20, margin: 0 }}>
              <li>
                {link.bot_url ? "Phụ huynh mở Zalo, quét mã QR hoặc tìm bot " : "Phụ huynh mở Zalo, tìm bot "}
                <strong>{link.bot_name}</strong>.
              </li>
              <li>Gửi mã 6 số ở trên cho bot.</li>
              <li>Đọc giới thiệu và trả lời “ĐỒNG Ý”.</li>
            </ol>
          </div>
          <div className="row">
            {link.bot_url && (
              <a className="btn" href={link.bot_url} target="_blank" rel="noopener noreferrer">
                Mở {link.bot_name}
              </a>
            )}
            <button type="button" className="btn btn-ghost" onClick={() => void newCode()} disabled={busy}>
              Tạo mã mới
            </button>
            {link.dev_verify && (
              <button type="button" className="btn btn-ghost" onClick={() => void devVerify()} disabled={busy}>
                Bỏ qua bước phụ huynh (chỉ dev)
              </button>
            )}
          </div>
        </div>
      )}
      {!verified && !link && status === "awaiting_consent" && (
        <p className="alert alert-info">Phụ huynh đã gửi mã. Đang chờ phụ huynh trả lời “ĐỒNG Ý” trên Zalo.</p>
      )}
      {!link && !verified && status !== "awaiting_consent" && error == null && <Loading />}

      <h2 style={{ marginTop: 20 }}>Trạng thái</h2>
      <ul className="status-list" aria-live="polite">
        {STATUS_STEPS.map((s, i) => (
          <li key={s.key} data-state={i < idx || verified ? "done" : i === idx ? "current" : "todo"}>
            <span className="dot" aria-hidden="true" />
            {s.label}
            {i === idx && !verified && <span className="spinner" role="img" aria-label="đang chờ" />}
          </li>
        ))}
      </ul>

      {IS_MOCK && !verified && (
        <div className="alert alert-warn">
          Mock: trạng thái tự chuyển sau vài giây.{" "}
          <button type="button" className="btn btn-sm" onClick={() => getMock()?.advanceParentLink()}>
            Giả lập bước tiếp theo
          </button>
        </div>
      )}

      {verified ? (
        <Link className="btn btn-primary" href={home}>
          Bắt đầu trò chuyện
        </Link>
      ) : (
        <>
          <button type="button" className="btn btn-primary" disabled aria-describedby="locked-hint">
            Bắt đầu trò chuyện
          </button>
          <p id="locked-hint" className="hint" style={{ marginTop: 6 }}>
            Trò chuyện đang khoá cho đến khi phụ huynh xác nhận.
          </p>
        </>
      )}
    </div>
  );
}

export default function OnboardingPage() {
  const { status, me } = useSession();
  const router = useRouter();
  const home = homePath(useDesktopMode());

  useEffect(() => {
    if (status === "anon") router.replace("/login");
  }, [status, router]);

  if (status !== "ready" || !me) return <Loading full />;

  const totalSteps = me.role === "ncs" ? 1 : 2;
  const step = me.onboarding_state === "needs_role" ? 1 : totalSteps;

  return (
    <div className="center-screen">
      <div className="auth-card" style={{ maxWidth: 640 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              M
            </span>
            Mentor
          </div>
          <ThemeToggle compact />
        </div>
        <main className="card">
          <HeroMascot />
          <ol className="steps" aria-label={`Bước ${step} / ${totalSteps}`}>
            {Array.from({ length: totalSteps }, (_, i) => (
              <li key={i} data-done={i < step} />
            ))}
          </ol>
          {me.onboarding_state === "needs_role" && <RoleStep />}
          {me.onboarding_state !== "needs_role" && me.role === "thpt" && <ParentStep />}
          {me.onboarding_state === "active" && me.role === "ncs" && (
            <div>
              <h1>Xong rồi!</h1>
              <p className="muted">Workspace của bạn đã sẵn sàng.</p>
              <Link className="btn btn-primary" href={home}>
                Bắt đầu trò chuyện
              </Link>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
