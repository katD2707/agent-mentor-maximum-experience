"use client";

import { RoleGate } from "@/components/AuthGate";
import { ChecklistCard } from "@/components/files/ChecklistCard";
import { Markdown } from "@/components/Markdown";
import { EmptyState, PageHeader } from "@/components/ui";
import { getApi } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { stripRefs } from "@/lib/learner";
import { splitFrontmatter } from "@/lib/markdown";

function ResearchQuestion() {
  const q = useAsync(() => getApi().getFile("research/thesis.md"), []);
  const rq = q.data ? researchQuestions(q.data.content) : null;
  if (!rq) return null;
  return (
    <section className="card" aria-labelledby="rq-title">
      <h2 id="rq-title">Câu hỏi nghiên cứu</h2>
      <Markdown>{stripRefs(rq)}</Markdown>
    </section>
  );
}

/** A bold `**Câu hỏi nghiên cứu:** …` line, else the body of the template's `## Câu hỏi nghiên cứu` section. */
function researchQuestions(content: string): string | null {
  const bold = content.match(/\*\*Câu hỏi nghiên cứu:?\*\*:?\s*(.+)/i);
  if (bold) return bold[1];
  const sec = content.match(/^#{2,6}\s*Câu hỏi nghiên cứu\s*$([\s\S]*?)(?=^#{1,6}\s|(?![\s\S]))/im);
  const body = sec?.[1].replace(/<!--[\s\S]*?-->/g, "").trim();
  return body || null;
}

interface PaperNote {
  key: string;
  title: string;
  body: string;
}

const humanize = (name: string) => {
  const t = name.replace(/\.md$/i, "").replace(/[-_]+/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

/** Paper notes as a readable list: the note's own title, opening it shows the note rendered. No paths. */
function PaperNotes() {
  const q = useAsync(async (): Promise<PaperNote[]> => {
    const tree = await getApi().getTree("research/papers");
    const files = tree.filter((e) => e.type === "file" && /\.md$/i.test(e.path)).slice(0, 40);
    const notes = await Promise.all(
      files.map(async (e) => {
        const f = await getApi().getFile(e.path).catch(() => null);
        if (!f) return null;
        const body = splitFrontmatter(f.content).body;
        const title = body.match(/^#\s+(.+)$/m)?.[1].trim() ?? humanize(e.path.split("/").pop() ?? "");
        return { key: e.path, title, body: body.replace(/^#\s+.+\n+/, "") };
      }),
    );
    return notes.filter((n): n is PaperNote => n !== null).sort((a, b) => a.title.localeCompare(b.title, "vi"));
  }, []);
  if (q.error != null || !q.data) return null;
  return (
    <section className="card" aria-labelledby="papers-h" style={{ marginTop: 16 }}>
      <h2 id="papers-h">Ghi chú paper</h2>
      {q.data.length === 0 ? (
        <EmptyState>Chưa có ghi chú paper nào. Đọc xong một paper, mentor sẽ giúp bạn ghi lại.</EmptyState>
      ) : (
        q.data.map((n) => (
          <details key={n.key} className="paper-note">
            <summary>{n.title}</summary>
            <Markdown>{stripRefs(n.body)}</Markdown>
          </details>
        ))
      )}
    </section>
  );
}

function Research() {
  return (
    <div className="page">
      <PageHeader title="Nghiên cứu" description="Câu hỏi nghiên cứu, mốc tiến độ luận văn, hàng đợi đọc và ghi chú paper." />
      <ResearchQuestion />
      <div className="grid-2" style={{ marginTop: 16 }}>
        <ChecklistCard
          path="research/thesis.md"
          title="Mốc tiến độ luận văn"
          section={/mốc|milestone/i}
          variant="timeline"
          celebrate="item"
          emptyText="Chưa có mốc nào. Hãy nhờ mentor lập các mốc tiến độ luận văn."
        />
        <ChecklistCard
          path="research/reading-queue.md"
          title="Hàng đợi đọc"
          emptyText="Hàng đợi đọc trống. Mentor sẽ gợi ý paper mới mỗi tuần."
          footer={<p className="hint" style={{ marginTop: 10 }}>Đánh dấu khi đọc xong; mentor sẽ hỏi bạn tóm tắt trước khi góp ý.</p>}
        />
      </div>
      <PaperNotes />
    </div>
  );
}

export default function ResearchPage() {
  return (
    <RoleGate role="ncs" fallback="/progress">
      <Research />
    </RoleGate>
  );
}
