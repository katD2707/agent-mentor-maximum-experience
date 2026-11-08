/** Fixture courses for the mock API (VITE_API_MOCK=1). Same shapes as the real content packs. */
import coverDien from "../assets/hub/khoa-hoc.jpg";
import coverTao from "../assets/courses/so-den-10.jpg";
import coverBayes from "../assets/courses/bayes.jpg";
import imgApple from "../assets/courses/apple.svg";
import imgBasket5 from "../assets/courses/basket-5.svg";
import imgBasket7 from "../assets/courses/basket-7.svg";
import imgBasket9 from "../assets/courses/basket-9.svg";
import imgField from "../assets/courses/field-lines.svg";
import { SOON_COVERS } from "./mock-soon";
import type { AssetRef, Block, CourseMeta, CoursePack, QuizItem, TreeChapter } from "./course";

const ZERO = "0".repeat(64);

/** Where each fixture asset lives in the bundle. Missing entries (the videos) simulate files that are not there. */
const FILES: Record<string, string> = {
  "images/field-lines.svg": imgField,
  "images/apple.svg": imgApple,
  "images/basket-5.svg": imgBasket5,
  "images/basket-7.svg": imgBasket7,
  "images/basket-9.svg": imgBasket9,
  "images/field-poster.svg": imgField,
};
const COVERS: Record<string, string> = {
  "vat-li-11-dien-truong": coverDien,
  "toan-1-dem-tao": coverTao,
  "xac-suat-bayes": coverBayes,
  ...SOON_COVERS,
};

export const mockAssetUrl = (_courseId: string, path: string): string | null => FILES[path] ?? null;
export const mockCoverUrl = (courseId: string): string | null => COVERS[courseId] ?? null;

const refs = new Map<string, AssetRef>();
function ref(path: string, mime: string): AssetRef {
  let r = refs.get(path);
  if (!r) refs.set(path, (r = { path, mime, sha256: ZERO, bytes: 0 }));
  return r;
}
const img = (p: string) => ref(p, "image/svg+xml");

function item(over: Partial<QuizItem> & Pick<QuizItem, "id" | "type" | "stem" | "answer_key" | "explanation">): QuizItem {
  return { options: [], statements: [], option_feedback: {}, skill_ids: [], difficulty: 2, ...over };
}

// ------------------------------------------------------------------ g10_12: Điện trường
const DIEN = "vat-li-11-dien-truong";

const dienBlocks2: Block[] = [
  {
    id: "l2-b1",
    kind: "text",
    md: "Đường sức điện là đường vẽ trong điện trường sao cho tiếp tuyến tại mỗi điểm trùng với hướng của vectơ cường độ điện trường tại điểm đó. Nhìn đường sức, em biết ngay chỗ nào điện trường mạnh, chỗ nào yếu.",
  },
  { id: "l2-b2", kind: "image", image: img("images/field-lines.svg"), alt: "Đường sức giữa điện tích dương và điện tích âm", caption: "Đường sức đi ra từ điện tích dương, đi vào điện tích âm." },
  {
    id: "l2-b3",
    kind: "video",
    video: ref("video/duong-suc.mp4", "video/mp4"),
    poster: img("images/field-poster.svg"),
    duration_s: 160,
    title: "Đường sức điện trong 2 phút 40 giây",
  },
  {
    id: "l2-b4",
    kind: "callout",
    variant: "remember",
    title: "Bốn điều cần nhớ",
    md: "1. Qua mỗi điểm chỉ vẽ được một đường sức, nên các đường sức không cắt nhau.\n2. Đường sức đi ra từ điện tích dương và đi vào điện tích âm.\n3. Chỗ điện trường mạnh, đường sức dày. Chỗ yếu, đường sức thưa.\n4. Đường sức của điện trường tĩnh không khép kín.",
  },
  {
    id: "l2-b5",
    kind: "text",
    md: "## Vì sao càng xa càng thưa?\n\nCường độ điện trường của điện tích điểm:\n\n$$E = k\\,\\frac{|q|}{\\varepsilon\\, r^2}$$\n\nVới $k = 9\\cdot 10^9\\ \\text{N}\\cdot\\text{m}^2/\\text{C}^2$. $E$ tỉ lệ nghịch với $r^2$: đi xa gấp đôi thì $E$ còn một phần tư, nên đường sức phải thưa ra.",
  },
  {
    id: "l2-b6",
    kind: "callout",
    variant: "example",
    title: "Ví dụ",
    md: "Điện tích $q = 4\\cdot 10^{-8}$ C trong không khí. Tính $E$ tại điểm cách $q$ 3 cm.\n\n$E_1 = 9\\cdot 10^9 \\cdot \\dfrac{4\\cdot 10^{-8}}{(0{,}03)^2} = 4\\cdot 10^5$ V/m.",
  },
  { id: "l2-b7", kind: "callout", variant: "tip", title: "Thầy Minh dặn", md: "Gặp bài hỏi chỗ nào điện trường mạnh hơn, nhìn độ dày đường sức trước rồi hãy tính." },
  {
    id: "l2-b8",
    kind: "quiz",
    title: "Kiểm tra",
    items: [
      item({
        id: "l2-q1",
        type: "SINGLE_CHOICE",
        stem: "Đường sức điện của điện tích dương điểm có dạng nào?",
        options: [
          { id: "A", text: "Các đường tròn đồng tâm" },
          { id: "B", text: "Các tia đi ra từ điện tích" },
          { id: "C", text: "Các tia đi vào điện tích" },
          { id: "D", text: "Các đường thẳng song song" },
        ],
        answer_key: { correct_option_id: "B" },
        hint: "Nhớ chiều: đường sức đi ra từ điện tích dương.",
        explanation: "Đường sức đi ra từ điện tích dương nên với một điện tích dương riêng lẻ, đó là các tia hướng ra xa.",
        option_feedback: { A: "Đường tròn đồng tâm là đường sức từ, không phải của điện trường tĩnh.", C: "Đường sức đi vào là của điện tích âm." },
      }),
      item({
        id: "l2-q2",
        type: "TRUE_FALSE_GROUP",
        stem: "Chọn đúng hoặc sai cho từng phát biểu về đường sức điện.",
        statements: [
          { id: "a", text: "Hai đường sức bất kì có thể cắt nhau." },
          { id: "b", text: "Chỗ đường sức dày thì điện trường mạnh." },
          { id: "c", text: "Đường sức điện trường tĩnh là đường khép kín." },
        ],
        answer_key: { statements: { a: false, b: true, c: false } },
        explanation: "Đường sức không cắt nhau, dày nghĩa là mạnh, và chúng bắt đầu ở điện tích dương rồi kết thúc ở điện tích âm nên không khép kín.",
      }),
      item({
        id: "l2-q3",
        type: "SHORT_ANSWER",
        stem: "Điện tích $q = 4\\cdot 10^{-8}$ C. Tại điểm cách $q$ 3 cm, $E = 4\\cdot 10^5$ V/m. Tại điểm cách 6 cm, $E$ bằng bao nhiêu V/m?",
        answer_key: { accepted: ["1e5", "100000"], tolerance: 0.01 },
        hint: "Khoảng cách gấp đôi thì E đổi bao nhiêu lần?",
        explanation: "r gấp đôi nên E giảm 4 lần: 4·10^5 : 4 = 10^5 V/m.",
      }),
    ],
  },
];

export const dienPack: CoursePack = {
  schema_version: 1,
  course_id: DIEN,
  version: 1,
  min_app_version: "0.1.0",
  language: "vi",
  age_band: "g10_12",
  title: "Vật lí 11: Điện trường",
  chapters: [
    {
      id: "ch1",
      title: "Điện trường",
      lessons: [
        {
          id: "l1",
          title: "Điện tích, định luật Cu-lông",
          est_minutes: 20,
          summary: "Hai điện tích hút hoặc đẩy nhau thế nào và mạnh bao nhiêu.",
          key_ideas: ["Điện tích cùng dấu đẩy, trái dấu hút", "Lực tỉ lệ nghịch với bình phương khoảng cách"],
          blocks: [
            { id: "l1-b1", kind: "text", md: "Hai điện tích điểm đặt trong chân không tác dụng lên nhau một lực tỉ lệ thuận với tích độ lớn hai điện tích và tỉ lệ nghịch với bình phương khoảng cách: $F = k\\dfrac{|q_1 q_2|}{r^2}$." },
            {
              id: "l1-b2",
              kind: "quiz",
              items: [
                item({
                  id: "l1-q1",
                  type: "SINGLE_CHOICE",
                  stem: "Hai điện tích cùng dấu đặt gần nhau sẽ như thế nào?",
                  options: [{ id: "A", text: "Hút nhau" }, { id: "B", text: "Đẩy nhau" }, { id: "C", text: "Không tác dụng" }],
                  answer_key: { correct_option_id: "B" },
                  explanation: "Cùng dấu thì đẩy, trái dấu thì hút.",
                }),
              ],
            },
          ],
        },
        {
          id: "l2",
          title: "Đường sức điện",
          est_minutes: 25,
          summary: "Cách đọc đường sức để biết hướng và độ mạnh của điện trường.",
          key_ideas: ["Đường sức không cắt nhau", "Chỗ dày thì mạnh, chỗ thưa thì yếu", "Đi ra từ điện tích dương, đi vào điện tích âm"],
          blocks: dienBlocks2,
        },
        {
          id: "l3",
          title: "Điện trường đều",
          est_minutes: 15,
          summary: "Điện trường có đường sức song song và cách đều nhau.",
          key_ideas: ["Cường độ như nhau tại mọi điểm", "Hiệu điện thế U = E·d"],
          blocks: [
            { id: "l3-b1", kind: "text", md: "Trong điện trường đều, vectơ cường độ điện trường tại mọi điểm giống nhau về hướng và độ lớn. Giữa hai bản kim loại phẳng song song tích điện trái dấu, ta có $U = E\\,d$." },
          ],
        },
      ],
    },
  ],
};

// ------------------------------------------------------------------ g1_5: Đếm táo
const TAO = "toan-1-dem-tao";
const basketOpt = (id: string, k: number, p: string) => ({ id, text: `${k}`, image: img(p) });

export const taoPack: CoursePack = {
  schema_version: 1,
  course_id: TAO,
  version: 1,
  min_app_version: "0.1.0",
  language: "vi",
  age_band: "g1_5",
  title: "Toán 1: Đếm táo",
  chapters: [
    {
      id: "ch1",
      title: "Đếm đến 10",
      lessons: [
        {
          id: "l1",
          title: "Cùng đếm táo",
          est_minutes: 8,
          summary: "Chạm từng quả táo để đếm.",
          key_ideas: ["Đếm từng quả một", "Số cuối cùng là số quả"],
          blocks: [
            { id: "l1-b1", kind: "text", md: "Cùng đếm táo nhé!" },
            { id: "l1-b2", kind: "image", image: img("images/apple.svg"), alt: "Một quả táo đỏ", caption: "Đây là quả táo." },
            {
              id: "l1-b3",
              kind: "quiz",
              items: [
                item({
                  id: "l1-q1",
                  type: "TAP_COUNT",
                  stem: "Chạm vào **5** quả táo.",
                  tap: { image: img("images/apple.svg"), total: 10 },
                  answer_key: { count: 5 },
                  hint: "Đếm lại chậm nhé.",
                  explanation: "Đúng rồi, năm quả táo.",
                }),
              ],
            },
            {
              id: "l1-b4",
              kind: "quiz",
              items: [
                item({
                  id: "l1-q2",
                  type: "PICTURE_CHOICE",
                  stem: "Giỏ nào có **7** quả táo?",
                  options: [basketOpt("A", 5, "images/basket-5.svg"), basketOpt("B", 7, "images/basket-7.svg"), basketOpt("C", 9, "images/basket-9.svg")],
                  answer_key: { correct_option_id: "B" },
                  hint: "Đếm lại chậm nhé.",
                  explanation: "Giỏ này có bảy quả táo.",
                }),
              ],
            },
          ],
        },
        {
          id: "l2",
          title: "Giỏ nào nhiều hơn",
          est_minutes: 6,
          summary: "So sánh số táo trong các giỏ.",
          key_ideas: ["Nhiều hơn, ít hơn"],
          blocks: [
            { id: "l2-b1", kind: "text", md: "Giỏ nào nhiều táo hơn?" },
            {
              id: "l2-b2",
              kind: "quiz",
              items: [
                item({
                  id: "l2-q1",
                  type: "PICTURE_CHOICE",
                  stem: "Giỏ nào có **9** quả táo?",
                  options: [basketOpt("A", 9, "images/basket-9.svg"), basketOpt("B", 5, "images/basket-5.svg")],
                  answer_key: { correct_option_id: "A" },
                  explanation: "Giỏ này có chín quả táo.",
                }),
              ],
            },
          ],
        },
      ],
    },
  ],
};

// ------------------------------------------------------------------ uni: Bayes (small, for the reading column)
const BAYES = "xac-suat-bayes";
export const bayesPack: CoursePack = {
  schema_version: 1,
  course_id: BAYES,
  version: 1,
  min_app_version: "0.1.0",
  language: "vi",
  age_band: "uni",
  title: "Xác suất thống kê: Suy luận Bayes",
  chapters: [
    {
      id: "ch2",
      title: "Suy luận Bayes",
      lessons: [
        {
          id: "s3",
          title: "Tiên nghiệm liên hợp Beta–Nhị thức",
          est_minutes: 18,
          summary: "Hậu nghiệm cùng họ với tiên nghiệm Beta.",
          key_ideas: ["Hậu nghiệm Beta(α+k, β+n−k)", "Trung bình hậu nghiệm là trung bình có trọng số"],
          blocks: [
            { id: "s3-b1", kind: "text", md: "Hậu nghiệm tỉ lệ với hợp lý nhân tiên nghiệm:\n\n$$p(\\theta\\mid x) = \\frac{p(x\\mid\\theta)\\,p(\\theta)}{p(x)} \\;\\propto\\; p(x\\mid\\theta)\\,p(\\theta).$$\n\nCái khó nằm ở mẫu số $p(x)=\\int p(x\\mid\\theta)\\,p(\\theta)\\,d\\theta$, thường không có dạng đóng." },
            { id: "s3-b2", kind: "callout", variant: "definition", title: "Định nghĩa", md: "Họ tiên nghiệm $\\mathcal{F}$ là *liên hợp* với mô hình $p(x\\mid\\theta)$ nếu hậu nghiệm luôn thuộc $\\mathcal{F}$." },
            { id: "s3-b3", kind: "text", md: "Với tiên nghiệm $\\theta\\sim\\operatorname{Beta}(\\alpha,\\beta)$ và $k$ lỗi trong $n$ lần kiểm:\n\n$$\\theta\\mid k \\;\\sim\\; \\operatorname{Beta}(\\alpha+k,\\ \\beta+n-k).$$" },
            {
              id: "s3-b4",
              kind: "quiz",
              title: "Kiểm tra nhanh",
              items: [
                item({
                  id: "s3-q1",
                  type: "SINGLE_CHOICE",
                  stem: "Tiên nghiệm Beta(2, 8), kiểm 20 sản phẩm thấy 3 lỗi. Hậu nghiệm là?",
                  options: [{ id: "A", text: "Beta(3, 20)" }, { id: "B", text: "Beta(5, 25)" }, { id: "C", text: "Beta(5, 28)" }],
                  answer_key: { correct_option_id: "B" },
                  explanation: "Beta(2+3, 8+17) = Beta(5, 25).",
                }),
              ],
            },
          ],
        },
      ],
    },
  ],
};

// ------------------------------------------------------------------ metadata
function kindsOf(pack: CoursePack): CourseMeta["media"] {
  const m = new Set<string>();
  for (const ch of pack.chapters)
    for (const ls of ch.lessons) for (const b of ls.blocks) m.add(b.kind === "text" || b.kind === "callout" || b.kind === "image" ? "reading" : b.kind);
  return [...m] as CourseMeta["media"];
}
const lessonsOf = (pack: CoursePack) => pack.chapters.flatMap((c) => c.lessons);

type Extra = Pick<CourseMeta, "subject" | "teacher_id" | "teacher_name" | "description_short" | "outcomes" | "est_minutes" | "level">;
const base = (pack: CoursePack, extra: Extra): CourseMeta => ({
  schema_version: 1,
  id: pack.course_id,
  title: pack.title,
  age_band: pack.age_band,
  language: pack.language,
  cover: "cover.webp",
  media: kindsOf(pack),
  lessons_count: lessonsOf(pack).length,
  latest_published: 1,
  versions: [{ version: 1, status: "published", created_at: "2026-10-20T08:00:00Z", published_at: "2026-10-21T08:00:00Z", pack_sha256: null, pack_bytes: null, note: "Bản đầu" }],
  ...extra,
});

export const FIXTURES: { meta: CourseMeta; pack: CoursePack }[] = [
  {
    pack: dienPack,
    meta: base(dienPack, {
      subject: "Vật lí",
      teacher_id: "u-gv",
      teacher_name: "Thầy Minh",
      description_short: "Điện tích, đường sức và cường độ điện trường theo SGK Vật lí 11. Có video, bài đọc ngắn và câu hỏi kiểm tra sau mỗi bài.",
      outcomes: ["Giải thích được vì sao điện tích hút, đẩy nhau mà không cần chạm", "Vẽ được đường sức quanh một hoặc hai điện tích", "Giải bài cường độ điện trường theo dạng đề thi"],
      est_minutes: 60,
      level: "intermediate",
    }),
  },
  {
    pack: taoPack,
    meta: base(taoPack, {
      subject: "Toán",
      teacher_id: "u-gv",
      teacher_name: "Cô Lan",
      description_short: "Đếm táo từ 1 đến 10 bằng hình và giọng đọc. Em chạm vào từng quả để đếm.",
      outcomes: ["Đếm được đến 10", "Chọn đúng giỏ có số táo cho trước"],
      est_minutes: 14,
      level: "basic",
    }),
  },
  {
    pack: bayesPack,
    meta: base(bayesPack, {
      subject: "Xác suất thống kê",
      teacher_id: "u-gv",
      teacher_name: "TS. Quang",
      description_short: "Suy luận Bayes cho tỉ lệ: tiên nghiệm Beta, hợp lý nhị thức, hậu nghiệm và khoảng tin cậy Bayes.",
      outcomes: ["Suy ra hậu nghiệm Beta từ dữ liệu nhị thức", "Đọc hậu nghiệm như trung bình có trọng số"],
      est_minutes: 18,
      level: "advanced",
    }),
  },
];

export function treeOf(pack: CoursePack): TreeChapter[] {
  return pack.chapters.map((c) => ({
    id: c.id,
    title: c.title,
    lessons: c.lessons.map((l) => ({
      id: l.id,
      title: l.title,
      est_minutes: l.est_minutes,
      summary: l.summary,
      key_ideas: l.key_ideas,
      media: kindsOf({ ...pack, chapters: [{ id: c.id, title: c.title, lessons: [l] }] }),
    })),
  }));
}
