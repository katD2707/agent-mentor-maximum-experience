import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "../../components/Icon";
import { RecorderError, startRecording, type Recording } from "../../lib/recorder";

export interface ComposerProps {
  /** a request is running: the send button becomes "stop" */
  busy: boolean;
  onSend(text: string): void;
  onCancel(): void;
  onCamera(): void;
  onPhoto(file: File): void;
  onAudio(blob: Blob): void;
  /** a line above the bar ("added a course") */
  notice?: React.ReactNode;
}

/** ChatGPT-style bar pinned to the bottom: growing text field, camera, photo library, microphone, round send button. */
export function Composer({ busy, onSend, onCancel, onCamera, onPhoto, onAudio, notice }: ComposerProps) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const rec = useRef<Recording | null>(null);
  const starting = useRef(false);

  // grow with the text, up to a few lines
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  useEffect(() => () => rec.current?.cancel(), []);

  const trimmed = text.trim();
  const submit = () => {
    if (busy || !trimmed) return;
    setNote(null);
    onSend(trimmed);
    setText("");
  };

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
  const listen = async () => {
    if (starting.current || rec.current) return;
    starting.current = true;
    setNote(null);
    try {
      rec.current = await startRecording({ onAutoStop: () => void done() });
      setListening(true);
    } catch (e) {
      const code = e instanceof RecorderError ? e.code : "failed";
      setNote(t(code === "denied" ? "ask.micDenied" : code === "unsupported" ? "ask.micUnsupported" : "ask.micFailed"));
    } finally {
      starting.current = false;
    }
  };
  const cancelListen = () => {
    rec.current?.cancel();
    rec.current = null;
    setListening(false);
  };

  return (
    <div className="composer-wrap">
      <div className="composer-in" data-guide="ask-composer" data-guide-label={t("ask.label")}>
        {notice}
        {note && (
          <p className="composer-note" role="alert">
            {note}
          </p>
        )}
        <form
          className={`composer${listening ? " is-listening" : ""}`}
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          {listening ? (
            <div className="listen" role="status" aria-live="polite">
              <span className="wave" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
                <i />
              </span>
              <span className="transcript">{t("ask.listening")}</span>
              <button className="c-btn" type="button" aria-label={t("ask.cancelListen")} onClick={cancelListen}>
                <Icon name="x" />
              </button>
              <button className="c-btn c-send" type="button" aria-label={t("ask.doneListen")} onClick={() => void done()}>
                <Icon name="check" />
              </button>
            </div>
          ) : (
            <>
              <textarea
                ref={area}
                className="c-input"
                rows={1}
                value={text}
                placeholder={t("ask.placeholder")}
                aria-label={t("ask.label")}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    submit();
                  }
                }}
              />
              <button className="c-btn" type="button" aria-label={t("ask.camera")} title={t("ask.camera")} onClick={onCamera}>
                <Icon name="camera" />
              </button>
              <button className="c-btn" type="button" aria-label={t("ask.library")} title={t("ask.library")} onClick={() => file.current?.click()}>
                <Icon name="image" />
              </button>
              <button className="c-btn" type="button" aria-label={t("ask.mic")} title={t("ask.mic")} onClick={() => void listen()} disabled={busy}>
                <Icon name="mic" />
              </button>
              {busy ? (
                <button className="c-btn c-send" type="button" aria-label={t("ask.stop")} title={t("ask.stop")} onClick={onCancel}>
                  <Icon name="stop" />
                </button>
              ) : (
                <button className="c-btn c-send" type="submit" aria-label={t("ask.send")} title={t("ask.send")} aria-disabled={!trimmed}>
                  <Icon name="up" />
                </button>
              )}
            </>
          )}
        </form>
        <input
          ref={file}
          type="file"
          accept="image/*"
          hidden
          data-testid="ask-photo-input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) onPhoto(f);
          }}
        />
      </div>
    </div>
  );
}
