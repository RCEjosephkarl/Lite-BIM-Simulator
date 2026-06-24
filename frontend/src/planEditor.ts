import {
  commitManualWalls, commitRoof, deleteImportBatch, previewManualWalls,
  previewRoof,
} from "./api";
import { MATERIAL_OPTIONS } from "./types";
import type {
  BimModel, ManualRoofInput, ManualWallFrameInput, PreviewResult,
} from "./types";

/** A wall drawn on the 2D plan. Carries the full ManualWallFrameInput contract
 *  the backend `generate_wall` engine consumes, plus a local id. */
interface DrawnWall extends ManualWallFrameInput { _id: string; }

interface Pt { x: number; z: number; }

const STORAGE_KEY = "timberbim.planEditor";
const MIN_WALL_MM = 300;
const ROOF_STYLES: [ManualRoofInput["style"], string][] = [
  ["gable_run", "Gable — normal-run trusses"],
  ["hip_rafter", "Hip rafter (stick framed)"],
  ["mitek_hip", "MiTek NZ hip truss"],
];

let seq = 0;
const newId = (): string => `pw-${Date.now().toString(36)}-${seq++}`;

function defaultWall(level: number, a: Pt, b: Pt): DrawnWall {
  const id = newId();
  return {
    _id: id, input_id: id, level,
    segment_id: id, segment_label: `Wall L${level}`,
    start_x_mm: a.x, start_z_mm: a.z, end_x_mm: b.x, end_z_mm: b.z,
    wall_height_mm: 2535, wall_thickness_mm: 90,
    stud_size: "90x45", stud_material: "SG8", stud_spacing_mm: 600, plies: 1,
    bottom_plate_size: "90x45", top_plate_size: "90x45",
    nog_count: 1, nog_spacing_mm: null, treatment: "H1.2",
    exterior: true, load_bearing: true, openings: [],
  };
}

const materialOptions = MATERIAL_OPTIONS.map(([, label]) =>
  `<option value="${label}">${label}</option>`).join("");

export class PlanEditor {
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};
  onCommitted: () => void = () => {};

  private canvas!: HTMLCanvasElement;
  private ctx!: CanvasRenderingContext2D;
  private form!: HTMLElement;
  private status!: HTMLElement;

  private walls: DrawnWall[] = [];
  private level = 1;
  private grid = 100;          // snap grid (mm)
  private tool: "draw" | "select" = "draw";
  private selectedId: string | null = null;
  private wallBatchId: string | null = null;
  private roofSourceId: string | null = null;

  // view transform: screen_px = pan + mm * scale  (z is up on screen)
  private scale = 0.028;
  private panX = 46;
  private panY = 286;
  // interaction state
  private pending: Pt | null = null;       // chain start (click-click)
  private down: Pt | null = null;          // press start (drag)
  private cursor: Pt | null = null;
  private moved = false;
  private panning: { x: number; y: number } | null = null;

  constructor(private root: HTMLElement) {
    this.load();
    this.build();
    this.draw();
  }

  // ---- persistence -------------------------------------------------------
  private load(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const data = JSON.parse(raw);
        this.walls = data.walls ?? [];
        this.wallBatchId = data.wallBatchId ?? null;
        this.roofSourceId = data.roofSourceId ?? null;
      }
    } catch { /* ignore corrupt drafts */ }
  }

  private save(): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      walls: this.walls, wallBatchId: this.wallBatchId,
      roofSourceId: this.roofSourceId,
    }));
  }

  // ---- DOM ---------------------------------------------------------------
  private build(): void {
    this.root.insertAdjacentHTML("beforeend", `
      <p class="plan-hint">Draw walls top-down: click-drag (or click each end)
        on the grid. Switch to <b>Select</b> to pick a wall and edit its frame
        and openings. Right-drag to pan, wheel to zoom.</p>
      <div class="plan-toolbar">
        <button id="pe-draw" class="on" title="Draw walls">✏ Draw</button>
        <button id="pe-select" title="Select / edit walls">▦ Select</button>
        <select id="pe-level" title="Active level"></select>
        <select id="pe-grid" title="Snap grid">
          <option value="50">50 mm</option>
          <option value="100" selected>100 mm</option>
          <option value="300">300 mm</option>
          <option value="600">600 mm</option>
        </select>
        <button id="pe-del" title="Delete selected wall">🗑 Del</button>
        <button id="pe-clear" title="Clear all drawn walls">Clear</button>
      </div>
      <canvas class="plan-canvas" id="pe-canvas"></canvas>
      <div class="plan-toolbar">
        <button id="pe-preview" class="primary-button">Preview frame</button>
        <button id="pe-build">Build frame</button>
      </div>
      <div id="pe-form"></div>
      <section>
        <h2>Roof over footprint</h2>
        <div class="field">
          <label for="pe-roof-style">Roof style</label>
          <select id="pe-roof-style">
            ${ROOF_STYLES.map(([v, l]) =>
              `<option value="${v}">${l}</option>`).join("")}
          </select>
        </div>
        <div class="form-grid">
          <label class="field"><span>Pitch (°)</span>
            <input id="pe-roof-pitch" type="number" value="25" min="1" max="60"></label>
          <label class="field"><span>Truss/rafter centres (mm)</span>
            <input id="pe-roof-spacing" type="number" value="900" min="200" step="50"></label>
          <label class="field"><span>Eave overhang (mm)</span>
            <input id="pe-roof-overhang" type="number" value="450" min="0" step="50"></label>
          <label class="field"><span>Ridge direction</span>
            <select id="pe-roof-dir">
              <option value="auto">Auto (along longer side)</option>
              <option value="x">Along X (east–west)</option>
              <option value="z">Along Z (north–south)</option>
            </select></label>
        </div>
        <div class="plan-toolbar">
          <button id="pe-roof-preview" class="primary-button">Preview roof</button>
          <button id="pe-roof-build">Build roof</button>
        </div>
        <p class="plan-hint">Footprint = bounding box of the current level's
          drawn walls (defaults to 9.0 × 7.0 m if none). MiTek hip and stick hip
          are framed off the shorter ends. Conceptual — supplier/SED required.</p>
      </section>
      <p id="pe-status" class="plan-hint"></p>`);

    this.canvas = this.root.querySelector("#pe-canvas")!;
    this.ctx = this.canvas.getContext("2d")!;
    this.form = this.root.querySelector("#pe-form")!;
    this.status = this.root.querySelector("#pe-status")!;
    this.populateLevels();

    const on = (id: string, ev: string, fn: (e: Event) => void) =>
      this.root.querySelector(`#${id}`)!.addEventListener(ev, fn);

    on("pe-draw", "click", () => this.setTool("draw"));
    on("pe-select", "click", () => this.setTool("select"));
    on("pe-level", "change", (e) => {
      this.level = Number((e.target as HTMLSelectElement).value);
      this.pending = null;
      this.draw();
    });
    on("pe-grid", "change", (e) =>
      this.grid = Number((e.target as HTMLSelectElement).value));
    on("pe-del", "click", () => this.deleteSelected());
    on("pe-clear", "click", () => this.clearAll());
    on("pe-preview", "click", () => void this.previewWalls());
    on("pe-build", "click", () => void this.buildWalls());
    on("pe-roof-preview", "click", () => void this.previewRoof());
    on("pe-roof-build", "click", () => void this.buildRoof());

    this.canvas.addEventListener("pointerdown", (e) => this.pointerDown(e));
    this.canvas.addEventListener("pointermove", (e) => this.pointerMove(e));
    window.addEventListener("pointerup", (e) => this.pointerUp(e));
    this.canvas.addEventListener("wheel", (e) => this.wheel(e), { passive: false });
    this.canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    window.addEventListener("resize", () => this.resize());
    // size after first layout
    requestAnimationFrame(() => this.resize());
  }

  private populateLevels(): void {
    const sel = this.root.querySelector<HTMLSelectElement>("#pe-level")!;
    const maxLevel = Math.max(3, ...this.walls.map((w) => w.level));
    sel.innerHTML = Array.from({ length: maxLevel }, (_, i) => i + 1)
      .map((n) => `<option value="${n}">Level ${n}</option>`).join("");
    sel.value = String(this.level);
  }

  private setTool(tool: "draw" | "select"): void {
    this.tool = tool;
    this.pending = null;
    this.root.querySelector("#pe-draw")!.classList.toggle("on", tool === "draw");
    this.root.querySelector("#pe-select")!.classList.toggle("on", tool === "select");
    this.canvas.style.cursor = tool === "draw" ? "crosshair" : "default";
    this.draw();
  }

  private resize(): void {
    const w = Math.max(200, this.canvas.clientWidth);
    this.canvas.width = w;
    this.canvas.height = this.canvas.clientHeight;
    this.draw();
  }

  // ---- coordinate transforms --------------------------------------------
  private toPx(x: number, z: number): [number, number] {
    return [this.panX + x * this.scale, this.panY - z * this.scale];
  }
  private toMm(px: number, py: number): Pt {
    return { x: (px - this.panX) / this.scale, z: (this.panY - py) / this.scale };
  }
  private snap(p: Pt): Pt {
    // snap to nearest existing endpoint first, else to grid
    const tol = 12 / this.scale;
    for (const w of this.walls) {
      for (const e of [{ x: w.start_x_mm, z: w.start_z_mm },
                       { x: w.end_x_mm, z: w.end_z_mm }]) {
        if (Math.hypot(e.x - p.x, e.z - p.z) < tol) return { ...e };
      }
    }
    return {
      x: Math.round(p.x / this.grid) * this.grid,
      z: Math.round(p.z / this.grid) * this.grid,
    };
  }
  private eventPt(e: PointerEvent): Pt {
    const r = this.canvas.getBoundingClientRect();
    return this.toMm(e.clientX - r.left, e.clientY - r.top);
  }

  // ---- pointer interaction ----------------------------------------------
  private pointerDown(e: PointerEvent): void {
    if (e.button === 2 || e.button === 1) {        // pan
      this.panning = { x: e.clientX, y: e.clientY };
      return;
    }
    const p = this.snap(this.eventPt(e));
    if (this.tool === "select") {
      this.selectAt(this.eventPt(e));
      this.panning = { x: e.clientX, y: e.clientY }; // allow drag-pan in select
      return;
    }
    this.down = p;
    this.moved = false;
  }

  private pointerMove(e: PointerEvent): void {
    if (this.panning) {
      this.panX += e.clientX - this.panning.x;
      this.panY += e.clientY - this.panning.y;
      this.panning = { x: e.clientX, y: e.clientY };
      this.draw();
      return;
    }
    this.cursor = this.snap(this.eventPt(e));
    if (this.down && Math.hypot(
      this.cursor.x - this.down.x, this.cursor.z - this.down.z) > this.grid / 2)
      this.moved = true;
    if (this.tool === "draw") this.draw();
  }

  private pointerUp(e: PointerEvent): void {
    if (this.panning) { this.panning = null; return; }
    if (this.tool !== "draw" || !this.down) { this.down = null; return; }
    const end = this.snap(this.eventPt(e));
    if (this.moved) {
      this.addWall(this.down, end);
      this.pending = null;
    } else if (this.pending) {
      this.addWall(this.pending, end);
      this.pending = end;                            // chain to next
    } else {
      this.pending = end;                            // start a click-click chain
    }
    this.down = null;
    this.moved = false;
    this.draw();
  }

  private wheel(e: WheelEvent): void {
    e.preventDefault();
    const r = this.canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    const before = this.toMm(mx, my);
    this.scale *= e.deltaY < 0 ? 1.12 : 1 / 1.12;
    this.scale = Math.min(0.4, Math.max(0.004, this.scale));
    // keep the point under the cursor fixed
    this.panX = mx - before.x * this.scale;
    this.panY = my + before.z * this.scale;
    this.draw();
  }

  private addWall(a: Pt, b: Pt): void {
    if (Math.hypot(b.x - a.x, b.z - a.z) < MIN_WALL_MM) {
      this.setStatus(`Wall too short (min ${MIN_WALL_MM} mm).`);
      return;
    }
    this.walls.push(defaultWall(this.level, a, b));
    this.save();
    this.setStatus(`${this.levelWalls().length} wall(s) on level ${this.level}.`);
  }

  private selectAt(p: Pt): void {
    const tol = 10 / this.scale;
    let best: string | null = null;
    let bestD = tol;
    for (const w of this.levelWalls()) {
      const d = distToSeg(p, { x: w.start_x_mm, z: w.start_z_mm },
        { x: w.end_x_mm, z: w.end_z_mm });
      if (d < bestD) { bestD = d; best = w._id; }
    }
    this.selectedId = best;
    this.renderForm();
    this.draw();
  }

  private deleteSelected(): void {
    if (!this.selectedId) { this.setStatus("Select a wall to delete."); return; }
    this.walls = this.walls.filter((w) => w._id !== this.selectedId);
    this.selectedId = null;
    this.save();
    this.renderForm();
    this.draw();
  }

  private clearAll(): void {
    if (!this.walls.length) return;
    if (!confirm("Clear all drawn walls from the canvas?")) return;
    this.walls = [];
    this.selectedId = null;
    this.pending = null;
    this.save();
    this.renderForm();
    this.draw();
  }

  private levelWalls(): DrawnWall[] {
    return this.walls.filter((w) => w.level === this.level);
  }
  private selected(): DrawnWall | undefined {
    return this.walls.find((w) => w._id === this.selectedId);
  }

  // ---- selected-wall + openings form ------------------------------------
  private renderForm(): void {
    const w = this.selected();
    if (!w) {
      this.form.innerHTML =
        `<p class="plan-hint">No wall selected. Use <b>Select</b> and click a wall.</p>`;
      return;
    }
    const len = Math.hypot(w.end_x_mm - w.start_x_mm, w.end_z_mm - w.start_z_mm);
    this.form.innerHTML = `
      <section>
        <h2>Selected wall — ${(len / 1000).toFixed(2)} m</h2>
        <div class="form-grid">
          <label class="field"><span>Label</span>
            <input data-k="segment_label" type="text" value="${w.segment_label}"></label>
          <label class="field"><span>Height (mm)</span>
            <input data-k="wall_height_mm" type="number" value="${w.wall_height_mm}"></label>
          <label class="field"><span>Thickness (mm)</span>
            <input data-k="wall_thickness_mm" type="number" value="${w.wall_thickness_mm}"></label>
          <label class="field"><span>Stud size</span>
            <input data-k="stud_size" type="text" value="${w.stud_size}"></label>
          <label class="field"><span>Stud material</span>
            <select data-k="stud_material">${materialOptions}</select></label>
          <label class="field"><span>Stud spacing (mm)</span>
            <input data-k="stud_spacing_mm" type="number" value="${w.stud_spacing_mm}"></label>
          <label class="field"><span>Plies</span>
            <input data-k="plies" type="number" min="1" max="6" value="${w.plies}"></label>
          <label class="field"><span>Treatment</span>
            <input data-k="treatment" type="text" value="${w.treatment}"></label>
          <label class="check-field"><input data-k="exterior" type="checkbox"
            ${w.exterior ? "checked" : ""}> Exterior</label>
          <label class="check-field"><input data-k="load_bearing" type="checkbox"
            ${w.load_bearing ? "checked" : ""}> Load bearing</label>
        </div>
        <h3>Openings</h3>
        <div id="pe-openings"></div>
        <button id="pe-add-opening">+ Add opening</button>
      </section>`;
    (this.form.querySelector<HTMLSelectElement>('[data-k="stud_material"]')!)
      .value = w.stud_material;
    this.form.querySelectorAll<HTMLElement>("[data-k]").forEach((el) =>
      el.addEventListener("change", () => this.applyField(el)));
    this.form.querySelector("#pe-add-opening")!.addEventListener("click", () => {
      w.openings.push({
        opening_id: `op-${w.openings.length + 1}`, opening_type: "window",
        start_offset_mm: 600, width_mm: 1200, height_mm: 1200,
        sill_height_mm: 900, head_height_mm: null, lintel_size: "", notes: "",
      });
      this.save();
      this.renderOpenings();
      this.draw();
    });
    this.renderOpenings();
  }

  private renderOpenings(): void {
    const w = this.selected();
    const host = this.form.querySelector("#pe-openings");
    if (!w || !host) return;
    host.innerHTML = w.openings.map((o, i) => `
      <fieldset class="subform" data-i="${i}">
        <legend>${o.opening_type} ${i + 1}</legend>
        <label class="field"><span>Type</span>
          <select data-o="opening_type">
            ${["window", "door", "garage", "custom"].map((t) =>
              `<option value="${t}" ${t === o.opening_type ? "selected" : ""}>${t}</option>`).join("")}
          </select></label>
        <label class="field"><span>Offset (mm)</span>
          <input data-o="start_offset_mm" type="number" value="${o.start_offset_mm}"></label>
        <label class="field"><span>Width (mm)</span>
          <input data-o="width_mm" type="number" value="${o.width_mm}"></label>
        <label class="field"><span>Height (mm)</span>
          <input data-o="height_mm" type="number" value="${o.height_mm}"></label>
        <label class="field"><span>Sill (mm)</span>
          <input data-o="sill_height_mm" type="number" value="${o.sill_height_mm}"></label>
        <button class="table-delete" data-del="${i}">Remove</button>
      </fieldset>`).join("");
    host.querySelectorAll<HTMLElement>("[data-o]").forEach((el) =>
      el.addEventListener("change", () => this.applyOpening(el)));
    host.querySelectorAll<HTMLButtonElement>("[data-del]").forEach((btn) =>
      btn.addEventListener("click", () => {
        w.openings.splice(Number(btn.dataset.del), 1);
        this.save();
        this.renderOpenings();
        this.draw();
      }));
  }

  private applyField(el: HTMLElement): void {
    const w = this.selected();
    if (!w) return;
    const key = el.dataset.k!;
    const input = el as HTMLInputElement | HTMLSelectElement;
    const record = w as unknown as Record<string, unknown>;
    if (input.type === "checkbox") record[key] = (input as HTMLInputElement).checked;
    else if (input.type === "number") record[key] = Number(input.value);
    else record[key] = input.value;
    this.save();
  }

  private applyOpening(el: HTMLElement): void {
    const w = this.selected();
    if (!w) return;
    const fs = el.closest<HTMLElement>("[data-i]")!;
    const o = w.openings[Number(fs.dataset.i)] as unknown as Record<string, unknown>;
    const key = el.dataset.o!;
    const input = el as HTMLInputElement | HTMLSelectElement;
    o[key] = input.type === "number" ? Number(input.value) : input.value;
    this.save();
    this.draw();
  }

  // ---- backend wiring ----------------------------------------------------
  private strip(walls: DrawnWall[]): ManualWallFrameInput[] {
    return walls.map(({ _id, ...rest }) => rest);
  }

  private async previewWalls(): Promise<void> {
    if (!this.walls.length) { this.setStatus("Draw a wall first."); return; }
    try {
      const result = await previewManualWalls(this.strip(this.walls));
      this.onPreview(result);
      this.setStatus(`Preview: ${result.metadata.member_count} members, ` +
        `est. $NZ${result.metadata.estimated_cost_nzd.toFixed(2)}.`);
    } catch (e) { this.setStatus((e as Error).message); }
  }

  private async buildWalls(): Promise<void> {
    if (!this.walls.length) { this.setStatus("Draw a wall first."); return; }
    try {
      if (this.wallBatchId) {
        await deleteImportBatch(this.wallBatchId).catch(() => undefined);
      }
      const { batch_id, model } = await commitManualWalls(this.strip(this.walls));
      this.wallBatchId = batch_id;
      this.save();
      this.onModel(model);
      this.onCommitted();
      this.setStatus(`Built ${this.walls.length} wall frame(s).`);
    } catch (e) { this.setStatus((e as Error).message); }
  }

  private footprint(): { L: number; W: number; sx: number; sz: number; dir: number } {
    const ws = this.levelWalls();
    if (!ws.length) return { L: 9000, W: 7000, sx: 0, sz: 0, dir: 0 };
    const xs = ws.flatMap((w) => [w.start_x_mm, w.end_x_mm]);
    const zs = ws.flatMap((w) => [w.start_z_mm, w.end_z_mm]);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minZ = Math.min(...zs), maxZ = Math.max(...zs);
    const dx = Math.max(300, maxX - minX), dz = Math.max(300, maxZ - minZ);
    const choice = this.root.querySelector<HTMLSelectElement>("#pe-roof-dir")!.value;
    const alongX = choice === "x" || (choice === "auto" && dx >= dz);
    return alongX
      ? { L: dx, W: dz, sx: minX, sz: minZ, dir: 0 }
      : { L: dz, W: dx, sx: maxX, sz: minZ, dir: 90 };
  }

  private roofInput(): ManualRoofInput {
    const fp = this.footprint();
    const num = (id: string) =>
      Number(this.root.querySelector<HTMLInputElement>(`#${id}`)!.value);
    const id = `roof-L${this.level}`;
    return {
      input_id: id, level: this.level, roof_id: id,
      roof_label: `Roof L${this.level}`,
      style: this.root.querySelector<HTMLSelectElement>("#pe-roof-style")!
        .value as ManualRoofInput["style"],
      length_mm: fp.L, width_mm: fp.W, start_x_mm: fp.sx, start_z_mm: fp.sz,
      direction_deg: fp.dir, pitch_deg: num("pe-roof-pitch"),
      spacing_mm: num("pe-roof-spacing"), overhang_mm: num("pe-roof-overhang"),
      heel_height_mm: 100,
      top_chord_size: "140x45", top_chord_material: "SG8",
      bottom_chord_size: "90x45", bottom_chord_material: "SG8",
      web_size: "90x45", web_material: "SG8", treatment: "H1.2",
    };
  }

  private async previewRoof(): Promise<void> {
    try {
      const result = await previewRoof(this.roofInput());
      this.onPreview(result);
      this.setStatus(`Roof preview: ${result.metadata.member_count} members, ` +
        `est. $NZ${result.metadata.estimated_cost_nzd.toFixed(2)}.`);
    } catch (e) { this.setStatus((e as Error).message); }
  }

  private async buildRoof(): Promise<void> {
    try {
      if (this.roofSourceId) {
        await deleteImportBatch(this.roofSourceId).catch(() => undefined);
      }
      const { source_id, model } = await commitRoof(this.roofInput());
      this.roofSourceId = source_id;
      this.save();
      this.onModel(model);
      this.onCommitted();
      this.setStatus("Roof built over the current footprint.");
    } catch (e) { this.setStatus((e as Error).message); }
  }

  private setStatus(msg: string): void { this.status.textContent = msg; }

  // ---- canvas drawing ----------------------------------------------------
  private draw(): void {
    const { ctx, canvas } = this;
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    this.drawGrid();
    // other-level walls (faint)
    for (const wall of this.walls) {
      if (wall.level === this.level) continue;
      this.drawWall(wall, "#3a4654", 1.5);
    }
    for (const wall of this.levelWalls()) {
      this.drawWall(wall, wall._id === this.selectedId ? "#f59e0b" : "#8fd0ff",
        wall._id === this.selectedId ? 4 : 3);
      this.drawOpenings(wall);
    }
    // rubber band
    const start = this.pending ?? (this.moved ? this.down : null);
    if (this.tool === "draw" && start && this.cursor) {
      const [ax, ay] = this.toPx(start.x, start.z);
      const [bx, by] = this.toPx(this.cursor.x, this.cursor.z);
      ctx.strokeStyle = "#f59e0b";
      ctx.setLineDash([5, 4]);
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
      ctx.setLineDash([]);
      const len = Math.hypot(this.cursor.x - start.x, this.cursor.z - start.z);
      ctx.fillStyle = "#f59e0b";
      ctx.font = "11px system-ui";
      ctx.fillText(`${(len / 1000).toFixed(2)} m`, (ax + bx) / 2 + 6, (ay + by) / 2 - 6);
    }
    if (this.pending) {
      const [px, py] = this.toPx(this.pending.x, this.pending.z);
      ctx.fillStyle = "#f59e0b";
      ctx.beginPath(); ctx.arc(px, py, 4, 0, Math.PI * 2); ctx.fill();
    }
  }

  private drawGrid(): void {
    const { ctx, canvas } = this;
    const stepMm = this.gridStepMm();
    const step = stepMm * this.scale;
    if (step < 4) return;
    ctx.strokeStyle = "#1d2630";
    ctx.lineWidth = 1;
    const x0 = this.panX % step;
    for (let x = x0; x < canvas.width; x += step) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    const y0 = this.panY % step;
    for (let y = y0; y < canvas.height; y += step) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }
    // origin axes
    const [ox, oy] = this.toPx(0, 0);
    ctx.strokeStyle = "#39506a";
    ctx.beginPath(); ctx.moveTo(0, oy); ctx.lineTo(canvas.width, oy);
    ctx.moveTo(ox, 0); ctx.lineTo(ox, canvas.height); ctx.stroke();
  }

  private gridStepMm(): number {
    // show ~1 m grid, scaling to keep lines legible
    let step = 1000;
    while (step * this.scale < 18) step *= 2;
    while (step * this.scale > 90) step /= 2;
    return step;
  }

  private drawWall(w: DrawnWall, color: string, width: number): void {
    const { ctx } = this;
    const [ax, ay] = this.toPx(w.start_x_mm, w.start_z_mm);
    const [bx, by] = this.toPx(w.end_x_mm, w.end_z_mm);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    // endpoint nodes
    ctx.fillStyle = color;
    for (const [px, py] of [[ax, ay], [bx, by]]) {
      ctx.beginPath(); ctx.arc(px, py, 2.5, 0, Math.PI * 2); ctx.fill();
    }
  }

  private drawOpenings(w: DrawnWall): void {
    const { ctx } = this;
    const len = Math.hypot(w.end_x_mm - w.start_x_mm, w.end_z_mm - w.start_z_mm);
    if (len < 1) return;
    const ux = (w.end_x_mm - w.start_x_mm) / len;
    const uz = (w.end_z_mm - w.start_z_mm) / len;
    for (const o of w.openings) {
      const a = Math.min(len, o.start_offset_mm);
      const b = Math.min(len, o.start_offset_mm + o.width_mm);
      const [ax, ay] = this.toPx(w.start_x_mm + ux * a, w.start_z_mm + uz * a);
      const [bx, by] = this.toPx(w.start_x_mm + ux * b, w.start_z_mm + uz * b);
      ctx.strokeStyle = o.opening_type === "door" || o.opening_type === "garage"
        ? "#34d399" : "#fca5a5";
      ctx.lineWidth = 5;
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    }
  }

  /** Refresh level choices after a model load (keeps the editor in sync). */
  syncLevels(): void { this.populateLevels(); }
}

function distToSeg(p: Pt, a: Pt, b: Pt): number {
  const dx = b.x - a.x, dz = b.z - a.z;
  const l2 = dx * dx + dz * dz;
  if (l2 === 0) return Math.hypot(p.x - a.x, p.z - a.z);
  let t = ((p.x - a.x) * dx + (p.z - a.z) * dz) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * dx), p.z - (a.z + t * dz));
}
