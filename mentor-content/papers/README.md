# Arena papers

One file per exam paper: `papers/<id>.json` (the file name is the paper id). The gateway reads them on start and when a file
changes; a file that fails validation is skipped and logged. Model: `mentor_schemas.paper.Paper`.

```jsonc
{
  "id": "thpt-toan-2025",                 // [a-z0-9._-], same as the file name
  "kind": "thpt",                         // thpt | minh-hoa | dgnl | cuoi-ky
  "band": "g10_12",                       // g10_12 | uni (students only see papers of their band)
  "chicken": "toan",                      // a chicken id of that band (see CONTRACTS-LANGGA section 1)
  "title_vi": "Đề thi tốt nghiệp THPT 2025, môn Toán",
  "title_en": "2025 national exam, maths",
  "year": 2025,
  "minutes": 90,                          // the countdown; the paper is submitted automatically at 0
  "parts": [
    {
      "id": "p1",                         // [a-z0-9_-], unique in the paper
      "title_vi": "Phần I. Trắc nghiệm nhiều lựa chọn",
      "title_en": "Part I. Multiple choice",
      "type": "SINGLE_CHOICE",            // informational (SINGLE_CHOICE | TRUE_FALSE_GROUP | SHORT_ANSWER | MIXED)
      "points_each": 0.25,                // optional; default = max_score / item count. The score shown is scaled to 10.
      "items": [ /* QuizItem, below */ ]
    }
  ],
  "source": { "name": "Bộ GD&ĐT", "url": "https://..." },
  "placeholder": false,                   // true = built from the bank, shown as "Đề mẫu"
  "note_vi": "", "note_en": ""            // optional, e.g. why a part is shortened
}
```

`items` are course quiz items (`mentor_schemas.course.QuizItem`), text only (no images or audio):

| type | fields |
|---|---|
| `SINGLE_CHOICE` | `options: [{id: "A", text}]`, `answer_key: {correct_option_id: "B"}` |
| `TRUE_FALSE_GROUP` | `statements: [{id: "a", text}]`, `answer_key: {statements: {a: true, b: false, ...}}` (4 statements scores 0.1 / 0.25 / 0.5 / 1 of the item's points for 1 / 2 / 3 / 4 right) |
| `SHORT_ANSWER` | `answer_key: {accepted: ["1,3", "1.3"], tolerance?: 0.01}` (numbers match as numbers; give both decimal marks) |

Every item also has `id` (unique in the paper), `stem` (Markdown + KaTeX), `explanation`, and optionally `hint`,
`option_feedback`, `skill_ids` (curriculum skill ids; they feed the learner's mastery), `difficulty` 1-4.

## Validate and import

```
uv run python -m mentor_gateway.langga.papers validate <dir>
uv run python -m mentor_gateway.langga.papers import <dir> [--content-dir mentor-content]
```

`validate` prints every problem (file, field, reason) and exits 1 when there is any. `import` validates, and only when the whole
directory is valid copies the files into `mentor-content/papers/` (an existing paper with the same id is replaced). The crawl
project writes its output in this format and runs `import`.

## Placeholders

`placeholder: true` papers are built from the question bank (`bank/`) with the 2025 structures, scaled down where the bank lacks
items (the title and `note_*` say so). Replace one by importing a real paper; delete the placeholder file when you do.
