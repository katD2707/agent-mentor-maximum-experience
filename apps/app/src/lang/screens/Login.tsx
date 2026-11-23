import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, type Role } from "../../api";
import { useAuth } from "../../state/auth";
import { setLang } from "../../i18n";
import { Icon } from "../../components/Icon";
import { ChickenGuide } from "../guide/ChickenGuide";
import "../styles/fonts";
import "../styles/lang.css";

type ErrKey = "required" | "role_mismatch" | "invalid_credentials" | "network" | "unknown" | "short" | "username_taken" | "bad_request";
const base = import.meta.env.BASE_URL;

/** The teacher picture of the login board (glasses, cardigan, book, small chalkboard). */
function TeacherArt() {
  return (
    <svg viewBox="0 0 140 170" aria-hidden="true">
      <rect x="84" y="30" width="48" height="36" rx="4" fill="#24453A" stroke="#8A5A2B" strokeWidth="3" />
      <path d="M92 44 h8 M96 40 v8 M106 44 h8 M92 56 q6 -6 12 0 t12 0" stroke="#E9F2EC" strokeWidth="2" fill="none" strokeLinecap="round" />
      <rect x="49" y="112" width="13" height="46" rx="4" fill="#3B3F4A" />
      <rect x="66" y="112" width="13" height="46" rx="4" fill="#3B3F4A" />
      <rect x="40" y="62" width="48" height="58" rx="13" fill="#12825A" />
      <path d="M56 64 L64 80 L72 64" fill="#fff" />
      <rect x="30" y="86" width="26" height="20" rx="3" fill="#4B2EBF" transform="rotate(6 43 96)" />
      <path d="M88 82 L112 62" stroke="#8A5A2B" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="64" cy="40" r="18" fill="#E2AE85" />
      <path d="M46 40 C44 20 84 18 82 40 C80 30 74 26 64 26 C54 26 48 30 46 40 Z" fill="#4A3A35" />
      <rect x="53" y="38" width="10" height="7" rx="2.5" fill="none" stroke="#2B2321" strokeWidth="1.8" />
      <rect x="66" y="38" width="10" height="7" rx="2.5" fill="none" stroke="#2B2321" strokeWidth="1.8" />
      <path d="M63 41 h3" stroke="#2B2321" strokeWidth="1.8" />
      <path d="M59 51 Q64 55 69 51" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/** Login (mockups/lg-00): pick who you are, then log in. Same flow and errors as the old screen. */
export function LgLogin() {
  const { t, i18n } = useTranslation();
  const { login, register, signupEnabled } = useAuth();
  const [role, setRole] = useState<Role>("student"); // most people here are students: the role is picked already
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<ErrKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [canSignup, setCanSignup] = useState(false); // only the self-contained desktop package has local sign-up
  const [creating, setCreating] = useState(false);
  const roleRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const accRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);
  const roles: Role[] = ["student", "teacher"];
  const lang = i18n.language === "en" ? "en" : "vi";

  useEffect(() => {
    let live = true;
    if (register) void signupEnabled().then((on) => live && setCanSignup(on));
    return () => {
      live = false;
    };
  }, [register, signupEnabled]);

  const pick = (r: Role) => {
    setRole(r);
    if (error === "role_mismatch") setError(null);
  };
  const onRoleKey = (e: KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const next = role === "student" ? 1 : 0;
    roleRefs.current[next]?.focus();
    pick(roles[next]);
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    // both boxes are needed: say so here, do not send an empty login and answer "wrong password"
    const empty = !account.trim() ? accRef.current : !password ? pwRef.current : null;
    if (empty) {
      setError("required");
      empty.focus();
      return;
    }
    if (creating && password.length < 6) {
      setError("short");
      pwRef.current?.focus();
      return;
    }
    setBusy(true);
    try {
      if (creating && register) await register(account, password, role);
      else await login(account, password, role);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "unknown";
      const known: ErrKey[] = creating ? ["username_taken", "bad_request", "network"] : ["role_mismatch", "invalid_credentials", "network"];
      setError(known.find((k) => k === code) ?? "unknown");
      setBusy(false);
    }
  };
  const switchMode = (on: boolean) => {
    setCreating(on);
    setError(null);
  };
  const bad = error === "invalid_credentials" || error === "username_taken" || error === "bad_request";
  const missing = (v: string) => error === "required" && !v.trim();

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

        <form className="lg-board" id="lg-login" onSubmit={submit} noValidate>
          <h1 className="lg-ribbon-t">{creating ? t("lg.login.signup") : t("login.submit")}</h1>
          <div className="lg-welcome">
            <span className="lg-hen" aria-hidden="true">
              <img src={`${base}ga/toan.png`} alt="" />
            </span>
            <p>
              <b>{t("lg.login.welcome")}</b>
              <span>{creating ? t("lg.login.signupPick") : t("lg.login.pick")}</span>
            </p>
          </div>

          <div className="lg-roles" role="radiogroup" aria-label={t("login.role")} onKeyDown={onRoleKey}>
            {roles.map((r, i) => (
              <button
                key={r}
                ref={(el) => {
                  roleRefs.current[i] = el;
                }}
                type="button"
                className="lg-role"
                role="radio"
                aria-checked={role === r}
                aria-label={t(`login.${r}`)}
                tabIndex={role === r ? 0 : -1}
                onClick={() => pick(r)}
              >
                <span className="lg-tick" aria-hidden="true">
                  <Icon name="check" />
                </span>
                {r === "student" ? <img src={`${base}ga/hs-nam.png`} alt="" /> : <TeacherArt />}
                <b>{t(`login.${r}`)}</b>
              </button>
            ))}
          </div>

          <div className="lg-fields">
            <div className="lg-field" id="lg-f-acc">
              <label htmlFor="acc">{t("login.account")}</label>
              <div className={"lg-pill" + (bad || missing(account) ? " bad" : "")}>
                <Icon name="user" />
                <input
                  ref={accRef}
                  id="acc"
                  name="acc"
                  autoComplete="username"
                  autoCapitalize="off"
                  spellCheck={false}
                  value={account}
                  onChange={(e) => {
                    setAccount(e.target.value);
                    if (bad || error === "required") setError(null);
                  }}
                />
              </div>
            </div>
            <div className="lg-field" id="lg-f-pw">
              <label htmlFor="pw">{t("login.password")}</label>
              <div className={"lg-pill" + (bad || missing(password) ? " bad" : "")}>
                <Icon name="lock" />
                <input
                  ref={pwRef}
                  id="pw"
                  name="pw"
                  type={show ? "text" : "password"}
                  autoComplete={creating ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (bad || error === "required") setError(null);
                  }}
                />
                <button type="button" className="lg-eye" aria-pressed={show} aria-label={show ? t("login.hidePassword") : t("login.showPassword")} onClick={() => setShow(!show)}>
                  <Icon name="eye" />
                </button>
              </div>
            </div>
          </div>

          {error && (
            <div className="lg-alert" role="alert">
              <Icon name="x" />
              <span>{error === "required" || error === "short" || error === "username_taken" || error === "bad_request" ? t(`lg.login.${error}`) : t(`login.errors.${error}`)}</span>
            </div>
          )}

          <button className="lg-submit" type="submit" disabled={busy}>
            {creating ? t("lg.login.signup") : t("login.submit")}
          </button>
          {canSignup && (
            <p className="lg-switch">
              {creating ? t("lg.login.haveAccount") : t("lg.login.noAccount")}{" "}
              <button type="button" className="lg-link" onClick={() => switchMode(!creating)}>
                {creating ? t("login.submit") : t("lg.login.signup")}
              </button>
            </p>
          )}
        </form>
      </div>
      <ChickenGuide screen="login" />
    </div>
  );
}
