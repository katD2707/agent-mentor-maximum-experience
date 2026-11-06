import { useMemo } from "react";
import { buildDiagram, type Prim, type Role } from "@/lib/practice/diagram";
import type { DiagramSpec } from "@/lib/practice/types";

const COLOR: Record<Role, string> = {
  ink: "var(--text)",
  grid: "var(--border)",
  primary: "var(--accent)",
  accent: "var(--danger)",
  secondary: "var(--info)",
  soft: "var(--surface-3)",
};

function PrimEl({ p, clip }: { p: Prim; clip?: string }) {
  const stroke = COLOR[p.role];
  switch (p.t) {
    case "line":
      return (
        <line x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} stroke={stroke} strokeWidth={p.w ?? 1.5} strokeLinecap="round" strokeDasharray={p.dash ? "5 4" : undefined} opacity={p.faint ? 0.55 : 1} />
      );
    case "path":
      return (
        <path
          d={p.d}
          stroke={stroke}
          strokeWidth={p.w ?? 1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={p.dash ? "5 4" : undefined}
          fill={p.fill && p.fill !== "none" ? COLOR[p.fill] : "none"}
          fillOpacity={p.fillOpacity}
          clipPath={p.clip && clip ? `url(#${clip})` : undefined}
        />
      );
    case "circle":
      return (
        <circle
          cx={p.cx}
          cy={p.cy}
          r={p.r}
          stroke={p.fill && !p.w ? "none" : stroke}
          strokeWidth={p.w ?? 1.5}
          strokeDasharray={p.dash ? "5 4" : undefined}
          fill={p.fill ? stroke : "none"}
          fillOpacity={p.fillOpacity}
        />
      );
    case "rect":
      return (
        <rect
          x={p.x}
          y={p.y}
          width={p.w}
          height={p.h}
          stroke={stroke}
          strokeWidth={2.2}
          fill={stroke}
          fillOpacity={p.fillOpacity}
          transform={p.rotate ? `rotate(${p.rotate.deg} ${p.rotate.cx} ${p.rotate.cy})` : undefined}
        />
      );
    case "text":
      return (
        <text
          x={p.x}
          y={p.y}
          fill={stroke}
          fontSize={p.size ?? 13}
          fontWeight={p.bold ? 700 : 400}
          fontStyle={p.italic ? "italic" : "normal"}
          textAnchor={p.anchor ?? "middle"}
          dominantBaseline="central"
          style={{ fontFamily: "var(--font)" }}
        >
          {p.s}
        </text>
      );
  }
}

/** A bank diagram as inline SVG: colours are theme variables, so it follows light/dark. `alt` names it for screen readers. */
export function Diagram({ spec, alt, idBase }: { spec: DiagramSpec; alt: string; idBase: string }) {
  const model = useMemo(() => buildDiagram(spec), [spec]);
  const clipId = `dg-clip-${idBase}`;
  return (
    <svg className="dg" viewBox={`0 0 ${model.width} ${model.height}`} role="img" aria-label={alt} preserveAspectRatio="xMidYMid meet">
      {model.clip && (
        <defs>
          <clipPath id={clipId}>
            <rect x={model.clip.x} y={model.clip.y} width={model.clip.w} height={model.clip.h} />
          </clipPath>
        </defs>
      )}
      {model.prims.map((p, i) => (
        <PrimEl key={i} p={p} clip={clipId} />
      ))}
    </svg>
  );
}
