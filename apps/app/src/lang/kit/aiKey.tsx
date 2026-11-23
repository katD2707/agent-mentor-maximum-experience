import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { aiKeyApi, AiKeyError, type AiKeyStatus } from "../../api/aikey";
import { useAuth } from "../../state/auth";
import "../styles/aikey.css";

/**
 * "Khóa AI": every user of a standalone install enters their own AI key (Settings > Khóa AI). One provider owns the status
 * and the dialog; the Settings row, the tray and every AI screen use `useAiKey()`. `configured` is null until the first
 * answer: callers treat null as "go ahead" so a slow status call never blocks a screen.
 */
interface Ctx {
  configured: boolean | null;
  status: AiKeyStatus | null;
  open(): void;
}
const AiKeyCtx = createContext<Ctx>({ configured: null, status: null, open: () => undefined });
export const useAiKey = () => useContext(AiKeyCtx);

const KNOWN = ["bad_key", "model_not_found", "rate_limited", "network", "provider_error", "bad_base"];
const errCode = (e: unknown) => (e instanceof AiKeyError && KNOWN.includes(e.code) ? e.code : "unknown");

export function AiKeyProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [status, setStatus] = useState<AiKeyStatus | null>(null);
  const [dlg, setDlg] = useState(false);
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    aiKeyApi.get(token).then(
      (s) => alive && setStatus(s),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [token]);

  const open = useCallback(() => {
    opener.current = document.activeElement as HTMLElement | null;
    setDlg(true);
  }, []);
  const close = useCallback(() => {
    setDlg(false);
    const el = opener.current;
    if (el && document.contains(el)) el.focus();
  }, []);
  const value = useMemo<Ctx>(() => ({ configured: status ? status.configured : null, status, open }), [status, open]);
  return (
    <AiKeyCtx.Provider value={value}>
      {children}
      {dlg && token && <AiKeyDialog token={token} status={status} onStatus={setStatus} onClose={close} />}
    </AiKeyCtx.Provider>
  );
}

function AiKeyDialog({ token, status, onStatus, onClose }: { token: string; status: AiKeyStatus | null; onStatus(s: AiKeyStatus): void; onClose(): void }) {
  const { t } = useTranslation();
  const [base, setBase] = useState(status?.base ?? status?.default_base ?? "");
  const [key, setKey] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState<"" | "test" | "save" | "remove">("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const saved = !!status?.configured && status.masked_key !== null;
  const form = () => ({ base: base.trim() || undefined, key: key.trim() || undefined });

  useEffect(() => {
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const run = async (what: "test" | "save" | "remove") => {
    if (busy) return;
    if (what !== "remove" && !key.trim() && !saved) return setMsg({ ok: false, text: t("aikey.needKey") });
    setBusy(what);
    setMsg(null);
    try {
      if (what === "test") {
        const r = await aiKeyApi.test(token, form());
        setMsg(r.ok ? { ok: true, text: t("aikey.ok") } : { ok: false, text: t(`aikey.err.${KNOWN.includes(r.code) ? r.code : "unknown"}`) });
      } else if (what === "save") {
        onStatus(await aiKeyApi.save(token, form()));
        setKey("");
        setMsg({ ok: true, text: t("aikey.saved") });
      } else {
        onStatus(await aiKeyApi.remove(token));
        setKey("");
        setMsg({ ok: true, text: t("aikey.removed") });
      }
    } catch (e) {
      setMsg({ ok: false, text: t(`aikey.err.${errCode(e)}`) });
    } finally {
      setBusy("");
    }
  };

  return createPortal(
    <div className="aik-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="aik-dlg" role="dialog" aria-modal="true" aria-labelledby="aik-t" aria-describedby="aik-d">
        <div className="aik-head">
          <h2 id="aik-t">{t("aikey.title")}</h2>
          <button type="button" className="aik-x" aria-label={t("aikey.close")} onClick={onClose}>
            ×
          </button>
        </div>
        <p id="aik-d" className="aik-desc">
          {t("aikey.intro")}
        </p>
        <div className="aik-field">
          <label htmlFor="aik-base">{t("aikey.base")}</label>
          <input id="aik-base" type="url" autoComplete="off" spellCheck={false} value={base} onChange={(e) => setBase(e.target.value)} />
        </div>
        <div className="aik-field">
          <label htmlFor="aik-key">{t("aikey.key")}</label>
          {saved && (
            <p className="aik-saved">
              {t("aikey.keySaved")}: <code>{status?.masked_key}</code>
            </p>
          )}
          <div className="aik-keybox">
            <input
              id="aik-key"
              ref={input}
              type={shown ? "text" : "password"}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              placeholder={saved ? t("aikey.keyChange") : t("aikey.keyPaste")}
              value={key}
              onChange={(e) => {
                setKey(e.target.value);
                setMsg(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void run("save");
                }
              }}
            />
            <button type="button" aria-pressed={shown} onClick={() => setShown((s) => !s)}>
              {shown ? t("aikey.hide") : t("aikey.show")}
            </button>
          </div>
        </div>
        <p className={"aik-msg" + (msg ? (msg.ok ? " ok" : " bad") : "")} role={msg && !msg.ok ? "alert" : "status"}>
          {msg?.text}
        </p>
        <div className="aik-actions">
          {saved && (
            <button type="button" className="aik-danger" disabled={!!busy} onClick={() => void run("remove")}>
              {t("aikey.remove")}
            </button>
          )}
          <span className="aik-grow" />
          <button type="button" disabled={!!busy} onClick={() => void run("test")}>
            {busy === "test" ? t("aikey.testing") : t("aikey.test")}
          </button>
          <button type="button" className="aik-primary" disabled={!!busy} onClick={() => void run("save")}>
            {busy === "save" ? t("aikey.saving") : t("aikey.save")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** The one-line prompt shown in place of an AI feature while no key is saved; its button opens the dialog. */
export function AiKeyPrompt({ className }: { className?: string }) {
  const { t } = useTranslation();
  const { open } = useAiKey();
  return (
    <p className={"aik-prompt" + (className ? " " + className : "")} role="status">
      <span>{t("aikey.prompt")}</span>
      <button type="button" onClick={open}>
        {t("aikey.add")}
      </button>
    </p>
  );
}

/** The single "Khóa AI" row of a settings panel; each panel passes its own row classes. */
export function AiKeyRow({ rowClass, labelClass, buttonClass }: { rowClass: string; labelClass: string; buttonClass: string }) {
  const { t } = useTranslation();
  const { status, open } = useAiKey();
  if (status?.mode === "router") return null; // a hosted or dev server brings its own AI: nothing to enter
  return (
    <div className={rowClass} data-testid="aikey-row">
      <span className={labelClass}>{t("aikey.row")}</span>
      <button type="button" className={buttonClass} onClick={open}>
        {status?.configured ? `${t("aikey.rowOn")} ${status.masked_key ?? ""}`.trim() : t("aikey.rowOff")}
      </button>
    </div>
  );
}
