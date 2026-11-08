import { useCallback, useEffect, useReducer, useRef } from "react";
import { AskError, streamAsk, type AskRequest } from "../../api";
import { logEvent } from "../../lib/events";
import { askReducer, initialAsk, type AskState, type MeTurn } from "../../lib/askState";

export interface Ask {
  state: AskState;
  /** a request is running */
  busy: boolean;
  /** send a question; `me` is what the thread shows as the learner's message, `inPlace` keeps the answer in the latest solution */
  send(req: Omit<AskRequest, "lang" | "thread_id">, me?: Omit<MeTurn, "id" | "role">, opts?: { inPlace?: boolean }): Promise<void>;
  /** stop the running request (closes the stream) */
  cancel(): void;
}

/** One Hỏi đáp thread: the reducer plus the streaming request. Leaving the screen cancels a running request. */
export function useAsk(token: string | null, lang: "vi" | "en"): Ask {
  const [state, dispatch] = useReducer(askReducer, initialAsk);
  const ctl = useRef<AbortController | null>(null);
  const thread = useRef<string | null>(null);
  thread.current = state.threadId;

  const cancel = useCallback(() => {
    if (!ctl.current) return;
    ctl.current.abort();
    ctl.current = null;
    dispatch({ type: "cancel" });
  }, []);

  useEffect(() => () => ctl.current?.abort(), []);

  const send = useCallback<Ask["send"]>(
    async (req, me, opts) => {
      if (!token || ctl.current) return;
      const c = new AbortController();
      ctl.current = c;
      dispatch({ type: "send", me, inPlace: opts?.inPlace });
      const input = req.image ? "photo" : req.audio ? "voice" : "text";
      const run = (threadId: string | null) =>
        streamAsk(
          token,
          { ...req, lang, thread_id: threadId },
          (ev) => {
            if (ctl.current !== c) return;
            // behaviour log: a new question, once the server has routed it (follow-up buttons are not new questions)
            if (ev.event === "intent" && !req.action) logEvent("ask_question", { intent: ev.data.intent, input });
            dispatch({ type: "event", ev });
          },
          c.signal,
        );
      try {
        try {
          await run(thread.current);
        } catch (e) {
          // the server forgot the thread (kept 7 days): ask again as a fresh one, unless a follow-up needs it
          if (e instanceof AskError && e.code === "thread_not_found" && !req.action) {
            dispatch({ type: "forgetThread" });
            await run(null);
          } else throw e;
        }
        if (ctl.current === c) dispatch({ type: "event", ev: { event: "done", data: {} } });
      } catch (e) {
        if (c.signal.aborted) return;
        dispatch({ type: "fail", code: e instanceof AskError ? e.code : "network" });
      } finally {
        if (ctl.current === c) ctl.current = null;
      }
    },
    [token, lang],
  );

  return { state, busy: state.target >= 0, send, cancel };
}
