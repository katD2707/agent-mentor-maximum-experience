import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Settings } from "./Settings";
import { Icon } from "../../components/Icon";
import { courseRoute } from "../../lib/teacher/status";
import { useTeacherCourses } from "./live";
import "./teacher.css";

const ENC = encodeURIComponent;

/** Where step 3 (Nhãn) and step 4 (Duyệt) of a course open: only once Mentor has composed it. */
export const labelsRoute = (id: string, v: number) => `/khoa/${ENC(id)}/nhan?v=${v || 1}`;
export const reviewRoute = (id: string, v: number) => `/khoa/${ENC(id)}/duyet?v=${v || 1}`;
const BUILT = new Set(["review", "published", "revising"]);

/**
 * Header of the four teacher screens (gv-01..04): logo, steps 1-4 as links with the current one marked, the screen's one
 * primary action on the right (`children`), then the gear. `courseId` says which course steps 2-4 open; on the home
 * screen the first course that is ready for that step is used. A step with nothing to open yet is dimmed, not a link.
 */
export function TeacherTop({ step, courseId, backTo, children }: { step: 1 | 2 | 3 | 4; courseId?: string; backTo?: string; children?: ReactNode }) {
  const { t } = useTranslation();
  const { courses } = useTeacherCourses();
  const own = courseId ? courses?.find((c) => c.id === courseId) : undefined;
  const to2 = (() => {
    if (courseId) return !courses || (own && own.status !== "reading") ? `/khoa/${ENC(courseId)}` : null;
    const c = courses?.find((x) => courseRoute(x)?.startsWith("/khoa/") && !courseRoute(x)?.includes("/duyet")) ?? courses?.find((x) => courseRoute(x));
    return c ? `/khoa/${ENC(c.id)}` : null;
  })();
  const built = (() => {
    const c = courseId ? own : courses?.find((x) => BUILT.has(x.status));
    return c && BUILT.has(c.status) ? c : null;
  })();
  const items: { n: 1 | 2 | 3 | 4; to: string | null }[] = [
    { n: 1, to: "/" },
    { n: 2, to: to2 },
    { n: 3, to: built ? labelsRoute(built.id, built.latest_version) : null },
    { n: 4, to: built ? reviewRoute(built.id, built.latest_version) : null },
  ];
  return (
    <header className="topbar">
      {backTo && (
        <Link className="icon-btn" to={backTo} aria-label={t("gv.back")}>
          <Icon name="back" />
        </Link>
      )}
      <Link className="logo" to="/">
        <span className="logo-mark">M</span>
        <span className="logo-word">Mentor</span>
      </Link>
      <nav className="steps" aria-label={t("teacher.steps")}>
        {items.map(({ n, to }) => {
          const label = n <= 2 ? t(`teacher.step${n}`) : t(`lg.gvl.step${n}`);
          const inner = (
            <>
              <span className="n">{n}</span>
              <span className="l">{label}</span>
            </>
          );
          if (n === step)
            return (
              <Link key={n} to={to ?? "/"} aria-current="step" aria-label={label}>
                {inner}
              </Link>
            );
          return to ? (
            <Link key={n} to={to} aria-label={label}>
              {inner}
            </Link>
          ) : (
            <span key={n} className="off" aria-disabled="true" aria-label={label}>
              {inner}
            </span>
          );
        })}
      </nav>
      <span className="grow" />
      {children}
      <Settings />
    </header>
  );
}

/** A short line at the bottom of the screen that goes away on its own ("Đã sửa."). */
export function useToast(ms = 2600) {
  const [text, setText] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const show = useCallback(
    (s: string) => {
      setText(s);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setText(null), ms);
    },
    [ms],
  );
  useEffect(() => () => clearTimeout(timer.current), []);
  const node = text ? (
    <div className="gv-toast" role="status">
      {text}
    </div>
  ) : null;
  return { show, node };
}

const coarse = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;

/**
 * "Chụp ảnh". On a phone the file input with capture opens the camera app. On a computer the browser camera is used
 * (getUserMedia) with a small viewfinder where several pictures can be taken in a row; no camera means the plain file
 * chooser instead.
 */
export function CameraButton({ onFiles, label, ariaLabel, className = "btn btn-ghost", single }: { onFiles(files: File[]): void; label: string; ariaLabel?: string; className?: string; single?: boolean }) {
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
      <button className={className} type="button" aria-label={ariaLabel} onClick={() => void click()}>
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
