import type { ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/**
 * KaTeX options: never `trust` (no \href, \includegraphics, \url ...), no throwing: a formula KaTeX cannot parse is
 * shown as its source text (errorColor "inherit" keeps it readable, not alarming red).
 */
export const KATEX_OPTIONS = { throwOnError: false, errorColor: "inherit", strict: "ignore", trust: false, output: "htmlAndMathml" } as const;

const baseComponents: Components = {
  table: ({ children }) => (
    <div className="table-wrap">
      <table>{children}</table>
    </div>
  ),
  a: ({ href, children }) => {
    const external = !!href && /^https?:\/\//i.test(href);
    return (
      <a href={href} {...(external ? { target: "_blank", rel: "noopener noreferrer nofollow" } : {})}>
        {children}
      </a>
    );
  },
};

/** Remote images from workspace content are never loaded; they show as links instead. */
function imgFallback(src: unknown, alt: unknown): ReactNode {
  return typeof src === "string" && src ? (
    <a href={src} target="_blank" rel="noopener noreferrer nofollow">
      [Ảnh: {typeof alt === "string" && alt ? alt : src}]
    </a>
  ) : null;
}

/** `asset:<id>` is the only extra scheme (bank figures, placed by `![](asset:id)`); everything else follows the default. */
function urlTransform(url: string): string {
  return /^asset:[A-Za-z0-9_.-]{1,64}$/.test(url) ? url : defaultUrlTransform(url);
}

/**
 * Safe markdown: GFM tables/task lists, `$...$` / `$$...$$` LaTeX (KaTeX, bundled CSS, no CDN, no trust), raw HTML is
 * skipped (no rehype-raw), and react-markdown's default urlTransform strips javascript:/data: links.
 *
 * `inline`: one span, paragraphs unwrapped (answer options, statements). `renderAsset`: places `![](asset:id)`.
 */
export function Markdown({
  children,
  className,
  inline = false,
  renderAsset,
}: {
  children: string;
  className?: string;
  inline?: boolean;
  renderAsset?: (id: string) => ReactNode;
}) {
  const components: Components = {
    ...baseComponents,
    ...(inline ? { p: ({ children: c }) => <>{c}</> } : {}),
    img: ({ src, alt }) => {
      if (typeof src === "string" && src.startsWith("asset:") && renderAsset) return <>{renderAsset(src.slice(6))}</>;
      return <>{imgFallback(src, alt)}</>;
    },
  };
  const cls = ["md", inline ? "md-inline" : "", className ?? ""].filter(Boolean).join(" ");
  const body = (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[[rehypeKatex, KATEX_OPTIONS]]}
      skipHtml
      urlTransform={urlTransform}
      components={components}
    >
      {children}
    </ReactMarkdown>
  );
  return inline ? <span className={cls}>{body}</span> : <div className={cls}>{body}</div>;
}
