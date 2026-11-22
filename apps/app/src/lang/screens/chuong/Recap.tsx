import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Chapter } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { courseStore, loadPack, type LoadedPack } from "../../../lib/offline";

/** One recap that can be played: a chapter whose spoken summary is ready. */
export interface Playable {
  chapter: Chapter;
  src: string;
  minutes: number;
  offline: boolean;
}

const HEAD = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4.5 15v-3a7.5 7.5 0 0 1 15 0v3" />
    <rect x="3.5" y="14" width="4" height="6" rx="1.5" />
    <rect x="16.5" y="14" width="4" height="6" rx="1.5" />
  </svg>
);

const SPEEDS = [1, 1.25];
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** The chapters of a course that have a recap ready. The recap travels with the course download, so it plays offline. */
export function useRecaps(courseId: string, version: number, sha: string | null | undefined, enabled: boolean): Playable[] {
  const { token } = useAuth();
  const [list, setList] = useState<Playable[]>([]);
  useEffect(() => {
    if (!token || !version || !enabled) return;
    let alive = true;
    let loaded: LoadedPack | null = null;
    loadPack({ api, token, store: courseStore() }, courseId, version, sha)
      .then((l) => {
        loaded = l;
        if (!alive) return l.dispose();
        const out: Playable[] = [];
        for (const chapter of l.pack.chapters) {
          const r = chapter.recap;
          const src = r?.audio ? l.url(r.audio.path) : "";
          if (r && src) out.push({ chapter, src, minutes: Math.max(1, Math.round(r.duration_s / 60)), offline: l.source === "cache" });
        }
        setList(out);
      })
      .catch(() => undefined); // no recap row without the pack: the course itself still works
    return () => {
      alive = false;
      loaded?.dispose();
    };
  }, [token, courseId, version, sha, enabled]);
  return list;
}

/** "Nghe tóm tắt" rows of one course (one per chapter whose recap is ready). */
export function RecapRows({ list, kid, name, onOpen }: { list: Playable[]; kid: boolean; name: string; onOpen(p: Playable): void }) {
  const { t } = useTranslation();
  if (!list.length) return null;
  return (
    <div className="ck-kids">
      {list.map((p) => (
        <button key={p.chapter.id} type="button" className="ck-node ck-listen" onClick={() => onOpen(p)}>
          <span className="ck-no">{kid ? <Icon name="volume" /> : HEAD}</span>
          <span className="ck-t">
            {t(kid ? "lg.cg.recapKid" : "lg.cg.recap", { n: p.minutes, name })}
            {list.length > 1 && <small> · {p.chapter.title}</small>}
          </span>
          <span className="ck-end" title={p.offline ? t("lg.cg.recapSaved") : undefined}>
            {p.offline && (
              <>
                <Icon name="download" />
                <span className="ck-sr">{t("lg.cg.recapSaved")}</span>
              </>
            )}
          </span>
        </button>
      ))}
    </div>
  );
}

/** The docked mini player: play, 10 s back, seek, 1x/1.25x, captions. Little ones get one big play button. */
export function MiniPlayer({ item, kid, name, face, onClose }: { item: Playable; kid: boolean; name: string; face: string; onClose(): void }) {
  const { t } = useTranslation();
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState(item.minutes * 60);
  const [speed, setSpeed] = useState(1);
  const [cc, setCc] = useState(true);
  const [failed, setFailed] = useState(false);
  const script = item.chapter.recap?.script ?? [];

  const play = () => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) a.play()?.then?.(() => setFailed(false), () => setFailed(true));
    else a.pause();
  };
  useEffect(() => {
    void audio.current?.play?.()?.catch?.(() => undefined); // opened by a tap: start at once
  }, []);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  const caption = script.length ? script[Math.min(script.length - 1, Math.floor((time / Math.max(1, length)) * script.length))] : "";
  return (
    <section className="ck-mini" aria-label={t("lg.cg.mini.aria")}>
      <div className="ck-mini-in">
        <audio
          ref={audio}
          src={item.src}
          preload="auto"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => Number.isFinite(e.currentTarget.duration) && setLength(e.currentTarget.duration)}
          onError={() => setFailed(true)}
        />
        <div className="ck-ttl">
          <span className="ck-face" aria-hidden="true" style={{ backgroundImage: `url(${face})` }} />
          <b>
            <span>{item.chapter.title}</span>
            <small>{t(kid ? "lg.cg.recapKid" : "lg.cg.recap", { n: item.minutes, name })}</small>
          </b>
          {item.offline && !kid && (
            <span className="ck-ib ck-dl" aria-pressed="true" title={t("lg.cg.recapSaved")}>
              <Icon name="download" />
              <span>{t("lg.cg.mini.saved")}</span>
            </span>
          )}
          <button className="ck-ib" type="button" aria-label={t("lg.cg.mini.close")} onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        {cc && caption && !kid && (
          <p className="ck-cap" aria-live="off">
            <span className="ck-said">{caption}</span>
          </p>
        )}
        <div className="ck-ctl">
          {!kid && (
            <button className="ck-ib" type="button" aria-label={t("lg.cg.mini.back")} onClick={() => audio.current && (audio.current.currentTime = Math.max(0, audio.current.currentTime - 10))}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12a7 7 0 1 1 2 5" />
                <path d="M5 6v4.5h4.5" />
              </svg>
              <span>10</span>
            </button>
          )}
          <button className="ck-pp" type="button" aria-label={playing ? t("lg.cg.mini.pause") : t("lg.cg.mini.play")} onClick={play}>
            {playing ? (
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 5.5v13M16 5.5v13" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" />
              </svg>
            ) : (
              <Icon name="play" />
            )}
          </button>
          {!kid && (
            <>
              <input
                type="range"
                min={0}
                max={Math.max(1, Math.round(length))}
                value={Math.min(Math.round(time), Math.round(length))}
                aria-label={t("lg.cg.mini.seek")}
                onChange={(e) => audio.current && (audio.current.currentTime = Number(e.target.value))}
              />
              <span className="ck-tm">-{clock(Math.max(0, length - time))}</span>
              <button
                className="ck-ib"
                type="button"
                aria-label={t("lg.cg.mini.speed", { n: speed })}
                onClick={() => {
                  const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
                  setSpeed(next);
                  if (audio.current) audio.current.playbackRate = next;
                }}
              >
                {speed}x
              </button>
              {script.length > 0 && (
                <button className="ck-ib ck-cc" type="button" aria-pressed={cc} aria-label="CC" onClick={() => setCc((v) => !v)}>
                  CC
                </button>
              )}
            </>
          )}
        </div>
        {failed && (
          <p className="ck-cap" role="alert">
            {t("lg.cg.mini.failed")}
          </p>
        )}
      </div>
    </section>
  );
}
