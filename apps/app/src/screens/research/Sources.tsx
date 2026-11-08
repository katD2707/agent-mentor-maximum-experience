import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { researchApi, ResearchError, type SearchDepth, type SourceKeysStatus, type SourceName } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";

/**
 * The optional paper sources (Semantic Scholar, Asta): one status for the whole app, one key dialog.
 * The dialog opens from the research search, the related papers and Settings ("Nguồn tìm paper").
 */
export const SOURCE_NAMES: Record<SourceName, string> = { s2: "Semantic Scholar", asta: "Asta" };
const HELP: Record<SourceName, string> = { asta: "https://allenai.org/asta", s2: "https://www.semanticscholar.org/product/api#api-key-form" };
const TOAST_MS = 2600;

/** Search depth, picked like a reasoning-effort level: each level adds one source and needs its key. */
export const DEPTHS = ["quick", "thorough", "deep"] as const satisfies readonly SearchDepth[];
export const DEPTH_NEEDS: (SourceName | null)[] = [null, "s2", "asta"];
const DEPTH_KEY = "mentor.researchDepth";
function savedDepth(): number {
  try {
    const i = DEPTHS.indexOf(localStorage.getItem(DEPTH_KEY) as SearchDepth);
    return i < 0 ? 2 : i; // never picked: the deepest level whose key is there
  } catch {
    return 2;
  }
}

export interface SourcesCtx {
  status: SourceKeysStatus;
  connected(src: SourceName): boolean;
  /** opens the key dialog; `thenDepth` is picked once that key is saved */
  open(src: SourceName, opener?: HTMLElement | null, thenDepth?: number): void;
  /** the chosen level, lowered to the deepest one whose key is there */
  depth: number;
  setDepth(i: number): void;
}
const Ctx = createContext<SourcesCtx | null>(null);

/** null outside the provider (everyone but the university band): the settings row and chips then do not show. */
export const useSourceKeys = () => useContext(Ctx);

interface Dlg {
  src: SourceName;
  mode: "enter" | "connected";
  busy: boolean;
  value: string;
  error: string;
}

export function SourceKeysProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const { t } = useTranslation();
  const [status, setStatus] = useState<SourceKeysStatus>({ asta_connected: false, s2_connected: false });
  const [dlg, setDlg] = useState<Dlg | null>(null);
  const [toast, setToast] = useState("");
  const [depthPref, setDepthPref] = useState(savedDepth);
  const pendingDepth = useRef(-1);
  const opener = useRef<HTMLElement | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    researchApi.sourceKeys(token).then(
      (s) => alive && setStatus(s),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [token]);
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const connected = useCallback((src: SourceName) => (src === "s2" ? status.s2_connected : status.asta_connected), [status]);
  let depth = depthPref;
  while (depth > 0 && !connected(DEPTH_NEEDS[depth] as SourceName)) depth--;
  const setDepth = useCallback((i: number) => {
    setDepthPref(i);
    try {
      localStorage.setItem(DEPTH_KEY, DEPTHS[i]);
    } catch {
      /* private window: the level just isn't remembered */
    }
  }, []);
  const say = (msg: string) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), TOAST_MS);
  };
  const open = useCallback(
    (src: SourceName, from?: HTMLElement | null, thenDepth?: number) => {
      opener.current = from ?? (document.activeElement as HTMLElement | null);
      pendingDepth.current = thenDepth !== undefined && DEPTH_NEEDS[thenDepth] === src ? thenDepth : -1;
      setDlg({ src, mode: connected(src) ? "connected" : "enter", busy: false, value: "", error: "" });
    },
    [connected],
  );
  const close = useCallback(() => {
    setDlg(null);
    const el = opener.current;
    if (el && document.contains(el)) el.focus();
  }, []);

  const save = async () => {
    if (!dlg || dlg.busy || !token) return;
    const name = SOURCE_NAMES[dlg.src];
    if (!dlg.value.trim()) return setDlg({ ...dlg, error: t("research.sources.empty", { name }) });
    const cur = dlg;
    setDlg({ ...cur, busy: true, error: "" });
    try {
      const s = await researchApi.putSourceKey(token, cur.src, cur.value.trim());
      setStatus(s);
      if (pendingDepth.current >= 0) setDepth(pendingDepth.current);
      pendingDepth.current = -1;
      close();
      say(t("research.sources.added", { name }));
    } catch (e) {
      const code = e instanceof ResearchError ? e.code : "unknown";
      const msg = code === "invalid_key" ? t("research.sources.invalid") : code === "source_unreachable" ? t("research.sources.unreachable") : code === "rate_limited" ? t("research.sources.rateLimited") : t("research.sources.failed");
      setDlg((d) => (d ? { ...d, busy: false, error: msg } : d));
    }
  };
  const remove = async () => {
    if (!dlg || !token) return;
    const name = SOURCE_NAMES[dlg.src];
    const src = dlg.src;
    setDlg({ ...dlg, busy: true });
    try {
      setStatus(await researchApi.deleteSourceKey(token, src));
      close();
      say(t("research.sources.removed", { name }));
    } catch {
      setDlg((d) => (d ? { ...d, busy: false, error: t("research.sources.failed") } : d));
    }
  };

  const value = useMemo<SourcesCtx>(() => ({ status, connected, open, depth, setDepth }), [status, connected, open, depth, setDepth]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {dlg && <KeyDialog dlg={dlg} setDlg={setDlg} onClose={close} onSave={save} onRemove={remove} />}
      {toast && createPortal(<div className="rs-toast" role="status">{toast}</div>, document.body)}
    </Ctx.Provider>
  );
}

function KeyDialog({ dlg, setDlg, onClose, onSave, onRemove }: { dlg: Dlg; setDlg: (d: Dlg) => void; onClose: () => void; onSave: () => void; onRemove: () => void }) {
  const { t } = useTranslation();
  const back = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [shown, setShown] = useState(false);
  const name = SOURCE_NAMES[dlg.src];
  const connected = dlg.mode === "connected";

  // everything behind the dialog is inert while it is open
  useEffect(() => {
    const others = [...document.body.children].filter((n) => n !== back.current && !(n as HTMLElement).inert) as HTMLElement[];
    others.forEach((n) => (n.inert = true));
    return () => others.forEach((n) => (n.inert = false));
  }, []);

  // focus: the key field, or the main button once connected; again after a failed check
  useEffect(() => {
    if (dlg.busy) return;
    (input.current ?? box.current?.querySelector<HTMLElement>(".btn-primary") ?? box.current)?.focus();
  }, [dlg.mode, dlg.busy, dlg.error]);

  const stateRef = useRef({ busy: dlg.busy, onClose });
  stateRef.current = { busy: dlg.busy, onClose };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        if (!stateRef.current.busy) stateRef.current.onClose();
        return;
      }
      if (e.key !== "Tab" || !box.current) return;
      const f = [...box.current.querySelectorAll<HTMLElement>("a[href],button,input")].filter((n) => !(n as HTMLButtonElement).disabled);
      if (!f.length) {
        e.preventDefault();
        box.current.focus();
        return;
      }
      const first = f[0];
      const last = f[f.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === box.current)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, []);

  return createPortal(
    <div className="rs-back" ref={back} onMouseDown={(e) => e.target === back.current && !dlg.busy && onClose()}>
      <div className="rs-dlg" ref={box} role="dialog" aria-modal="true" aria-labelledby="rs-dlg-t" aria-describedby="rs-dlg-d" tabIndex={-1}>
        <div className="rs-dlg-head">
          <h2 id="rs-dlg-t">{connected ? name : t("research.sources.add", { name })}</h2>
          {connected && (
            <button type="button" className="icon-btn rs-dlg-x" aria-label={t("research.sources.close")} onClick={onClose}>
              <Icon name="x" />
            </button>
          )}
        </div>
        <p id="rs-dlg-d" className="rs-dlg-desc">
          {t(`research.sources.${connected ? "on" : "new"}.${dlg.src}`)}
        </p>
        {!connected && (
          <div className="rs-dlg-field">
            <label htmlFor="rs-key" className="set-label">
              {t("research.sources.keyLabel", { name })}
            </label>
            <div className={"rs-keybox" + (dlg.error ? " bad" : "")}>
              <input
                id="rs-key"
                ref={input}
                type={shown ? "text" : "password"}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                placeholder={t("research.sources.paste")}
                value={dlg.value}
                disabled={dlg.busy}
                aria-invalid={dlg.error ? true : undefined}
                aria-describedby={dlg.error ? "rs-key-err" : undefined}
                onChange={(e) => setDlg({ ...dlg, value: e.target.value, error: "" })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    onSave();
                  }
                }}
              />
              <button type="button" className="rs-eye" aria-pressed={shown} aria-label={t(shown ? "research.sources.hideKey" : "research.sources.showKey")} onClick={() => setShown((s) => !s)}>
                <Icon name="eye" />
              </button>
            </div>
            <p id="rs-key-err" className="rs-keyerr" role="alert">
              {dlg.error && <span>{dlg.error}</span>}
            </p>
            <a className="rs-help" href={HELP[dlg.src]} target="_blank" rel="noopener noreferrer">
              {t("research.sources.where")}
            </a>
          </div>
        )}
        {connected && dlg.error && (
          <p className="rs-keyerr" role="alert">
            {dlg.error}
          </p>
        )}
        <div className="rs-dlg-actions">
          {connected ? (
            <>
              <button type="button" className="btn btn-ghost rs-danger" disabled={dlg.busy} onClick={onRemove}>
                {t("research.sources.remove", { name })}
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setDlg({ ...dlg, mode: "enter", value: "", error: "" })}>
                {t("research.sources.change")}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn btn-ghost" disabled={dlg.busy} onClick={onClose}>
                {t("research.sources.cancel")}
              </button>
              <button type="button" className="btn btn-primary" disabled={dlg.busy} aria-busy={dlg.busy || undefined} onClick={onSave}>
                {dlg.busy ? (
                  <>
                    <span className="rs-spin" aria-hidden="true" />
                    {t("research.sources.checking")}
                  </>
                ) : (
                  t("research.sources.save")
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** The dashed "+ Semantic Scholar" / "Semantic Scholar ✓" chip; opens the key dialog. */
export function SourceChip({ src }: { src: SourceName }) {
  const { t } = useTranslation();
  const ctx = useSourceKeys();
  if (!ctx) return null;
  const on = ctx.connected(src);
  const name = SOURCE_NAMES[src];
  return (
    <button
      className="rs-srcchip"
      type="button"
      data-on={on ? "1" : "0"}
      aria-haspopup="dialog"
      aria-label={on ? t("research.sources.chipOn", { name }) : t("research.sources.add", { name })}
      onClick={(e) => ctx.open(src, e.currentTarget)}
    >
      <span className="pill">
        {on ? (
          <>
            {name} <Icon name="check" />
          </>
        ) : (
          <>
            <Icon name="plus" /> {name}
          </>
        )}
      </span>
    </button>
  );
}

/** "Nguồn tìm paper" row of the settings popover; nothing outside the university band. */
export function SettingsSourcesRow({ onOpen, returnTo }: { onOpen?: () => void; returnTo?: React.RefObject<HTMLElement | null> }) {
  const { t } = useTranslation();
  const ctx = useSourceKeys();
  const { user } = useAuth();
  if (!ctx || user?.age_band !== "uni") return null;
  return (
    <div className="set-row set-srcs" data-guide="research-sources">
      <span className="set-label">{t("research.sources.row")}</span>
      <span className="set-src">
        <span>
          arXiv <span className="muted">{t("research.sources.always")}</span>
        </span>
      </span>
      {(["s2", "asta"] as const).map((src) => {
        const on = ctx.connected(src);
        const name = SOURCE_NAMES[src];
        return (
          <span className="set-src" key={src}>
            <span>
              {name}: <span className="muted">{t(on ? "research.sources.stateOn" : "research.sources.stateOff")}</span>
            </span>
            <button
              type="button"
              className="set-srcbtn"
              aria-label={t(on ? "research.sources.removeAria" : "research.sources.add", { name })}
              onClick={(e) => {
                onOpen?.();
                ctx.open(src, returnTo?.current ?? e.currentTarget);
              }}
            >
              {t(on ? "research.sources.removeShort" : "research.sources.addShort")}
            </button>
          </span>
        );
      })}
    </div>
  );
}
