import { currentProjectId } from "./api";
import { customRows, writeCsv } from "./csv";
import { escapeHtml, message } from "./dom";
import { FormDraftStorage } from "./draftStorage";
import { boundsOf } from "./memberGeometry";
import { openingDraft } from "./drafts";
import type { OpeningDraft } from "./drafts";
import { FormGuidance, FormInputError } from "./formGuidance";
import {
  commitManualTruss, commitManualWallFrame, previewManualTruss,
  previewManualWallFrame,
  StaleResponseError,
  ApiError,
  updateManualWallFrame, updateManualTruss,
} from "./api";
import { MATERIAL_OPTIONS, TREATMENT_OPTIONS } from "./types";
import type {
  BimModel, ManualOpening, ManualTrussInput, ManualWallFrameInput,
  PreviewResult, TrussMember, TrussNode,
} from "./types";

const materialOptions = MATERIAL_OPTIONS.map(([key, label]) =>
  `<option value="${label}" data-key="${key}">${label}</option>`).join("");

const treatmentField = `<label class="field"><span>Treatment (NZS 3640)</span>
  <select name="treatment">${TREATMENT_OPTIONS.map((t) =>
    `<option value="${t}">${t}</option>`).join("")}</select></label>`;

function field(label: string, name: string, value: string | number,
  type = "number", extra = ""): string {
  return `<label class="field"><span>${label}</span>
    <input name="${name}" type="${type}" value="${escapeHtml(value)}" ${extra}></label>`;
}

function number(form: FormData, key: string, fallback = 0): number {
  const value = Number(form.get(key));
  return Number.isFinite(value) ? value : fallback;
}

function fillForm(form: HTMLFormElement, values: object): void {
  for (const [name, value] of Object.entries(values)) {
    const input = form.elements.namedItem(name);
    if (!(input instanceof HTMLInputElement || input instanceof HTMLSelectElement || input instanceof HTMLTextAreaElement)) continue;
    if (input instanceof HTMLInputElement && input.type === "checkbox") input.checked = Boolean(value);
    else {
      if (input instanceof HTMLSelectElement && !Array.from(input.options).some(option => option.value === String(value)))
        input.add(new Option(String(value), String(value)));
      input.value = value === null ? "" : String(value);
    }
  }
}

export class ManualInputs {
  readonly wall: ManualWallPanel;
  readonly truss: ManualTrussPanel;
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};
  onDraftChange: () => void = () => {};
  onEditTarget: (id: string | null, kind: "wall" | "truss") => void = () => {};
  setWorkspaceBusy(busy: boolean): void {
    this.wall.setWorkspaceBusy(busy); this.truss.setWorkspaceBusy(busy);
  }

  constructor(wallRoot: HTMLElement, trussRoot: HTMLElement) {
    this.wall = new ManualWallPanel(wallRoot);
    this.truss = new ManualTrussPanel(trussRoot);
    this.wall.onPreview = (result) => this.onPreview(result);
    this.truss.onPreview = (result) => this.onPreview(result);
    this.wall.onModel = (model) => this.onModel(model);
    this.truss.onModel = (model) => this.onModel(model);
    this.wall.onDraftChange = () => this.onDraftChange();
    this.truss.onDraftChange = () => this.onDraftChange();
    this.wall.onEditTarget = id => this.onEditTarget(id, "wall");
    this.truss.onEditTarget = id => this.onEditTarget(id, "truss");
  }
}

class ManualWallPanel {
  private draftStorage: FormDraftStorage;
  private guide: FormGuidance;
  private openings: OpeningDraft[] = [];
  private previewSignature = "";
  private pending = false;
  private workspaceBusy = false;
  private editId: string | null = null;
  private savedDefinition: ManualWallFrameInput | null = null;
  onEditTarget: (id: string | null) => void = () => {};
  editAssembly(id: string, definition: ManualWallFrameInput): void {
    this.onDraftChange();
    this.editId = id; this.savedDefinition = structuredClone(definition);
    this.draftStorage.setAssembly(id);
    const form = this.root.querySelector<HTMLFormElement>("form")!;
    form.reset(); fillForm(form, definition);
    this.openings = definition.openings.map(openingDraft);
    this.restore(); this.invalidatePreview(); this.updateEditStatus();
    this.onEditTarget(id);
  }
  private updateEditStatus(): void {
    this.root.querySelector("#wall-edit-status")!.textContent = this.editId
      ? `Editing saved wall ${this.editId}. Preview and Save replace this assembly; other assemblies remain. Unsaved edits have a separate draft.` : "New wall assembly";
    this.root.querySelector<HTMLButtonElement>("#wall-edit-exit")!.hidden = !this.editId;
    this.root.querySelector("#wall-commit")!.textContent = this.editId ? "Save wall changes" : "Commit wall";
  }
  onDraftChange: () => void = () => {};
  setWorkspaceBusy(busy: boolean): void { this.workspaceBusy = busy; this.updatePending(); }
  loadProject(): void {
    this.editId = null; this.savedDefinition = null; this.draftStorage.setAssembly(null);
    this.root.querySelector<HTMLFormElement>("form")!.reset();
    this.openings = [];
    this.renderOpenings();
    this.invalidatePreview();
    this.restore();
    this.updateEditStatus();
  }
  invalidatePreview(): void {
    this.previewSignature = "";
    this.guide.invalidate();
    this.updatePending();
  }
  private updatePending(): void {
    const pending = this.pending || this.workspaceBusy;
    this.root.querySelectorAll<HTMLInputElement | HTMLButtonElement | HTMLSelectElement | HTMLTextAreaElement>("input,button,select,textarea").forEach(control => control.disabled = pending);
    this.root.querySelector<HTMLButtonElement>("button[id$='-commit']")!.disabled = pending || !this.previewSignature;
  }
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <p id="wall-edit-status" role="status">New wall assembly</p><button id="wall-edit-exit" hidden>Exit wall editing</button>
      <form id="wall-form" class="form-grid">
        ${field("Level / storey", "level", 1, "number", 'min="1" max="20"')}
        ${field("Segment ID", "segment_id", "", "text")}
        ${field("Segment label", "segment_label", "Manual wall", "text")}
        ${field("Start X (mm)", "start_x_mm", 0)}
        ${field("Start Z (mm)", "start_z_mm", 0)}
        ${field("End X (mm)", "end_x_mm", 6000)}
        ${field("End Z (mm)", "end_z_mm", 0)}
        ${field("Wall height (mm)", "wall_height_mm", 2535, "number", 'min="300"')}
        ${field("Wall thickness (mm)", "wall_thickness_mm", 90, "number", 'min="20"')}
        ${field("Stud size", "stud_size", "90x45", "text")}
        <label class="field"><span>Stud material</span>
          <select name="stud_material">${materialOptions}</select></label>
        <label class="field"><span>Plate / nog material</span>
          <select name="plate_material">${materialOptions}</select></label>
        <label class="field"><span>Lintel material</span>
          <select name="lintel_material">${materialOptions}</select></label>
        <label class="check-field"><input name="panelize" type="checkbox">
          Split a long logical wall into fabrication panels</label>
        ${field("Stud spacing (mm)", "stud_spacing_mm", 600, "number", 'min="200"')}
        ${field("Number of plies", "plies", 1, "number", 'min="1" max="12"')}
        ${field("Bottom plate size", "bottom_plate_size", "90x45", "text")}
        ${field("Top plate size", "top_plate_size", "90x45", "text")}
        ${field("Nog count", "nog_count", 1, "number", 'min="0" max="10"')}
        ${field("Nog spacing (mm, optional)", "nog_spacing_mm", "", "number", 'min="0"')}
        ${treatmentField}
        <label class="check-field"><input name="exterior" type="checkbox" checked>
          Exterior wall</label>
        <label class="check-field"><input name="load_bearing" type="checkbox" checked>
          Load bearing</label>
      </form>
      <fieldset class="form-section"><legend>4. Openings</legend>
        <p class="notice">Offsets run from the wall start. Clear height plus sill height determines the head; leave Head empty to derive it.</p>
        <div id="wall-openings"></div><button id="add-opening" class="secondary-button">Add opening</button>
      </fieldset>
      <div class="button-row">
        <button id="wall-preview" class="secondary-button">Preview wall</button>
        <button id="wall-commit" class="primary-button" disabled>Commit wall</button>
        <button id="wall-reset" class="secondary-button">Reset form</button>
      </div>
      <div id="wall-result" class="message-list"></div>`);
    this.guide=new FormGuidance(root,root.querySelector<HTMLFormElement>("#wall-form")!,"wall",[
      {title:"Placement",fields:["level","segment_id","segment_label","start_x_mm","start_z_mm","end_x_mm","end_z_mm","exterior","load_bearing"],hint:"X points east; plan Z points north. Coordinates and dimensions are millimetres."},
      {title:"Geometry",fields:["wall_height_mm","wall_thickness_mm","stud_spacing_mm","plies","nog_count","nog_spacing_mm","panelize"],hint:"Panelization preserves the logical run. Fabrication joints and structural capacity require review."},
      {title:"Materials",fields:["stud_size","stud_material","plate_material","lintel_material","bottom_plate_size","top_plate_size","treatment"]},
    ]);
    this.draftStorage = new FormDraftStorage(root, root.querySelector<HTMLFormElement>("#wall-form")!, "wall");
    this.bind();
    this.restore();
  }

  private bind(): void {
    const form = this.root.querySelector<HTMLFormElement>("#wall-form")!;
    this.root.querySelector("#wall-edit-exit")!.addEventListener("click", () => {
      this.onDraftChange(); this.loadProject(); this.onEditTarget(null);
    });
    form.addEventListener("input", () => {
      this.previewSignature = "";
      this.root.querySelector<HTMLButtonElement>("#wall-commit")!.disabled = true;
      this.guide.edited(this.openings);this.onDraftChange();
      this.saveDraft();
    });
    this.root.querySelector("#add-opening")!.addEventListener("click", () => {
      this.openings.push(openingDraft({
        opening_id: `O${this.openings.length + 1}`, opening_type: "window",
        start_offset_mm: 1000, width_mm: 1200, height_mm: 1200,
        sill_height_mm: 900, head_height_mm: 2100, lintel_size: "", notes: "",
      }));
      this.guide.edited(this.openings);
      this.invalidatePreview(); this.renderOpenings(); this.saveDraft();
      this.onDraftChange();
    });
    this.root.querySelector("#wall-preview")!.addEventListener("click",
      () => void this.preview());
    this.root.querySelector("#wall-commit")!.addEventListener("click",
      () => void this.commit());
    this.root.querySelector("#wall-reset")!.addEventListener("click", () => {
      if (!confirm("Reset the manual wall draft?")) return;
      form.reset();
      if (this.savedDefinition) fillForm(form, this.savedDefinition);
      this.openings = (this.savedDefinition?.openings ?? []).map(openingDraft); this.previewSignature = "";
      this.draftStorage.reset(currentProjectId());
      this.renderOpenings(); this.invalidatePreview();
      this.guide.reset(this.openings);
      this.onDraftChange();
    });
  }

  private renderOpenings(): void {
    const target = this.root.querySelector("#wall-openings")!;
    target.innerHTML = this.openings.map((opening, index) => `
      <fieldset class="subform" data-opening="${index}"><legend>Opening ${index + 1}</legend>
        ${field("ID", "opening_id", opening.opening_id, "text")}
        <label class="field"><span>Type</span><select name="opening_type">
          ${["door", "window", "garage", "custom"].map((type) =>
            `<option ${type === opening.opening_type ? "selected" : ""}>${type}</option>`
          ).join("")}</select></label>
        ${field("Start offset (mm)", "start_offset_mm", opening.start_offset_mm)}
        ${field("Width (mm)", "width_mm", opening.width_mm)}
        ${field("Height (mm)", "height_mm", opening.height_mm)}
        ${field("Sill height (mm)", "sill_height_mm", opening.sill_height_mm)}
        ${field("Head height (mm)", "head_height_mm", opening.head_height_mm ?? "")}
        ${field("Lintel size", "lintel_size", opening.lintel_size, "text")}
        ${field("Notes", "notes", opening.notes, "text")}
        <button class="table-delete remove-opening">Remove opening</button>
      </fieldset>`).join("");
    target.querySelectorAll<HTMLElement>("[data-opening]").forEach((fieldset) => {
      const index = Number(fieldset.dataset.opening);
      fieldset.addEventListener("input", () => {
        const get = (name: string) =>
          fieldset.querySelector<HTMLInputElement | HTMLSelectElement>(
            `[name="${name}"]`)!.value;
        this.openings[index] = {
          ...this.openings[index], opening_id: get("opening_id"),
          opening_type: get("opening_type") as ManualOpening["opening_type"],
          start_offset_mm: get("start_offset_mm"),
          width_mm: get("width_mm"), height_mm: get("height_mm"),
          sill_height_mm: get("sill_height_mm"),
          head_height_mm: get("head_height_mm"),
          lintel_size: get("lintel_size"),
          notes:get("notes"),
        };
        this.guide.edited(this.openings);
        this.invalidatePreview(); this.saveDraft();
        this.onDraftChange();
      });
      fieldset.querySelector(".remove-opening")!.addEventListener("click", () => {
        this.openings.splice(index, 1);this.guide.edited(this.openings); this.invalidatePreview(); this.renderOpenings(); this.saveDraft();
        this.onDraftChange();
        (target.querySelector<HTMLButtonElement>(`[data-opening="${Math.min(index,this.openings.length-1)}"] .remove-opening`)??this.root.querySelector<HTMLButtonElement>("#add-opening"))!.focus();
      });
    });
    this.guide.refresh(this.openings);
  }

  private value(): ManualWallFrameInput {
    this.guide.validate(this.openings);
    const form = this.root.querySelector<HTMLFormElement>("#wall-form")!;
    const data = new FormData(form);
    return {
      input_id: this.savedDefinition?.input_id ?? "", level: number(data, "level", 1),
      segment_id: String(data.get("segment_id") ?? ""),
      segment_label: String(data.get("segment_label") ?? "Manual wall"),
      start_x_mm: number(data, "start_x_mm"), start_z_mm: number(data, "start_z_mm"),
      end_x_mm: number(data, "end_x_mm"), end_z_mm: number(data, "end_z_mm"),
      wall_height_mm: number(data, "wall_height_mm", 2535),
      wall_thickness_mm: number(data, "wall_thickness_mm", 90),
      stud_size: String(data.get("stud_size") ?? "90x45"),
      stud_material: String(data.get("stud_material") ?? "SG8"),
      plate_material: String(data.get("plate_material") ?? "SG8"),
      lintel_material: String(data.get("lintel_material") ?? "SG8"),
      panelize: data.has("panelize"),
      stud_spacing_mm: number(data, "stud_spacing_mm", 600),
      plies: number(data, "plies", 1),
      bottom_plate_size: String(data.get("bottom_plate_size") ?? "90x45"),
      top_plate_size: String(data.get("top_plate_size") ?? "90x45"),
      nog_count: number(data, "nog_count", 1),
      nog_spacing_mm: data.get("nog_spacing_mm")
        ? number(data, "nog_spacing_mm") : null,
      treatment: String(data.get("treatment") ?? "H1.2"),
      exterior: data.has("exterior"), load_bearing: data.has("load_bearing"),
      openings: this.openings.map(o=>({...o,start_offset_mm:Number(o.start_offset_mm),width_mm:Number(o.width_mm),
        height_mm:Number(o.height_mm),sill_height_mm:Number(o.sill_height_mm),head_height_mm:o.head_height_mm===""?null:Number(o.head_height_mm)})),
    };
  }

  private async preview(): Promise<void> {
    if (this.pending) return;
    this.previewSignature = "";
    try {
      const input = this.value();
      this.pending = true; this.updatePending();
      const result = await previewManualWallFrame(input);
      this.previewSignature = JSON.stringify(input);
      this.root.querySelector<HTMLButtonElement>("#wall-commit")!.disabled = false;
      this.result(`Preview: ${result.metadata.member_count} members, ` +
        `${result.metadata.lineal_metres} m, estimated US$` +
        `${result.metadata.estimated_cost_usd.toFixed(2)} priced cut subtotal; stock US$${result.metadata.estimated_stock_cost_usd.toFixed(2)} · ${result.metadata.physical_board_quantity} boards · ${result.metadata.unpriced_cut_quantity} unpriced cuts.`, "success");
      this.onPreview({ ...result, replace_source_id: this.editId ?? undefined, replace_source_type: "manual_wall",
        metadata:{...result.metadata,wall_dimensions:{
          span_mm:Math.hypot(input.end_x_mm-input.start_x_mm,input.end_z_mm-input.start_z_mm),
          height_mm:input.wall_height_mm,direction_deg:(Math.atan2(input.end_z_mm-input.start_z_mm,input.end_x_mm-input.start_x_mm)*180/Math.PI+360)%360,
          level:input.level,elevation_mm:boundsOf(result.elements)!.minimum[2],openings:structuredClone(input.openings)}} });
      this.guide.success("Previewed");
    } catch (error) { if (!(error instanceof StaleResponseError)){this.pending=false;this.updatePending();this.guide.showError(error);this.result((error as Error).message, "error");} }
    finally { this.pending = false; this.updatePending(); }
  }

  private async commit(): Promise<void> {
    if (this.pending) return;
    let input: ManualWallFrameInput;
    try { input = this.value(); } catch (error) {this.guide.showError(error); this.result((error as Error).message, "error"); return; }
    if (this.previewSignature !== JSON.stringify(input)) {
      this.result("Preview the current wall draft before committing.", "error");
      return;
    }
    this.pending = true; this.updatePending();
    try {
      const result = await (this.editId ? updateManualWallFrame(this.editId, input) : commitManualWallFrame(input));
      this.previewSignature = "";
      this.onModel(result.model);
      if (this.editId) this.savedDefinition = structuredClone(input);
      this.result(`${this.editId ? "Updated" : "Committed"} wall ${result.source_id}.`, "success");
      this.guide.success("Committed");
    } catch (error) {
      if (!(error instanceof StaleResponseError)) {
        const retry=!(error instanceof ApiError)||error.status>=500||[408,429].includes(error.status);
        if(!retry)this.previewSignature="";
        this.pending=false;this.updatePending();this.guide.showError(error,retry&&Boolean(this.previewSignature));this.result((error as Error).message,"error");
      }
    }
    finally { this.pending = false; this.updatePending(); }
  }

  private saveDraft(): void {
    this.draftStorage.save(currentProjectId(), this.openings);
  }

  private restore(): void {
    const openings = this.draftStorage.restore(currentProjectId());
    if (openings) this.openings = openings;
    this.renderOpenings();
    this.guide.reset(this.openings);
  }

  private result(text: string, kind: string): void {
    message(this.root.querySelector("#wall-result")!, text, kind);
  }
}

class ManualTrussPanel {
  private draftStorage: FormDraftStorage;
  private guide:FormGuidance;
  private previewSignature = "";
  private pending = false;
  private workspaceBusy = false;
  private editId: string | null = null;
  private savedDefinition: ManualTrussInput | null = null;
  onEditTarget: (id: string | null) => void = () => {};
  private fillDefinition(definition: ManualTrussInput): void {
    const form = this.root.querySelector<HTMLFormElement>("form")!;
    fillForm(form, definition);
    if (definition.nodes.length) (form.elements.namedItem("nodes_csv") as HTMLTextAreaElement).value = writeCsv(definition.nodes.map(node => [node.id, node.x, node.y]));
    if (definition.members.length) (form.elements.namedItem("members_csv") as HTMLTextAreaElement).value = writeCsv(definition.members.map(member => [member.start_node, member.end_node, member.element_type, member.size, member.material]));
  }
  editAssembly(id: string, definition: ManualTrussInput): void {
    this.onDraftChange();
    this.editId = id; this.savedDefinition = structuredClone(definition);
    this.draftStorage.setAssembly(id);
    this.root.querySelector<HTMLFormElement>("form")!.reset();
    this.fillDefinition(definition); this.restore(); this.invalidatePreview(); this.updateEditStatus();
    this.onEditTarget(id);
  }
  private updateEditStatus(): void {
    this.root.querySelector("#truss-edit-status")!.textContent = this.editId
      ? `Editing saved truss layout ${this.editId}. Preview and Save replace its instances; other assemblies remain. Unsaved edits have a separate draft.` : "New truss layout";
    this.root.querySelector<HTMLButtonElement>("#truss-edit-exit")!.hidden = !this.editId;
    this.root.querySelector("#truss-commit")!.textContent = this.editId ? "Save truss changes" : "Commit trusses";
  }
  onDraftChange: () => void = () => {};
  setWorkspaceBusy(busy: boolean): void { this.workspaceBusy = busy; this.updatePending(); }
  loadProject(): void {
    this.editId = null; this.savedDefinition = null; this.draftStorage.setAssembly(null);
    this.root.querySelector<HTMLFormElement>("form")!.reset();
    this.invalidatePreview();
    this.restore();
    this.updateEditStatus();
  }
  invalidatePreview(): void {
    this.previewSignature = "";
    this.guide.invalidate();
    this.updatePending();
  }
  private updatePending(): void {
    const pending = this.pending || this.workspaceBusy;
    this.root.querySelectorAll<HTMLInputElement | HTMLButtonElement | HTMLSelectElement | HTMLTextAreaElement>("input,button,select,textarea").forEach(control => control.disabled = pending);
    this.root.querySelector<HTMLButtonElement>("button[id$='-commit']")!.disabled = pending || !this.previewSignature;
  }
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <p id="truss-edit-status" role="status">New truss layout</p><button id="truss-edit-exit" hidden>Exit truss editing</button>
      <form id="truss-form" class="form-grid">
        ${field("Level / storey", "level", 1, "number", 'min="1" max="20"')}
        ${field("Truss ID", "truss_id", "", "text")}
        ${field("Truss label", "truss_label", "Manual truss", "text")}
        ${field("Span (mm)", "span_mm", 9000)}
        ${field("Pitch (degrees)", "pitch_deg", 25)}
        ${field("Spacing (mm)", "spacing_mm", 900)}
        ${field("Quantity", "quantity", 1, "number", 'min="1" max="500"')}
        ${field("Truss origin X (mm)", "start_x_mm", 0)}
        ${field("Truss origin Z (mm)", "start_z_mm", 0)}
        ${field("Direction (degrees)", "direction_deg", 0)}
        <label class="field"><span>Truss type</span><select name="truss_type">
          ${["common", "girder", "mono", "scissor", "attic", "custom"].map(
            (type) => `<option>${type}</option>`).join("")}</select></label>
        ${field("Top chord size", "top_chord_size", "140x45", "text")}
        <label class="field"><span>Top chord material</span>
          <select name="top_chord_material">${materialOptions}</select></label>
        ${field("Bottom chord size", "bottom_chord_size", "90x45", "text")}
        <label class="field"><span>Bottom chord material</span>
          <select name="bottom_chord_material">${materialOptions}</select></label>
        ${field("Web size", "web_size", "90x45", "text")}
        <label class="field"><span>Web material</span>
          <select name="web_material">${materialOptions}</select></label>
        ${field("Overhang (mm)", "overhang_mm", 450)}
        ${field("Heel height (mm)", "heel_height_mm", 100)}
        ${treatmentField}
        <label class="field full custom-truss" hidden><span>Custom nodes CSV:
          id,x,y</span><textarea name="nodes_csv" rows="5">L,-4500,0
C,0,2100
R,4500,0
B,0,0</textarea></label>
        <label class="field full custom-truss" hidden><span>Custom members CSV:
          start_node,end_node,element_type,size,material</span>
          <textarea name="members_csv" rows="5">L,C,top_chord,140x45,SG8
C,R,top_chord,140x45,SG8
L,R,bottom_chord,90x45,SG8
B,C,king_post,90x45,SG8</textarea></label>
      </form>
      <p class="notice">Template origins are at the center between bearings. Custom CSV node coordinates are relative to this origin. Direction runs from local left to right; repeated instances advance perpendicular to it.</p>
      <div class="button-row">
        <button id="truss-preview" class="secondary-button">Preview truss layout</button>
        <button id="truss-commit" class="primary-button" disabled>Commit trusses</button>
        <button id="truss-reset" class="secondary-button">Reset form</button>
      </div>
      <div id="truss-result" class="message-list"></div>`);

    this.guide=new FormGuidance(root,root.querySelector<HTMLFormElement>("#truss-form")!,"truss",[
      {title:"Placement",fields:["level","truss_id","truss_label","start_x_mm","start_z_mm","direction_deg","spacing_mm","quantity"],hint:"Template origins lie between the bearings. Repeated instances advance perpendicular to the truss direction."},
      {title:"Geometry",fields:["truss_type","span_mm","pitch_deg","overhang_mm","heel_height_mm"]},
      {title:"Materials",fields:["top_chord_size","top_chord_material","bottom_chord_size","bottom_chord_material","web_size","web_material","treatment"]},
      {title:"Webs / custom graph",fields:["nodes_csv","members_csv"],hint:"Templates generate connected webs automatically. Custom nodes use local horizontal x and elevation y coordinates; members connect those node IDs."},
    ]);
    this.draftStorage = new FormDraftStorage(root, root.querySelector<HTMLFormElement>("#truss-form")!, "truss");
    this.bind(); this.restore();
  }

  private bind(): void {
    const form = this.root.querySelector<HTMLFormElement>("#truss-form")!;
    this.root.querySelector("#truss-edit-exit")!.addEventListener("click", () => {
      this.onDraftChange(); this.loadProject(); this.onEditTarget(null);
    });
    form.addEventListener("input", () => {
      this.previewSignature = "";
      this.root.querySelector<HTMLButtonElement>("#truss-commit")!.disabled = true;
      this.toggleCustom();this.guide.edited(); this.saveDraft();
      this.onDraftChange();
    });
    this.root.querySelector("#truss-preview")!.addEventListener("click",
      () => void this.preview());
    this.root.querySelector("#truss-commit")!.addEventListener("click",
      () => void this.commit());
    this.root.querySelector("#truss-reset")!.addEventListener("click", () => {
      if (!confirm("Reset the manual truss draft?")) return;
      form.reset(); this.previewSignature = "";
      if (this.savedDefinition) this.fillDefinition(this.savedDefinition);
      this.draftStorage.reset(currentProjectId()); this.toggleCustom(); this.invalidatePreview();
      this.guide.reset();
      this.onDraftChange();
    });
  }

  private parseNodes(raw: string): TrussNode[] {
    try {
      return customRows(raw, ["id", "x", "y"]).map(([id, x, y], index) => {
        if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y)))
          throw new Error(`Custom node row ${index + 1}: x and y must be finite numbers.`);
        return { id, x: Number(x), y: Number(y) };
      });
    }catch(error){throw new FormInputError([{path:["nodes_csv"],message:(error as Error).message}]);}
  }

  private parseMembers(raw: string): TrussMember[] {
    try {
      return customRows(raw, ["start_node", "end_node", "element_type", "size", "material"])
        .map(([start_node, end_node, element_type, size, material]) => ({ start_node, end_node, element_type, size, material }));
    }catch(error){throw new FormInputError([{path:["members_csv"],message:(error as Error).message}]);}
  }

  private value(): ManualTrussInput {
    this.guide.validate();
    const data = new FormData(
      this.root.querySelector<HTMLFormElement>("#truss-form")!);
    const type = String(data.get("truss_type")) as ManualTrussInput["truss_type"];
    return {
      input_id: this.savedDefinition?.input_id ?? "", level: number(data, "level", 1),
      truss_id: String(data.get("truss_id") ?? ""),
      truss_label: String(data.get("truss_label") ?? "Manual truss"),
      span_mm: number(data, "span_mm", 9000), pitch_deg: number(data, "pitch_deg", 25),
      spacing_mm: number(data, "spacing_mm", 900),
      quantity: number(data, "quantity", 1),
      start_x_mm: number(data, "start_x_mm"), start_z_mm: number(data, "start_z_mm"),
      direction_deg: number(data, "direction_deg"),
      top_chord_size: String(data.get("top_chord_size") ?? "140x45"),
      top_chord_material: String(data.get("top_chord_material") ?? "SG8"),
      bottom_chord_size: String(data.get("bottom_chord_size") ?? "90x45"),
      bottom_chord_material: String(data.get("bottom_chord_material") ?? "SG8"),
      web_size: String(data.get("web_size") ?? "90x45"),
      web_material: String(data.get("web_material") ?? "SG8"),
      overhang_mm: number(data, "overhang_mm", 450),
      heel_height_mm: number(data, "heel_height_mm", 100),
      treatment: String(data.get("treatment") ?? "H1.2"), truss_type: type,
      nodes: type === "custom" ? this.parseNodes(String(data.get("nodes_csv"))) : [],
      members: type === "custom"
        ? this.parseMembers(String(data.get("members_csv"))) : [],
    };
  }

  private toggleCustom(): void {
    const type = this.root.querySelector<HTMLSelectElement>(
      '[name="truss_type"]')!.value;
    this.root.querySelectorAll<HTMLElement>(".custom-truss").forEach(
      (element) => element.hidden = type !== "custom");
  }

  private async preview(): Promise<void> {
    if (this.pending) return;
    this.previewSignature = "";
    try {
      const input = this.value();
      this.pending = true; this.updatePending();
      const result = await previewManualTruss(input);
      this.previewSignature = JSON.stringify(input);
      this.root.querySelector<HTMLButtonElement>("#truss-commit")!.disabled = false;
      this.result(`Preview: ${input.quantity} trusses, ` +
        `${result.metadata.member_count} members, ${result.metadata.lineal_metres} m, ` +
        `priced cut subtotal US$${result.metadata.estimated_cost_usd.toFixed(2)}; stock US$${result.metadata.estimated_stock_cost_usd.toFixed(2)} · ${result.metadata.cut_quantity} cuts / ${result.metadata.physical_board_quantity} boards · ${result.metadata.unpriced_cut_quantity} unpriced cuts.`, "success");
      this.onPreview({ ...result, replace_source_id: this.editId ?? undefined, replace_source_type: "manual_truss" });
      this.guide.success("Previewed");
    } catch (error) { if (!(error instanceof StaleResponseError)){this.pending=false;this.updatePending();this.guide.showError(error);this.result((error as Error).message, "error");} }
    finally { this.pending = false; this.updatePending(); }
  }

  private async commit(): Promise<void> {
    if (this.pending) return;
    let input: ManualTrussInput;
    try { input = this.value(); } catch (error) {this.guide.showError(error); this.result((error as Error).message, "error"); return; }
    if (this.previewSignature !== JSON.stringify(input)) {
      this.result("Preview the current truss draft before committing.", "error");
      return;
    }
    this.pending = true; this.updatePending();
    try {
      const result = await (this.editId ? updateManualTruss(this.editId, input) : commitManualTruss(input));
      this.previewSignature = "";
      this.onModel(result.model);
      if (this.editId) this.savedDefinition = structuredClone(input);
      this.result(`${this.editId ? "Updated" : "Committed"} truss layout ${result.source_id}.`, "success");
      this.guide.success("Committed");
    } catch (error) {
      if (!(error instanceof StaleResponseError)) {
        const retry=!(error instanceof ApiError)||error.status>=500||[408,429].includes(error.status);
        if(!retry)this.previewSignature="";
        this.pending=false;this.updatePending();this.guide.showError(error,retry&&Boolean(this.previewSignature));this.result((error as Error).message,"error");
      }
    }
    finally { this.pending = false; this.updatePending(); }
  }

  private saveDraft(): void {
    this.draftStorage.save(currentProjectId());
  }

  private restore(): void {
    this.draftStorage.restore(currentProjectId());
    this.toggleCustom();
    this.guide.reset();
  }

  private result(text: string, kind: string): void {
    message(this.root.querySelector("#truss-result")!, text, kind);
  }
}
