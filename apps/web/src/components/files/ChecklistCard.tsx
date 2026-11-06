"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { getApi, isApiError } from "@/lib/api";
import { fireConfetti, originOf } from "@/lib/confetti";
import { formatDate, localDateStamp } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { stripRefs } from "@/lib/learner";
import { parseChecklist, toggleChecklistLine, type ChecklistItem } from "@/lib/markdown";
import { Markdown } from "../Markdown";
import { useToast } from "../toast";
import { EmptyState, ErrorBox, Loading, errorText } from "../ui";

function daysUntil(date: string): number {
  const today = Date.parse(`${localDateStamp()}T00:00:00+07:00`);
  return Math.round((Date.parse(`${date}T00:00:00+07:00`) - today) / 86_400_000);
}

/** Section label for "the whole goal is done" (the heading, or the whole list). */
export function sectionDone(items: ChecklistItem[], section: string | null): boolean {
  const group = items.filter((i) => i.section === section);
  return group.length > 0 && group.every((i) => i.done);
}

/**
 * Renders `- [ ]` items of a workspace file and lets the learner tick them.
 * Writes go through PUT /workspace/file with base_sha; a 409 reloads the file. The tick shows at once
 * (optimistic) and rolls back if the write fails.
 * `celebrate`: "item" = every ticked item is a goal/milestone (confetti pop); "section" = confetti when the
 * last open item of a section is ticked; "none".
 */
export function ChecklistCard({
  path,
  title,
  section,
  variant = "list",
  emptyText,
  footer,
  celebrate = "section",
}: {
  path: string;
  title: string;
  section?: RegExp;
  variant?: "list" | "timeline";
  emptyText: string;
  footer?: ReactNode;
  celebrate?: "item" | "section" | "none";
}) {
  const toast = useToast();
  const q = useAsync(() => getApi().getFile(path), [path]);
  const [busyLine, setBusyLine] = useState<number | null>(null);
  const [justDone, setJustDone] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (!justDone) return;
    const t = window.setTimeout(() => setJustDone(null), 700);
    return () => window.clearTimeout(t);
  }, [justDone]);

  async function toggle(item: ChecklistItem, el: HTMLElement) {
    if (!q.data) return;
    const before = q.data;
    const content = toggleChecklistLine(before.content, item.line, !item.done, item.slot);
    const ticking = !item.done;
    setBusyLine(item.line);
    q.setData({ ...before, content }); // optimistic: the tick draws immediately
    if (ticking) setJustDone(`${item.line}:${item.slot}`);
    try {
      const r = await getApi().putFile(path, content, before.sha);
      q.setData({ path, content, sha: r.sha });
      if (ticking && celebrate !== "none") {
        const after = parseChecklist(content, section);
        const label = stripRefs(item.text).replace(/\*\*/g, "").replace(/[\s.!…]+$/u, "");
        if (celebrate === "item") {
          void fireConfetti({ origin: originOf(el), size: "pop" });
          toast(`Hoàn thành: ${label}. Làm tốt lắm!`, "ok");
        } else if (sectionDone(after, item.section)) {
          void fireConfetti({ origin: originOf(listRef.current) });
          toast(item.section ? `Xong cả mục “${item.section}”!` : "Xong hết danh sách rồi!", "ok");
        }
      }
    } catch (e) {
      q.setData(before);
      if (isApiError(e, 409)) {
        toast("Tệp vừa được cập nhật ở nơi khác. Đã tải lại, bạn thử lại nhé.", "error");
        q.reload();
      } else toast(errorText(e), "error");
    } finally {
      setBusyLine(null);
    }
  }

  const items = q.data ? parseChecklist(q.data.content, section) : [];
  const done = items.filter((i) => i.done).length;
  const nextIdx = items.findIndex((i) => !i.done);

  return (
    <section className="card" aria-labelledby={`cl-${path}`}>
      <div className="card-header">
        <h2 id={`cl-${path}`}>{title}</h2>
        {items.length > 0 && (
          <span className="badge badge-ok">
            {done}/{items.length} xong
          </span>
        )}
      </div>
      {q.error != null && (isApiError(q.error, 404) ? <EmptyState>{emptyText}</EmptyState> : <ErrorBox error={q.error} onRetry={q.reload} />)}
      {q.loading && !q.data && q.error == null && <Loading />}
      {q.data && items.length === 0 && <EmptyState>{emptyText}</EmptyState>}
      {items.length > 0 && (
        <ul className={variant === "timeline" ? "timeline" : "memory-items"} ref={listRef}>
          {items.map((it, i) => {
            const d = it.date ? daysUntil(it.date) : null;
            const label = stripRefs(it.text).replace(/\*\*/g, "");
            return (
              <li
                key={`${it.line}:${it.slot}`}
                data-done={it.done}
                data-next={i === nextIdx}
                data-just-done={justDone === `${it.line}:${it.slot}` || undefined}
              >
                {variant === "timeline" && <span className="marker" aria-hidden="true" />}
                <label className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", flex: 1, cursor: "pointer" }}>
                  <span className="check">
                    <input
                      type="checkbox"
                      checked={it.done}
                      disabled={busyLine !== null}
                      onChange={(e) => void toggle(it, e.currentTarget)}
                      aria-label={`${it.done ? "Bỏ đánh dấu" : "Đánh dấu xong"}: ${label}`}
                    />
                    <span className="check-box" aria-hidden="true">
                      <svg viewBox="0 0 16 16" width="14" height="14">
                        <path d="M3.5 8.5l3 3 6-6.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </span>
                  </span>
                  <span className="check-label" style={{ minWidth: 0 }}>
                    {it.date && (
                      <span className="row" style={{ gap: 6 }}>
                        <strong>{formatDate(it.date)}</strong>
                        {!it.done && d !== null && (
                          <span className={`badge ${d < 0 ? "badge-danger" : d <= 14 ? "badge-warn" : ""}`}>
                            {d < 0 ? `quá hạn ${-d} ngày` : d === 0 ? "hôm nay" : `còn ${d} ngày`}
                          </span>
                        )}
                      </span>
                    )}
                    <Markdown className="inline-md">{stripRefs(it.text)}</Markdown>
                    {it.section && variant === "list" && !section && <span className="section-label">{stripRefs(it.section)}</span>}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      {footer}
    </section>
  );
}
