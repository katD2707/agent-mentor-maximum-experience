export interface FunctionPlotSpec {
  kind: "function_plot";
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
  functions: { expr: string; label?: string | null }[];
  points?: { x: number; y: number; label?: string | null }[];
  show_grid?: boolean;
}
export interface ForceDiagramSpec {
  kind: "force_diagram";
  body?: "box" | "ball" | "point" | string;
  incline_deg?: number | null;
  forces: { label: string; angle_deg: number; magnitude: number }[];
}
export interface GeometrySpec {
  kind: "geometry";
  points: { id: string; x: number; y: number; label?: string | null }[];
  segments?: { from: string; to: string; dashed?: boolean; label?: string | null }[];
  circles?: { center: string; radius: number; dashed?: boolean }[];
  right_angles?: { vertex: string; from: string; to: string }[];
}
export type DiagramSpec = FunctionPlotSpec | ForceDiagramSpec | GeometrySpec;
