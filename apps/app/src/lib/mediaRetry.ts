import { useCallback, useRef, useState, type SyntheticEvent } from "react";
import { recoverMediaUrl, retryMedia } from "../api";

/** onError for <img> and <audio> on a network media URL: one retry with a fresh media token (expired = 401). */
export const onMediaError = (e: SyntheticEvent<HTMLImageElement | HTMLMediaElement>) => retryMedia(e.currentTarget);

/**
 * A media URL whose element has no onError we can reach (`<video poster>`, `<track>`). Call `recover` when it fails:
 * if the cause was an expired media token, `url` becomes the same URL with a fresh one. Once per mount, so a server
 * that keeps refusing cannot loop.
 */
export function useRecoveredUrl(original: string): { url: string; recover: () => void } {
  const [swap, setSwap] = useState<{ from: string; to: string } | null>(null);
  const tried = useRef(false);
  const recover = useCallback(() => {
    if (tried.current) return;
    tried.current = true;
    void recoverMediaUrl(original).then((to) => to && setSwap({ from: original, to }));
  }, [original]);
  return { url: swap?.from === original ? swap.to : original, recover };
}
