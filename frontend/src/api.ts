import type {
  BimModel, BomRow, BomScope, CsvPlanRow, CsvValidationResult,
  ImportBatch,
  ManualTrussInput, ManualWallFrameInput, ModelParams, PreviewResult,
  PricingRow, AssemblyDefinition,
  RuleCheck, ModelReview,
} from "./types";
import { RequestState, StaleResponseError } from "./requestState";
export { StaleResponseError } from "./requestState";

let projectId = new URLSearchParams(location.search).get("project_id") ?? "default";
let revision: number | null = null;
const requestState = new RequestState(projectId);
export const subscribeApiState = (listener: (operation: string | null) => void) => requestState.subscribe(listener);
export const isApiBusy = () => requestState.busy();
const proofs = new Map<string, { token: string; key: string }>();
let previewGeneration = 0;
let activePreview: AbortController | null = null;
export function invalidatePreviewProofs(): void {
  proofs.clear(); previewGeneration++;
  activePreview?.abort(); activePreview = null;
}
export function setProjectContext(id: string, nextRevision: number | null = null): void {
  if (id !== projectId || nextRevision !== revision) proofs.clear();
  projectId = id;
  revision = nextRevision;
  requestState.setProject(id, nextRevision);
}
export function currentProjectId(): string { return projectId; }
export function currentProjectRevision(): number | null { return revision; }
function scoped(url: string, id = projectId): string {
  const parsed = new URL(url, location.origin);
  parsed.searchParams.set("project_id", id);
  return parsed.pathname + parsed.search;
}

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

export class ApiError extends Error {
  constructor(message: string, readonly detail: unknown, readonly status = 0, readonly requestId: string | null = null) {
    super(requestId?`${message} (reference ${requestId})`:message);
    this.name = "ApiError";
  }
}

async function json<T>(url: string, init?: RequestInit, previewFamily?: string): Promise<T> {
  const scope = requestState.capture();
  const mutation = Boolean(init?.method && init.method !== "GET");
  const path = url.split("?")[0];
  const previewStarted = previewGeneration;
  const assertPreview = () => {
    if (path.endsWith("/preview") && previewStarted !== previewGeneration)
      throw new StaleResponseError();
  };
  const release = mutation || (path === "/api/model" && scope.revision === null) ? requestState.begin(path.endsWith("/preview") ? "Preparing preview"
    : path.endsWith("/commit") ? "Committing model" : mutation ? "Updating workspace" : "Opening home") : () => {};
  const controller = path.endsWith("/preview") ? new AbortController() : null;
  if (controller) activePreview = controller;
  try {
    const headers = new Headers(init?.headers);
    if (mutation && scope.revision !== null)
      headers.set("If-Match", String(scope.revision));
    const family = previewFamily ?? url.replace(/\/(preview|commit)$/, "");
    const proof = proofs.get(family);
    if ((url.endsWith("/commit") || previewFamily) && proof) {
      headers.set("X-Preview-Token", proof.token);
      headers.set("Idempotency-Key", proof.key);
    }
    const response = await fetch(scoped(url, scope.projectId), { ...init, headers,
      ...(controller ? { signal: controller.signal } : {}) });
    assertPreview();
    if (!response.ok) {
      requestState.assertCurrent(scope);
      let detail = `${response.status} ${response.statusText}`;
      let payload: unknown;
      try {
        const body = await response.json();
        payload = body.detail ?? body;
        if (typeof body.detail === "string") detail = body.detail;
        // pydantic validation errors: detail is a list of {loc, msg}
        else if (Array.isArray(body.detail) && body.detail.length)
          detail = body.detail
            .map((d: { msg?: string }) => d.msg ?? "").filter(Boolean)
            .join("; ") || detail;
        else if (Array.isArray(body.detail?.errors))
          detail = body.detail.errors.map((issue: { row: number; field?: string; message: string }) =>
            `Row ${issue.row}${issue.field ? ` (${issue.field})` : ""}: ${issue.message}`).join("; ");
        else detail = body.detail?.message ?? body.message ?? detail;
      } catch { /* keep HTTP message */ }
      requestState.assertCurrent(scope);
      const reference=response.headers.get("X-Request-ID");
      throw new ApiError(detail, payload, response.status, reference&&/^[0-9a-f]{32}$/.test(reference)?reference:null);
    }
    const result = await response.json();
    assertPreview();
    const model = result.model ?? (result.meta ? result : null);
    const newHome = model?.meta?.project?.project_id && model.meta.project.project_id !== scope.projectId;
    if (newHome && path !== "/api/projects" && !(path === "/api/import/csv-plan/commit"
      && typeof init?.body === "string" && JSON.parse(init.body).mode === "new_project_from_csv"))
      throw new Error("Response home does not match the requested home.");
    requestState.assertCurrent(scope, newHome ? undefined : model?.meta?.project?.revision ?? result.project_revision);
    if (url.endsWith("/preview") && result.preview_token)
      proofs.set(family, { token: result.preview_token, key: crypto.randomUUID() });
    if (model?.meta?.project)
      setProjectContext(model.meta.project.project_id, model.meta.project.revision);
    return result;
  } catch (error) {
    if (controller?.signal.aborted) throw new StaleResponseError();
    throw error;
  } finally {
    if (activePreview === controller) activePreview = null;
    release();
  }
}

function post<T>(url: string, body: unknown): Promise<T> {
  return json<T>(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchModel(): Promise<BimModel> {
  return json("/api/model");
}
export const initializeProject = () => post<BimModel>("/api/project/initialize", {});
export const updateModel = (params: ModelParams) => post<BimModel>(
  `/api/model?${paramsToQuery(params)}`, {});
export const getProjects = () => json<{ projects: { project_id: string; name: string; revision?: number; unavailable?: boolean }[] }>("/api/projects");
const creationAttempts = new Map<string, string>();
export async function createProject(name: string, geometryMode: "sample" | "custom"): Promise<BimModel> {
  const attempt = JSON.stringify([projectId, name, geometryMode]);
  const key = creationAttempts.get(attempt) ?? crypto.randomUUID();
  creationAttempts.set(attempt, key);
  const model = await json<BimModel>("/api/projects", {
    method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify({ name, geometry_mode: geometryMode }),
  });
  creationAttempts.delete(attempt);
  return model;
}
export const getRevisions = () => json<{ revisions: { revision: number; action: string; saved_at: string }[] }>("/api/project/revisions");
export const getDefinitions = () => json<{ definitions: AssemblyDefinition[] }>("/api/project/definitions");
export const getHomeDefinition = () => json<{ definition: Record<string, unknown> | null }>("/api/project/home");
export const getHomeExamples = () => json<{ examples: { id: string; definition: Record<string, unknown> }[] }>("/api/project/home/examples");
export const exportHomeArchive = () => json<Record<string, unknown>>("/api/project/archive");
export const previewHomeDefinition = (definition: unknown) => post<PreviewResult>("/api/project/home/preview", definition);
export const saveHomeDefinition = (definition: unknown, preserve: boolean) => json<BimModel>(`/api/project/home/commit?preserve_additions=${preserve}`, {
  method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(definition),
}, "/api/project/home");
export const previewHomeArchive = (archive: unknown) => post<PreviewResult>("/api/project/archive/preview", archive);
export const importHomeArchive = (archive: unknown) => post<BimModel>("/api/project/archive/commit", archive);
export const restoreRevision = (value: number) => post<BimModel>(`/api/project/revisions/${value}/restore`, {});

export function downloadBom(): void {
  window.location.href = scoped(`/api/bom.csv${revision !== null ? `?revision=${revision}` : ""}`);
}

export function getBomJson(memberId?:number):Promise<{rows:BomRow[];scope:BomScope|null;disclaimer:string}> {
  const query=new URLSearchParams();
  if(memberId!==undefined)query.set("member_id",String(memberId));
  if(revision!==null)query.set("revision",String(revision));
  return json(`/api/bom.json?${query}`);
}
export const getPricing = () => json<{ rows: PricingRow[]; overrides: Record<string, number>; disclaimer: string }>(
  "/api/pricing");
export const savePriceOverrides = (overrides: Record<string, number>) => post<BimModel>("/api/pricing/overrides", { overrides });
export const getWarnings = () => json<{
  warnings: RuleCheck[];
  review: ModelReview;
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

export const reviewCsvPlan = (rows: CsvPlanRow[]) => post<CsvValidationResult>(
  "/api/import/csv-plan/review", { rows, units: "mm" });

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

export const updateManualWallFrame = (id: string, input: ManualWallFrameInput) =>
  json<{ source_id: string; model: BimModel }>(`/api/manual/wall-frame/${encodeURIComponent(id)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }, "/api/manual/wall-frame");
export const updateManualTruss = (id: string, input: ManualTrussInput) =>
  json<{ source_id: string; model: BimModel }>(`/api/manual/truss/${encodeURIComponent(id)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }, "/api/manual/truss");
export const updateCsvPlan = (id: string, rows: CsvPlanRow[], fileName: string) =>
  json<{ batch_id: string; model: BimModel }>(`/api/import/csv-plan/${encodeURIComponent(id)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, units: "mm", file_name: fileName }),
  }, "/api/import/csv-plan");

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
