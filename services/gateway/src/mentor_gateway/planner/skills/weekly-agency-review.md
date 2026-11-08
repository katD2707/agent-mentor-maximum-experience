<!-- Adapted from garethmanning/education-agent-skills, skills/student-learning/weekly-agency-review/SKILL.md (CC BY-SA 4.0). Changed: teacher-for-a-class rewritten for one student planned by software; nothing is ever asked of the student. See ATTRIBUTION.md. -->
# Weekly pattern review (agent-only)

Once a week (`mode: weekly_review`) read the past 7 days of recorded data and adjust the next week. The original skill is a conversation with the learner; here it is a silent analysis and the student is never asked anything.
- Separate what was recorded (sessions, minutes, accuracy, skipped slots, reminder outcomes) from your interpretation. Do not compute trends from sparse data: with fewer than 3 active days keep the plan close to the age-band default.
- Look for patterns in how the student studied: which slot is actually used, which weekday is skipped, whether accuracy drops late in a session, whether review was done.
- Offer alternative explanations rather than certainty (a lower score may be harder material).
- Output: adjust the plan, and put one natural sentence about the change in the item reason (for example: moved because Wednesday was skipped). Never judge the student.
