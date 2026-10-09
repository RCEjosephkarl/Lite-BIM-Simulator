import "./styles.css";
import { ApiError, currentProjectId, downloadBom, fetchModel, initializeProject, paramsToQuery, updateModel, subscribeApiState, StaleResponseError, invalidatePreviewProofs, getDefinitions, getImportBatches, isApiBusy } from "./api";
import { BomPanel } from "./bomPanel";
import { ImportsPanel } from "./imports";
import { HomePanel } from "./homePanel";
import { ManualInputs } from "./manualInputs";
import { PricingPanel } from "./pricingPanel";
import { Viewer } from "./scene";
import { Sidebar } from "./sidebar";
import { DEFAULT_PARAMS, TREATMENT_OPTIONS } from "./types";
import type {
  BimModel, ModelParams, PreviewResult,
  AssemblyDefinition,
} from "./types";
import { Panel } from "./ui";
import { WorkspaceTools } from "./workspaceTools";
import { WorkspaceState, validCamera, viewFromQuery, viewToQuery } from "./workspaceState";
import { storage } from "./dom";
import { installDiagnostics } from "./diagnostics";

const viewport = document.getElementById("viewport")!;
const sidebarRoot = document.getElementById("sidebar")!;
const viewer = new Viewer(viewport);
const sidebar = new Sidebar(sidebarRoot);
const workspace = new WorkspaceState(storage);
if(new URLSearchParams(location.search).get("diagnostics")==="1")installDiagnostics(viewer,()=>workspace.activeModel,()=>render());
const initialViewQuery=new URLSearchParams(location.search);
let viewQueryConsumed=false;
let rendering = false;
let saveViewTimer: number | undefined;
let params: ModelParams = { ...DEFAULT_PARAMS, ...paramsFromUrl() };
const workspaceTools = new WorkspaceTools(viewport);
sidebar.onPanelOpen=()=>{if(matchMedia("(max-width: 600px)").matches)workspaceTools.closeOverlays();};
workspaceTools.onView = view => {
  workspace.patch({standardView:view});viewer.fit(view);workspace.patch({camera:viewer.cameraState()});saveView();syncWorkspaceControls();
};
workspaceTools.onSelect = id => revealMember(id);
workspaceTools.onFitSelection = () => {viewer.fit(workspace.view.standardView==="custom"?"iso":workspace.view.standardView,true);workspace.patch({camera:viewer.cameraState()});saveView();};
workspaceTools.onPatchView = patch => {workspace.patch(patch);render();saveView();};
workspaceTools.onIsolate = ids => {
  workspace.isolate(ids ? workspace.activeModel!.elements.filter(m=>ids.includes(m.id)) : null);
  render();viewer.fit(workspace.view.standardView==="custom"?"iso":workspace.view.standardView);workspace.patch({camera:viewer.cameraState()});saveView();
};
workspaceTools.onCancel = cancelPreview;
workspaceTools.onRecoverView = () => {workspace.discardRecovery();syncWorkspaceControls();};
workspaceTools.onDownloadViewRecovery = () => {
  if(workspace.recoveryRaw===null)return;
  const url=URL.createObjectURL(new Blob([workspace.recoveryRaw],{type:"application/json"}));
  const a=document.createElement("a");a.href=url;a.download="timberbim-view-recovery.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};

const bomPanel = new BomPanel(sidebar.getSection("bom"));
workspaceTools.onCameraAction=action=>viewer.cameraAction(action);
viewer.onFit=()=>workspaceTools.onView("iso");
workspaceTools.onBom=id=>{
  sidebar.open("bom");
  const status=sidebar.getSection("bom").querySelector<HTMLElement>("#bom-scope")!;
  status.tabIndex=-1;status.focus();
  void bomPanel.showAssembly(id);
};
bomPanel.onLocate=ids=>{
  cancelPreview();
  const wanted=new Set(ids);
  const members=workspace.model?.elements.filter(member=>wanted.has(member.id))??[];
  if(!members.length)return;
  workspace.patch({source:"",level:null,section:null,layers:{...workspace.view.layers,
    ...Object.fromEntries(members.map(m=>[workspace.model!.types.find(t=>t.code===m.type_code)!.category,true]))}});
  workspace.isolate(members);render();viewer.selectElement(members[0].id);
  viewer.fit(workspace.view.standardView==="custom"?"iso":workspace.view.standardView);
  workspace.patch({camera:viewer.cameraState()});saveView();
  sidebar.close();
  viewer.renderer.domElement.focus();
};
const pricingPanel = new PricingPanel(sidebar.getSection("pricing"));
const importsPanel = new ImportsPanel(sidebar.getSection("imports"));
const homePanel = new HomePanel(sidebar.getSection("imports"));
const manualInputs = new ManualInputs(
  sidebar.getSection("wall"), sidebar.getSection("truss"));

const panel = new Panel(sidebar.getSection("specs"), {
  onParams(patch) {
    params = { ...params, ...patch };
    void load(true);
  },
  onColorMode(value) {
    workspace.patch({mode:value});
    viewer.setColorMode(value);
    panel.syncView(workspace.view);saveView();
  },
  onCategory(category, visible) {
    workspace.patch({layers:{...workspace.view.layers,[category]:visible}});render();saveView();
  },
  onSource(source) {
    workspace.patch({source});render();saveView();
  },
  onAutoRotate(on) {
    viewer.setAutoRotate(on);
    workspace.patch({autoRotate:on});saveView();
  },
  onExport() {
    downloadBom();
  },
});

panel.syncParams(params);
viewer.onPick = (info) => {
  if (!rendering) { workspace.select(info?.element??null);saveView(); }
  if(info&&!rendering&&matchMedia("(max-width: 600px)").matches)sidebar.close();
  panel.showSelection(info);
  workspaceTools.showSelection(info, sidebarRoot.querySelector<HTMLElement>("#info")!);
};

importsPanel.onModel = setModel;
homePanel.onModel = setModel;
homePanel.onPreview = showPreview;
homePanel.onDraftChange = cancelPreview;
manualInputs.onModel = setModel;
importsPanel.onPreview = showPreview;
manualInputs.onPreview = showPreview;
sidebar.onModel = setModel;
sidebar.onContextChange = cancelPreview;
sidebar.onWarningSelect = id => { cancelPreview();revealMember(id); };
viewer.onOrbitStart = () => { workspace.patch({standardView:"custom"});syncWorkspaceControls(); };
viewer.onCameraChange = camera => {
  if(rendering || !workspace.model || !validCamera(camera))return;
  workspace.patch({camera});viewport.dataset.camera=JSON.stringify(camera);saveView();
};
function saveView(): void {
  if(saveViewTimer!==undefined)return;
  saveViewTimer=window.setTimeout(()=>{saveViewTimer=undefined;workspace.persist();if(!workspace.preview)syncUrl(params);syncWorkspaceControls();},300);
}
window.addEventListener("pagehide",()=>workspace.persist());
document.addEventListener("visibilitychange",()=>{if(document.hidden)workspace.persist();});
function revealMember(id:number): void {
  const member=workspace.activeModel?.elements.find(m=>m.id===id);
  if(member){
    const type=workspace.activeModel!.types.find(t=>t.code===member.type_code)!;
    workspace.patch({source:"",level:null,isolation:null,section:null,layers:{...workspace.view.layers,[type.category]:true}});
    render();
  }
  viewer.selectElement(id);
}
pricingPanel.onModel = setModel;
importsPanel.onDraftChange = cancelPreview;
manualInputs.onDraftChange = cancelPreview;
manualInputs.onEditTarget = (id, section) => editUrl(id, section);
importsPanel.onEditTarget = id => editUrl(id, "imports");
importsPanel.onEdit = (definition, fileName) => { void openAssembly(definition, fileName); };
function editUrl(id: string | null, section: "wall" | "truss" | "imports"): void {
  sidebar.open(section);
  const url = new URL(location.href);
  if (id) url.searchParams.set("edit_assembly", id);
  else url.searchParams.delete("edit_assembly");
  history.replaceState(null, "", url.pathname + url.search);
  editLoaded = id ? `${currentProjectId()}:${id}` : "";
}
async function openAssembly(definition: AssemblyDefinition, fileName = ""): Promise<void> {
  if (isApiBusy()) return;
  cancelPreview();
  if (definition.kind === "manual_wall") manualInputs.wall.editAssembly(definition.definition_id, definition.payload);
  else if (definition.kind === "manual_truss") manualInputs.truss.editAssembly(definition.definition_id, definition.payload);
  else await importsPanel.editBatch(definition.definition_id, definition.payload, fileName);
}
let editLoaded = "";
async function resumeAssembly(): Promise<void> {
  const id = new URLSearchParams(location.search).get("edit_assembly");
  const key = `${currentProjectId()}:${id}`;
  if (!id || key === editLoaded) return;
  editLoaded = key;
  try {
    const [result, batches] = await Promise.all([getDefinitions(), getImportBatches()]);
    const definition = result.definitions.find(item => item.definition_id === id);
    if (!definition) throw new Error("Saved assembly was not found in this home. Open Imports to select an available definition.");
    if (isApiBusy()) { editLoaded = ""; return; }
    await openAssembly(definition, batches.batches.find(batch => batch.batch_id === id)?.file_name ?? "");
  } catch (error) {
    if (error instanceof StaleResponseError) return;
    viewport.dataset.error = (error as Error).message;
  }
}
const requestStatus = document.createElement("div");
requestStatus.id = "workspace-request-status";
requestStatus.setAttribute("role", "status");
viewport.querySelector("#workspace-tools")!.append(requestStatus);
subscribeApiState(operation => {
  const busy = operation !== null;
  manualInputs.setWorkspaceBusy(busy);
  importsPanel.setWorkspaceBusy(busy);
  homePanel.setWorkspaceBusy(busy);
  pricingPanel.setWorkspaceBusy(busy);
  sidebar.setWorkspaceBusy(busy);
  panel.setWorkspaceBusy(busy);
  requestStatus.textContent = operation ? `${operation}…` : "";
  viewport.querySelector<HTMLButtonElement>("#preview-cancel")!.hidden = operation !== "Preparing preview" && !workspace.preview;
});

function showPreview(result: PreviewResult): void {
  workspace.beginPreview(result);
  render();
}

function setModel(model: BimModel): void {
  invalidatePreviewProofs();
  const previous=workspace.model;
  const wasPreview=Boolean(workspace.preview);
  const changed=workspace.setModel(model);
  if(!viewQueryConsumed){
    viewQueryConsumed=true;
    const patch=viewFromQuery(initialViewQuery);
    // A requested standard view takes precedence over the browser's previous camera.
    workspace.patch({...patch,...(patch.standardView&&patch.standardView!==workspace.view.standardView?{camera:null}:{})});workspace.reconcile();
  }
  if (changed) {
    manualInputs.wall.loadProject();
    manualInputs.truss.loadProject();
    importsPanel.loadProject();
    homePanel.loadProject();
    if (previous) {
      const url = new URL(location.href); url.searchParams.delete("edit_assembly");
      history.replaceState(null, "", url.pathname + url.search);
      editLoaded = "";
    }
  }
  delete viewport.dataset.error;
  importsPanel.invalidateForModel();
  homePanel.setModel(model);
  manualInputs.wall.invalidatePreview();
  manualInputs.truss.invalidatePreview();
  params = { ...DEFAULT_PARAMS, ...model.meta.params };
  panel.syncParams(params);
  syncUrl(params);
  panel.setModel(model);
  render(changed||wasPreview||!previous?.elements.length);
  void refreshDataPanels();
  void resumeAssembly();
}

function render(restoreCamera=false): void {
  const model = workspace.activeModel;
  if (!model) return;
  rendering=true;
  panel.setInspectionModel(model);
  panel.syncView(workspace.view);
  const filtered = { ...model, elements: workspace.visibleMembers() };
  viewer.setCategories(workspace.view.layers);
  viewer.setSection(workspace.view.section);
  viewer.buildModel(filtered, workspace.view.mode);
  viewer.setAutoRotate(workspace.view.autoRotate);
  if(restoreCamera && model.elements.length){
    if(workspace.view.camera)viewer.restoreCamera(workspace.view.camera);
    else viewer.fit(workspace.view.standardView==="custom"?"iso":workspace.view.standardView);
    workspace.patch({camera:viewer.cameraState()});
  }
  const selected=workspace.selectedMember();
  if(selected && filtered.elements.includes(selected)
    && workspace.view.layers[model.types.find(t=>t.code===selected.type_code)!.category]!==false){if(!viewer.selectElement(selected.id))workspace.select(null);}
  else {if(selected)workspace.select(null);viewer.selectElement(Number.NaN);}
  viewer.setDimensions(workspace.view.dimensions);
  viewport.dataset.camera=JSON.stringify(viewer.cameraState());
  rendering=false;syncWorkspaceControls();saveView();
}
function syncWorkspaceControls(): void {
  const model=workspace.activeModel;if(!model)return;
  bomPanel.syncContext();
  workspaceTools.setModel(model,workspace.preview?Math.max(1,model.elements.filter(m=>m.id<0).length):0);
  workspaceTools.syncView(workspace.view,workspace.recoveryRaw,workspace.storageUnavailable);
}

function cancelPreview(): void {
  const hadPreview=Boolean(workspace.preview);
  homePanel.invalidateForModel();
  invalidatePreviewProofs();
  workspace.cancelPreview();
  importsPanel.invalidateForModel();
  manualInputs.wall.invalidatePreview();
  manualInputs.truss.invalidatePreview();
  if(hadPreview)render(true);
}

async function refreshDataPanels(): Promise<void> {
  await Promise.allSettled([
    bomPanel.refresh(), pricingPanel.refresh(),
    sidebar.refreshWarnings(), importsPanel.refreshBatches(),
    ...(workspace.model ? [sidebar.refreshProjects(workspace.model)] : []),
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
  const treatment = query.get("wall_treatment");
  if (treatment && TREATMENT_OPTIONS.includes(treatment))
    output.wall_treatment = treatment;
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
  const scoped = paramsToQuery(value);
  scoped.set("project_id", currentProjectId());
  scoped.set("section", sidebarRoot.dataset.active ?? "specs");
  const editId = new URLSearchParams(location.search).get("edit_assembly");
  if (editId) scoped.set("edit_assembly", editId);
  if(workspace.model&&workspace.projectId===currentProjectId()&&!workspace.preview)viewToQuery(scoped,workspace.view);
  else {
    const previous=new URLSearchParams(location.search);
    for(const key of ["view","source","level","dimensions","section_axis","section_mm","section_keep"])
      if(previous.has(key))scoped.set(key,previous.get(key)!);
  }
  const query = scoped.toString();
  history.replaceState(null, "", query ? `?${query}` : location.pathname);
}

let loadSequence = 0;
async function load(update = false): Promise<void> {
  const sequence = ++loadSequence;
  syncUrl(params);
  viewport.classList.add("loading");
  try {
    let model: BimModel;
    try { model = await (update ? updateModel(params) : fetchModel()); }
    catch (error) {
      if (!update && currentProjectId() === "default" && error instanceof ApiError
        && /not initialized|migration|recovery/.test(error.message))
        model = await initializeProject();
      else throw error;
    }
    if (sequence !== loadSequence) return;
    setModel(model);
    delete viewport.dataset.error;
  } catch (error) {
    if (error instanceof StaleResponseError || sequence !== loadSequence) return;
    if (update && workspace.model?.meta.project.project_id === currentProjectId()) {
      params = { ...DEFAULT_PARAMS, ...workspace.model.meta.params };
      panel.syncParams(params);
      syncUrl(params);
    }
    viewport.dataset.error = (error as Error).message;
  } finally {
    if (sequence === loadSequence) viewport.classList.remove("loading");
  }
}

void load();
