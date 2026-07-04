import { downloadBom, fetchModel, paramsToQuery } from "./api";
import { BomPanel } from "./bomPanel";
import { ImportsPanel } from "./imports";
import { ManualInputs } from "./manualInputs";
import { PricingPanel } from "./pricingPanel";
import { Viewer } from "./scene";
import { Sidebar } from "./sidebar";
import { DEFAULT_PARAMS } from "./types";
import type {
  BimModel, ColorMode, ModelParams, PreviewResult,
} from "./types";
import { Panel } from "./ui";

const viewport = document.getElementById("viewport")!;
const sidebarRoot = document.getElementById("sidebar")!;
const viewer = new Viewer(viewport);
const sidebar = new Sidebar(sidebarRoot);
let mode: ColorMode = "function";
let sourceFilter = "";
let params: ModelParams = { ...DEFAULT_PARAMS, ...paramsFromUrl() };
let currentModel: BimModel | null = null;
let previewModel: BimModel | null = null;

const bomPanel = new BomPanel(sidebar.getSection("bom"));
const pricingPanel = new PricingPanel(sidebar.getSection("pricing"));
const importsPanel = new ImportsPanel(sidebar.getSection("imports"));
const manualInputs = new ManualInputs(
  sidebar.getSection("wall"), sidebar.getSection("truss"));

const panel = new Panel(sidebar.getSection("specs"), {
  onParams(patch) {
    params = { ...params, ...patch };
    void load();
  },
  onColorMode(value) {
    mode = value;
    viewer.setColorMode(value);
  },
  onCategory(category, visible) {
    viewer.setCategoryVisible(category, visible);
  },
  onSource(source) {
    sourceFilter = source;
    render();
  },
  onAutoRotate(on) {
    viewer.setAutoRotate(on);
  },
  onExport() {
    downloadBom();
  },
});

panel.syncParams(params);
viewer.onPick = (element, type) => {
  panel.showElement(element, type);
  if (element) sidebar.open("specs");
};

importsPanel.onModel = setModel;
manualInputs.onModel = setModel;
importsPanel.onPreview = showPreview;
manualInputs.onPreview = showPreview;
sidebar.onModel = setModel;

function showPreview(result: PreviewResult): void {
  if (!currentModel) return;
  previewModel = {
    ...currentModel,
    elements: [...currentModel.elements, ...result.elements],
    types: result.types,
    meta: {
      ...currentModel.meta,
      warnings: [...currentModel.meta.warnings, ...result.metadata.warnings],
    },
  };
  sourceFilter = "";
  render();
}

function setModel(model: BimModel): void {
  currentModel = model;
  previewModel = null;
  panel.setModel(model);
  render();
  void refreshDataPanels();
}

function render(): void {
  const model = previewModel ?? currentModel;
  if (!model) return;
  const filtered = sourceFilter
    ? { ...model, elements: model.elements.filter(
      (element) => element.source === sourceFilter) }
    : model;
  viewer.buildModel(filtered, mode);
}

async function refreshDataPanels(): Promise<void> {
  await Promise.allSettled([
    bomPanel.refresh(), pricingPanel.refresh(),
    sidebar.refreshWarnings(), importsPanel.refreshBatches(),
  ]);
}

function jsonRecord<T extends string | number>(
  raw: string | null, kind: "string" | "number",
): Record<string, T> | undefined {
  if (!raw) return undefined;
  try {
    const data: unknown = JSON.parse(raw);
    if (!data || typeof data !== "object" || Array.isArray(data)) return undefined;
    const output: Record<string, T> = {};
    for (const [key, value] of Object.entries(data)) {
      if (kind === "string" && typeof value === "string") output[key] = value as T;
      if (kind === "number" && typeof value === "number" && Number.isFinite(value))
        output[key] = value as T;
    }
    return Object.keys(output).length ? output : undefined;
  } catch { return undefined; }
}

function paramsFromUrl(): Partial<ModelParams> {
  const query = new URLSearchParams(location.search);
  const output: Partial<ModelParams> = {};
  const storeys = Number(query.get("storeys"));
  if (storeys >= 1 && storeys <= 3) output.storeys = storeys;
  const roof = query.get("roof");
  if (roof === "gable" || roof === "hip") output.roof = roof;
  if (query.get("wind_zone")) output.wind_zone = query.get("wind_zone")!;
  const speed = Number(query.get("wind_speed"));
  if (query.get("wind_speed") && Number.isFinite(speed)) output.wind_speed = speed;
  if (query.get("snow_zone")) output.snow_zone = query.get("snow_zone")!;
  const gable = Number(query.get("gable_spacing"));
  if (gable >= 300 && gable <= 1200) output.gable_spacing = gable;
  if (query.get("stud_material_overall"))
    output.stud_material_overall = query.get("stud_material_overall")!;
  const spacing = Number(query.get("stud_spacing_overall"));
  if (query.get("stud_spacing_overall") && Number.isFinite(spacing))
    output.stud_spacing_overall = spacing;
  const plies = Number(query.get("wall_plies_overall"));
  if (query.get("wall_plies_overall") && Number.isFinite(plies))
    output.wall_plies_overall = plies;
  const maps = [
    ["stud_material_levels", "string"], ["stud_spacing_levels", "number"],
    ["wall_plies_levels", "number"], ["stud_material_segments", "string"],
    ["stud_spacing_segments", "number"], ["wall_plies_segments", "number"],
  ] as const;
  for (const [key, kind] of maps) {
    const value = jsonRecord(query.get(key), kind);
    if (value) Object.assign(output, { [key]: value });
  }
  return output;
}

function syncUrl(value: ModelParams): void {
  const query = paramsToQuery(value).toString();
  history.replaceState(null, "", query ? `?${query}` : location.pathname);
}

let loadSequence = 0;
async function load(): Promise<void> {
  const sequence = ++loadSequence;
  syncUrl(params);
  viewport.classList.add("loading");
  try {
    const model = await fetchModel(params);
    if (sequence !== loadSequence) return;
    setModel(model);
  } catch (error) {
    viewport.dataset.error = (error as Error).message;
  } finally {
    if (sequence === loadSequence) viewport.classList.remove("loading");
  }
}

void load();
