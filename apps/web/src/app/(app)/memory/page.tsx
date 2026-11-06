"use client";

import { useState } from "react";
import { Markdown } from "@/components/Markdown";
import { useToast } from "@/components/toast";
import { ConfirmDialog, EmptyState, ErrorBox, Loading, PageHeader, errorText } from "@/components/ui";
import { getApi, isApiError } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { refDate, relativeDay, stripRefs } from "@/lib/learner";
import { parseMemoryItems, removeLine, replaceBulletText } from "@/lib/markdown";
import type { WorkspaceFile } from "@/lib/types";

const SECTIONS: { path: string; label: string }[] = [
  { path: "me/profile.md", label: "Hồ sơ" },
  { path: "me/now.md", label: "Hiện tại" },
  { path: "me/preferences.md", label: "Sở thích" },
  { path: "me/people.md", label: "Người quen" },
  { path: "me/what-works.md", label: "Điều gì hiệu quả" },
];

const shown = (text: string) => stripRefs(text.replace(/^\[suy luận\]\s*/i, ""));

type Files = Record<string, WorkspaceFile | null>;

function Memory() {
  const toast = useToast();
  const q = useAsync<Files>(async () => {
    const out: Files = {};
    await Promise.all(
      SECTIONS.map(async (s) => {
        out[s.path] = await getApi()
          .getFile(s.path)
          .catch((e: unknown) => {
            if (isApiError(e, 404)) return null;
            throw e;
          });
      }),
    );
    return out;
  }, []);
  const [editing, setEditing] = useState<{ path: string; line: number; text: string } | null>(null);
  const [forget, setForget] = useState<{ path: string; line: number; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function write(path: string, change: (content: string) => string, done: string, close: () => void) {
    const file = q.data?.[path];
    if (!file) return;
    setBusy(true);
    try {
      const content = change(file.content);
      const r = await getApi().putFile(path, content, file.sha);
      q.setData({ ...q.data!, [path]: { path, content, sha: r.sha } });
      toast(done, "ok");
      close();
    } catch (e) {
      if (isApiError(e, 409)) {
        toast("Mentor vừa cập nhật phần này. Đã tải lại, bạn thử lại nhé.", "error");
        q.reload();
        close();
      } else toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  }

  const groups = SECTIONS.map((s) => {
    const file = q.data?.[s.path];
    // "Profile: thpt" is the platform's own field in profile.md, not something the mentor learned.
    const items = file ? parseMemoryItems(file.content).filter((i) => !/^profile\s*:/i.test(i.text.trim())) : [];
    return { ...s, items };
  }).filter((g) => g.items.length > 0);

  return (
    <div className="page">
      <PageHeader
        title="Mentor nhớ gì về tôi"
        description="Những điều mentor đã ghi nhớ. Sai thì bấm Sửa, không muốn mentor nhớ nữa thì bấm Quên."
      />
      {q.error != null && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.loading && !q.data && <Loading />}
      {q.data && groups.length === 0 && <EmptyState card>Mentor chưa ghi nhớ điều gì về bạn.</EmptyState>}
      {groups.map((g) => (
        <section key={g.path} className="card mem-group" aria-labelledby={`mem-${g.path}`}>
          <h2 id={`mem-${g.path}`}>{g.label}</h2>
          <ul className="memory-items">
            {g.items.map((it) => {
              const text = shown(it.text);
              const when = refDate(it.text);
              const isEditing = editing?.path === g.path && editing.line === it.line;
              return (
                <li key={it.line}>
                  {isEditing ? (
                    <form
                      style={{ flex: 1, display: "flex", gap: 8, flexWrap: "wrap" }}
                      onSubmit={(e) => {
                        e.preventDefault();
                        const t = editing.text.trim();
                        if (!t || t === text) return setEditing(null);
                        void write(g.path, (c) => replaceBulletText(c, it.line, t), "Đã sửa.", () => setEditing(null));
                      }}
                    >
                      <label className="sr-only" htmlFor="mem-edit">
                        Nội dung mục nhớ
                      </label>
                      <input
                        id="mem-edit"
                        className="input"
                        style={{ flex: 1, minWidth: 200 }}
                        value={editing.text}
                        autoFocus
                        onChange={(e) => setEditing({ ...editing, text: e.target.value })}
                      />
                      <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
                        Lưu
                      </button>
                      <button type="button" className="btn btn-sm" onClick={() => setEditing(null)} disabled={busy}>
                        Huỷ
                      </button>
                    </form>
                  ) : (
                    <>
                      <div className="text">
                        {it.inferred && (
                          <span className="badge badge-warn" style={{ marginRight: 6 }}>
                            Suy luận
                          </span>
                        )}
                        <Markdown className="inline-md">{text}</Markdown>
                        {when && <span className="mem-when">{relativeDay(when)}</span>}
                      </div>
                      <div className="mem-actions">
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => setEditing({ path: g.path, line: it.line, text })}
                          aria-label={`Sửa: ${text.slice(0, 80)}`}
                        >
                          Sửa
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => setForget({ path: g.path, line: it.line, text })}
                          aria-label={`Quên: ${text.slice(0, 80)}`}
                        >
                          Quên
                        </button>
                      </div>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {groups.some((g) => g.items.some((i) => i.inferred)) && (
        <p className="hint" style={{ marginTop: 10 }}>
          Mục có nhãn “Suy luận” là điều mentor tự đoán, không phải bạn nói trực tiếp. Nếu sai, hãy sửa hoặc quên.
        </p>
      )}
      <ConfirmDialog
        open={!!forget}
        title="Quên mục này?"
        confirmLabel="Quên"
        danger
        busy={busy}
        onConfirm={() => forget && void write(forget.path, (c) => removeLine(c, forget.line), "Mentor sẽ không còn nhớ mục này.", () => setForget(null))}
        onCancel={() => setForget(null)}
      >
        <p>Mentor sẽ không còn nhớ điều này:</p>
        <blockquote className="md" style={{ margin: 0 }}>
          {forget?.text}
        </blockquote>
      </ConfirmDialog>
    </div>
  );
}

export default function MemoryPage() {
  return <Memory />;
}
