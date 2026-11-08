import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "../../components/Icon";

/** Live camera with a framing guide (desktop and web). Without a camera, or when it is blocked, the device camera / file picker takes over. */
export function Camera({ onShot, onFile, onClose }: { onShot(blob: Blob): void; onFile(file: File): void; onClose(): void }) {
  const { t } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const device = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<"starting" | "live" | "denied">("starting");

  useEffect(() => {
    let alive = true;
    let stream: MediaStream | null = null;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false });
        if (!alive) return stream.getTracks().forEach((tr) => tr.stop());
        const v = video.current;
        if (v) {
          v.srcObject = stream;
          await v.play().catch(() => undefined);
        }
        setState("live");
      } catch {
        if (alive) setState("denied");
      }
    })();
    return () => {
      alive = false;
      stream?.getTracks().forEach((tr) => tr.stop());
    };
  }, []);

  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  const shoot = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")?.drawImage(v, 0, 0);
    c.toBlob((b) => b && onShot(b), "image/jpeg", 0.92);
  };
  const picked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) onFile(f);
  };

  return (
    <section className="cam" aria-label={t("ask.cam.title")}>
      <div className="cam-top">
        <button className="icon-btn" type="button" onClick={onClose} aria-label={t("ask.cam.close")}>
          <Icon name="x" />
        </button>
        <span className="muted">{t("ask.cam.title")}</span>
      </div>
      <div className="viewfinder" data-guide="ask-camera" data-guide-label={t("ask.camera")}>
        <video ref={video} playsInline muted autoPlay />
        <div className="guide" />
        {state === "live" && <p className="tip">{t("ask.cam.hold")}</p>}
        {state === "starting" && <p className="tip">{t("ask.cam.starting")}</p>}
        {state === "denied" && (
          <div className="cam-denied" role="alert">
            <p>{t("ask.cam.denied")}</p>
            <button className="btn btn-primary" type="button" onClick={() => device.current?.click()}>
              <Icon name="camera" />
              <span>{t("ask.cam.useDevice")}</span>
            </button>
          </div>
        )}
      </div>
      <div className="camrow">
        <button className="btn btn-ghost" type="button" onClick={() => library.current?.click()} style={{ justifySelf: "start" }}>
          <Icon name="image" />
          <span>{t("ask.cam.fromPhotos")}</span>
        </button>
        <button className="shutter" type="button" aria-label={t("ask.cam.shoot")} onClick={shoot} disabled={state !== "live"} />
        <span />
      </div>
      <input ref={device} type="file" accept="image/*" capture="environment" hidden onChange={picked} />
      <input ref={library} type="file" accept="image/*" hidden onChange={picked} />
    </section>
  );
}
