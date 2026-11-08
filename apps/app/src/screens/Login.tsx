import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, type Role } from "../api";
import { useAuth } from "../state/auth";
import { setLang } from "../i18n";
import { Icon } from "../components/Icon";
import { StudentArt, TeacherArt } from "../components/Illustrations";

type ErrKey = "noRole" | "role_mismatch" | "invalid_credentials" | "network" | "unknown";

export function Login() {
  const { t, i18n } = useTranslation();
  const { login } = useAuth();
  const [role, setRole] = useState<Role | null>(null);
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<ErrKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [shake, setShake] = useState(false);
  const roleRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const roles: Role[] = ["student", "teacher"];

  const pick = (r: Role) => {
    setRole(r);
    if (error === "noRole" || error === "role_mismatch") setError(null);
  };

  const onRoleKey = (e: React.KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const next = role === "student" ? 1 : 0;
    roleRefs.current[next]?.focus();
    pick(roles[next]);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!role) {
      setError("noRole");
      setShake(false);
      requestAnimationFrame(() => setShake(true));
      roleRefs.current[0]?.focus();
      return;
    }
    setBusy(true);
    try {
      await login(account, password, role);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "unknown";
      setError(code === "role_mismatch" || code === "invalid_credentials" || code === "network" ? code : "unknown");
      setBusy(false);
    }
  };

  const bad = error === "invalid_credentials";
  const lang = i18n.language === "en" ? "en" : "vi";

  return (
    <div className="stage">
      <div className="lang-mini" role="group" aria-label={t("login.language")}>
        <button type="button" aria-pressed={lang === "vi"} onClick={() => setLang("vi")}>
          VI
        </button>
        <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>
          EN
        </button>
      </div>

      <form className="card oli" onSubmit={submit} noValidate>
        <span className="logo">
          <span className="logo-mark">M</span>
          <span>Mentor</span>
        </span>

        <div className={"roles" + (shake ? " shake" : "")} data-guide="login-role" data-guide-label={t("login.role")} role="radiogroup" aria-label={t("login.role")} onKeyDown={onRoleKey}>
          {roles.map((r, i) => (
            <button
              key={r}
              ref={(el) => {
                roleRefs.current[i] = el;
              }}
              type="button"
              className="role"
              role="radio"
              aria-checked={role === r}
              aria-label={t(`login.${r}`)}
              tabIndex={role === r || (role === null && i === 0) ? 0 : -1}
              onClick={() => pick(r)}
            >
              <span className="tick" aria-hidden="true">
                <Icon name="check" />
              </span>
              {r === "student" ? <StudentArt /> : <TeacherArt />}
            </button>
          ))}
        </div>

        <div className="fields">
          <div className="field">
            <label htmlFor="acc">{t("login.account")}</label>
            <div className={"pill" + (bad ? " bad" : "")}>
              <Icon name="user" />
              <input
                id="acc"
                name="acc"
                autoComplete="username"
                autoCapitalize="off"
                spellCheck={false}
                value={account}
                onChange={(e) => {
                  setAccount(e.target.value);
                  if (bad) setError(null);
                }}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="pw">{t("login.password")}</label>
            <div className={"pill" + (bad ? " bad" : "")}>
              <Icon name="lock" />
              <input
                id="pw"
                name="pw"
                type={show ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (bad) setError(null);
                }}
              />
              <button type="button" className="eye" aria-pressed={show} aria-label={show ? t("login.hidePassword") : t("login.showPassword")} onClick={() => setShow(!show)}>
                <Icon name="eye" />
              </button>
            </div>
          </div>
        </div>

        {error && (
          <div className="alert" role="alert">
            <Icon name="x" />
            <span>{t(`login.errors.${error}`)}</span>
          </div>
        )}

        <button className="btn btn-primary btn-big submit" type="submit" disabled={busy}>
          {t("login.submit")}
        </button>
      </form>
    </div>
  );
}
