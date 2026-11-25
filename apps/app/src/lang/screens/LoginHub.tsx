import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { ChickenGuide } from "../guide/ChickenGuide";
import { TeacherArt } from "./TeacherArt";
import { CodeBoxes, errKey, HubAlert, HubBoard, HubLinks, Info, Pill, type HubErr } from "./hub-ui";

type View = "login" | "create" | "student" | "teacher" | "forgot" | "code" | "nomail" | "sent";
const base = import.meta.env.BASE_URL;

const USERNAME = /^[a-z0-9][a-z0-9._-]{1,31}$/;
const MAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const GRADES = [...Array.from({ length: 12 }, (_, i) => String(i + 1)), "dh"];

/** "Nguyễn Lan" -> "nguyenlan": no accents, lowercase, letters and digits only (the child can still edit it). */
export const slugName = (n: string) =>
  n
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/gi, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .slice(0, 32);

interface Err {
  key: HubErr;
  /** ids of the boxes to paint red */
  on: string[];
  soft?: boolean;
}

/**
 * Login with the hub on (mockups/lg-00): one box for username or email, sign-up by role (student form with grade
 * buttons and an optional parent email, teacher form), and forgot password by code or by a request to the teachers.
 * The role is not asked at login. A teacher who just signed up lands on the gate (TeacherGate), not here.
 */
export function LoginHub() {
  const { t } = useTranslation();
  const { login, register } = useAuth();
  const [view, setView] = useState<View>("login");
  const [err, setErr] = useState<Err | null>(null);
  const [busy, setBusy] = useState(false);
  const [changed, setChanged] = useState(false); // "Đã đổi mật khẩu" note on the login view

  const [acc, setAcc] = useState("");
  const [pw, setPw] = useState("");
  // student
  const [sName, setSName] = useState("");
  const [sUser, setSUser] = useState("");
  const [userDirty, setUserDirty] = useState(false);
  const [sPw, setSPw] = useState("");
  const [grade, setGrade] = useState("");
  const [sMail, setSMail] = useState("");
  const [asking, setAsking] = useState(false);
  // teacher
  const [tMail, setTMail] = useState("");
  const [tUser, setTUser] = useState("");
  const [tName, setTName] = useState("");
  const [tPw, setTPw] = useState("");
  // forgot
  const [fAcc, setFAcc] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [code, setCode] = useState("");
  const [nPw, setNPw] = useState("");
  const [phone, setPhone] = useState("");
  const [cooling, setCooling] = useState(false);
  const mailRef = useRef<HTMLInputElement>(null);

  const go = (v: View) => {
    setErr(null);
    setAsking(false);
    setView(v);
  };
  const fail = (key: HubErr, on: string[] = []) => setErr({ key, on });
  const bad = (id: string) => !!err && !err.soft && err.on.includes(id);
  const clear = () => err && setErr(null);
  const empty = (pairs: [string, string][]) => {
    const miss = pairs.filter(([, v]) => !v.trim()).map(([id]) => id);
    if (miss.length) fail("empty", miss);
    return miss.length > 0;
  };

  /** `on`: the boxes a failure paints red; `mailBox`: the one for `email_taken`. */
  const run = async (job: () => Promise<void>, on: string[] = [], mailBox?: string) => {
    setBusy(true);
    try {
      await job();
    } catch (e) {
      const key = errKey(e);
      if (key === "email_taken" && mailBox) fail(key, [mailBox]);
      else if (key === "username_taken") fail(key, on.slice(0, 1));
      else fail(key, key === "wrong" || key === "bad_request" || key === "wrong_code" ? on : []);
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setErr(null);
    switch (view) {
      case "login": {
        if (empty([["acc", acc], ["pw", pw]])) return;
        await run(() => login(acc.trim(), pw).then(() => undefined), ["acc", "pw"]);
        return;
      }
      case "student": {
        if (empty([["s-name", sName], ["s-user", sUser], ["s-pw", sPw]])) return;
        if (!USERNAME.test(sUser.trim().toLowerCase())) return fail("bad_request", ["s-user"]);
        if (sPw.length < 6) return fail("short", ["s-pw"]);
        if (!grade) return fail("grade", ["s-grade"]);
        if (sMail.trim() && !MAIL.test(sMail.trim())) return fail("email", ["s-mail"]);
        if (!sMail.trim() && !asking) {
          setAsking(true); // the parent email is optional, but say what it is for before skipping it
          return;
        }
        await doStudent();
        return;
      }
      case "teacher": {
        if (empty([["t-mail", tMail], ["t-user", tUser], ["t-name", tName], ["t-pw", tPw]])) return;
        if (!MAIL.test(tMail.trim())) return fail("email", ["t-mail"]);
        if (!USERNAME.test(tUser.trim().toLowerCase())) return fail("bad_request", ["t-user"]);
        if (tPw.length < 6) return fail("short", ["t-pw"]);
        await run(
          () => register!(tUser.trim().toLowerCase(), tPw, "teacher", { display_name: tName.trim(), email: tMail.trim().toLowerCase() }).then(() => undefined),
          ["t-user"],
          "t-mail",
        );
        return;
      }
      case "forgot": {
        if (empty([["f-acc", fAcc]])) return;
        await run(async () => {
          const r = await api.forgot!(fAcc.trim());
          if (r.via === "email") {
            setSentTo(r.to ?? "");
            setCode("");
            setNPw("");
            go("code");
          } else go("nomail");
        }, ["f-acc"]);
        return;
      }
      case "code": {
        if (code.length < 6) return setErr({ key: "wrong_code", on: ["code"] });
        if (nPw.length < 6) return fail("short", ["n-pw"]);
        await run(async () => {
          await api.reset!(fAcc.trim(), code, nPw);
          setChanged(true);
          setPw("");
          setAcc(fAcc.trim());
          go("login");
        }, ["code"]);
        return;
      }
      case "nomail": {
        const ph = phone.replace(/[\s.-]/g, "");
        if (ph && !/^\+?\d{9,12}$/.test(ph)) return fail("phone", ["r-phone"]);
        await run(async () => {
          await api.forgotRequest!(fAcc.trim(), ph || undefined);
          go("sent");
        });
        return;
      }
      case "sent":
        setChanged(false);
        go("login");
    }
  };

  const doStudent = () =>
    run(
      () =>
        register!(sUser.trim().toLowerCase(), sPw, "student", {
          display_name: sName.trim(),
          grade,
          ...(sMail.trim() ? { parent_email: sMail.trim().toLowerCase() } : {}),
        }).then(() => undefined),
      ["s-user"],
    );

  const resend = async () => {
    if (cooling) return;
    setCooling(true);
    setTimeout(() => setCooling(false), 4000);
    try {
      await api.forgot!(fAcc.trim());
      setErr({ key: "sent", on: [], soft: true });
    } catch (e) {
      fail(errKey(e));
    }
  };

  const ribbon =
    view === "login" ? t("lg.hub.title.login") : view === "create" || view === "student" || view === "teacher" ? t("lg.hub.title.create") : view === "code" ? t("lg.hub.title.newPw") : view === "sent" ? t("lg.hub.title.sent") : t("lg.hub.title.forgot");
  const goLabel: Record<View, string | null> = {
    login: t("lg.hub.title.login"),
    create: null,
    student: t("lg.hub.title.create"),
    teacher: t("lg.hub.title.create"),
    forgot: t("lg.hub.forgot.send"),
    code: t("lg.hub.forgot.change"),
    nomail: t("lg.hub.forgot.request"),
    sent: t("lg.hub.forgot.toLogin"),
  };
  const links: Record<View, { label: string; onClick(): void; disabled?: boolean }[]> = {
    login: [
      { label: t("lg.hub.link.create"), onClick: () => go("create") },
      { label: t("lg.hub.link.forgot"), onClick: () => (setFAcc(acc), go("forgot")) },
    ],
    create: [{ label: t("lg.hub.link.login"), onClick: () => go("login") }],
    student: [
      { label: t("lg.hub.link.changeRole"), onClick: () => go("create") },
      { label: t("lg.hub.link.login"), onClick: () => go("login") },
    ],
    teacher: [
      { label: t("lg.hub.link.changeRole"), onClick: () => go("create") },
      { label: t("lg.hub.link.login"), onClick: () => go("login") },
    ],
    forgot: [{ label: t("lg.hub.link.login"), onClick: () => go("login") }],
    code: [{ label: t("lg.hub.forgot.resend"), onClick: () => void resend(), disabled: cooling }],
    nomail: [{ label: t("lg.hub.link.back"), onClick: () => go("forgot") }],
    sent: [],
  };

  const alertText = err ? t(`lg.hub.err.${err.key}`) : null;

  return (
    <HubBoard ribbon={ribbon} onSubmit={(e) => void submit(e)} footer={<ChickenGuide screen="login" />}>
      {view === "login" && (
        <div className="hub-stack">
          <div className="lg-welcome">
            <span className="lg-hen" aria-hidden="true">
              <img src={`${base}ga/toan.webp`} alt="" />
            </span>
            <p>
              <b>{t("lg.login.welcome")}</b>
            </p>
          </div>
          {changed && (
            <div className="hub-note-ok" role="status">
              <Icon name="check" />
              <span>{t("lg.hub.doneNote")}</span>
            </div>
          )}
          <div className="lg-fields">
            <Pill id="acc" label={t("lg.hub.account")} icon="user" value={acc} onChange={(v) => (setAcc(v), clear())} bad={bad("acc")} autoComplete="username" />
            <Pill id="pw" label={t("lg.hub.password")} icon="lock" value={pw} onChange={(v) => (setPw(v), clear())} bad={bad("pw")} autoComplete="current-password" password />
          </div>
        </div>
      )}

      {view === "create" && (
        <div className="lg-roles" role="group" aria-label={t("lg.hub.role.aria")}>
          <button type="button" className="lg-role" onClick={() => go("student")}>
            <img src={`${base}ga/hs-nam.png`} alt="" />
            <b>{t("lg.hub.role.student")}</b>
          </button>
          <button type="button" className="lg-role" onClick={() => go("teacher")}>
            <TeacherArt />
            <b>{t("lg.hub.role.teacher")}</b>
          </button>
        </div>
      )}

      {view === "student" && (
        <div className="lg-fields">
          <Pill
            id="s-name"
            label={t("lg.hub.student.name")}
            icon="user"
            value={sName}
            onChange={(v) => {
              setSName(v);
              if (!userDirty) setSUser(slugName(v));
              clear();
            }}
            bad={bad("s-name")}
            autoComplete="nickname"
          />
          <Pill
            id="s-user"
            label={t("lg.hub.student.user")}
            icon="user"
            small
            value={sUser}
            onChange={(v) => {
              setSUser(v);
              setUserDirty(!!v);
              clear();
            }}
            bad={bad("s-user")}
            autoComplete="username"
          />
          <Pill id="s-pw" label={t("lg.hub.password")} icon="lock" value={sPw} onChange={(v) => (setSPw(v), clear())} bad={bad("s-pw")} hint={t("lg.hub.student.pwHint")} autoComplete="new-password" password />
          <div className="lg-field">
            <span className="hub-grade-label" id="grade-l">
              {t("lg.hub.student.grade")}
            </span>
            <div className={"hub-grades" + (bad("s-grade") ? " bad" : "")} role="radiogroup" aria-labelledby="grade-l">
              {GRADES.map((g) => (
                <button
                  key={g}
                  type="button"
                  role="radio"
                  aria-checked={grade === g}
                  className={"hub-grade" + (g === "dh" ? " wide" : "")}
                  onClick={() => (setGrade(g), clear())}
                >
                  {g === "dh" ? t("lg.hub.student.uni") : g}
                </button>
              ))}
            </div>
          </div>
          <Pill
            id="s-mail"
            label={t("lg.hub.student.mail")}
            icon="mail"
            type="email"
            value={sMail}
            onChange={(v) => (setSMail(v), setAsking(false), clear())}
            bad={bad("s-mail")}
            hint={t("lg.hub.student.mailHint")}
            autoComplete="email"
            inputRef={mailRef}
          />
          {asking && (
            <div className="hub-ask" role="alertdialog" aria-label={t("lg.hub.student.mail")}>
              <span>{t("lg.hub.student.askText")}</span>
              <span className="two">
                <button
                  type="button"
                  className="lg-submit"
                  onClick={() => {
                    setAsking(false);
                    mailRef.current?.focus();
                  }}
                >
                  {t("lg.hub.student.askAdd")}
                </button>
                <button type="button" className="hub-ghost" disabled={busy} onClick={() => void doStudent()}>
                  {t("lg.hub.student.askSkip")}
                </button>
              </span>
            </div>
          )}
        </div>
      )}

      {view === "teacher" && (
        <div className="lg-fields">
          <Pill id="t-mail" label={t("lg.hub.teacher.mail")} icon="mail" type="email" value={tMail} onChange={(v) => (setTMail(v), clear())} bad={bad("t-mail")} placeholder={t("lg.hub.teacher.mailPh")} autoComplete="email" />
          <Pill id="t-user" label={t("lg.hub.teacher.user")} icon="user" value={tUser} onChange={(v) => (setTUser(v), clear())} bad={bad("t-user")} autoComplete="username" />
          <Pill id="t-name" label={t("lg.hub.teacher.name")} icon="user" value={tName} onChange={(v) => (setTName(v), clear())} bad={bad("t-name")} autoComplete="nickname" />
          <Pill id="t-pw" label={t("lg.hub.password")} icon="lock" value={tPw} onChange={(v) => (setTPw(v), clear())} bad={bad("t-pw")} hint={t("lg.hub.student.pwHint")} autoComplete="new-password" password />
        </div>
      )}

      {view === "forgot" && (
        <div className="lg-fields">
          <Pill id="f-acc" label={t("lg.hub.account")} icon="user" value={fAcc} onChange={(v) => (setFAcc(v), clear())} bad={bad("f-acc")} autoComplete="username" />
        </div>
      )}

      {view === "code" && (
        <div className="hub-stack">
          <Info>
            <p>
              {t("lg.hub.forgot.sentTo")} <b>{sentTo}</b>
            </p>
          </Info>
          <CodeBoxes value={code} onChange={(v) => (setCode(v), clear())} bad={bad("code")} />
          <div className="lg-fields">
            <Pill id="n-pw" label={t("lg.hub.forgot.newPw")} icon="lock" value={nPw} onChange={(v) => (setNPw(v), clear())} bad={bad("n-pw")} autoComplete="new-password" password />
          </div>
        </div>
      )}

      {view === "nomail" && (
        <div className="hub-stack">
          <Info icon="user" title={t("lg.hub.forgot.noMail")}>
            <p>
              {t("lg.hub.forgot.username")}: <b>{fAcc.trim()}</b>
            </p>
          </Info>
          <div className="lg-fields">
            <Pill id="r-phone" label={t("lg.hub.forgot.phone")} icon="user" type="tel" inputMode="tel" value={phone} onChange={(v) => (setPhone(v), clear())} bad={bad("r-phone")} hint={t("lg.hub.forgot.optional")} autoComplete="tel" />
          </div>
        </div>
      )}

      {view === "sent" && <Info icon="check" title={t("lg.hub.forgot.done")} />}

      <HubAlert text={alertText} soft={err?.soft} />

      {goLabel[view] && !asking && (
        <button className="lg-submit" type="submit" disabled={busy}>
          {goLabel[view]}
        </button>
      )}
      <HubLinks items={links[view]} />
    </HubBoard>
  );
}
