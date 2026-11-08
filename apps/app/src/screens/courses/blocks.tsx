import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AssetRef, AudioBlock, Block, CalloutBlock, ImageAttribution, ImageBlock, Lang, TextBlock, VideoBlock } from "../../api";
import { Icon } from "../../components/Icon";
import { onMediaError, useRecoveredUrl } from "../../lib/mediaRetry";
import { recoverMediaUrl, retryMedia } from "../../api";
import { renderMd } from "../../lib/md";
import { speak } from "../../lib/speak";
import { plainText } from "../../lib/text";

export interface BlockCtx {
  lang: Lang;
  /** URL for an asset ref (cached blob or network); "" when there is none */
  url(ref: AssetRef | null | undefined): string;
  /** behaviour log: how far into a video the learner got (25, 50, 75, 100), each once */
  watch?(blockId: string, pct: number): void;
}

export function Md({ md, className }: { md: string; className?: string }) {
  const html = useMemo(() => renderMd(md), [md]);
  return <div className={`md ${className ?? ""}`} dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Speaker on every text for the little ones: the recorded audio if the block has one, else the platform voice. */
export function SpeakButton({ text, audioUrl, lang, label }: { text: string; audioUrl?: string; lang: Lang; label?: string }) {
  const { t } = useTranslation();
  const audio = useRef<HTMLAudioElement | null>(null);
  const play = () => {
    audio.current?.pause();
    if (audioUrl) {
      const a = new Audio(audioUrl);
      audio.current = a;
      a.play().catch(async () => {
        // an expired media token looks like a failed play(): retry once with a fresh one, then fall back to the voice
        const next = await recoverMediaUrl(audioUrl);
        if (!next) return speak(plainText(text), lang);
        const b = new Audio(next);
        audio.current = b;
        b.play().catch(() => speak(plainText(text), lang));
      });
    } else speak(plainText(text), lang);
  };
  return (
    <button className="speak speak-inline" type="button" aria-label={label ?? t("courses.player.speak")} onClick={play}>
      <Icon name="volume" />
    </button>
  );
}

function TextView({ b, ctx }: { b: TextBlock; ctx: BlockCtx }) {
  return (
    <div className="blk-text">
      <Md md={b.md} />
      <SpeakButton text={b.md} audioUrl={ctx.url(b.audio)} lang={ctx.lang} />
    </div>
  );
}

function CalloutView({ b, ctx }: { b: CalloutBlock; ctx: BlockCtx }) {
  const { t } = useTranslation();
  return (
    <aside className={`callout callout-${b.variant} ${b.variant === "remember" ? "oli" : ""}`}>
      <div className="callout-body">
        <b className="callout-title">{b.title || t(`courses.player.calloutTitle.${b.variant}`)}</b>
        <Md md={b.md} />
      </div>
      <SpeakButton text={`${b.title ?? ""}. ${b.md}`} audioUrl={ctx.url(b.audio)} lang={ctx.lang} />
    </aside>
  );
}

function ImageCredit({ a }: { a: ImageAttribution }) {
  const { t } = useTranslation();
  const safe = (u?: string | null) => (u && /^https?:\/\//i.test(u) ? u : undefined);
  const parts = [a.title, a.author, a.provider].filter(Boolean) as string[];
  if (!parts.length && !a.license) return null;
  const source = safe(a.source_url);
  const licenseUrl = safe(a.license_url);
  return (
    <p className="img-credit">
      <span>{t("courses.player.imageCredit")}: </span>
      {source ? <a href={source} target="_blank" rel="noopener noreferrer">{parts.join(", ")}</a> : <span>{parts.join(", ")}</span>}
      {a.license && (
        <>
          {" · "}
          {licenseUrl ? <a href={licenseUrl} target="_blank" rel="noopener noreferrer">{a.license}</a> : <span>{a.license}</span>}
        </>
      )}
    </p>
  );
}

function ImageView({ b, ctx }: { b: ImageBlock; ctx: BlockCtx }) {
  const src = ctx.url(b.image);
  return (
    <figure className="blk-image">
      {src ? <img src={src} alt={b.alt} onError={onMediaError} /> : <div className="ph" role="img" aria-label={b.alt} />}
      {b.caption && (
        <figcaption>
          <span>{b.caption}</span>
          <SpeakButton text={b.caption} audioUrl={ctx.url(b.audio)} lang={ctx.lang} />
        </figcaption>
      )}
      {b.attribution && <ImageCredit a={b.attribution} />}
    </figure>
  );
}

function VideoView({ b, ctx }: { b: VideoBlock; ctx: BlockCtx }) {
  const { t } = useTranslation();
  const [broken, setBroken] = useState(false);
  const src = ctx.url(b.video);
  const { url: poster, recover: recoverPoster } = useRecoveredUrl(ctx.url(b.poster));
  const { url: captions, recover: recoverCaptions } = useRecoveredUrl(ctx.url(b.captions));
  // a <track> reports its failure on itself only (the event does not bubble)
  const trackRef = useCallback((el: HTMLTrackElement | null) => el?.addEventListener("error", recoverCaptions, { once: true }), [recoverCaptions]);
  const mins = Math.floor(b.duration_s / 60);
  const secs = String(Math.round(b.duration_s % 60)).padStart(2, "0");
  const reached = useRef(0);
  const onTime = (v: HTMLVideoElement) => {
    if (!ctx.watch || !v.duration) return;
    const pct = Math.floor((v.currentTime / v.duration) * 4) * 25;
    if (pct > reached.current) {
      reached.current = pct;
      ctx.watch(b.id, pct);
    }
  };
  return (
    <figure className="blk-video">
      <div className="video">
        {src && !broken ? (
          <>
            {/* crossOrigin: a <track> from the gateway origin is only loaded when the request is a CORS one */}
            <video controls preload="metadata" src={src} onTimeUpdate={(e) => onTime(e.currentTarget)} onEnded={() => ctx.watch && reached.current < 100 && ((reached.current = 100), ctx.watch(b.id, 100))} crossOrigin="anonymous" poster={poster || undefined} onError={(e) => retryMedia(e.currentTarget, () => setBroken(true))} aria-label={b.title ?? undefined}>
              {captions && <track ref={trackRef} kind="captions" src={captions} default />}
            </video>
            {/* a <video poster> has no error event: this hidden copy tells us when its token expired */}
            {poster && <img src={poster} alt="" hidden onError={recoverPoster} />}
          </>
        ) : (
          <div className="video-missing">
            {poster && <img src={poster} alt="" onError={onMediaError} />}
            <p role="status">{src ? t("courses.player.noPlay") : t("courses.player.videoMissing")}</p>
          </div>
        )}
        <span className="dur">
          {mins}:{secs}
        </span>
      </div>
      {b.title && <figcaption>{b.title}</figcaption>}
    </figure>
  );
}

function AudioView({ b, ctx }: { b: AudioBlock; ctx: BlockCtx }) {
  const { t } = useTranslation();
  const src = ctx.url(b.audio);
  return (
    <div className="blk-audio">
      {src ? <audio controls preload="metadata" src={src} onError={onMediaError} /> : <SpeakButton text={b.transcript} lang={ctx.lang} />}
      <details>
        <summary>{t("courses.player.transcript")}</summary>
        <p>{b.transcript}</p>
      </details>
    </div>
  );
}

/** Every non-quiz block kind (quiz blocks are rendered by the runner so it can track answers). */
export function StaticBlock({ b, ctx }: { b: Exclude<Block, { kind: "quiz" }>; ctx: BlockCtx }) {
  switch (b.kind) {
    case "text":
      return <TextView b={b} ctx={ctx} />;
    case "callout":
      return <CalloutView b={b} ctx={ctx} />;
    case "image":
      return <ImageView b={b} ctx={ctx} />;
    case "video":
      return <VideoView b={b} ctx={ctx} />;
    case "audio":
      return <AudioView b={b} ctx={ctx} />;
  }
}
