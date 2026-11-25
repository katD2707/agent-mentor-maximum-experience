import { useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../../api";
import { setLang } from "../../i18n";
import { Icon, type IconName } from "../../components/Icon";
import "../styles/fonts";
import "../styles/lang.css";
import "../styles/hub.css";

/** The wooden board of lg-00 over the blurred village: language switch, ribbon title, then the stacks. */
export function HubBoard({ ribbon, children, onSubmit, id = "lg-login", footer }: { ribbon: string; children: ReactNode; onSubmit?: (e: React.FormEvent) => void; id?: string; footer?: ReactNode }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "en" ? "en" : "vi";
  return (
    <div className="lg lg-back" data-age="g10_12">
      <div className="lg-stage">
        <div className="lg-lang-mini" role="group" aria-label={t("login.language")}>
          <button type="button" aria-pressed={lang === "vi"} onClick={() => setLang("vi")}>
            VI
          </button>
          <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>
            EN
          </button>
        </div>
        <form className="lg-board hub-board" id={id} onSubmit={onSubmit ?? ((e) => e.preventDefault())} noValidate>
          <h1 className="lg-ribbon-t">{ribbon}</h1>
          {children}
        </form>
        {footer}
      </div>
    </div>
  );
}

/** One text box in the board's pill style. `bad` paints the red border. */
export function Pill({
  id,
  label,
  icon,
  value,
  onChange,
  bad,
  hint,
  small,
  type = "text",
  autoComplete,
  placeholder,
  inputRef,
  inputMode,
  password,
}: {
  id: string;
  label: string;
  icon: IconName;
  value: string;
  onChange(v: string): void;
  bad?: boolean;
  hint?: string;
  small?: boolean;
  type?: string;
  autoComplete?: string;
  placeholder?: string;
  inputRef?: RefObject<HTMLInputElement | null>;
  inputMode?: "tel" | "email" | "text";
  /** adds the eye button */
  password?: boolean;
}) {
  const { t } = useTranslation();
  const [show, setShow] = useState(false);
  return (
    <div className="lg-field">
      <label htmlFor={id}>{label}</label>
      <div className={"lg-pill" + (small ? " small" : "") + (bad ? " bad" : "")}>
        <Icon name={icon} />
        <input
          ref={inputRef}
          id={id}
          name={id}
          type={password ? (show ? "text" : "password") : type}
          inputMode={inputMode}
          autoComplete={autoComplete}
          autoCapitalize="off"
          spellCheck={false}
          placeholder={placeholder}
          value={value}
          aria-invalid={bad || undefined}
          onChange={(e) => onChange(e.target.value)}
        />
        {password && (
          <button type="button" className="lg-eye" aria-pressed={show} aria-label={show ? t("lg.hub.hide") : t("lg.hub.show")} onClick={() => setShow(!show)}>
            <Icon name="eye" />
          </button>
        )}
      </div>
      {hint && <p className="hub-hint">{hint}</p>}
    </div>
  );
}

/** Six boxes for a 6-digit code: typing moves on, Backspace goes back, a paste fills them all. */
export function CodeBoxes({ value, onChange, bad }: { value: string; onChange(v: string): void; bad?: boolean }) {
  const { t } = useTranslation();
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length: 6 }, (_, i) => value[i] ?? "");
  const set = (i: number, d: string) => {
    const next = digits.slice();
    next[i] = d;
    onChange(next.join(""));
  };
  const onKey = (i: number, e: KeyboardEvent) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
  };
  const onPaste = (e: ClipboardEvent) => {
    const d = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!d) return;
    e.preventDefault();
    onChange(d);
    refs.current[Math.min(d.length, 5)]?.focus();
  };
  return (
    <div className={"hub-code" + (bad ? " bad" : "")} role="group" aria-label={t("lg.hub.code.aria")} onPaste={onPaste}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          inputMode="numeric"
          maxLength={1}
          autoComplete="one-time-code"
          aria-label={t("lg.hub.code.digit", { n: i + 1 })}
          value={d}
          onKeyDown={(e) => onKey(i, e)}
          onChange={(e) => {
            const v = e.target.value.replace(/\D/g, "").slice(-1);
            set(i, v);
            if (v && i < 5) refs.current[i + 1]?.focus();
          }}
        />
      ))}
    </div>
  );
}

/** A centred picture-and-words block: check email, in review, rejected. */
export function Info({ icon, title, children }: { icon?: IconName; title?: ReactNode; children?: ReactNode }) {
  return (
    <div className="hub-info">
      {icon && (
        <span className="big" aria-hidden="true">
          <Icon name={icon} />
        </span>
      )}
      {title && <h2>{title}</h2>}
      {children}
    </div>
  );
}

export function HubAlert({ text, soft }: { text: string | null; soft?: boolean }) {
  if (!text) return null;
  return (
    <div className={"lg-alert" + (soft ? " soft" : "")} role={soft ? "status" : "alert"}>
      <Icon name={soft ? "check" : "x"} />
      <span>{text}</span>
    </div>
  );
}

/** The text links under the button (Quên mật khẩu?, Đăng xuất ...). */
export function HubLinks({ items }: { items: { label: string; onClick(): void; disabled?: boolean }[] }) {
  if (!items.length) return null;
  return (
    <div className="hub-links">
      {items.map((it) => (
        <button key={it.label} type="button" className="hub-link" disabled={it.disabled} onClick={it.onClick}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

/** Which message an API error gets: a key of `lg.hub.err`. */
export type HubErr = "empty" | "wrong" | "email" | "username_taken" | "email_taken" | "short" | "grade" | "wrong_code" | "phone" | "sent" | "hub_offline" | "bad_request" | "teacher_unverified" | "network" | "unknown";

export function errKey(err: unknown, wrongKey: HubErr = "wrong"): HubErr {
  if (!(err instanceof ApiError)) return "unknown";
  switch (err.code) {
    case "invalid_credentials":
      return wrongKey;
    case "username_taken":
    case "email_taken":
    case "wrong_code":
    case "hub_offline":
    case "bad_request":
    case "teacher_unverified":
    case "network":
      return err.code;
    default:
      return "unknown";
  }
}
