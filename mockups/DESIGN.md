# Design System: Mentor (student + teacher learning app)
**Project ID:** 329963714617921949 (design system asset 5a874cfa3c0b472ebd7d400ab0072270)

> Written in the Stitch `design-md` format (google-labs-code/stitch-skills) so it can be loaded into Stitch as the
> project's design system. Written in English because it is Stitch's working language; the UI copy itself is
> Vietnamese-first with an English switch.

## 1. Visual Theme & Atmosphere

A Vietnamese school notebook come to life. The signature surface is **vở ô li**, the grid-ruled exercise book every
Vietnamese child writes in: fine blue-violet rules every few millimetres, a stronger square every fourth line, and a
pink margin line on the left. It is used only where learning happens (today's plan, the lesson cover, the teacher's
drop zone, a solved problem). Everything else is plain paper, so the notebook surface always means "this is the thing
to do now".

The mood is calm, warm and quiet: a desk at night with one lamp on. Density is very low. Each screen has **one**
obvious next action, usually a large pill button. The app never asks the learner to configure, choose or fill in
anything beyond role, grade and language. Planning, reminders and difficulty are decided by Mentor in the background, so the
interface has no settings-heavy panels and no dashboards. Chat exists only inside Hỏi đáp.

The interface **grows and simplifies with age**. For grades 1–5 it becomes picture-first and voice-first: huge tap
targets, a speaker button next to every sentence, almost no text. For university it becomes reading-first: smaller
controls, a serif reading column, real formulas and diagrams. One layout, four densities.

## 2. Color Palette & Roles

- **Notebook Paper White (#F2F0F5)**: page background. A soft lilac grey rather than white, so large surfaces never glare; the purple ink still reads crisp on it.
- **Soft Sheet (#FAF9FB)**: raised surfaces such as lesson blocks, list rows on hover, settings groups.
- **Night Ink (#2B283F)**: primary text and the selected tab. A deep violet-black, the colour of ink, not pure black.
- **Faded Pencil (#5F5B74)**: secondary text, explanations, meta lines.
- **School Purple Ink (#5A4BC0)**: the one action colour, taken from the purple ink Vietnamese pupils write with.
  Primary buttons, progress, the camera button, focus rings. Never used for decoration.
- **Purple Ink Wash (#E9E5F6)**: tinted backgrounds for tags and the "Mentor planned this" note.
- **Teacher's Red Pen (#B23C3C)**: corrections. Wrong answers, unreadable photo regions, and the teacher's margin
  comments while reviewing a course. Learners recognise it as "the teacher marked this", which is more familiar and
  less alarming than a generic error red.
- **Highlighter Yellow (#F0D76E)** with **Soft Highlight (#F6EDCB)**: what the teacher selected to comment on, search
  matches, and the "new course" tag.
- **Full Marks Green (#1D7052)**: correct answers and finished days.
- **Waiting Amber (#925409)**: something is being prepared ("Mentor is reading your documents").
- **Notebook Rules (#E4E0EC fine, #D2CCE0 strong)** and **Margin Pink (#E9B4BF)**: only inside the ô li surface.

Dark mode keeps the same roles: paper becomes **Blackboard Violet (#15132A)**, ink becomes **Chalk (#ECEAF7)** and the
purple ink lightens to **Lavender Ink (#9C8AFF)** so it keeps contrast. Shadows are always neutral black, never tinted.

## 3. Typography Rules

- **Lexend** for the whole interface. It was designed to improve reading fluency, it has full Vietnamese diacritics,
  and its open, even letterforms work for a six-year-old and an undergraduate alike.
- **Literata** (serif) for long lesson text and formulas at university level, and for printed problems the learner
  photographed. It signals "now you are reading", separate from "now you are tapping".
- Weights: 400 for body, 500 for labels and tabs, 600 for headings and buttons, 700 only for the logo mark and the big
  score. No italics for emphasis; bold is enough.
- Letter-spacing is natural, headings slightly tightened. No all-caps labels anywhere, no small tracked eyebrows above
  headings.
- Base size moves with age: about 20px for grades 1–5, 18px for grades 6–9, 17px for grades 10–12, 16px for
  university. Headings scale from that base, at least 1.3× the body.

## 4. Component Stylings

* **Buttons:** Pill-shaped. The primary button is School Purple Ink with white text and a slightly darker bottom lip,
  like a physical key you press. Height follows age: about 68px for small children, about 46px for university. A
  secondary button is a pill with a thin pencil-grey outline and no fill. Text buttons are purple ink with no frame.
  Labels name the result ("Học tiếp", "Chụp lại", "Xuất bản"), never "Submit" or "OK".
* **Ask composer (Hỏi đáp):** a ChatGPT-style rounded bar pinned to the bottom of the Ask screen: a growing text
  field, then camera, photo library and microphone buttons side by side, and a round purple send button. No mode or
  reasoning selector. Course suggestions arrive as compact cards with a "+ Thêm" toggle; opening one shows the
  course as a tree (chapters, lessons, key ideas) with a two-sentence description.
* **Role picker (login):** two large illustrations, student and teacher, with no visible words. The chosen one gets
  a thick purple ring and a check badge. Errors appear only after a failed attempt, in red-pen tone.
* **Hub squares:** each of the four squares is filled edge to edge by one warm flat illustration (cream paper,
  purple ink, yellow, coral, mint, soft grain). The title sits on its own solid band at the bottom, never on top of the
  picture, and the bands slide up from below once when the hub opens, a few hundredths of a second apart.
* **Course covers:** every course has its own illustration chosen by Mentor from the course content. Covers live in
  their own rounded frame (square crop in lists, 16:10 on cards, round in small chips such as the courses under a goal)
  and never sit behind text, so rows with and without a cover align identically.
* **Cards/Containers:** Few cards. Lists are open rows separated by fine rules, not boxes. The single "today" block and
  lesson covers use the ô li surface with generously rounded corners (about 22px; 28px for small children; 16px for
  university) and a soft, low, neutral shadow. Teacher comments hang in the right margin like red-pen notes.
* **Tags:** small pills with tinted backgrounds: purple wash for subjects, highlighter yellow for "Mới", green for
  "Đã xuất bản", amber for "Đang soạn", red-pen wash for "Cần chụp lại".
* **Inputs/Forms:** almost none. The search field is a pill with a pencil-grey outline that turns purple with a pale
  purple halo ring on focus. The teacher's drop zone is a whole ô li page with a dashed purple border that turns solid
  while a file is dragged over it.
* **Quiz options:** full-width rows with a letter key in a rounded square. Right turns Full Marks Green; wrong turns
  red pen and the correct option lights up green next to it, followed by one short sentence explaining the slip.

## 5. Layout Principles

- One column, left-aligned, max reading width about 68 characters for lessons and 1080px for the page. Text is never
  centred except the score on the result screen.
- Learners land on one hub of **four large squares**: Khóa học, Luyện tập, Hỏi đáp, Tiến độ. Each square carries
  one live line from Mentor (tonight's lesson, today's practice, goals). There are no tabs and no bottom bar; every
  feature screen has a grid button top-left to return to the hub.
- Settings is only a small gear button top-right that opens a popover (grade, language, theme, reminders, quiet
  time for 30 min / 1 h / 2 h / until tomorrow / this week / a custom day and time, log out). A small amber dot on the
  gear shows quiet time is on.
  There is no settings page.
- Lesson, practice and photo screens are focus screens: only a close button and a progress bar remain.
- The teacher side has no navigation at all: one drop zone, one list of courses, one review screen per course.
- Whitespace is generous and grows with the learner's youth. Spacing steps: 8, 12, 16, 20, 24, 32, 40px.
- Every state that waits on Mentor (reading documents, writing lessons) says so in one calm sentence and tells the
  user they can close the app. No spinners that demand attention.
- Motion makes the app feel alive but never blocks a tap: pages cross-fade, content arrives in a short stagger,
  progress bars fill from zero, numbers count up, the main headline gets a highlighter swipe, hub squares lean toward
  the pointer, buttons press in with a ripple, and right answers, added courses, saved goals and publishing throw a
  small confetti burst. Everything turns off under reduced-motion.
- A guide character, **Mực** (an original purple ink-drop with a pencil), lives on every screen. Tap it for a speech
  bubble; hold and drag it onto anything to hear what that part does; afterwards it runs off to a new spot.
