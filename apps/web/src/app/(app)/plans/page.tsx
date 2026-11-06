"use client";

import { ChecklistCard } from "@/components/files/ChecklistCard";
import { Markdown } from "@/components/Markdown";
import { PageHeader } from "@/components/ui";
import { getApi } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { parseChecklist } from "@/lib/markdown";
import { weekPlan } from "@/lib/learner";

const PATH = "goals/plans/this-week.md";

/** This week's own tasks: tickable when they are `- [ ]` items, plain text otherwise. Nothing the mentor does itself. */
function ThisWeek() {
  const q = useAsync(() => getApi().getFile(PATH).then((f) => f.content, () => null), []);
  if (q.data == null) return null;
  const plan = weekPlan(q.data);
  const section = plan.hasLearnerSection ? /việc của người học/i : undefined;
  if (parseChecklist(q.data, section).length > 0) {
    return (
      <div style={{ marginTop: 16 }}>
        <ChecklistCard
          path={PATH}
          title="Việc tuần này"
          section={section}
          emptyText="Chưa có việc nào cho tuần này."
          footer={
            plan.plain.length > 0 ? (
              <ul className="plain-list task-rest">
                {plan.plain.map((t) => (
                  <li key={t}>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            ) : null
          }
        />
      </div>
    );
  }
  if (!plan.text) return null;
  return (
    <section className="card" aria-labelledby="week-h" style={{ marginTop: 16 }}>
      <h2 id="week-h">Việc tuần này</h2>
      <Markdown>{plan.text}</Markdown>
    </section>
  );
}

export default function PlansPage() {
  return (
    <div className="page">
      <PageHeader title="Mục tiêu" description="Mục tiêu của bạn và những việc cần làm trong tuần này." />
      <ChecklistCard path="goals/goals.md" title="Tiến độ mục tiêu" celebrate="item" emptyText="Chưa có mục tiêu nào. Hãy kể với mentor điều bạn muốn đạt được." />
      <ThisWeek />
    </div>
  );
}
