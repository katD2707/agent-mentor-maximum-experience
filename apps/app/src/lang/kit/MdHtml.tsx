import "katex/dist/katex.min.css";
import { renderMd } from "../../lib/md";

/** Markdown + KaTeX as inline HTML. Loaded on demand (`lazy`) so the village does not carry the Markdown and maths libraries. */
export default function MdHtml({ md }: { md: string }) {
  return <span dangerouslySetInnerHTML={{ __html: renderMd(md) }} />;
}
