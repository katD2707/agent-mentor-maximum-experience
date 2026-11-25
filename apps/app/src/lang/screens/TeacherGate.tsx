import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, type TeacherStatus } from "../../api";
import { useAuth } from "../../state/auth";
import { CodeBoxes, errKey, HubAlert, HubBoard, HubLinks, Info, type HubErr } from "./hub-ui";

/** How often the gate asks the hub again while it waits (the owner may approve at any time). */
const POLL_MS = 30000;

/**
 * The teacher gate (mockups/lg-00, "Chờ" screens). A teacher whose `teacher_status` is not `xac_minh` sees only this, never the
 * course pages. The status comes from the gateway (which asks the hub); a correct code opens the teacher home.
 */
export function TeacherGate() {
  const { t } = useTranslation();
  const { user, token, logout, refreshMe } = useAuth();
  const [status, setStatus] = useState<TeacherStatus>(user?.teacher_status ?? "chua_nop");
  const [reason, setReason] = useState<string | null>(null);
  const [mail, setMail] = useState(user?.email ?? "");
  const [code, setCode] = useState("");
  const [err, setErr] = useState<{ key: HubErr; soft?: boolean; text?: string; codeBad?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [cooling, setCooling] = useState(false);
  const alive = useRef(true);

  const pull = useCallback(async () => {
    if (!token || !api.teacherAccount) return;
    try {
      const a = await api.teacherAccount(token);
      if (!alive.current || !a.teacher_status) return;
      setStatus(a.teacher_status);
      setReason(a.reject_reason);
      if (a.email) setMail(a.email);
      if (a.teacher_status === "xac_minh") void refreshMe();
    } catch {
      /* offline: keep what is shown, the next look tries again */
    }
  }, [token, refreshMe]);

  useEffect(() => {
    alive.current = true;
    void pull();
    const id = setInterval(() => void pull(), POLL_MS);
    const onFocus = () => void pull();
    window.addEventListener("focus", onFocus);
    return () => {
      alive.current = false;
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [pull]);

  const sent = (text: string) => setErr({ key: "sent", soft: true, text });
  const resend = async (what: "form" | "code") => {
    if (!token || cooling) return;
    setCooling(true);
    setTimeout(() => setCooling(false), 4000);
    try {
      await (what === "form" ? api.teacherResendForm?.(token) : api.teacherResendCode?.(token));
      sent(what === "form" && status === "tu_choi" ? t("lg.hub.gate.tuChoi.sent") : t("lg.hub.err.sent"));
    } catch (e) {
      setErr({ key: errKey(e) });
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !token) return;
    setErr(null);
    if (status === "tu_choi") return void resend("form");
    if (status !== "da_duyet") return;
    if (code.length < 6) return setErr({ key: "wrong_code", codeBad: true });
    setBusy(true);
    try {
      await api.teacherVerify?.(token, code);
      await refreshMe(); // a verified teacher drops out of the gate and opens the home
    } catch (er) {
      const key = errKey(er);
      setErr({ key, codeBad: key === "wrong_code" });
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const out = { label: t("lg.hub.gate.logout"), onClick: () => void logout() };
  let ribbon = t("lg.hub.gate.chuaNop.ribbon");
  let body;
  let go: string | null = null;
  let links = [{ label: t("lg.hub.gate.resendMail"), onClick: () => void resend("form"), disabled: cooling }, out];
  if (status === "cho_duyet") {
    ribbon = t("lg.hub.gate.cho.ribbon");
    body = (
      <Info icon="clock" title={t("lg.hub.gate.cho.h")}>
        <p>{t("lg.hub.gate.cho.p1")}</p>
        <p>{t("lg.hub.gate.cho.p2")}</p>
      </Info>
    );
    links = [out];
  } else if (status === "tu_choi") {
    ribbon = t("lg.hub.gate.tuChoi.ribbon");
    go = t("lg.hub.gate.tuChoi.again");
    body = (
      <>
        <Info icon="x" title={t("lg.hub.gate.tuChoi.h")} />
        {reason && <p className="hub-why">{reason}</p>}
      </>
    );
    links = [out];
  } else if (status === "da_duyet") {
    ribbon = t("lg.hub.gate.duyet.ribbon");
    go = t("lg.hub.gate.duyet.ok");
    body = (
      <>
        <Info title={t("lg.hub.gate.duyet.h")}>
          <p>
            <b>{mail}</b>
          </p>
        </Info>
        <CodeBoxes value={code} onChange={(v) => (setCode(v), setErr(null))} bad={!!err?.codeBad} />
      </>
    );
    links = [{ label: t("lg.hub.gate.resendCode"), onClick: () => void resend("code"), disabled: cooling }, out];
  } else {
    body = (
      <Info icon="mail" title={t("lg.hub.gate.chuaNop.h")}>
        <p>
          <b>{mail}</b>
        </p>
      </Info>
    );
  }

  return (
    <HubBoard ribbon={ribbon} id="lg-gate" onSubmit={(e) => void submit(e)}>
      {body}
      <HubAlert text={err ? (err.text ?? t(`lg.hub.err.${err.key}`)) : null} soft={err?.soft} />
      {go && (
        <button className="lg-submit" type="submit" disabled={busy || (status === "tu_choi" && cooling)}>
          {go}
        </button>
      )}
      <HubLinks items={links} />
    </HubBoard>
  );
}
