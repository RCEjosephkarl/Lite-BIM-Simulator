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
  source: "generated" | "csv_import" | "csv_preview" | "vision_import" |
    "vision_preview" | "manual_wall" | "manual_truss";
  source_id: string;
  editable: boolean;
  confidence: number | null;
  warnings: string[];
  truss_id: string;
  truss_label: string;
  pitch_deg: number | null;
  span_mm: number | null;
  spacing_mm: number | null;
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

export type SidebarSection =
  "specs" | "bom" | "pricing" | "imports" |
  "wall" | "truss" | "settings";

export interface DashboardSummary {
  storeys: number;
  roof_type: string;
  wind_zone: string;
  wind_speed: number | null;
  snow_zone: string;
  total_elements: number;
  wall_frame_lineal_m: number;
  roof_truss_lineal_m: number;
  estimated_material_cost_usd: number;
  warning_count: number;
}

export interface BomRow {
  category: string;
  element: string;
  storey: number;
  segment: string;
  size: string;
  grade: string;
  treatment: string;
  material: string;
  plies: number;
  stock_length_m: number;
  qty: number;
  total_length_m: number;
  total_effective_length_m: number;
  effective_length_m: number;
  unit_price_usd_per_lm: number | null;
  total_cost_usd: number;
  estimated_cost_usd: number;
  price_confidence: string;
  price_source_name: string;
  price_source_url: string;
  nzs_ref: string;
  notes: string;
  pricing_notes: string;
}

export interface PricingRow {
  material: string;
  key: string;
  category: string;
  default_size: string;
  usd_per_linear_metre: number;
  confidence: string;
  source_name: string;
  source_date: string;
  source_url: string;
  notes: string;
}

export interface CsvPlanRow {
  type: "wall" | "opening" | "truss";
  valid?: boolean;
  errors?: string[];
  warnings?: string[];
  _row?: number;
  [key: string]: unknown;
}

export interface CsvValidationResult {
  rows: CsvPlanRow[];
  normalized_entities: CsvPlanRow[];
  errors: { row: number; message: string }[];
  warnings: { row: number; message: string }[];
  summary: {
    wall_count: number;
    opening_count: number;
    truss_count: number;
    estimated_total_wall_length_m: number;
    error_count: number;
    warning_count: number;
  };
  can_preview: boolean;
  file_name?: string;
}

export interface ImportBatch {
  batch_id: string;
  source_type: string;
  file_name: string;
  uploaded_at: string;
  row_count: number;
  accepted_count: number;
  rejected_count: number;
  warning_count: number;
}

export interface ManualOpening {
  opening_id: string;
  opening_type: "door" | "window" | "garage" | "custom";
  start_offset_mm: number;
  width_mm: number;
  height_mm: number;
  sill_height_mm: number;
  head_height_mm: number | null;
  lintel_size: string;
  notes: string;
}

export interface ManualWallFrameInput {
  input_id: string;
  level: number;
  segment_id: string;
  segment_label: string;
  start_x_mm: number;
  start_z_mm: number;
  end_x_mm: number;
  end_z_mm: number;
  wall_height_mm: number;
  wall_thickness_mm: number;
  stud_size: string;
  stud_material: string;
  stud_spacing_mm: number;
  plies: number;
  bottom_plate_size: string;
  top_plate_size: string;
  nog_count: number;
  nog_spacing_mm: number | null;
  treatment: string;
  exterior: boolean;
  load_bearing: boolean;
  openings: ManualOpening[];
}

export interface TrussNode {
  id: string;
  x: number;
  y: number;
}

export interface TrussMember {
  start_node: string;
  end_node: string;
  element_type: string;
  size: string;
  material: string;
}

export interface ManualTrussInput {
  input_id: string;
  level: number;
  truss_id: string;
  truss_label: string;
  span_mm: number;
  pitch_deg: number;
  spacing_mm: number;
  quantity: number;
  start_x_mm: number;
  start_z_mm: number;
  direction_deg: number;
  top_chord_size: string;
  top_chord_material: string;
  bottom_chord_size: string;
  bottom_chord_material: string;
  web_size: string;
  web_material: string;
  overhang_mm: number;
  heel_height_mm: number;
  treatment: string;
  truss_type: "common" | "girder" | "mono" | "scissor" | "attic" | "custom";
  nodes: TrussNode[];
  members: TrussMember[];
}

export interface PreviewResult {
  elements: BimElement[];
  types: ElementType[];
  metadata: {
    temporary: boolean;
    member_count: number;
    lineal_metres: number;
    estimated_cost_usd: number;
    warnings: string[];
  };
}

export interface VisionProposal extends CsvPlanRow {
  proposal_id?: string;
  confidence?: number;
  source_drawing?: string;
  accepted?: boolean;
}

export interface VisionPlanAnalysisResult {
  status: string;
  proposals: VisionProposal[];
  warnings: string[];
  review_required?: boolean;
}
