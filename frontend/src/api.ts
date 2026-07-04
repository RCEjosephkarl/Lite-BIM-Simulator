import type {
  BimModel, BomRow, CsvPlanRow, CsvValidationResult,
  ImportBatch,
  ManualTrussInput, ManualWallFrameInput, ModelParams, PreviewResult,
  PricingRow,
} from "./types";

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
  if (p.wall_treatment) q.set("wall_treatment", p.wall_treatment);
  const dicts = [
    "stud_material_levels", "stud_spacing_levels", "wall_plies_levels",
    "stud_material_segments", "stud_spacing_segments", "wall_plies_segments",
  ] as const;
  for (const key of dicts)
    if (Object.keys(p[key]).length) q.set(key, JSON.stringify(p[key]));
  return q;
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      // pydantic validation errors: detail is a list of {loc, msg}
      else if (Array.isArray(body.detail) && body.detail.length)
        detail = body.detail
          .map((d: { msg?: string }) => d.msg ?? "").filter(Boolean)
          .join("; ") || detail;
      else detail = body.detail?.message ?? body.message ?? detail;
    } catch { /* keep HTTP message */ }
    throw new Error(detail);
  }
  return response.json();
}

function post<T>(url: string, body: unknown): Promise<T> {
  return json<T>(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchModel(params: ModelParams): Promise<BimModel> {
  return json(`/api/model?${paramsToQuery(params)}`);
}

export function downloadBom(): void {
  window.location.href = "/api/bom.csv";
}

export const getBomJson = () => json<{ rows: BomRow[]; disclaimer: string }>(
  "/api/bom.json");
export const getPricing = () => json<{ rows: PricingRow[]; disclaimer: string }>(
  "/api/pricing");
export const getWarnings = () => json<{
  warnings: { message: string; source?: string; source_id?: string }[];
  count: number;
}>("/api/warnings");

export async function uploadCsvPlanValidate(
  file: File, units: "mm" | "metres" | "feet_inches",
): Promise<CsvValidationResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("units", units);
  return json("/api/import/csv-plan/validate", { method: "POST", body: form });
}

export const uploadCsvPlanPreview = (
  rows: CsvPlanRow[], fileName = "",
) => post<PreviewResult & { validation: CsvValidationResult }>(
  "/api/import/csv-plan/preview", { rows, units: "mm", file_name: fileName });

export const commitCsvPlan = (
  rows: CsvPlanRow[], mode: string, fileName = "",
) => post<{ batch_id: string; model: BimModel }>(
  "/api/import/csv-plan/commit",
  { rows, units: "mm", file_name: fileName, mode });

export const previewManualWallFrame = (input: ManualWallFrameInput) =>
  post<PreviewResult>("/api/manual/wall-frame/preview", input);
export const commitManualWallFrame = (input: ManualWallFrameInput) =>
  post<{ source_id: string; model: BimModel }>(
    "/api/manual/wall-frame/commit", input);
export const previewManualTruss = (input: ManualTrussInput) =>
  post<PreviewResult>("/api/manual/truss/preview", input);
export const commitManualTruss = (input: ManualTrussInput) =>
  post<{ source_id: string; model: BimModel }>(
    "/api/manual/truss/commit", input);

export const resetProject = () => post<BimModel>("/api/project/reset", {});
export const getImportBatches = () => json<{ batches: ImportBatch[] }>(
  "/api/import/batches");
export const deleteImportBatch = (batchId: string) =>
  json<{ model: BimModel }>(`/api/import/batches/${encodeURIComponent(batchId)}`, {
    method: "DELETE",
  });
export const regenerateProject = (
  preserveManual = true, preserveImports = true,
) => post<BimModel>("/api/project/regenerate", {
  preserve_manual: preserveManual,
  preserve_imports: preserveImports,
  replace_geometry: false,
});
