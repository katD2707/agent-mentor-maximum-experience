import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Chapter } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { courseStore, loadPack, type LoadedPack } from "../../lib/offline";

/** One recap that can be played: a chapter whose spoken summary is ready. */
interface Playable {
  chapter: Chapter;
  src: string;
  minutes: number;
}

const SPEEDS = [1, 1.25];
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/**
 * "Nghe tóm tắt" (hs-04): one quiet row per chapter whose recap is ready, and a mini player docked at the bottom. The recap
 * comes with the course's download, so it plays without internet. Little ones get one big play button.
 */
export function RecapRows({ courseId, version, sha, kid }: { courseId: string; version: number; sha?: string | null; kid: boolean }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [list, setList] = useState<Playable[]>([]);
  const [offline, setOffline] = useState(false);
  const [open, setOpen] = useState<Playable | null>(null);

  useEffect(() => {
    if (!token || !version) return;
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
          if (r && src) out.push({ chapter, src, minutes: Math.max(1, Math.round(r.duration_s / 60)) });
        }
        setList(out);
        setOffline(l.source === "cache");
      })
      .catch(() => undefined); // no recap row without the pack: the course page itself already works
    return () => {
      alive = false;
      loaded?.dispose();
    };
  }, [token, courseId, version, sha]);

  if (!list.length) return null;
  return (
    <>
      {list.map((p) => (
        <button key={p.chapter.id} type="button" className="ct-node listen" onClick={() => setOpen(p)}>
          <span className="no">
            <Icon name="volume" />
          </span>
          <span className="t">
            {t(kid ? "courses.intro.recapKid" : "courses.intro.recap", { n: p.minutes })}
            {list.length > 1 && <small className="muted"> · {p.chapter.title}</small>}
          </span>
          <span className="end" title={offline ? t("courses.intro.recapOffline") : undefined}>
            {offline && (
              <>
                <Icon name="download" />
                <span className="sr">{t("courses.intro.recapOffline")}</span>
              </>
            )}
          </span>
        </button>
      ))}
      {open && <MiniPlayer key={open.chapter.id} item={open} offline={offline} kid={kid} onClose={() => setOpen(null)} />}
    </>
  );
}

function MiniPlayer({ item, offline, kid, onClose }: { item: Playable; offline: boolean; kid: boolean; onClose(): void }) {
  const { t } = useTranslation();
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState(item.minutes * 60);
  const [speed, setSpeed] = useState(1);
  const [failed, setFailed] = useState(false);

  const play = () => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) a.play()?.then?.(() => setFailed(false), () => setFailed(true));
    else a.pause();
  };
  useEffect(() => {
    void audio.current?.play?.()?.catch?.(() => undefined); // opened by a tap: start at once
  }, []);
  // the floating Mực sits where the player docks: he steps aside while the recap plays
  useEffect(() => {
    const root = document.documentElement;
    const had = root.hasAttribute("data-no-mascot");
    root.setAttribute("data-no-mascot", "");
    return () => {
      if (!had) root.removeAttribute("data-no-mascot");
    };
  }, []);

  return (
    <section className={`mini ${kid ? "kid" : ""}`} aria-label={t("courses.intro.mini.aria")}>
      <div className="mini-in">
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
        <div className="ttl">
          <b>{item.chapter.title}</b>
          {offline && !kid && (
            <span className="ib dl" aria-pressed="true" title={t("courses.intro.recapOffline")}>
              <Icon name="download" />
            </span>
          )}
          <button className="ib" type="button" aria-label={t("courses.intro.mini.close")} onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="ctl">
          {!kid && (
            <button className="ib" type="button" aria-label={t("courses.intro.mini.back")} onClick={() => audio.current && (audio.current.currentTime = Math.max(0, audio.current.currentTime - 10))}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12a7 7 0 1 1 2 5" />
                <path d="M5 6v4.5h4.5" />
              </svg>
              <span>10</span>
            </button>
          )}
          <button className="pp" type="button" aria-label={playing ? t("courses.intro.mini.pause") : t("courses.intro.mini.play")} onClick={play}>
            {playing ? (
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" />
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
                aria-label={t("courses.intro.mini.seek")}
                onChange={(e) => audio.current && (audio.current.currentTime = Number(e.target.value))}
              />
              <span className="tm">{clock(Math.max(0, length - time))}</span>
              <button
                className="ib"
                type="button"
                aria-label={t("courses.intro.mini.speed", { n: speed })}
                onClick={() => {
                  const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
                  setSpeed(next);
                  if (audio.current) audio.current.playbackRate = next;
                }}
              >
                {speed}x
              </button>
            </>
          )}
        </div>
        {failed && (
          <p className="muted" role="alert">
            {t("courses.intro.mini.failed")}
          </p>
        )}
      </div>
    </section>
  );
}
