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
}

/** Generation parameters sent to /api/model. */
export interface ModelParams {
  storeys: number;
  roof: "gable" | "hip";
  wind_zone: string; // 'low'|'medium'|'high'|'very high'|'extra high'
  wind_speed: number | null; // m/s — when set, overrides wind_zone
  snow_zone: string; // 'N0'..'N5'
  gable_spacing: number; // gable-end stud centres, mm
}

export const DEFAULT_PARAMS: ModelParams = {
  storeys: 1,
  roof: "gable",
  wind_zone: "medium",
  wind_speed: null,
  snow_zone: "N0",
  gable_spacing: 600,
};

export interface ModelMeta extends Omit<ModelParams, "wind_speed"> {
  wind_speed: number | null;
  stud_spacing_mm: number[]; // per storey (index 0 = ground)
  rafter_spacing_mm: number;
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
