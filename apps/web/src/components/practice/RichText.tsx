"use client";

import { useId, type ReactNode } from "react";
import { API_BASE } from "@/lib/api";
import { imageUrl, placedElsewhere, unplacedAssets } from "@/lib/practice/assets";
import type { ClientItem, PracticeAsset } from "@/lib/practice/types";
import { Markdown } from "../Markdown";
import { Diagram } from "./Diagram";

/** One bank figure: a theme-aware SVG diagram, a table (cells may hold LaTeX) or a raster image with alt text. */
export function AssetFigure({ asset, inline = false }: { asset: PracticeAsset; inline?: boolean }) {
  const uid = useId().replace(/:/g, "");
  let body: ReactNode = null;
  if (asset.type === "diagram" && asset.diagram) {
    body = <Diagram spec={asset.diagram} alt={asset.alt_text} idBase={uid} />;
  } else if (asset.type === "table" && asset.table) {
    body = (
      <div className="table-wrap" role="group" aria-label={asset.alt_text}>
        <table className="table">
          <thead>
            <tr>
              {asset.table.headers.map((h, i) => (
                <th key={i} scope="col">
                  <Markdown inline>{h}</Markdown>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {asset.table.rows.map((r, ri) => (
              <tr key={ri}>
                {r.map((c, ci) => (
                  <td key={ci}>
                    <Markdown inline>{c}</Markdown>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  } else if (asset.type === "image" && asset.image) {
    const src = imageUrl(API_BASE, asset.image.sha256);
    body = src ? (
      // eslint-disable-next-line @next/next/no-img-element -- bank figure from our own gateway, size known
      <img src={src} alt={asset.alt_text} width={asset.image.width} height={asset.image.height} loading="lazy" className="pf-img" />
    ) : (
      <span className="pf-alt">[Hình: {asset.alt_text}]</span>
    );
  } else {
    body = <span className="pf-alt">[Hình: {asset.alt_text}]</span>;
  }
  return (
    // A span, not <figure>: a token sits inside a markdown paragraph (<p>), which only allows phrasing content.
    <span className={inline ? "pf pf-inline" : "pf"}>
      {body}
      {asset.caption && <span className="pf-cap">{asset.caption}</span>}
    </span>
  );
}

/** Text with `$...$` LaTeX that places `![](asset:id)` tokens from `assets`. */
export function RichText({ text, assets = [], inline = false, className }: { text: string; assets?: PracticeAsset[]; inline?: boolean; className?: string }) {
  return (
    <Markdown
      inline={inline}
      className={className}
      renderAsset={(id) => {
        const a = assets.find((x) => x.id === id);
        return a ? <AssetFigure asset={a} inline={inline} /> : null;
      }}
    >
      {text}
    </Markdown>
  );
}

/** The stem, then the figures nothing placed (in order). */
export function StemView({ item, extraAssets = [] }: { item: Pick<ClientItem, "stem" | "assets" | "options" | "statements">; extraAssets?: PracticeAsset[] }) {
  const all = [...item.assets, ...extraAssets];
  const rest = unplacedAssets(item.stem, all, placedElsewhere(item));
  return (
    <div className="pstem">
      <RichText text={item.stem} assets={all} className="pstem-text" />
      {rest.map((a) => (
        <AssetFigure key={a.id} asset={a} />
      ))}
    </div>
  );
}
