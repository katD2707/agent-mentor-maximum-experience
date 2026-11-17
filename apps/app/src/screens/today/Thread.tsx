import { useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Icon, type IconName } from "../../components/Icon";
import { RecorderError, startRecording, type Recording } from "../../lib/recorder";

/** A quick reply under one of Mực's messages: a link (the main action) or a step in the conversation. */
export interface Reply {
  label: string;
  /** time it takes, shown after the label ("15 phút") */
  dur?: string;
  primary?: boolean;
  icon?: IconName;
  to?: string;
  run?: () => void;
}

/** Mực's face: the same ink drop as the guide character, small. */
export function MucFace() {
  return (
    <span className="td-ava" aria-hidden="true">
      <svg viewBox="0 0 80 100">
        <path d="M40 4 C47 18 68 33 68 56 A28 28 0 0 1 12 56 C12 33 33 18 40 4 Z" fill="var(--tim)" />
        <ellipse cx="31" cy="52" rx="7" ry="8" fill="#fff" />
        <ellipse cx="49" cy="52" rx="7" ry="8" fill="#fff" />
        <circle cx="32" cy="53" r="4" fill="#1F1B3A" />
        <circle cx="50" cy="53" r="4" fill="#1F1B3A" />
      </svg>
    </span>
  );
}

/** One message from Mực, with its quick replies; replies disappear once one is chosen (the choice shows as a reply bubble). */
export function MucMessage({ text, rich, replies, used, typing, onUse }: {
  text: ReactNode;
  rich?: ReactNode;
  replies?: Reply[];
  used?: boolean;
  typing?: boolean;
  onUse(r: Reply): void;
}) {
  const { t } = useTranslation();
  return (
    <div className="td-msg muc">
      <MucFace />
      <div className="td-body">
        {typing ? (
          <div className="td-bub td-typing" role="status" aria-label={t("today.typing")}>
            <i />
            <i />
            <i />
          </div>
        ) : (
          <>
            <div className="td-bub">{text}</div>
            {rich && <div className="td-rich">{rich}</div>}
            {replies && replies.length > 0 && !used && (
              <div className="td-replies">
                {replies.map((r, i) => {
                  const inner = (
                    <>
                      {r.primary && <Icon name="play" />}
                      {!r.primary && r.icon && <Icon name={r.icon} />}
                      <span>{r.label}</span>
                      {r.dur && <span className="td-dur">· {r.dur}</span>}
                    </>
                  );
                  const cls = `td-reply${r.primary ? " primary" : ""}`;
                  return r.to ? (
                    <Link key={i} className={cls} to={r.to} state={{ back: "/" }} onClick={() => onUse({ ...r, run: undefined })}>
                      {inner}
                    </Link>
                  ) : (
                    <button key={i} className={cls} type="button" onClick={() => onUse(r)}>
                      {inner}
                    </button>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function MeMessage({ text }: { text: string }) {
  return (
    <div className="td-msg me">
      <div className="td-bub">{text}</div>
    </div>
  );
}

/** Primary school: the next step is a spot on a path (done, this one, the next, the star at the end). */
export function KidPath({ done, total }: { done: number; total: number }) {
  const { t } = useTranslation();
  return (
    <div className="td-pathbox">
      <svg className="td-path" viewBox="0 0 300 130" role="img" aria-label={t("today.pathAria", { done, total })}>
        <path className="road" d="M30 96 C70 30, 110 30, 140 64 S 210 112, 266 46" />
        {done > 0 && (
          <g className="done">
            <circle cx="30" cy="96" r="20" />
            <path d="M21 96 l6 6 11-12" fill="none" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )}
        <g className="now">
          <circle className="halo" cx="140" cy="64" r="36" />
          <circle className="dot" cx="140" cy="64" r="28" />
          <path d="M132 51 L153 64 L132 77 Z" />
        </g>
        {total - done > 1 && (
          <g className="todo">
            <circle cx="212" cy="104" r="17" />
          </g>
        )}
        <g transform="translate(268 44)">
          <circle r="24" fill="var(--vang-soft)" stroke="var(--vang)" strokeWidth="4" />
          <path d="M0 -13 L4 -4 L14 -3 L7 4 L9 13 L0 8 L-9 13 L-7 4 L-14 -3 L-4 -4 Z" fill="var(--vang)" />
        </g>
      </svg>
    </div>
  );
}

/** Primary school: two big buttons instead of typing. "Nói với Mực" records, a second tap sends. */
export function KidAsk({ onCamera, onAudio, busy }: { onCamera(): void; onAudio(b: Blob): void; busy: boolean }) {
  const { t } = useTranslation();
  const rec = useRef<Recording | null>(null);
  const [listening, setListening] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const done = async () => {
    const r = rec.current;
    if (!r) return;
    rec.current = null;
    setListening(false);
    try {
      onAudio(await r.stop());
    } catch {
      setNote(t("ask.micFailed"));
    }
  };
  const talk = async () => {
    if (listening) return void done();
    setNote(null);
    try {
      rec.current = await startRecording({ onAutoStop: () => void done() });
      setListening(true);
    } catch (e) {
      const code = e instanceof RecorderError ? e.code : "failed";
      setNote(t(code === "denied" ? "ask.micDenied" : code === "unsupported" ? "ask.micUnsupported" : "ask.micFailed"));
    }
  };

  return (
    <div className="td-kid-ask">
      {note && (
        <p className="td-note" role="status">
          {note}
        </p>
      )}
      <button type="button" className="td-kid" onClick={onCamera} disabled={busy}>
        <Icon name="camera" />
        <span>{t("today.kidSnap")}</span>
      </button>
      <button type="button" className={`td-kid alt${listening ? " on" : ""}`} onClick={() => void talk()} disabled={busy && !listening} aria-pressed={listening}>
        <Icon name={listening ? "stop" : "mic"} />
        <span>{listening ? t("today.kidDone") : t("today.kidTalk")}</span>
      </button>
    </div>
  );
}
