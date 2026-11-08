# Attribution

The eight skill files in this directory are adapted from **education-agent-skills** by Gareth Manning
(https://github.com/garethmanning/education-agent-skills), licensed under
**Creative Commons Attribution-ShareAlike 4.0 International** (https://creativecommons.org/licenses/by-sa/4.0/).

| File here | Original |
|---|---|
| spaced-practice-scheduler.md | skills/memory-learning-science/spaced-practice-scheduler |
| individual-spacing-algorithm-explainer.md | skills/ai-learning-science/individual-spacing-algorithm-explainer |
| study-strategy-selector.md | skills/self-regulated-learning/study-strategy-selector |
| weekly-agency-review.md | skills/student-learning/weekly-agency-review |
| flow-state-condition-designer.md | skills/wellbeing-motivation-agency/flow-state-condition-designer |
| implementation-intention-designer.md | skills/wellbeing-motivation-agency/implementation-intention-designer |
| motivation-diagnostic-task-redesign.md | skills/wellbeing-motivation-agency/motivation-diagnostic-task-redesign |
| interleaving-unit-planner.md | skills/memory-learning-science/interleaving-unit-planner |

Changes made (adaptation): condensed to a few rules each; rewritten from the point of view of a teacher planning for a whole
class to software planning for one student; every step that asks the learner a question was removed (the planner never asks
the student anything); outputs changed to the planner's JSON fields. The adapted text is shared under the same licence
(CC BY-SA 4.0): these files, and only these, stay under CC BY-SA 4.0 even though the rest of the repository is not.
The planner loads them into the model prompt (`planner/skills.py`).
