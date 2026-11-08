import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { coverUrl, type Lang, type Media } from "../../api";
import { useAuth } from "../../state/auth";
import { cacheCover, courseStore, type DownloadState } from "../../lib/offline";
import { onMediaError } from "../../lib/mediaRetry";
import { subscribeDownload, currentDownloadState } from "../../lib/sync";
import { Icon, type IconName } from "../../components/Icon";
import { fold } from "../../lib/text";

/**
 * Course cover. Shown from the local copy; a cover seen for the first time (in any list, enrolled or not) is fetched
 * once and kept, so lists look the same offline. Falls back to the network URL when it cannot be kept.
 */
export function CourseCover({ courseId, className, alt = "" }: { courseId: string; className?: string; alt?: string }) {
  const { token } = useAuth();
  const [src, setSrc] = useState<string>("");
  useEffect(() => {
    let url: string | null = null;
    let alive = true;
    (async () => {
      const store = courseStore();
      let blob = await store.getCover(courseId).catch(() => null);
      if (!blob && token) {
        await cacheCover(token, store, courseId);
        blob = await store.getCover(courseId).catch(() => null);
      }
      if (!alive) return;
      if (blob) {
        url = URL.createObjectURL(blob);
        setSrc(url);
      } else if (token) setSrc(coverUrl(token, courseId));
    })();
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [courseId, token]);
  return <img className={className} src={src || undefined} alt={alt} loading="lazy" onError={onMediaError} />;
}

/** "Tiếng Việt" / "English" tag (§3.10): the language of the course content, not of the interface. */
export function LangTag({ lang }: { lang: Lang }) {
  const { t } = useTranslation();
  return (
    <span className="tag" lang={lang}>
      {t(`courses.lang.${lang}`)}
    </span>
  );
}

export function formatMinutes(t: TFunction, min: number): string {
  if (min < 60) return t("courses.minutes", { count: min });
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? t("courses.hoursMinutes", { h, m }) : t("courses.hours", { h });
}

const MEDIA_ICON: Record<Media, IconName> = { video: "video", reading: "text", quiz: "quiz", audio: "volume", interactive: "layers" };

export function MediaIcons({ media = [] }: { media?: Media[] }) {
  const { t } = useTranslation();
  return (
    <>
      {media.map((m) => (
        <span key={m} title={t(`courses.media.${m}`)}>
          <Icon name={MEDIA_ICON[m]} />
          <span className="sr">{t(`courses.media.${m}`)}</span>
        </span>
      ))}
    </>
  );
}

/** Subtle download state: nothing while unknown, a quiet line otherwise. */
export function useDownload(courseId: string, version: number): DownloadState {
  const [s, setS] = useState<DownloadState>({ kind: "none" });
  useEffect(() => {
    let alive = true;
    void currentDownloadState(courseId, version).then((x) => alive && setS(x));
    const off = subscribeDownload(courseId, version, (x) => alive && setS(x));
    return () => {
      alive = false;
      off();
    };
  }, [courseId, version]);
  return s;
}

export function DownloadNote({ state }: { state: DownloadState }) {
  const { t } = useTranslation();
  if (state.kind === "none") return null;
  let text: string;
  if (state.kind === "downloading") text = t("courses.download.downloading", { pct: state.total ? Math.round((state.done / state.total) * 100) : 0 });
  else text = t(`courses.download.${state.kind}`);
  return (
    <span className={`dl dl-${state.kind}`} role="status">
      <Icon name={state.kind === "downloading" ? "download" : "check"} />
      {text}
    </span>
  );
}

/** Wrap every occurrence of the matched words (accent-insensitive) in <mark>. */
export function Highlight({ text, words }: { text: string; words?: string[] }) {
  if (!words?.length) return <>{text}</>;
  let folded = "";
  const map: number[] = []; // folded index -> original index
  Array.from(text).forEach((ch, i) => {
    const f = fold(ch);
    for (let j = 0; j < f.length; j++) map.push(i);
    folded += f;
  });
  const chars = Array.from(text);
  const on = new Array<boolean>(chars.length).fill(false);
  for (const w of words) {
    if (!w) continue;
    for (let at = folded.indexOf(w); at !== -1; at = folded.indexOf(w, at + 1)) for (let j = at; j < at + w.length; j++) on[map[j]] = true;
  }
  const out: React.ReactNode[] = [];
  let buf = "";
  let cur = false;
  const flush = (key: number) => {
    if (buf) out.push(cur ? <mark key={key}>{buf}</mark> : buf);
    buf = "";
  };
  chars.forEach((ch, i) => {
    if (on[i] !== cur) {
      flush(i);
      cur = on[i];
    }
    buf += ch;
  });
  flush(chars.length);
  return <>{out}</>;
}
