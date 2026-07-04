import {
  commitManualTruss, commitManualWallFrame, previewManualTruss,
  previewManualWallFrame,
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
    <input name="${name}" type="${type}" value="${value}" ${extra}></label>`;
}

function number(form: FormData, key: string, fallback = 0): number {
  const value = Number(form.get(key));
  return Number.isFinite(value) ? value : fallback;
}

export class ManualInputs {
  readonly wall: ManualWallPanel;
  readonly truss: ManualTrussPanel;
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};

  constructor(wallRoot: HTMLElement, trussRoot: HTMLElement) {
    this.wall = new ManualWallPanel(wallRoot);
    this.truss = new ManualTrussPanel(trussRoot);
    this.wall.onPreview = (result) => this.onPreview(result);
    this.truss.onPreview = (result) => this.onPreview(result);
    this.wall.onModel = (model) => this.onModel(model);
    this.truss.onModel = (model) => this.onModel(model);
  }
}

class ManualWallPanel {
  private openings: ManualOpening[] = [];
  private previewSignature = "";
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
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
        ${field("Stud spacing (mm)", "stud_spacing_mm", 600, "number", 'min="200"')}
        ${field("Number of plies", "plies", 1, "number", 'min="1" max="12"')}
        ${field("Bottom plate size", "bottom_plate_size", "90x45", "text")}
        ${field("Top plate size", "top_plate_size", "90x45", "text")}
        ${field("Nog count", "nog_count", 1, "number", 'min="0" max="10"')}
        ${field("Nog spacing (mm, optional)", "nog_spacing_mm", "", "number", 'min="100"')}
        ${treatmentField}
        <label class="check-field"><input name="exterior" type="checkbox" checked>
          Exterior wall</label>
        <label class="check-field"><input name="load_bearing" type="checkbox" checked>
          Load bearing</label>
      </form>
      <h3>Openings</h3>
      <div id="wall-openings"></div>
      <div class="button-row">
        <button id="add-opening" class="secondary-button">Add opening</button>
        <button id="wall-preview" class="secondary-button">Preview wall</button>
        <button id="wall-commit" class="primary-button" disabled>Commit wall</button>
        <button id="wall-reset" class="secondary-button">Reset form</button>
      </div>
      <div id="wall-result" class="message-list"></div>`);
    this.bind();
    this.restore();
  }

  private bind(): void {
    const form = this.root.querySelector<HTMLFormElement>("#wall-form")!;
    form.addEventListener("input", () => {
      this.previewSignature = "";
      this.root.querySelector<HTMLButtonElement>("#wall-commit")!.disabled = true;
      this.saveDraft();
    });
    this.root.querySelector("#add-opening")!.addEventListener("click", () => {
      this.openings.push({
        opening_id: `O${this.openings.length + 1}`, opening_type: "window",
        start_offset_mm: 1000, width_mm: 1200, height_mm: 1200,
        sill_height_mm: 900, head_height_mm: 2100, lintel_size: "", notes: "",
      });
      this.renderOpenings(); this.saveDraft();
    });
    this.root.querySelector("#wall-preview")!.addEventListener("click",
      () => void this.preview());
    this.root.querySelector("#wall-commit")!.addEventListener("click",
      () => void this.commit());
    this.root.querySelector("#wall-reset")!.addEventListener("click", () => {
      if (!confirm("Reset the manual wall draft?")) return;
      form.reset(); this.openings = []; this.previewSignature = "";
      localStorage.removeItem("timberbim.manualWallDraft");
      this.renderOpenings();
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
          start_offset_mm: Number(get("start_offset_mm")),
          width_mm: Number(get("width_mm")), height_mm: Number(get("height_mm")),
          sill_height_mm: Number(get("sill_height_mm")),
          head_height_mm: get("head_height_mm") ? Number(get("head_height_mm")) : null,
          lintel_size: get("lintel_size"),
        };
        this.previewSignature = ""; this.saveDraft();
      });
      fieldset.querySelector(".remove-opening")!.addEventListener("click", () => {
        this.openings.splice(index, 1); this.renderOpenings(); this.saveDraft();
      });
    });
  }

  private value(): ManualWallFrameInput {
    const form = this.root.querySelector<HTMLFormElement>("#wall-form")!;
    const data = new FormData(form);
    return {
      input_id: "", level: number(data, "level", 1),
      segment_id: String(data.get("segment_id") ?? ""),
      segment_label: String(data.get("segment_label") ?? "Manual wall"),
      start_x_mm: number(data, "start_x_mm"), start_z_mm: number(data, "start_z_mm"),
      end_x_mm: number(data, "end_x_mm"), end_z_mm: number(data, "end_z_mm"),
      wall_height_mm: number(data, "wall_height_mm", 2535),
      wall_thickness_mm: number(data, "wall_thickness_mm", 90),
      stud_size: String(data.get("stud_size") ?? "90x45"),
      stud_material: String(data.get("stud_material") ?? "SG8"),
      stud_spacing_mm: number(data, "stud_spacing_mm", 600),
      plies: number(data, "plies", 1),
      bottom_plate_size: String(data.get("bottom_plate_size") ?? "90x45"),
      top_plate_size: String(data.get("top_plate_size") ?? "90x45"),
      nog_count: number(data, "nog_count", 1),
      nog_spacing_mm: data.get("nog_spacing_mm")
        ? number(data, "nog_spacing_mm") : null,
      treatment: String(data.get("treatment") ?? "H1.2"),
      exterior: data.has("exterior"), load_bearing: data.has("load_bearing"),
      openings: this.openings,
    };
  }

  private async preview(): Promise<void> {
    try {
      const input = this.value();
      const result = await previewManualWallFrame(input);
      this.previewSignature = JSON.stringify(input);
      this.root.querySelector<HTMLButtonElement>("#wall-commit")!.disabled = false;
      this.result(`Preview: ${result.metadata.member_count} members, ` +
        `${result.metadata.lineal_metres} m, estimated US$` +
        `${result.metadata.estimated_cost_usd.toFixed(2)}.`, "success");
      this.onPreview(result);
    } catch (error) { this.result((error as Error).message, "error"); }
  }

  private async commit(): Promise<void> {
    const input = this.value();
    if (this.previewSignature !== JSON.stringify(input)) {
      this.result("Preview the current wall draft before committing.", "error");
      return;
    }
    const result = await commitManualWallFrame(input);
    this.onModel(result.model);
    this.result(`Committed wall ${result.source_id}.`, "success");
  }

  private saveDraft(): void {
    localStorage.setItem("timberbim.manualWallDraft", JSON.stringify(this.value()));
  }

  private restore(): void {
    const raw = localStorage.getItem("timberbim.manualWallDraft");
    if (!raw) return;
    try {
      const draft = JSON.parse(raw) as ManualWallFrameInput;
      const form = this.root.querySelector<HTMLFormElement>("#wall-form")!;
      Object.entries(draft).forEach(([key, value]) => {
        if (key === "openings") return;
        const input = form.elements.namedItem(key) as HTMLInputElement | HTMLSelectElement;
        if (!input) return;
        if (input.type === "checkbox") (input as HTMLInputElement).checked = Boolean(value);
        else input.value = String(value);
      });
      this.openings = draft.openings ?? [];
      this.renderOpenings();
    } catch { localStorage.removeItem("timberbim.manualWallDraft"); }
  }

  private result(text: string, kind: string): void {
    this.root.querySelector("#wall-result")!.innerHTML =
      `<div class="message ${kind}">${text}</div>`;
  }
}

class ManualTrussPanel {
  private previewSignature = "";
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <form id="truss-form" class="form-grid">
        ${field("Level / storey", "level", 1, "number", 'min="1" max="20"')}
        ${field("Truss ID", "truss_id", "", "text")}
        ${field("Truss label", "truss_label", "Manual truss", "text")}
        ${field("Span (mm)", "span_mm", 9000)}
        ${field("Pitch (degrees)", "pitch_deg", 25)}
        ${field("Spacing (mm)", "spacing_mm", 900)}
        ${field("Quantity", "quantity", 1, "number", 'min="1" max="500"')}
        ${field("Start X (mm)", "start_x_mm", 0)}
        ${field("Start Z (mm)", "start_z_mm", 0)}
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
R,4500,0</textarea></label>
        <label class="field full custom-truss" hidden><span>Custom members CSV:
          start_node,end_node,element_type,size,material</span>
          <textarea name="members_csv" rows="5">L,C,top_chord,140x45,SG8
C,R,top_chord,140x45,SG8
L,R,bottom_chord,90x45,SG8</textarea></label>
      </form>
      <div class="button-row">
        <button id="truss-preview" class="secondary-button">Preview truss layout</button>
        <button id="truss-commit" class="primary-button" disabled>Commit trusses</button>
        <button id="truss-reset" class="secondary-button">Reset form</button>
      </div>
      <div id="truss-result" class="message-list"></div>`);
    this.bind(); this.restore();
  }

  private bind(): void {
    const form = this.root.querySelector<HTMLFormElement>("#truss-form")!;
    form.addEventListener("input", () => {
      this.previewSignature = "";
      this.root.querySelector<HTMLButtonElement>("#truss-commit")!.disabled = true;
      this.toggleCustom(); this.saveDraft();
    });
    this.root.querySelector("#truss-preview")!.addEventListener("click",
      () => void this.preview());
    this.root.querySelector("#truss-commit")!.addEventListener("click",
      () => void this.commit());
    this.root.querySelector("#truss-reset")!.addEventListener("click", () => {
      if (!confirm("Reset the manual truss draft?")) return;
      form.reset(); this.previewSignature = "";
      localStorage.removeItem("timberbim.manualTrussDraft"); this.toggleCustom();
    });
  }

  private parseNodes(raw: string): TrussNode[] {
    return raw.split(/\r?\n/).filter(Boolean).map((line) => {
      const [id, x, y] = line.split(",").map((item) => item.trim());
      return { id, x: Number(x), y: Number(y) };
    });
  }

  private parseMembers(raw: string): TrussMember[] {
    return raw.split(/\r?\n/).filter(Boolean).map((line) => {
      const [start_node, end_node, element_type, size, material] =
        line.split(",").map((item) => item.trim());
      return { start_node, end_node, element_type, size, material };
    });
  }

  private value(): ManualTrussInput {
    const data = new FormData(
      this.root.querySelector<HTMLFormElement>("#truss-form")!);
    const type = String(data.get("truss_type")) as ManualTrussInput["truss_type"];
    return {
      input_id: "", level: number(data, "level", 1),
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
    try {
      const input = this.value();
      const result = await previewManualTruss(input);
      this.previewSignature = JSON.stringify(input);
      this.root.querySelector<HTMLButtonElement>("#truss-commit")!.disabled = false;
      this.result(`Preview: ${input.quantity} trusses, ` +
        `${result.metadata.member_count} members, ${result.metadata.lineal_metres} m, ` +
        `estimated US$${result.metadata.estimated_cost_usd.toFixed(2)}.`, "success");
      this.onPreview(result);
    } catch (error) { this.result((error as Error).message, "error"); }
  }

  private async commit(): Promise<void> {
    const input = this.value();
    if (this.previewSignature !== JSON.stringify(input)) {
      this.result("Preview the current truss draft before committing.", "error");
      return;
    }
    const result = await commitManualTruss(input);
    this.onModel(result.model);
    this.result(`Committed truss layout ${result.source_id}.`, "success");
  }

  private saveDraft(): void {
    localStorage.setItem("timberbim.manualTrussDraft", JSON.stringify(this.value()));
  }

  private restore(): void {
    const raw = localStorage.getItem("timberbim.manualTrussDraft");
    if (!raw) return;
    try {
      const draft = JSON.parse(raw) as ManualTrussInput;
      const form = this.root.querySelector<HTMLFormElement>("#truss-form")!;
      Object.entries(draft).forEach(([key, value]) => {
        const input = form.elements.namedItem(key) as HTMLInputElement | HTMLSelectElement;
        if (input && !Array.isArray(value)) input.value = String(value);
      });
      if (draft.nodes.length)
        (form.elements.namedItem("nodes_csv") as HTMLTextAreaElement).value =
          draft.nodes.map((node) => `${node.id},${node.x},${node.y}`).join("\n");
      if (draft.members.length)
        (form.elements.namedItem("members_csv") as HTMLTextAreaElement).value =
          draft.members.map((member) => [
            member.start_node, member.end_node, member.element_type,
            member.size, member.material,
          ].join(",")).join("\n");
      this.toggleCustom();
    } catch { localStorage.removeItem("timberbim.manualTrussDraft"); }
  }

  private result(text: string, kind: string): void {
    this.root.querySelector("#truss-result")!.innerHTML =
      `<div class="message ${kind}">${text}</div>`;
  }
}
