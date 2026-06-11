/** Shared model interfaces — mirror backend/schema.sql + server.py. */

export interface ElementType {
  code: string;
  name: string;
  category: string; // 'wall' | 'floor' | 'ceiling' | 'roof' | 'outdoor' | 'concrete'
  nzs_ref: string;
  color_hex: string;
}

export interface BimElement {
  id: number;
  type_code: string;
  storey: number;
  size: string;
  grade: string;
  treatment: string;
  length_mm: number;
  w_mm: number;
  h_mm: number;
  cx: number;
  cy: number;
  cz: number;
  yaw: number;
  pitch: number;
  note: string;
  material: string; // display name, e.g. 'SG8', 'HySPAN'
  plies: number; // wall-frame plies (1..6)
  segment_id: string; // e.g. 'G-EXT-001' ('' for non-wall members)
  segment_label: string;
  stud_spacing_mm: number | null; // effective wall stud centres
  unit_price_usd_per_lm: number | null; // estimating data
  price_confidence: string; // 'high' | 'medium' | 'low' | ''
  price_source_name: string;
  price_source_url: string;
}

/** Stud material options (internal key, display name). */
export const MATERIAL_OPTIONS: [string, string][] = [
  ["sg8", "SG8"],
  ["sg10", "SG10"],
  ["prolam", "Prolam"],
  ["glulam", "Glulam"],
  ["hychord", "HyCHORD"],
  ["hyspan", "HySPAN"],
  ["hy90", "Hy90"],
];

/** Generation parameters sent to /api/model. */
export interface ModelParams {
  storeys: number;
  roof: "gable" | "hip";
  wind_zone: string; // 'low'|'medium'|'high'|'very high'|'extra high'
  wind_speed: number | null; // m/s — when set, overrides wind_zone
  snow_zone: string; // 'N0'..'N5'
  gable_spacing: number; // gable-end stud centres, mm
  // wall stud design overrides; precedence segment > level > overall > default
  stud_material_overall: string | null; // material key, e.g. 'sg10'
  stud_spacing_overall: number | null; // mm, 300..1200
  wall_plies_overall: number | null; // 1..6
  stud_material_levels: Record<string, string>; // keyed by storey "1".."3"
  stud_spacing_levels: Record<string, number>;
  wall_plies_levels: Record<string, number>;
  stud_material_segments: Record<string, string>; // keyed by segment_id
  stud_spacing_segments: Record<string, number>;
  wall_plies_segments: Record<string, number>;
}

export const DEFAULT_PARAMS: ModelParams = {
  storeys: 1,
  roof: "gable",
  wind_zone: "medium",
  wind_speed: null,
  snow_zone: "N0",
  gable_spacing: 600,
  stud_material_overall: null,
  stud_spacing_overall: null,
  wall_plies_overall: null,
  stud_material_levels: {},
  stud_spacing_levels: {},
  wall_plies_levels: {},
  stud_material_segments: {},
  stud_spacing_segments: {},
  wall_plies_segments: {},
};

/** Per-wall-segment metadata (meta.frame_segments). */
export interface FrameSegment {
  segment_id: string;
  storey: number;
  label: string;
  length_mm: number;
  exterior: boolean;
  openings: number;
  material: string; // effective material display name
  spacing_mm: number; // effective stud spacing
  plies: number; // effective wall plies
}

export interface CostGroup {
  cost_usd: number;
  [key: string]: string | number | boolean | null;
}

export interface CostSummary {
  currency: string;
  grand_total_usd: number;
  by_material: CostGroup[];
  by_storey: CostGroup[];
  by_segment: CostGroup[];
  by_element: CostGroup[];
  disclaimer: string;
}

export interface ModelMeta {
  storeys: number;
  roof: "gable" | "hip";
  wind_zone: string;
  wind_speed: number | null;
  snow_zone: string;
  gable_spacing: number;
  stud_spacing_mm: number[]; // per storey (index 0 = ground)
  rafter_spacing_mm: number;
  frame_segments: FrameSegment[];
  cost_summary: CostSummary;
  units: string;
  standard: string;
  warnings: string[];
  disclaimer: string;
}

export interface BimModel {
  meta: ModelMeta;
  types: ElementType[];
  elements: BimElement[];
}

export type ColorMode = "function" | "material" | "realistic";
