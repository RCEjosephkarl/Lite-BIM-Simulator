import type { BimModel, ModelParams } from "./types";

/**
 * Build the /api/model query string. Defaults and empty overrides are
 * omitted so plain/legacy URLs stay clean and shareable.
 */
export function paramsToQuery(p: ModelParams): URLSearchParams {
  const q = new URLSearchParams();
  if (p.storeys !== 1) q.set("storeys", String(p.storeys));
  if (p.roof !== "gable") q.set("roof", p.roof);
  if (p.wind_zone !== "medium") q.set("wind_zone", p.wind_zone);
  if (p.wind_speed !== null) q.set("wind_speed", String(p.wind_speed));
  if (p.snow_zone !== "N0") q.set("snow_zone", p.snow_zone);
  if (p.gable_spacing !== 600) q.set("gable_spacing", String(p.gable_spacing));
  if (p.stud_material_overall)
    q.set("stud_material_overall", p.stud_material_overall);
  if (p.stud_spacing_overall !== null)
    q.set("stud_spacing_overall", String(p.stud_spacing_overall));
  if (p.wall_plies_overall !== null && p.wall_plies_overall !== 1)
    q.set("wall_plies_overall", String(p.wall_plies_overall));
  const dicts = [
    "stud_material_levels",
    "stud_spacing_levels",
    "wall_plies_levels",
    "stud_material_segments",
    "stud_spacing_segments",
    "wall_plies_segments",
  ] as const;
  for (const k of dicts) {
    if (Object.keys(p[k]).length) q.set(k, JSON.stringify(p[k]));
  }
  return q;
}

export async function fetchModel(params: ModelParams): Promise<BimModel> {
  const res = await fetch(`/api/model?${paramsToQuery(params)}`);
  if (!res.ok) throw new Error(`model fetch failed: ${res.status}`);
  return res.json();
}

/** Trigger a CSV download of the timber bill of materials. */
export function downloadBom(): void {
  window.location.href = "/api/bom.csv";
}
