"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getApi } from "@/lib/api";
import { rise, useReducedMotion } from "@/lib/motion";
import { mockRoute, practiceRoute } from "@/lib/practice/routes";
import type { MockCard, PracticeCard } from "@/lib/types";
import { useAsync } from "@/lib/hooks";
import { Icon } from "../Icon";

/**
 * Chat card `practice` / `mock` (CONTRACTS 10.5/10.6): one button that opens the setup or the mock confirmation,
 * prefilled. Nothing starts here. Unknown topics/profiles are tolerated: the target page falls back to its defaults.
 * In the desktop pop-up the full page opens in the browser (the pop-up is too small for the player).
 */
export function PracticeLinkCard({ card, live }: { card: PracticeCard | MockCard; live: boolean }) {
  const reduce = useReducedMotion();
  const pathname = usePathname();
  const popup = pathname.startsWith("/popup");
  const r = rise(reduce, { y: 10, scale: 0.97 });
  const isMock = card.kind === "mock";
  // Only to name the subject and hide the button when the bank no longer offers it.
  const subjects = useAsync(() => getApi().practice.subjects().catch(() => null), []);
  const subject = subjects.data?.find((s) => s.id === card.subject);
  const gone = isMock && !!subject && !subject.mock_profiles.some((p) => p.id === (card as MockCard).profile_id);
  const href = isMock
    ? mockRoute({ subject: card.subject, profile_id: gone ? undefined : (card as MockCard).profile_id })
    : practiceRoute({ subject: card.subject, minutes: (card as PracticeCard).minutes, goal: (card as PracticeCard).goal, topics: (card as PracticeCard).topics });
  const label = isMock ? "Xem và bắt đầu thi thử" : "Chọn buổi luyện này";
  const title = `${card.title}`;
  const body = (
    <>
      <Icon name="cards" size={16} /> {label}
    </>
  );
  return (
    <motion.section className={`cc cc-${card.kind}`} aria-label={isMock ? "Gợi ý thi thử" : "Gợi ý luyện tập"} initial={live ? r.initial : false} animate={r.animate} transition={r.transition}>
      <header className="cc-head">
        <span className="cc-icon" aria-hidden="true">
          <Icon name="cards" size={18} />
        </span>
        <div className="cc-titles">
          <h3 className="cc-title">{title}</h3>
          <p className="cc-meta">
            {subject?.label ?? card.subject}
            {card.kind === "practice" && ` · ${card.minutes} phút`}
          </p>
        </div>
      </header>
      {card.kind === "practice" && card.reason && <p className="cc-body">{card.reason}</p>}
      {gone && <p className="cc-meta">Đề này không còn nữa, mình sẽ chọn đề thi thử gần nhất.</p>}
      <div className="row">
        {popup ? (
          <a className="btn btn-primary btn-sm" href={href} target="_blank" rel="noopener">
            {body}
          </a>
        ) : (
          <Link className="btn btn-primary btn-sm" href={href}>
            {body}
          </Link>
        )}
      </div>
    </motion.section>
  );
}
