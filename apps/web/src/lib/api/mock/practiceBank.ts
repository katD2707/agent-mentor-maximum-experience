/**
 * A small invented question bank for mock mode (tests and `pnpm dev` without the gateway). Not the real bank: the
 * real items live in mentor-content/bank and are served by the gateway. Keys here never leave `MockPractice`.
 */
import type { ItemType, PracticeAsset } from "../../practice/types";

export interface BankItem {
  id: string;
  subject: string;
  topic: string;
  topicTitle: string;
  type: ItemType;
  level: 1 | 2 | 3 | 4;
  stem: string;
  options?: { id: string; text: string }[];
  key?: string;
  statements?: { id: string; text: string; truth: boolean; explanation?: string }[];
  sa?: { answer: string; decimals: number | null; max_chars: number | null; unit?: string };
  hint: string;
  explanation: string;
  tip?: string;
  optionFeedback?: Record<string, string>;
  assets?: PracticeAsset[];
  /** Assets placed only in the solution (shown after the answer is revealed). */
  solutionAssets?: PracticeAsset[];
  seconds: number;
}

export const SUBJECT_META: Record<string, { label: string; topics: Record<string, string> }> = {
  math: { label: "Toán", topics: { function: "Hàm số", calculus: "Đạo hàm và tích phân", geometry: "Hình học", stats: "Xác suất, thống kê" } },
  physics: { label: "Vật lí", topics: { mechanics: "Cơ học", thermal: "Nhiệt học" } },
  english: { label: "Tiếng Anh", topics: { grammar: "Ngữ pháp", vocabulary: "Từ vựng" } },
};

const LETTERS = ["A", "B", "C", "D"];

function mcq(
  id: string,
  subject: string,
  topic: string,
  level: 1 | 2 | 3 | 4,
  stem: string,
  opts: string[],
  key: string,
  hint: string,
  explanation: string,
  extra: Partial<BankItem> = {},
): BankItem {
  return {
    id,
    subject,
    topic,
    topicTitle: SUBJECT_META[subject].topics[topic],
    type: "SINGLE_CHOICE",
    level,
    stem,
    options: opts.map((text, i) => ({ id: LETTERS[i], text })),
    key,
    hint,
    explanation,
    seconds: 60 + level * 20,
    ...extra,
  };
}

const parabola: PracticeAsset = {
  id: "fig1",
  type: "diagram",
  alt_text: "Đồ thị hàm số y = x^2 - 2x với đỉnh I(1; -1)",
  diagram: {
    kind: "function_plot",
    x_min: -2,
    x_max: 4,
    y_min: -2,
    y_max: 5,
    functions: [{ expr: "x^2 - 2*x", label: "y = f(x)" }],
    points: [{ x: 1, y: -1, label: "I" }],
    show_grid: true,
  },
};

const triangle: PracticeAsset = {
  id: "fig2",
  type: "diagram",
  alt_text: "Tam giác ABC vuông tại A với AB = 4, AC = 3",
  diagram: {
    kind: "geometry",
    points: [
      { id: "A", x: 0, y: 0 },
      { id: "B", x: 4, y: 0 },
      { id: "C", x: 0, y: 3 },
    ],
    segments: [
      { from: "A", to: "B", label: "4" },
      { from: "A", to: "C", label: "3" },
      { from: "B", to: "C", dashed: false, label: "5" },
    ],
    right_angles: [{ vertex: "A", from: "B", to: "C" }],
  },
};

const incline: PracticeAsset = {
  id: "fig3",
  type: "diagram",
  alt_text: "Vật nằm trên mặt phẳng nghiêng 30 độ chịu trọng lực P và phản lực N",
  diagram: {
    kind: "force_diagram",
    body: "box",
    incline_deg: 30,
    forces: [
      { label: "P", angle_deg: 270, magnitude: 1 },
      { label: "N", angle_deg: 120, magnitude: 0.87 },
    ],
  },
};

const BAD_FORMULA = "Hàm số $\\frac{1}{ có công thức lỗi vẫn hiện được nhưng không làm hỏng trang";

export const BANK: BankItem[] = [
  // ---- math / function
  mcq("math.function.001", "math", "function", 2, "Cho hàm số $y = x^2 - 2x$ có đồ thị như hình. Tọa độ đỉnh $I$ của parabol là", ["$I(1; -1)$", "$I(-1; 3)$", "$I(2; 0)$", "$I(0; 0)$"], "A", "Dùng công thức hoành độ đỉnh $x = -\\frac{b}{2a}$.", "Hoành độ đỉnh $x_I = -\\frac{-2}{2\\cdot 1} = 1$, suy ra $y_I = 1 - 2 = -1$. Vậy $I(1; -1)$.", {
    assets: [parabola],
    optionFeedback: { B: "Bạn đổi dấu hoành độ đỉnh.", C: "Đây là một giao điểm với trục hoành, không phải đỉnh.", D: "Đây là giao điểm với trục tung." },
    tip: "Đỉnh nằm giữa hai nghiệm khi parabol cắt trục hoành.",
  }),
  mcq("math.function.002", "math", "function", 1, "Tập xác định của hàm số $y = \\sqrt{x - 1}$ là", ["$[1; +\\infty)$", "$(1; +\\infty)$", "$(-\\infty; 1]$", "$\\mathbb{R}$"], "A", "Biểu thức dưới căn phải không âm.", "Điều kiện $x - 1 \\ge 0 \\iff x \\ge 1$.", {
    optionFeedback: { B: "Căn bậc hai cho phép bằng 0 nên đầu mút 1 được lấy.", C: "Bạn lấy dấu bất đẳng thức ngược.", D: "Hàm có căn nên có điều kiện." },
  }),
  mcq("math.function.003", "math", "function", 2, "Hàm số $y = x^3 - 3x$ nghịch biến trên khoảng nào?", ["$(-1; 1)$", "$(-\\infty; -1)$", "$(1; +\\infty)$", "$(0; +\\infty)$"], "A", "Xét dấu $y'$.", "$y' = 3x^2 - 3 < 0 \\iff -1 < x < 1$.", {}),
  mcq("math.function.004", "math", "function", 3, "Giá trị lớn nhất của hàm số $y = -x^2 + 4x + 1$ bằng", ["$5$", "$4$", "$1$", "$3$"], "A", "Hàm bậc hai có $a<0$ đạt max tại đỉnh.", "Đỉnh tại $x = 2$, $y = -4 + 8 + 1 = 5$.", {}),
  mcq("math.function.005", "math", "function", 4, BAD_FORMULA + ". Tập nghiệm của $x^2 = 4$ là", ["$\\{-2; 2\\}$", "$\\{2\\}$", "$\\{4\\}$", "$\\{-4; 4\\}$"], "A", "Căn hai vế.", "$x = \\pm 2$.", {}),
  // ---- math / calculus
  ...[2, 3, 4, 5].map((n) =>
    mcq(`math.calculus.00${n}`, "math", "calculus", 1, `Đạo hàm của hàm số $y = x^{${n}}$ là`, [`$y' = ${n}x^{${n - 1}}$`, `$y' = x^{${n - 1}}$`, `$y' = ${n - 1}x^{${n}}$`, `$y' = ${n}x^{${n}}$`], "A", "Quy tắc $(x^n)' = nx^{n-1}$.", `Áp dụng $(x^n)' = nx^{n-1}$ với $n = ${n}$.`, {
      optionFeedback: { B: "Bạn quên hệ số $n$.", C: "Bạn nhân với $n-1$ thay vì $n$.", D: "Bạn không giảm số mũ." },
    }),
  ),
  mcq("math.calculus.010", "math", "calculus", 3, "Tính $\\displaystyle\\int_0^1 2x\\,dx$.", ["$1$", "$2$", "$\\frac{1}{2}$", "$0$"], "A", "Nguyên hàm của $2x$ là $x^2$.", "$\\int_0^1 2x\\,dx = x^2\\big|_0^1 = 1$.", {}),
  {
    id: "math.calculus.020",
    subject: "math",
    topic: "calculus",
    topicTitle: "Đạo hàm và tích phân",
    type: "TRUE_FALSE_GROUP",
    level: 3,
    stem: "Cho hàm số $f(x) = x^3 - 3x + 1$. Xét các mệnh đề sau.",
    statements: [
      { id: "a", text: "$f'(x) = 3x^2 - 3$.", truth: true, explanation: "Đạo hàm từng số hạng." },
      { id: "b", text: "Hàm số đồng biến trên khoảng $(-1; 1)$.", truth: false, explanation: "Trên $(-1;1)$ ta có $f'(x) < 0$ nên hàm nghịch biến." },
      { id: "c", text: "Hàm số có hai điểm cực trị.", truth: true, explanation: "$f'(x)=0$ có hai nghiệm $x=\\pm 1$ và đổi dấu." },
      { id: "d", text: "Giá trị cực đại của hàm số bằng $-1$.", truth: false, explanation: "$f(-1) = -1 + 3 + 1 = 3$." },
    ],
    hint: "Tính $f'(x)$ rồi xét dấu.",
    explanation: "$f'(x)=3x^2-3$; $f'>0$ khi $|x|>1$, $f'<0$ khi $|x|<1$. Cực đại $f(-1)=3$, cực tiểu $f(1)=-1$.",
    seconds: 150,
  },
  {
    id: "math.calculus.021",
    subject: "math",
    topic: "calculus",
    topicTitle: "Đạo hàm và tích phân",
    type: "TRUE_FALSE_GROUP",
    level: 2,
    stem: "Xét hàm số $y = e^x$.",
    statements: [
      { id: "a", text: "Tập xác định là $\\mathbb{R}$.", truth: true },
      { id: "b", text: "$y' = e^x$.", truth: true },
      { id: "c", text: "Đồ thị cắt trục hoành.", truth: false, explanation: "$e^x > 0$ với mọi $x$." },
      { id: "d", text: "Hàm số nghịch biến trên $\\mathbb{R}$.", truth: false, explanation: "$y' = e^x > 0$." },
    ],
    hint: "Nhớ tính chất của hàm mũ.",
    explanation: "Hàm mũ cơ số $e>1$ xác định trên $\\mathbb{R}$, đồng biến, luôn dương.",
    seconds: 120,
  },
  {
    id: "math.calculus.030",
    subject: "math",
    topic: "calculus",
    topicTitle: "Đạo hàm và tích phân",
    type: "SHORT_ANSWER",
    level: 3,
    stem: "Tính $\\displaystyle\\int_1^2 \\frac{1}{x}\\,dx$ (làm tròn đến hàng phần trăm).",
    sa: { answer: "0,69", decimals: 2, max_chars: 4 },
    hint: "Nguyên hàm của $\\frac{1}{x}$ là $\\ln|x|$.",
    explanation: "$\\ln 2 - \\ln 1 = \\ln 2 \\approx 0{,}69$.",
    seconds: 100,
  },
  // ---- math / geometry
  mcq("math.geometry.001", "math", "geometry", 1, "Cho tam giác $ABC$ vuông tại $A$ với $AB = 4$, $AC = 3$. Độ dài cạnh $BC$ bằng", ["$5$", "$7$", "$\\sqrt{7}$", "$12$"], "A", "Định lí Pythagore.", "$BC = \\sqrt{4^2 + 3^2} = 5$.", { assets: [triangle], optionFeedback: { B: "Bạn cộng hai cạnh góc vuông.", C: "Bạn lấy hiệu bình phương." } }),
  mcq("math.geometry.002", "math", "geometry", 2, "Trong không gian $Oxyz$, khoảng cách từ $O$ đến điểm $M(1; 2; 2)$ bằng", ["$3$", "$5$", "$\\sqrt{5}$", "$9$"], "A", "$OM = \\sqrt{x^2+y^2+z^2}$.", "$OM = \\sqrt{1+4+4} = 3$.", {}),
  {
    id: "math.geometry.030",
    subject: "math",
    topic: "geometry",
    topicTitle: "Hình học",
    type: "SHORT_ANSWER",
    level: 2,
    stem: "Cho $\\vec{u} = (1; -2; 2)$. Tính độ dài $|\\vec{u}|$.",
    sa: { answer: "3", decimals: 0, max_chars: 4 },
    hint: "Độ dài vectơ là căn của tổng bình phương các tọa độ.",
    explanation: "$|\\vec{u}| = \\sqrt{1 + 4 + 4} = 3$.",
    seconds: 80,
  },
  {
    id: "math.geometry.031",
    subject: "math",
    topic: "geometry",
    topicTitle: "Hình học",
    type: "SHORT_ANSWER",
    level: 3,
    stem: "Diện tích tam giác vuông có hai cạnh góc vuông $3$ và $5$ bằng bao nhiêu (làm tròn đến hàng phần mười)?",
    sa: { answer: "7,5", decimals: 1, max_chars: 4 },
    hint: "Diện tích bằng nửa tích hai cạnh góc vuông.",
    explanation: "$S = \\frac{1}{2}\\cdot 3\\cdot 5 = 7{,}5$.",
    seconds: 80,
  },
  // ---- math / stats
  mcq("math.stats.001", "math", "stats", 1, "Gieo một con xúc xắc cân đối. Xác suất xuất hiện mặt chẵn là", ["$\\frac{1}{2}$", "$\\frac{1}{3}$", "$\\frac{1}{6}$", "$\\frac{2}{3}$"], "A", "Có 3 mặt chẵn trong 6 mặt.", "$P = \\frac{3}{6} = \\frac{1}{2}$.", {}),
  mcq("math.stats.002", "math", "stats", 2, "Số cách chọn 2 bạn từ 5 bạn là", ["$10$", "$20$", "$5$", "$25$"], "A", "Chọn không phân biệt thứ tự.", "$C_5^2 = 10$.", { optionFeedback: { B: "Đó là chỉnh hợp $A_5^2$." } }),
  {
    id: "math.stats.030",
    subject: "math",
    topic: "stats",
    topicTitle: "Xác suất, thống kê",
    type: "SHORT_ANSWER",
    level: 2,
    stem: "Trung bình cộng của dãy số $2; 4; 6; 8$ bằng bao nhiêu?",
    sa: { answer: "5", decimals: 0, max_chars: 4 },
    hint: "Tổng chia số phần tử.",
    explanation: "$(2+4+6+8)/4 = 5$.",
    seconds: 60,
  },
  // ---- physics
  mcq("physics.mechanics.001", "physics", "mechanics", 2, "Vật đặt trên mặt phẳng nghiêng $30^\\circ$ chịu trọng lực $\\vec{P}$ và phản lực $\\vec{N}$ như hình. Thành phần của trọng lực dọc theo mặt phẳng nghiêng có độ lớn", ["$P\\sin 30^\\circ$", "$P\\cos 30^\\circ$", "$P\\tan 30^\\circ$", "$P$"], "A", "Phân tích $\\vec{P}$ theo phương dọc và vuông góc mặt phẳng.", "Thành phần dọc mặt phẳng nghiêng là $P\\sin\\alpha$.", { assets: [incline], optionFeedback: { B: "$P\\cos\\alpha$ là thành phần vuông góc, cân bằng với $N$." } }),
  mcq("physics.mechanics.002", "physics", "mechanics", 1, "Đơn vị của lực trong hệ SI là", ["newton (N)", "jun (J)", "oát (W)", "pascal (Pa)"], "A", "Nhớ định luật II Newton.", "Lực đo bằng newton, $1\\ \\text{N} = 1\\ \\text{kg·m/s}^2$.", {}),
  mcq("physics.mechanics.003", "physics", "mechanics", 2, "Vật khối lượng $2\\ \\text{kg}$ chịu lực $6\\ \\text{N}$. Gia tốc của vật là", ["$3\\ \\text{m/s}^2$", "$12\\ \\text{m/s}^2$", "$0{,}33\\ \\text{m/s}^2$", "$4\\ \\text{m/s}^2$"], "A", "$a = F/m$.", "$a = 6/2 = 3\\ \\text{m/s}^2$.", {}),
  {
    id: "physics.thermal.030",
    subject: "physics",
    topic: "thermal",
    topicTitle: "Nhiệt học",
    type: "SHORT_ANSWER",
    level: 2,
    stem: "Đổi $27^\\circ\\text{C}$ sang nhiệt độ Kelvin (làm tròn đến hàng đơn vị).",
    sa: { answer: "300", decimals: 0, max_chars: 4, unit: "K" },
    hint: "Cộng thêm $273$.",
    explanation: "$T = 27 + 273 = 300\\ \\text{K}$.",
    seconds: 60,
  },
  mcq("physics.thermal.001", "physics", "thermal", 1, "Nhiệt độ sôi của nước ở áp suất khí quyển chuẩn là", ["$100^\\circ\\text{C}$", "$0^\\circ\\text{C}$", "$37^\\circ\\text{C}$", "$212^\\circ\\text{C}$"], "A", "Thang Celsius.", "Nước sôi ở $100^\\circ\\text{C}$.", {}),
  // ---- english
  mcq("english.grammar.001", "english", "grammar", 1, "She ____ to school every day.", ["goes", "go", "going", "gone"], "A", "Chủ ngữ ngôi thứ ba số ít.", "Hiện tại đơn, ngôi thứ ba số ít thêm -es: goes.", {}),
  mcq("english.grammar.002", "english", "grammar", 2, "If I ____ more time, I would learn Japanese.", ["had", "have", "will have", "having"], "A", "Câu điều kiện loại 2.", "Điều kiện loại 2: If + quá khứ đơn, would + V.", {}),
  mcq("english.grammar.003", "english", "grammar", 2, "They have lived here ____ 2015.", ["since", "for", "during", "in"], "A", "Mốc thời gian dùng giới từ nào?", "Dùng since với mốc thời gian (2015).", {}),
  mcq("english.vocabulary.001", "english", "vocabulary", 1, "Choose the word closest in meaning to “huge”.", ["enormous", "tiny", "narrow", "quiet"], "A", "Nghĩa là rất lớn.", "huge ≈ enormous.", {}),
  mcq("english.vocabulary.002", "english", "vocabulary", 2, "He made a ____ to study harder this year.", ["resolution", "revolution", "reaction", "relation"], "A", "Quyết tâm.", "make a resolution: đặt ra quyết tâm.", {}),
  mcq("english.vocabulary.003", "english", "vocabulary", 3, "The scientist’s findings were ____ by further experiments.", ["confirmed", "confused", "conformed", "confined"], "A", "Được xác nhận.", "confirm: xác nhận.", {}),
];

export function bankFor(subject: string): BankItem[] {
  return BANK.filter((b) => b.subject === subject);
}
