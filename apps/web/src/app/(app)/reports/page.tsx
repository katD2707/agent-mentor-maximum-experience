"use client";

import { useState } from "react";
import { RoleGate } from "@/components/AuthGate";
import { Markdown } from "@/components/Markdown";
import { EmptyState, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { getApi } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { splitFrontmatter } from "@/lib/markdown";

function ReportView({ path }: { path: string }) {
  const q = useAsync(() => getApi().getFile(path), [path]);
  if (q.error != null) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data || q.data.path !== path) return <Loading />;
  // The period and flags live in the front matter; the learner sees them as the badges above, not as raw keys.
  return <Markdown>{splitFrontmatter(q.data.content).body}</Markdown>;
}

function Reports() {
  const q = useAsync(() => getApi().getReports(), []);
  const [chosen, setChosen] = useState<string | null>(null);
  const reports = [...(q.data ?? [])].sort((a, b) => b.period_end.localeCompare(a.period_end));
  const current = chosen ?? reports[0]?.path ?? null;

  return (
    <div className="page">
      <PageHeader
        title="Báo cáo phụ huynh"
        description="Các báo cáo đã gửi cho phụ huynh qua Zalo, hai tuần một lần. Bạn thấy đúng những gì phụ huynh nhận được."
      />
      <div className="alert alert-info">
        Báo cáo chỉ gồm tiến độ mục tiêu, mức độ đều đặn và xu hướng theo chủ đề.{" "}
        <strong>Không có điểm từng bài, nội dung trò chuyện hay những điều mentor nhớ về bạn.</strong>
      </div>
      {q.error != null && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.loading && !q.data && <Loading />}
      {q.data && reports.length === 0 && <EmptyState card>Chưa có báo cáo nào được gửi.</EmptyState>}
      {reports.length > 0 && (
        <div className="workbench">
          <nav aria-label="Danh sách báo cáo">
            <ul className="file-list">
              {reports.map((r) => (
                <li key={r.path}>
                  <button type="button" aria-current={r.path === current} onClick={() => setChosen(r.path)}>
                    <span className="name">
                      {formatDate(r.period_start)} – {formatDate(r.period_end)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          {current && (
            <section className="card" aria-label="Nội dung báo cáo">
              {(() => {
                const r = reports.find((x) => x.path === current)!;
                return (
                  <div className="row" style={{ marginBottom: 12 }}>
                    <span className="badge">
                      Kỳ {formatDate(r.period_start)} – {formatDate(r.period_end)}
                    </span>
                    {r.sent_at ? (
                      <span className="badge badge-ok">Đã gửi {formatDateTime(r.sent_at)}</span>
                    ) : (
                      <span className="badge badge-warn">Chưa gửi</span>
                    )}
                  </div>
                );
              })()}
              <ReportView path={current} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <RoleGate role="thpt" fallback="/chat">
      <Reports />
    </RoleGate>
  );
}
