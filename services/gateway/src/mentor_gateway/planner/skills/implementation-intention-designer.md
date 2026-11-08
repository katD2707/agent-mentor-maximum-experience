<!-- Adapted from garethmanning/education-agent-skills, skills/wellbeing-motivation-agency/implementation-intention-designer/SKILL.md (CC BY-SA 4.0). Changed: teacher-for-a-class rewritten for one student planned by software; nothing is ever asked of the student. See ATTRIBUTION.md. -->
# If-then reminders (implementation intentions)

Use to write reminder text and to anchor it to a habit the data shows is real.
- A good reminder links a concrete cue to a small action: "after dinner, open lesson 3 and do the last 2 questions" rather than "keep going". Use the student's real habit slot (`profile.windows`) as the cue.
- Make the first step tiny and easy to start; starting is harder than continuing. Name the course, the lesson and the minutes.
- Only reference habits that are in the data. Do not invent personal barriers or motives.
- Follow-through low at a slot (`reminder_response`): change the slot or the size of the task, do not just repeat the reminder.
- Tone: warm, short, no pressure, no guilt.
