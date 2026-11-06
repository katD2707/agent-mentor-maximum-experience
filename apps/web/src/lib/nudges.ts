/**
 * Nudge actions (CONTRACTS 9): one code path for the in-app toast, the notification centre, the desktop
 * balloon (`mentor://nudge-action`) and a Web Push click. The gateway applies the action; the UI only reacts.
 */
import { getApi } from "./api";
import type { NotificationAction } from "./types";

export interface NudgeOutcome {
  /** Text to put in the chat composer (`open`). */
  prefill: string | null;
  /** Short confirmation for a toast, or null when the action speaks for itself. */
  message: string | null;
}

/** Confirmation copy per action; `answer:<x>` echoes the answer. */
export function nudgeActionMessage(action: string, label?: string): string | null {
  if (action === "open") return null;
  if (action === "snooze_1h") return "Mình sẽ nhắc lại sau 1 giờ.";
  if (action === "done") return "Đã đánh dấu xong.";
  if (action === "start_focus") return "Bắt đầu phiên tập trung. Chúc bạn tập trung tốt!";
  if (action.startsWith("answer:")) return `Đã gửi: ${label ?? action.slice("answer:".length)}`;
  return label ? `Đã chọn: ${label}` : null;
}

/**
 * Calls POST /notifications/{id}/action. Without a server id (older gateway) only `open` works, locally.
 * Throws the ApiError on failure so the caller can show it.
 */
export async function performNudgeAction(
  serverId: string | undefined,
  action: string,
  opts: { fallbackPrefill?: string | null; actions?: NotificationAction[] } = {},
): Promise<NudgeOutcome> {
  const label = opts.actions?.find((a) => a.id === action)?.label;
  let prefill: string | null = null;
  if (serverId) {
    const r = await getApi().notificationAction(serverId, action);
    prefill = r?.prefill ?? null;
  }
  if (action === "open") prefill = prefill || opts.fallbackPrefill || null;
  return { prefill, message: nudgeActionMessage(action, label) };
}

/** The primary button: the first action that moves the learner forward. */
export function primaryActionId(actions: NotificationAction[]): string | null {
  const order = ["start_focus", "open", "done"];
  for (const id of order) if (actions.some((a) => a.id === id)) return id;
  return actions[0]?.id ?? null;
}
