import { MATERIAL_LEGEND } from "./colors";
import { DEFAULT_PARAMS, MATERIAL_OPTIONS } from "./types";
import type {
  BimElement, BimModel, ColorMode, ElementType, ModelParams,
} from "./types";

const SPACING_OPTIONS = [300, 400, 450, 480, 600, 900, 1200];

type StudScope = "overall" | "level" | "segment";

export interface UiCallbacks {
  onParams(patch: Partial<ModelParams>): void;
  onColorMode(mode: ColorMode): void;
  onCategory(category: string, visible: boolean): void;
  onSource(source: string): void;
  onAutoRotate(on: boolean): void;
  onExport(): void;
}

const CATEGORY_LABELS: Record<string, string> = {
  wall: "Wall framing",
  floor: "Floor framing",
  ceiling: "Ceiling framing",
  roof: "Roof framing",
  outdoor: "Porch / outdoor",
  concrete: "Concrete (non-timber)",
};

const WIND_OPTIONS: [string, string][] = [
  ["low", "Low (≤32 m/s)"],
  ["medium", "Medium (≤37 m/s)"],
  ["high", "High (≤44 m/s)"],
  ["very high", "Very High (≤50 m/s)"],
  ["extra high", "Extra High (≤55 m/s)"],
  ["speed", "By design wind speed…"],
];

const SNOW_OPTIONS: [string, string][] = [
  ["N0", "N0 — no snow load"],
  ["N1", "N1 — 0.5 kPa"],
  ["N2", "N2 — 1.0 kPa"],
  ["N3", "N3 — 1.5 kPa"],
  ["N4", "N4 — 2.0 kPa"],
  ["N5", "N5 — >2.0 kPa (SED)"],
];

export class Panel {
  private root: HTMLElement;
  private legendEl!: HTMLElement;
  private infoEl!: HTMLElement;
  private statsEl!: HTMLElement;
  private mode: ColorMode = "function";
  private model: BimModel | null = null;
  private params: ModelParams = { ...DEFAULT_PARAMS };
  private scope: StudScope = "overall";

  constructor(root: HTMLElement, private cb: UiCallbacks) {
    this.root = root;
    this.build();
  }

  private build(): void {
    this.root.innerHTML = `
      <section>
        <h2>View</h2>
        <label class="layer"><input type="checkbox" id="autorotate">
          Auto-rotate model</label>
        <div class="field">
          <label for="source-filter">Element source</label>
          <select id="source-filter"><option value="">All sources</option></select>
        </div>
      </section>

      <section>
        <h2>Storeys</h2>
        <div class="seg" id="storeys">
          ${[1, 2, 3].map((n) =>
            `<button data-n="${n}" class="${n === 1 ? "on" : ""}">${n}</button>`).join("")}
        </div>
      </section>

      <section>
        <h2>Roof style</h2>
        <div class="seg" id="roof">
          <button data-r="gable" class="on">Gable</button>
          <button data-r="hip">Hip</button>
        </div>
        <div class="field" id="gable-field">
          <label for="gable-spacing">Gable-end stud centres (mm)</label>
          <input type="number" id="gable-spacing" value="600"
                 min="300" max="1200" step="50">
        </div>
      </section>

      <section>
        <h2>Site exposure (NZS 3604 §5 / §15)</h2>
        <div class="field">
          <label for="wind">Wind zone</label>
          <select id="wind">
            ${WIND_OPTIONS.map(([v, l]) => `<option value="${v}">${l}</option>`)
              .join("")}
          </select>
        </div>
        <div class="field" id="speed-field" hidden>
          <label for="wind-speed">Design wind speed (m/s)</label>
          <input type="number" id="wind-speed" value="37" min="0" max="120" step="1">
        </div>
        <div class="field">
          <label for="snow">Snow zone</label>
          <select id="snow">
            ${SNOW_OPTIONS.map(([v, l]) => `<option value="${v}">${l}</option>`)
              .join("")}
          </select>
        </div>
        <p class="hint" id="spacing-note"></p>
        <p class="hint warn-note" id="warnings"></p>
      </section>

      <section>
        <h2>Wall stud design</h2>
        <div class="seg" id="stud-scope">
          <button data-s="overall" class="on">Overall</button>
          <button data-s="level">Per level</button>
          <button data-s="segment">Segment</button>
        </div>
        <div class="field" id="stud-level-field" hidden>
          <label for="stud-level">Level</label>
          <select id="stud-level"></select>
        </div>
        <div class="field" id="stud-segment-field" hidden>
          <label for="stud-segment">Frame segment</label>
          <select id="stud-segment"></select>
        </div>
        <div class="field">
          <label for="stud-material">Stud material</label>
          <select id="stud-material"></select>
        </div>
        <div class="field">
          <label for="stud-spacing">Stud spacing (mm)</label>
          <select id="stud-spacing"></select>
        </div>
        <div class="field" id="stud-spacing-custom-field" hidden>
          <label for="stud-spacing-custom">Custom spacing (300–1200 mm)</label>
          <input type="number" id="stud-spacing-custom" value="600"
                 min="300" max="1200" step="10">
        </div>
        <div class="field">
          <label for="wall-plies">Wall plies (1–6, blank = default)</label>
          <input type="number" id="wall-plies" min="1" max="6" step="1"
                 placeholder="1">
        </div>
        <button id="stud-clear" class="clear-override" hidden>
          Clear override for this level/segment</button>
        <p class="hint">Precedence: segment &gt; level &gt; overall &gt;
          NZS 3604 default. Estimating/design study only — material and
          spacing changes require NZS 3604 / SED verification.</p>
      </section>

      <section>
        <h2>Colour by</h2>
        <div class="seg" id="mode">
          <button data-m="function" class="on">Function</button>
          <button data-m="material">Material</button>
          <button data-m="realistic">Realistic</button>
        </div>
      </section>

      <section>
        <h2>Layers</h2>
        <div id="layers"></div>
      </section>

      <section>
        <h2>Legend</h2>
        <div id="legend"></div>
      </section>

      <section>
        <h2>Selected element</h2>
        <div id="info" class="info">Click a member in the 3D view.</div>
      </section>

      <button id="export" class="export">Export BOM CSV - timber only</button>
      <p class="stats" id="stats"></p>
      <p class="hint" id="disclaimer"></p>
    `;
    this.legendEl = this.q("#legend");
    this.infoEl = this.q("#info");
    this.statsEl = this.q("#stats");

    this.q("#autorotate").addEventListener("change", () =>
      this.cb.onAutoRotate(this.q<HTMLInputElement>("#autorotate").checked));
    this.q("#source-filter").addEventListener("change", () =>
      this.cb.onSource(this.q<HTMLSelectElement>("#source-filter").value));

    this.q("#storeys").addEventListener("click", (e) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      this.segSelect("#storeys", b);
      this.emit({ storeys: Number(b.dataset.n) });
    });

    this.q("#roof").addEventListener("click", (e) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      this.segSelect("#roof", b);
      const roof = b.dataset.r as ModelParams["roof"];
      this.q("#gable-field").hidden = roof !== "gable";
      this.emit({ roof });
    });

    this.q("#gable-spacing").addEventListener("change", () => {
      const v = this.q<HTMLInputElement>("#gable-spacing");
      const n = Math.max(300, Math.min(1200, Number(v.value) || 600));
      v.value = String(n);
      this.emit({ gable_spacing: n });
    });

    this.q("#wind").addEventListener("change", () => this.emitExposure());
    this.q("#wind-speed").addEventListener("change", () => this.emitExposure());
    this.q("#snow").addEventListener("change", () => this.emitExposure());

    this.q("#mode").addEventListener("click", (e) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      this.segSelect("#mode", b);
      this.mode = b.dataset.m as ColorMode;
      this.cb.onColorMode(this.mode);
      this.renderLegend();
    });

    this.q("#stud-scope").addEventListener("click", (e) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      this.segSelect("#stud-scope", b);
      this.scope = b.dataset.s as StudScope;
      this.refreshStudControls();
    });
    this.q("#stud-level").addEventListener("change", () =>
      this.refreshStudControls());
    this.q("#stud-segment").addEventListener("change", () =>
      this.refreshStudControls());
    this.q("#stud-material").addEventListener("change", () =>
      this.applyStudPatch());
    this.q("#stud-spacing").addEventListener("change", () => {
      const custom = this.q<HTMLSelectElement>("#stud-spacing").value === "custom";
      this.q("#stud-spacing-custom-field").hidden = !custom;
      this.applyStudPatch();
    });
    this.q("#stud-spacing-custom").addEventListener("change", () =>
      this.applyStudPatch());
    this.q("#wall-plies").addEventListener("change", () =>
      this.applyStudPatch());
    this.q("#stud-clear").addEventListener("click", () =>
      this.clearStudOverride());
    this.refreshStudControls();

    this.q("#export").addEventListener("click", () => this.cb.onExport());
  }

  /** Current override target: '' for overall, storey "1".."3", or segment id. */
  private studTarget(): string {
    if (this.scope === "level")
      return this.q<HTMLSelectElement>("#stud-level").value;
    if (this.scope === "segment")
      return this.q<HTMLSelectElement>("#stud-segment").value;
    return "";
  }

  /** Reflect the stored override for the current scope/target in the controls. */
  private refreshStudControls(): void {
    const isOverall = this.scope === "overall";
    this.q("#stud-level-field").hidden = this.scope !== "level";
    this.q("#stud-segment-field").hidden = this.scope !== "segment";
    this.q<HTMLButtonElement>("#stud-clear").hidden = isOverall;

    const matSel = this.q<HTMLSelectElement>("#stud-material");
    const blank: [string, string] = ["", isOverall ? "Default (SG8)" : "Inherit"];
    matSel.innerHTML = [blank, ...MATERIAL_OPTIONS]
      .map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
    const spSel = this.q<HTMLSelectElement>("#stud-spacing");
    spSel.innerHTML = [
      `<option value="">${isOverall ? "Default (NZS 3604)" : "Inherit"}</option>`,
      ...SPACING_OPTIONS.map((n) => `<option value="${n}">${n}</option>`),
      '<option value="custom">Custom…</option>',
    ].join("");

    const key = this.studTarget();
    const p = this.params;
    let mat: string | null = null;
    let spacing: number | null = null;
    let plies: number | null = null;
    if (isOverall) {
      mat = p.stud_material_overall;
      spacing = p.stud_spacing_overall;
      plies = p.wall_plies_overall;
    } else if (key) {
      const sfx = this.scope === "level" ? "levels" : "segments";
      mat = p[`stud_material_${sfx}`][key] ?? null;
      spacing = p[`stud_spacing_${sfx}`][key] ?? null;
      plies = p[`wall_plies_${sfx}`][key] ?? null;
    }
    matSel.value = mat ?? "";
    const custom = spacing !== null && !SPACING_OPTIONS.includes(spacing);
    spSel.value = spacing === null ? "" : custom ? "custom" : String(spacing);
    this.q("#stud-spacing-custom-field").hidden = !custom;
    if (custom)
      this.q<HTMLInputElement>("#stud-spacing-custom").value = String(spacing);
    this.q<HTMLInputElement>("#wall-plies").value =
      plies === null ? "" : String(plies);
  }

  /** Read the three controls and store them for the current scope/target. */
  private applyStudPatch(): void {
    const mat = this.q<HTMLSelectElement>("#stud-material").value || null;
    const spSel = this.q<HTMLSelectElement>("#stud-spacing").value;
    let spacing: number | null = null;
    if (spSel === "custom") {
      const v = this.q<HTMLInputElement>("#stud-spacing-custom");
      const n = Math.max(300, Math.min(1200, Number(v.value) || 600));
      v.value = String(n);
      spacing = n;
    } else if (spSel) {
      spacing = Number(spSel);
    }
    const pliesEl = this.q<HTMLInputElement>("#wall-plies");
    let plies: number | null = null;
    if (pliesEl.value !== "") {
      plies = Math.max(1, Math.min(6, Math.round(Number(pliesEl.value) || 1)));
      pliesEl.value = String(plies);
    }

    if (this.scope === "overall") {
      this.emit({
        stud_material_overall: mat,
        stud_spacing_overall: spacing,
        wall_plies_overall: plies,
      });
      return;
    }
    const key = this.studTarget();
    if (!key) return;
    const sfx = this.scope === "level" ? "levels" : "segments";
    const upd = <T extends string | number>(
      d: Record<string, T>, v: T | null): Record<string, T> => {
      const out = { ...d };
      if (v === null) delete out[key];
      else out[key] = v;
      return out;
    };
    this.emit({
      [`stud_material_${sfx}`]: upd(this.params[`stud_material_${sfx}`], mat),
      [`stud_spacing_${sfx}`]: upd(this.params[`stud_spacing_${sfx}`], spacing),
      [`wall_plies_${sfx}`]: upd(this.params[`wall_plies_${sfx}`], plies),
    } as Partial<ModelParams>);
  }

  /** Remove all three overrides for the selected level/segment. */
  private clearStudOverride(): void {
    const key = this.studTarget();
    if (this.scope === "overall" || !key) return;
    const sfx = this.scope === "level" ? "levels" : "segments";
    const drop = <T,>(d: Record<string, T>): Record<string, T> => {
      const out = { ...d };
      delete out[key];
      return out;
    };
    this.emit({
      [`stud_material_${sfx}`]: drop(this.params[`stud_material_${sfx}`]),
      [`stud_spacing_${sfx}`]: drop(this.params[`stud_spacing_${sfx}`]),
      [`wall_plies_${sfx}`]: drop(this.params[`wall_plies_${sfx}`]),
    } as Partial<ModelParams>);
    this.refreshStudControls();
  }

  /** Rebuild the level + segment dropdowns from the loaded model. */
  private populateStudTargets(): void {
    if (!this.model) return;
    const m = this.model.meta;
    const lvl = this.q<HTMLSelectElement>("#stud-level");
    const keepLvl = lvl.value;
    lvl.innerHTML = Array.from({ length: m.storeys }, (_, i) => i + 1)
      .map((n) => `<option value="${n}">Level ${n}</option>`).join("");
    if ([...lvl.options].some((o) => o.value === keepLvl)) lvl.value = keepLvl;

    const seg = this.q<HTMLSelectElement>("#stud-segment");
    const keepSeg = seg.value;
    seg.innerHTML = m.frame_segments
      .map((s) => `<option value="${s.segment_id}">` +
        `${s.label} — ${(s.length_mm / 1000).toFixed(2)} m</option>`)
      .join("");
    if ([...seg.options].some((o) => o.value === keepSeg)) seg.value = keepSeg;
    this.refreshStudControls();
  }

  /** Reflect externally-set params (defaults / URL) in the controls. */
  syncParams(p: ModelParams): void {
    this.params = { ...p };
    this.segSelect("#storeys", this.q(`#storeys button[data-n="${p.storeys}"]`));
    this.segSelect("#roof", this.q(`#roof button[data-r="${p.roof}"]`));
    this.q("#gable-field").hidden = p.roof !== "gable";
    this.q<HTMLInputElement>("#gable-spacing").value = String(p.gable_spacing);
    const wind = this.q<HTMLSelectElement>("#wind");
    if (p.wind_speed !== null) {
      wind.value = "speed";
      this.q<HTMLInputElement>("#wind-speed").value = String(p.wind_speed);
      this.q("#speed-field").hidden = false;
    } else {
      wind.value = p.wind_zone;
      this.q("#speed-field").hidden = true;
    }
    this.q<HTMLSelectElement>("#snow").value = p.snow_zone;
    this.refreshStudControls();
  }

  private emitExposure(): void {
    const zone = this.q<HTMLSelectElement>("#wind").value;
    const bySpeed = zone === "speed";
    this.q("#speed-field").hidden = !bySpeed;
    const speed = Number(this.q<HTMLInputElement>("#wind-speed").value);
    this.emit({
      wind_zone: bySpeed ? "medium" : zone,
      wind_speed: bySpeed && Number.isFinite(speed) ? speed : null,
      snow_zone: this.q<HTMLSelectElement>("#snow").value,
    });
  }

  /** Merge a patch into the tracked params and notify the app. */
  private emit(patch: Partial<ModelParams>): void {
    this.params = { ...this.params, ...patch };
    this.cb.onParams(patch);
  }

  private q<T extends HTMLElement = HTMLElement>(sel: string): T {
    return this.root.querySelector(sel) as T;
  }

  private segSelect(group: string, btn: HTMLElement): void {
    this.q(group).querySelectorAll("button").forEach((b) =>
      b.classList.toggle("on", b === btn));
  }

  setModel(model: BimModel): void {
    this.model = model;
    this.renderLayers();
    this.renderLegend();
    this.showElement(null, null);
    this.populateStudTargets();

    const timber = model.elements.filter((el) => {
      const t = model.types.find((t) => t.code === el.type_code);
      return t && t.category !== "concrete";
    });
    const totalLm = timber.reduce((s, el) => s + el.length_mm, 0) / 1000;
    const cost = model.meta.cost_summary?.grand_total_nzd;
    this.statsEl.textContent =
      `${timber.length} timber members · ${totalLm.toFixed(0)} lineal metres` +
      (cost ? ` · est. NZ$${cost.toLocaleString("en-NZ", {
        maximumFractionDigits: 0 })} materials` : "");

    const m = model.meta;
    const studs = m.stud_spacing_mm
      .map((s, i) => `L${i + 1} @ ${s}`)
      .join(", ");
    const wind = m.wind_speed !== null
      ? `${m.wind_zone} (${m.wind_speed} m/s)` : m.wind_zone;
    this.q("#spacing-note").textContent =
      `Studs ${studs} crs — wind: ${wind} · ` +
      `Rafters @ ${m.rafter_spacing_mm} crs — snow: ${m.snow_zone}`;
    this.q("#warnings").innerHTML =
      m.warnings.map((w) => `Warning: ${w}`).join("<br>");
    this.q("#disclaimer").textContent = m.disclaimer;
    const source = this.q<HTMLSelectElement>("#source-filter");
    const selected = source.value;
    const sources = [...new Set(model.elements.map((element) => element.source))];
    source.innerHTML = `<option value="">All sources</option>` +
      sources.map((value) => `<option value="${value}">${value}</option>`).join("");
    if (sources.includes(selected as BimElement["source"])) source.value = selected;
  }

  private renderLayers(): void {
    if (!this.model) return;
    const cats = [...new Set(this.model.types.map((t) => t.category))];
    const el = this.q("#layers");
    el.innerHTML = cats.map((c) => `
      <label class="layer"><input type="checkbox" checked data-c="${c}">
        ${CATEGORY_LABELS[c] ?? c}</label>`).join("");
    el.querySelectorAll("input").forEach((input) =>
      input.addEventListener("change", () =>
        this.cb.onCategory(input.dataset.c!, input.checked)));
  }

  private renderLegend(): void {
    if (!this.model) return;
    if (this.mode === "material") {
      this.legendEl.innerHTML = MATERIAL_LEGEND.map((m) => `
        <div class="key"><i style="background:${m.hex}"></i>${m.label}</div>`).join("");
      return;
    }
    const counts = new Map<string, number>();
    for (const el of this.model.elements)
      counts.set(el.type_code, (counts.get(el.type_code) ?? 0) + 1);
    this.legendEl.innerHTML = this.model.types
      .filter((t) => counts.get(t.code))
      .map((t) => `
        <div class="key"><i style="background:${t.color_hex}"></i>
          ${t.name}<b>${counts.get(t.code)}</b></div>`).join("");
  }

  showElement(el: BimElement | null, type: ElementType | null): void {
    if (!el || !type) {
      this.infoEl.innerHTML = "Click a member in the 3D view.";
      return;
    }
    const price = el.unit_price_nzd_per_lm;
    const estCost = price !== null
      ? (el.length_mm / 1000) * el.plies * price : null;
    const rows: [string, string][] = [
      ["Function", type.name],
      ["Category", CATEGORY_LABELS[type.category] ?? type.category],
      ["Size", el.plies > 1 && !el.size.includes("/")
        ? `${el.plies}/${el.size}` : el.size],
      ["Material", el.material],
      ["Grade", el.grade],
      ["Treatment", el.treatment],
      ["Plies", String(el.plies)],
      ["Stud spacing", el.stud_spacing_mm !== null
        ? `${el.stud_spacing_mm} mm crs` : "—"],
      ["Segment", el.segment_id
        ? `${el.segment_id} · ${el.segment_label}` : "—"],
      ["Truss", el.truss_id ? `${el.truss_id} · ${el.truss_label}` : "—"],
      ["Source", `${el.source}${el.source_id ? ` · ${el.source_id}` : ""}`],
      ["Editable", el.editable ? "Yes" : "No"],
      ["Confidence", el.confidence === null ? "—" : el.confidence.toFixed(2)],
      ["Length", `${(el.length_mm / 1000).toFixed(2)} m`],
      ["Storey", String(el.storey)],
      ["Unit price", price !== null ? `NZ$${price.toFixed(2)}/lm` : "—"],
      ["Est. cost", estCost !== null ? `NZ$${estCost.toFixed(2)}` : "—"],
      ["NZS 3604:2011", type.nzs_ref],
    ];
    const source = el.price_confidence
      ? `<div class="hint">Price: ${el.price_confidence} confidence · ` +
        `<a href="${el.price_source_url}" target="_blank" rel="noopener">` +
        `${el.price_source_name}</a> — estimating only</div>`
      : "";
    this.infoEl.innerHTML =
      rows.map(([k, v]) => `<div class="row"><span>${k}</span><b>${v}</b></div>`)
        .join("") +
      source +
      (el.warnings?.length
        ? `<div class="warn">${el.warnings.join("<br>")}</div>` : "") +
      (el.note ? `<div class="warn">${el.note}</div>` : "");
  }
}
