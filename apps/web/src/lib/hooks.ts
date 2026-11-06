"use client";

import { useCallback, useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: (d: T) => void;
}

/**
 * Run `fn` whenever `deps` change. State is only set from promise callbacks, so the
 * previous data stays visible while reloading.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [nonce, setNonce] = useState(0);
  const key = JSON.stringify(deps) + "#" + nonce;
  const [state, setState] = useState<{ key: string | null; data: T | undefined; error: unknown }>({
    key: null,
    data: undefined,
    error: undefined,
  });

  useEffect(() => {
    let alive = true;
    fn().then(
      (data) => alive && setState({ key, data, error: undefined }),
      (error: unknown) => alive && setState((s) => ({ key, data: s.data, error })),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T) => setState((s) => ({ ...s, data, error: undefined })), []);

  return {
    data: state.data,
    error: state.key === key ? state.error : undefined,
    loading: state.key !== key,
    reload,
    setData,
  };
}

/** Polls `fn` every `ms` while `active`. */
export function useInterval(fn: () => void, ms: number, active = true) {
  useEffect(() => {
    if (!active) return;
    const t = setInterval(fn, ms);
    return () => clearInterval(t);
  }, [fn, ms, active]);
}
