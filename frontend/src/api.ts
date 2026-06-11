import type { BimModel, ModelParams } from "./types";

export async function fetchModel(params: ModelParams): Promise<BimModel> {
  const q = new URLSearchParams({
    storeys: String(params.storeys),
    roof: params.roof,
    wind_zone: params.wind_zone,
    snow_zone: params.snow_zone,
    gable_spacing: String(params.gable_spacing),
  });
  if (params.wind_speed !== null) q.set("wind_speed", String(params.wind_speed));
  const res = await fetch(`/api/model?${q}`);
  if (!res.ok) throw new Error(`model fetch failed: ${res.status}`);
  return res.json();
}

/** Trigger a CSV download of the timber bill of materials. */
export function downloadBom(): void {
  window.location.href = "/api/bom.csv";
}
