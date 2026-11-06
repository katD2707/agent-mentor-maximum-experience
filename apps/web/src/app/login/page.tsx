"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";
import { getApi, getMock, isApiError, IS_MOCK } from "@/lib/api";
import { homePath, useDesktopMode } from "@/lib/desktop";
import type { Persona } from "@/lib/api/mock/seed";
import { PERSONA_LABELS } from "@/lib/api/mock/seed";
import { useSession } from "@/components/session";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ErrorBox } from "@/components/ui";
import { HeroMascot } from "@/components/Mascot";

export default function LoginPage() {
  const { status, me, refresh } = useSession();
  const router = useRouter();
  const desktop = useDesktopMode();
  const emailId = useId();
  const codeId = useId();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [sent, setSent] = useState<{ email: string; devLink?: string; devCode?: string } | null>(null);
  const [code, setCode] = useState("");
  const [codeBusy, setCodeBusy] = useState(false);
  const [codeError, setCodeError] = useState<unknown>(null);
  const [persona, setPersona] = useState<Persona>(() => getMock()?.state.persona ?? "thpt");

  useEffect(() => {
    if (status === "ready" && me) router.replace(me.onboarding_state === "active" ? homePath() : "/onboarding");
  }, [status, me, router]);

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    if (!sent || !/^\d{6}$/.test(code)) return;
    setCodeBusy(true);
    setCodeError(null);
    try {
      await getApi().verifyCode(sent.email, code);
      await refresh(); // the effect above moves on to the chat or onboarding
    } catch (err) {
      setCodeError(
        isApiError(err, 400)
          ? new Error("Mã không đúng hoặc đã hết hạn. Sai 5 lần thì mã bị huỷ: hãy gửi lại email để nhận mã mới.")
          : err,
      );
    } finally {
      setCodeBusy(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const mock = getMock();
      if (mock && mock.state.persona !== persona) mock.resetPersona(persona, false);
      const r = await getApi().requestLink(email.trim());
      setSent({ email: email.trim(), devLink: r.dev_link, devCode: r.dev_code });
      setCode("");
      setCodeError(null);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="auth-card">
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
          <h1>Đăng nhập</h1>
          <p className="muted">
            {desktop
              ? "Nhập email, chúng tôi sẽ gửi cho bạn một mã đăng nhập 6 số. Không cần mật khẩu."
              : "Nhập email, chúng tôi sẽ gửi cho bạn một liên kết đăng nhập. Không cần mật khẩu."}
          </p>

          {sent ? (
            <div>
              <div className="alert alert-ok" role="status" aria-live="polite">
                Đã gửi email đăng nhập tới <strong>{sent.email}</strong>.{" "}
                {desktop
                  ? "Nhập mã 6 số trong email vào ô bên dưới."
                  : "Bấm vào liên kết trong email, hoặc nhập mã 6 số trong email vào ô bên dưới."}
              </div>
              <form onSubmit={submitCode} className="stack" style={{ marginBottom: 12 }}>
                {codeError != null && <ErrorBox error={codeError} />}
                <div className="field" style={{ marginBottom: 0 }}>
                  <label htmlFor={codeId}>Nhập mã 6 số</label>
                  <input
                    id={codeId}
                    className="input code-input"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    required
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="000000"
                  />
                </div>
                <button type="submit" className="btn btn-primary" disabled={codeBusy || code.length !== 6} style={{ width: "100%" }}>
                  {codeBusy ? "Đang kiểm tra…" : "Đăng nhập bằng mã"}
                </button>
              </form>
              {sent.devCode && (
                <div className="alert alert-warn">
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Môi trường dev: mã đăng nhập</div>
                  <span className="row" style={{ gap: 8 }}>
                    <code>{sent.devCode}</code>
                    <button type="button" className="btn btn-sm" onClick={() => setCode(sent.devCode ?? "")}>
                      Điền mã
                    </button>
                  </span>
                </div>
              )}
              {sent.devLink && !desktop && (
                <div className="alert alert-warn">
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Môi trường dev: liên kết đăng nhập</div>
                  <a href={sent.devLink} style={{ overflowWrap: "anywhere" }}>
                    {sent.devLink}
                  </a>
                </div>
              )}
              <button type="button" className="btn" onClick={() => setSent(null)}>
                Dùng email khác
              </button>
            </div>
          ) : (
            <form onSubmit={submit} noValidate={false}>
              {error != null && <ErrorBox error={error} />}
              <div className="field">
                <label htmlFor={emailId}>Email</label>
                <input
                  id={emailId}
                  className="input"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="ten@example.com"
                />
              </div>
              {IS_MOCK && (
                <fieldset>
                  <legend>Dữ liệu mẫu (chế độ mock)</legend>
                  <div className="stack">
                    {(Object.keys(PERSONA_LABELS) as Persona[]).map((p) => (
                      <label key={p} className="choice">
                        <input type="radio" name="persona" value={p} checked={persona === p} onChange={() => setPersona(p)} />
                        <span>{PERSONA_LABELS[p]}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              )}
              <button type="submit" className="btn btn-primary" disabled={busy || !email.trim()} style={{ width: "100%" }}>
                {busy ? "Đang gửi…" : desktop ? "Gửi mã đăng nhập" : "Gửi liên kết đăng nhập"}
              </button>
            </form>
          )}
        </main>
      </div>
    </div>
  );
}
