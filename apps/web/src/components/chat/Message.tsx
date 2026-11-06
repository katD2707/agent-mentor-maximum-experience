"use client";

import { memo, useState } from "react";
import type { CardEvent } from "@/lib/chat/cards";
import type { ChatMessage, ToolActivity } from "@/lib/chat/reducer";
import { formatTime } from "@/lib/format";
import { isToolFailure, plainStep, toolHeadline } from "@/lib/learner";
import type { ChatCard, MascotState } from "@/lib/types";
import { Icon } from "../Icon";
import { Markdown } from "../Markdown";
import { Mascot } from "../Mascot";
import { ChatCardView } from "./ChatCards";

/** Three dots while the mentor works on a reply that has no text yet. */
export function TypingDots({ label = "Mentor đang soạn trả lời" }: { label?: string }) {
  return (
    <span className="typing-dots" role="status">
      <i aria-hidden="true" />
      <i aria-hidden="true" />
      <i aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

/**
 * Tool activity of a turn as ONE neutral line ("Mentor đang tra cứu…"), with the steps behind a disclosure.
 * Failures are never shown as-is: in the detail they read "chưa thực hiện được", and file paths become "tệp".
 */
function ToolSummary({ tools }: { tools: ToolActivity[] }) {
  const running = tools.some((t) => t.status === "running");
  return (
    <details className="tools-fold" data-running={running || undefined}>
      <summary>
        {running && <span className="spinner" aria-hidden="true" />}
        <span>{toolHeadline(tools)}</span>
      </summary>
      <ul className="tools" aria-label="Chi tiết các bước mentor đã làm">
        {tools.map((t, i) => (
          <li key={i} className="tool" data-status={t.status}>
            <span className="tool-dot" aria-hidden="true" />
            <span className="tool-text">{isToolFailure(t.summary) ? "Một bước chưa thực hiện được, mentor đã thử cách khác." : plainStep(t.summary)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export interface MessageViewProps {
  m: ChatMessage;
  /** Live mascot next to this message (the newest mentor message only); null = no avatar. */
  avatar?: MascotState | null;
  /** The turn this message belongs to looks crisis-related. */
  crisis?: boolean;
  /** A turn is running: card buttons wait (the gateway refuses clicks meanwhile). */
  busy?: boolean;
  onCardEvent?: (card: ChatCard, ev: CardEvent) => void;
  onCelebrate?: (card: ChatCard) => void;
}

const noop = () => {};

function MessageViewImpl({ m, avatar = null, crisis = false, busy = false, onCardEvent, onCelebrate }: MessageViewProps) {
  // Mentor messages that start streaming in this tab rise in once; history and the learner's own
  // messages appear instantly (sending is a keyboard action and must feel immediate).
  const [enter] = useState(() => m.role === "mentor" && (m.status === "streaming" || m.live === true));

  if (m.role === "user") {
    return (
      <div className="msg msg-user" data-ts={m.createdAt}>
        {m.attachments.length > 0 && (
          <div className="chips" style={{ justifyContent: "flex-end", marginBottom: 0 }}>
            {m.attachments.map((a) => (
              <span key={a.path} className="chip" style={{ paddingRight: 10 }}>
                <Icon name="file" size={14} />
                <span className="name">{a.path.split("/").pop()}</span>
              </span>
            ))}
          </div>
        )}
        {m.text && <div className="bubble">{m.text}</div>}
        <div className="msg-meta">
          {m.status === "sending" ? "Đang gửi…" : m.status === "error" ? "Không hoàn tất" : formatTime(m.createdAt)}
        </div>
      </div>
    );
  }

  const avatarEl = avatar ? (
    <span className="msg-avatar">
      <Mascot state={avatar} size={30} tail="left" />
    </span>
  ) : null;

  if (m.card) {
    return (
      <div className="msg msg-mentor msg-card" data-avatar={avatar ? true : undefined} data-ts={m.createdAt}>
        {avatarEl}
        <ChatCardView
          card={m.card}
          ui={m.cardUi ?? {}}
          live={m.live === true && !!onCardEvent}
          busy={busy}
          crisis={crisis}
          onEvent={onCardEvent ?? noop}
          onCelebrate={onCelebrate}
        />
      </div>
    );
  }

  return (
    <div className={`msg msg-mentor${enter ? " msg-enter" : ""}`} data-avatar={avatar ? true : undefined} data-ts={m.createdAt}>
      {avatarEl}
      {m.tools.length > 0 && <ToolSummary tools={m.tools} />}
      {(m.text || m.status === "streaming") && (
        <div className="bubble">
          {m.text ? <Markdown>{m.text}</Markdown> : <TypingDots />}
          {m.status === "streaming" && m.text && <span className="typing" aria-hidden="true" />}
        </div>
      )}
      <div className="msg-meta">
        {m.status === "error" ? "Phản hồi bị gián đoạn" : m.status === "done" ? formatTime(m.createdAt) : ""}
      </div>
    </div>
  );
}

/** Memoised: only the streaming message re-renders on each text delta. */
export const MessageView = memo(MessageViewImpl);
