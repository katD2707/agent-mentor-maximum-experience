<!-- Adapted from garethmanning/education-agent-skills, skills/ai-learning-science/individual-spacing-algorithm-explainer/SKILL.md (CC BY-SA 4.0). Changed: teacher-for-a-class rewritten for one student planned by software; nothing is ever asked of the student. See ATTRIBUTION.md. -->
# Individual spacing (with FSRS due items)

Use to size and order review sessions from the per-item data the code already computed (`due_items`, `mastery`).
- Rank by forgetting risk, not by importance: an item the student keeps getting wrong and is overdue comes first; a well-known item can wait.
- Each successful retrieval lengthens the interval; each miss shortens it. The code's FSRS schedule already does this per item: treat `due_items` as the list of what is due, and do not invent other intervals for those items.
- Interval roughly 10-20% of the time until the knowledge is needed: an exam in 3 weeks means short gaps now; no deadline means gradual expansion.
- Review slots are the student's real habit slots (`profile.windows`), 5-10 minutes each. Never plan more review than the student's real pace allows.
- The reason for a review slot is one plain sentence: what is due and why now.
