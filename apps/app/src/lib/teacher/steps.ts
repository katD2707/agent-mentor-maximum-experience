import type { Block, CoursePack, Lesson, QuizItem } from "../../api";

/** What a teacher calls a step: the icon and label key come from this. */
export type StepKind = "explain" | "pick" | "fill" | "match" | "order" | "drag" | "recall";

export function stepKind(b: Block): StepKind {
  switch (b.kind) {
    case "interactive":
      return "drag";
    case "recall":
      return "recall";
    case "quiz": {
      const t = b.items[0]?.type;
      return t === "FILL_TILES" || t === "SHORT_ANSWER" ? "fill" : t === "MATCH_PAIRS" ? "match" : t === "ORDER_STEPS" ? "order" : "pick";
    }
    default:
      return "explain";
  }
}

export const STEP_ICON: Record<StepKind, "text" | "image" | "edit" | "layers" | "up" | "target" | "refresh"> = {
  explain: "text",
  pick: "image",
  fill: "edit",
  match: "layers",
  order: "up",
  drag: "target",
  recall: "refresh",
};

const TEX: Record<string, string> = { cdot: "·", times: "×", div: "÷", pm: "±", le: "≤", leq: "≤", ge: "≥", geq: "≥", neq: "≠", ne: "≠", approx: "≈", to: "→", rightarrow: "→", infty: "∞", pi: "π", alpha: "α", beta: "β", gamma: "γ", delta: "δ", theta: "θ", lambda: "λ", mu: "μ", sigma: "σ", omega: "ω", Delta: "Δ", Omega: "Ω", sum: "Σ", int: "∫", sqrt: "√", ldots: "…", dots: "…" };

/** Markdown + LaTeX to one plain line: no list dashes, no `**`, no `\cdot`; for titles in a list (the full text renders in the preview). */
export function plainLine(md: string): string {
  return md
    .replace(/\{\{gap\}\}/g, "…")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\$\$?([^$]+)\$\$?/g, (_m, tex: string) =>
      tex
        .replace(/\\(?:d|t)?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, "$1/$2")
        .replace(/\\(?:text|mathrm|mathbf|operatorname)\s*\{([^{}]*)\}/g, "$1")
        .replace(/\\([A-Za-z]+)/g, (_x, c: string) => TEX[c] ?? "")
        .replace(/\\[,;:! ]/g, " ")
        .replace(/[{}]/g, "")
        .replace(/\^2/g, "²")
        .replace(/\^3/g, "³"),
    )
    .replace(/\\+([A-Za-z]+)/g, (_x, c: string) => TEX[c] ?? "")
    .replace(/^[\s>]*(?:[-*+]|\d+[.)])\s+/gm, "")
    .replace(/^#+\s*/gm, "")
    .replace(/[*_`~>#]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

const cut = (s: string) => plainLine(s).slice(0, 60);

/** One short line for a step in a list. */
export function stepLabel(b: Block): string {
  switch (b.kind) {
    case "text":
    case "callout":
      return cut(b.md);
    case "quiz":
      return cut(b.items[0]?.stem ?? b.title ?? "");
    case "interactive":
      return cut(b.prompt);
    case "recall":
      return cut(b.items[0]?.prompt ?? "");
    case "image":
      return cut(b.alt);
    case "video":
      return cut(b.title ?? "");
    case "audio":
      return cut(b.transcript);
  }
}

export const lessonSteps = (l: Lesson) => l.blocks.length;

/** Practice questions of the whole pack, by difficulty 1..4. */
export function questionsByLevel(pack: CoursePack): { level: number; items: { block_id: string; item: QuizItem }[] }[] {
  const out = [1, 2, 3, 4].map((level) => ({ level, items: [] as { block_id: string; item: QuizItem }[] }));
  for (const l of pack.chapters.flatMap((c) => c.lessons))
    for (const b of l.blocks)
      if (b.kind === "quiz") for (const item of b.items) out[Math.min(4, Math.max(1, item.difficulty || 1)) - 1].items.push({ block_id: b.id, item });
  return out;
}

/** The right answer of an item as one short text, for a list row. */
export function rightText(item: QuizItem): string {
  const k = item.answer_key as Record<string, unknown>;
  if (typeof k.correct_option_id === "string") return item.options.find((o) => o.id === k.correct_option_id)?.text ?? "";
  if (Array.isArray(k.accepted)) return String(k.accepted[0] ?? "");
  if (Array.isArray(k.gaps)) return (k.gaps as string[]).map((g) => item.parts?.find((p) => p.id === g)?.text ?? "").join(", ");
  return "";
}
