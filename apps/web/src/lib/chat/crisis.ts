/**
 * Crisis context per turn (CONTRACTS 9): a turn whose mentor reply points to support lines or talks about
 * self-harm, or a session with a safety approval, gets no celebration, confetti, streak or playful mascot.
 */
import { isCrisisApproval, isCrisisText } from "../mascot";
import type { ApprovalCardState, ChatMessage } from "./reducer";

/**
 * One flag per message: true when the message's turn (from a learner message up to the next one) is
 * crisis-related. Cards in that turn inherit it, including cards that arrive before the crisis text.
 */
export function crisisFlags(messages: readonly ChatMessage[]): boolean[] {
  const flags = new Array<boolean>(messages.length).fill(false);
  let start = 0;
  const close = (end: number) => {
    let crisis = false;
    for (let i = start; i < end; i++) {
      const m = messages[i];
      if (m.role === "mentor" && m.text && isCrisisText(m.text)) crisis = true;
    }
    if (crisis) for (let i = start; i < end; i++) flags[i] = true;
  };
  messages.forEach((m, i) => {
    if (m.role === "user" && i > start) {
      close(i);
      start = i;
    }
  });
  close(messages.length);
  return flags;
}

/**
 * Is the current (last) turn crisis-related? Safety approvals count for the whole session, and a crisis turn
 * stays in force while the learner's next message has no reply text yet (no cheerful flip in between).
 */
export function currentTurnCrisis(messages: readonly ChatMessage[], approvals: readonly ApprovalCardState[]): boolean {
  if (approvals.some((a) => isCrisisApproval(a.approval))) return true;
  const flags = crisisFlags(messages);
  if (flags.length === 0) return false;
  if (flags[flags.length - 1]) return true;
  let lastUser = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      lastUser = i;
      break;
    }
  }
  const replied = messages.slice(lastUser + 1).some((m) => m.role === "mentor" && m.text.length > 0);
  return !replied && lastUser > 0 && flags[lastUser - 1];
}
