import type { BimElement, BimModel, ColorMode, PreviewResult } from "./types";

export type StandardView = "iso" | "top" | "front" | "side" | "custom";
export interface CameraState {
  position: [number, number, number]; target: [number, number, number];
  near: number; far: number;
  projection?: "perspective" | "orthographic"; ortho_height?: number; zoom?: number; up?: [number,number,number];
}
export interface SectionState { axis: "x" | "y" | "z"; position_mm: number; keep: "lower" | "upper" }
export interface ViewPreferences {
  mode: ColorMode; source: string; level: number | null;
  layers: Record<string, boolean>; selection: string | null; isolation: string[] | null;
  camera: CameraState | null; standardView: StandardView; autoRotate: boolean;
  dimensions: boolean; section: SectionState | null;
}
interface ViewStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): boolean;
}
const clone = <T>(value: T): T => structuredClone(value);
export const defaultView = (): ViewPreferences => ({ mode: "function", source: "", level: null, layers: {},
  selection: null, isolation: null, camera: null, standardView: "iso", autoRotate: false, dimensions: false, section: null });

/** Small shareable view hints. Detailed cameras/selections remain home-local. */
export function viewFromQuery(query: URLSearchParams): Partial<ViewPreferences> {
  const patch:Partial<ViewPreferences>={};
  const view=query.get("view");if(view&&["iso","top","front","side"].includes(view))patch.standardView=view as StandardView;
  if(query.has("source"))patch.source=query.get("source")!;
  const level=query.get("level");if(level&&/^\d+$/.test(level)&&Number.isSafeInteger(Number(level))&&Number(level)>0)patch.level=Number(level);
  if(query.has("dimensions"))patch.dimensions=query.get("dimensions")==="1";
  const axis=query.get("section_axis"),coordinate=query.get("section_mm"),keep=query.get("section_keep");
  if(axis&&["x","y","z"].includes(axis)&&coordinate?.trim()&&Number.isFinite(Number(coordinate))&&["lower","upper"].includes(keep??""))
    patch.section={axis:axis as SectionState["axis"],position_mm:Number(coordinate),keep:keep as SectionState["keep"]};
  return patch;
}
export function viewToQuery(query: URLSearchParams,view:ViewPreferences): void {
  for(const key of ["view","source","level","dimensions","section_axis","section_mm","section_keep"])query.delete(key);
  if(view.standardView!=="iso"&&view.standardView!=="custom")query.set("view",view.standardView);
  if(view.source)query.set("source",view.source);
  if(view.level!==null)query.set("level",String(view.level));
  if(view.dimensions)query.set("dimensions","1");
  if(view.section){query.set("section_axis",view.section.axis);query.set("section_mm",String(view.section.position_mm));query.set("section_keep",view.section.keep);}
}

/** Graph segments share a cut ID; endpoint IDs identify the selected segment. */
export function memberKey(member: BimElement, revision: number): string {
  return JSON.stringify([member.source, member.source_id, member.storey,
    member.physical_member_id || `legacy-row:${revision}:${member.id}`,
    member.start_node || "", member.end_node || ""]);
}
const object = (v: unknown): v is Record<string, unknown> => Boolean(v && typeof v === "object" && !Array.isArray(v));
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const keys = (v: Record<string, unknown>, allowed: string[]) => Object.keys(v).every(k => allowed.includes(k));
export function validCamera(value: unknown): value is CameraState {
  if (!object(value) || !keys(value, ["position", "target", "near", "far","projection","ortho_height","zoom","up"])) return false;
  const vector = (v: unknown): v is number[] => Array.isArray(v) && v.length === 3 && v.every(finite);
  return vector(value.position) && vector(value.target) && finite(value.near) && finite(value.far)
    && (value.projection===undefined || ["perspective","orthographic"].includes(value.projection as string))
    && (value.projection!=="orthographic" || (finite(value.ortho_height)&&value.ortho_height>0))
    && (value.zoom===undefined || (finite(value.zoom)&&value.zoom>0))
    && (value.up===undefined || (vector(value.up)&&finite(Math.hypot(...value.up))&&Math.hypot(...value.up)>0))
    && value.near > 0 && value.far > value.near
    && finite(Math.hypot(...value.position.map((n,i)=>n-(value.target as number[])[i])))
    && Math.hypot(...value.position.map((n, i) => n - (value.target as number[])[i])) > .00001;
}
export function decodeView(raw: string, project: string): ViewPreferences {
  if (raw.length > 2 * 1024 * 1024) throw new Error("Saved view exceeds the recovery limit");
  const envelope: unknown = JSON.parse(raw);
  if (!object(envelope) || !keys(envelope, ["schema_version", "project_id", "view"])
    || envelope.schema_version !== 1 || envelope.project_id !== project || !object(envelope.view))
    throw new Error("Saved view belongs to an unsupported version or another home");
  const v = envelope.view;
  if (!keys(v, Object.keys(defaultView())) || Object.keys(v).length !== Object.keys(defaultView()).length
    || !["function", "material", "realistic"].includes(v.mode as string)
    || !["iso", "top", "front", "side", "custom"].includes(v.standardView as string)
    || typeof v.source !== "string" || !object(v.layers) || Object.values(v.layers).some(n => typeof n !== "boolean")
    || !(v.level === null || (Number.isInteger(v.level) && Number(v.level) > 0))
    || !(v.selection === null || typeof v.selection === "string")
    || !(v.isolation === null || (Array.isArray(v.isolation) && v.isolation.every(n => typeof n === "string")))
    || !(v.camera === null || validCamera(v.camera))
    || typeof v.autoRotate !== "boolean" || typeof v.dimensions !== "boolean")
    throw new Error("Saved view contains invalid preferences");
  if (v.section !== null && (!object(v.section) || !keys(v.section, ["axis", "position_mm", "keep"])
    || !["x", "y", "z"].includes(v.section.axis as string) || !finite(v.section.position_mm)
    || !["lower", "upper"].includes(v.section.keep as string)))
    throw new Error("Saved section contains invalid coordinates");
  return clone(v as unknown as ViewPreferences);
}

/** One displayed home, one saved view, and a reversible preview overlay. */
export class WorkspaceState {
  model: BimModel | null = null;
  preview: BimModel | null = null;
  view = defaultView();
  recoveryRaw: string | null = null;
  storageUnavailable = false;
  private baseline: ViewPreferences | null = null;
  private port: ViewStorage;
  constructor(port: ViewStorage) { this.port = port; }
  get activeModel(): BimModel | null { return this.preview ?? this.model; }
  get projectId(): string | null { return this.model?.meta.project.project_id ?? null; }
  private storageKey(): string { return `timberbim.view.v1.${this.projectId}`; }
  setModel(model: BimModel): boolean {
    const changed = this.projectId !== model.meta.project.project_id;
    this.cancelPreview();
    if (changed) {
      this.persist(); this.model = model; this.view = defaultView(); this.recoveryRaw = null;
      const raw = this.port.getItem(this.storageKey());
      if (raw !== null) {
        try { this.view = decodeView(raw, this.projectId!); }
        catch { this.recoveryRaw = raw; }
      }
    } else this.model = model;
    this.reconcile(); return changed;
  }
  patch(patch: Partial<ViewPreferences>): void {
    this.view = { ...this.view, ...clone(patch) };
    // Deliberate layer/colour/motion preferences also survive preview cancel.
    if (this.baseline) for (const key of ["layers", "mode", "autoRotate", "dimensions"] as const)
      if (key in patch) this.baseline = { ...this.baseline, [key]: clone(this.view[key]) };
  }
  persist(): void {
    if (!this.projectId || this.recoveryRaw !== null) return;
    const raw=JSON.stringify({schema_version:1,project_id:this.projectId,view:this.baseline??this.view});
    this.storageUnavailable=raw.length>2*1024*1024||!this.port.setItem(this.storageKey(),raw);
  }
  discardRecovery(): void { this.recoveryRaw = null; this.persist(); }
  beginPreview(result: PreviewResult): void {
    if (!this.model) return;
    if (!this.baseline) this.baseline = clone(this.view);
    this.view = { ...clone(this.baseline), source: "", level: null, isolation: null, selection: null, section: null };
    const keep = (m: { source: string; source_id: string }) => !result.replace_all
      && !(result.replace_generated && m.source === "generated")
      && !(m.source_id === result.replace_source_id && (!result.replace_source_type || m.source === result.replace_source_type));
    this.preview = { ...this.model, elements: [...this.model.elements.filter(keep), ...result.elements], types: result.types,
      meta: { ...this.model.meta, review: result.metadata.review,
        preview_wall_dimensions:result.metadata.wall_dimensions,
        warnings: [...this.model.meta.warnings, ...result.metadata.warnings],
        frame_segments: [...this.model.meta.frame_segments.filter(keep), ...result.metadata.frame_segments] } };
  }
  cancelPreview(): void {
    this.preview = null;
    if (this.baseline) this.view = this.baseline;
    this.baseline = null;
  }
  select(member: BimElement | null): void {
    this.patch({ selection: member && this.activeModel ? memberKey(member, this.activeModel.meta.project.revision) : null });
  }
  isolate(members: BimElement[] | null): void {
    this.patch({ isolation: members?.map(m => memberKey(m, this.activeModel!.meta.project.revision)) ?? null });
  }
  reconcile(): void {
    const model = this.activeModel; if (!model) return;
    const keys = new Set(model.elements.map(m => memberKey(m, model.meta.project.revision)));
    if (this.view.selection && !keys.has(this.view.selection)) this.view.selection = null;
    if (this.view.isolation) {
      const surviving = this.view.isolation.filter(k => keys.has(k));
      this.view.isolation = surviving.length ? surviving : null;
    }
    if (this.view.source && !model.elements.some(m => m.source === this.view.source)) this.view.source = "";
    if (this.view.level !== null && !model.elements.some(m => m.storey === this.view.level)) this.view.level = null;
  }
  selectedMember(): BimElement | undefined {
    const model = this.activeModel;
    return model?.elements.find(m => memberKey(m, model.meta.project.revision) === this.view.selection);
  }
  visibleMembers(): BimElement[] {
    const model = this.activeModel; if (!model) return [];
    const isolated = this.view.isolation && new Set(this.view.isolation);
    return model.elements.filter(m => (!this.view.source || m.source === this.view.source)
      && (this.view.level === null || m.storey === this.view.level)
      && (!isolated || isolated.has(memberKey(m, model.meta.project.revision))));
  }
}
