import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Settings } from "../../components/Settings";
import { Icon } from "../../components/Icon";
import "../../styles/teacher.css";

/** Top bar of every teacher screen. Only the home screen has no back button. */
export function TeacherTop({ back, children }: { back?: boolean; children?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <header className="topbar">
      {back && (
        <Link className="icon-btn" to="/" aria-label={t("gv.back")} data-guide="gv-back" data-guide-label={t("gv.back")}>
          <Icon name="back" />
        </Link>
      )}
      <Link className="logo" to="/">
        <span className="logo-mark">M</span>
        <span className="logo-word">Mentor</span>
      </Link>
      <span className="role-tag">{t("teacher.role")}</span>
      <span className="grow" />
      {children}
      <Settings />
    </header>
  );
}

const coarse = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;

/**
 * "Chụp ảnh". On a phone the file input with capture opens the camera app. On a computer the browser camera is used
 * (getUserMedia) with a small viewfinder where several pictures can be taken in a row; no camera means the plain file
 * chooser instead.
 */
export function CameraButton({ onFiles, label, className = "btn btn-ghost", single }: { onFiles(files: File[]): void; label: string; className?: string; single?: boolean }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [live, setLive] = useState(false);
  const click = async () => {
    if (!coarse() && navigator.mediaDevices?.getUserMedia) {
      try {
        const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        s.getTracks().forEach((x) => x.stop()); // permission check only; the viewfinder opens its own stream
        setLive(true);
        return;
      } catch {
        /* no camera or denied: the file chooser */
      }
    }
    input.current?.click();
  };
  return (
    <>
      <button className={className} type="button" onClick={() => void click()}>
        <Icon name="camera" />
        <span>{label}</span>
      </button>
      <input
        ref={input}
        className="sr"
        type="file"
        accept="image/*"
        capture="environment"
        multiple={!single}
        tabIndex={-1}
        aria-label={t("gv.camera")}
        onChange={(e) => {
          const f = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (f.length) onFiles(f);
        }}
      />
      {live && (
        <Viewfinder
          single={single}
          onClose={(files) => {
            setLive(false);
            if (files.length) onFiles(files);
          }}
        />
      )}
    </>
  );
}

function Viewfinder({ onClose, single }: { onClose(files: File[]): void; single?: boolean }) {
  const { t } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const [shots, setShots] = useState<File[]>([]);
  const [err, setErr] = useState(false);
  const shotsRef = useRef<File[]>([]);
  shotsRef.current = shots;

  useEffect(() => {
    let stream: MediaStream | null = null;
    let dead = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } } })
      .then((s) => {
        if (dead) return s.getTracks().forEach((x) => x.stop());
        stream = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play().catch(() => undefined);
        }
      })
      .catch(() => setErr(true));
    return () => {
      dead = true;
      stream?.getTracks().forEach((x) => x.stop());
    };
  }, []);

  const snap = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")?.drawImage(v, 0, 0);
    c.toBlob(
      (b) => {
        if (!b) return;
        const f = new File([b], `anh-${String(shotsRef.current.length + 1).padStart(3, "0")}.jpg`, { type: "image/jpeg" });
        if (single) onClose([f]);
        else setShots((s) => [...s, f]);
      },
      "image/jpeg",
      0.92,
    );
  };

  return (
    <div className="gv-cam" role="dialog" aria-modal="true" aria-label={t("gv.camera")}>
      <div className="gv-cam-box">
        {err ? <p className="gv-cam-err" role="alert">{t("gv.cameraFail")}</p> : <video ref={video} playsInline muted />}
        <div className="gv-cam-bar">
          <button className="btn btn-ghost" type="button" onClick={() => onClose([])}>
            {t("gv.cancel")}
          </button>
          <button className="btn btn-primary btn-big gv-cam-snap" type="button" onClick={snap} disabled={err}>
            <Icon name="camera" />
            <span>{t("gv.snap")}</span>
          </button>
          {!single && (
            <button className="btn btn-ghost" type="button" onClick={() => onClose(shots)} disabled={!shots.length}>
              {t("gv.doneShots", { shots: shots.length })}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function useLangText() {
  const { i18n } = useTranslation();
  return (vi: string, en: string) => (i18n.language === "en" ? en : vi);
}
