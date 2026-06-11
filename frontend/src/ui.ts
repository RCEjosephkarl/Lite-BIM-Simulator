import { MATERIAL_LEGEND } from "./colors";
import type {
  BimElement, BimModel, ColorMode, ElementType, ModelParams,
} from "./types";

export interface UiCallbacks {
  onParams(patch: Partial<ModelParams>): void;
  onColorMode(mode: ColorMode): void;
  onCategory(category: string, visible: boolean): void;
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

  constructor(root: HTMLElement, private cb: UiCallbacks) {
    this.root = root;
    this.build();
  }

  private build(): void {
    this.root.innerHTML = `
      <h1>Timber<span>BIM</span> Lite</h1>
      <p class="sub">Light timber-framed residential · NZS 3604:2011</p>

      <section>
        <h2>View</h2>
        <label class="layer"><input type="checkbox" id="autorotate">
          Auto-rotate model</label>
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

      <button id="export" class="export">⬇ Export BOM (CSV) — timber only</button>
      <p class="stats" id="stats"></p>
      <p class="hint" id="disclaimer"></p>
    `;
    this.legendEl = this.q("#legend");
    this.infoEl = this.q("#info");
    this.statsEl = this.q("#stats");

    this.q("#autorotate").addEventListener("change", () =>
      this.cb.onAutoRotate(this.q<HTMLInputElement>("#autorotate").checked));

    this.q("#storeys").addEventListener("click", (e) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      this.segSelect("#storeys", b);
      this.cb.onParams({ storeys: Number(b.dataset.n) });
    });

    this.q("#roof").addEventListener("click", (e) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      this.segSelect("#roof", b);
      const roof = b.dataset.r as ModelParams["roof"];
      this.q("#gable-field").hidden = roof !== "gable";
      this.cb.onParams({ roof });
    });

    this.q("#gable-spacing").addEventListener("change", () => {
      const v = this.q<HTMLInputElement>("#gable-spacing");
      const n = Math.max(300, Math.min(1200, Number(v.value) || 600));
      v.value = String(n);
      this.cb.onParams({ gable_spacing: n });
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

    this.q("#export").addEventListener("click", () => this.cb.onExport());
  }

  /** Reflect externally-set params (defaults / URL) in the controls. */
  syncParams(p: ModelParams): void {
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
  }

  private emitExposure(): void {
    const zone = this.q<HTMLSelectElement>("#wind").value;
    const bySpeed = zone === "speed";
    this.q("#speed-field").hidden = !bySpeed;
    const speed = Number(this.q<HTMLInputElement>("#wind-speed").value);
    this.cb.onParams({
      wind_zone: bySpeed ? "medium" : zone,
      wind_speed: bySpeed && Number.isFinite(speed) ? speed : null,
      snow_zone: this.q<HTMLSelectElement>("#snow").value,
    });
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

    const timber = model.elements.filter((el) => {
      const t = model.types.find((t) => t.code === el.type_code);
      return t && t.category !== "concrete";
    });
    const totalLm = timber.reduce((s, el) => s + el.length_mm, 0) / 1000;
    this.statsEl.textContent =
      `${timber.length} timber members · ${totalLm.toFixed(0)} lineal metres`;

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
      m.warnings.map((w) => `⚠ ${w}`).join("<br>");
    this.q("#disclaimer").textContent = m.disclaimer;
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
    const rows: [string, string][] = [
      ["Function", type.name],
      ["Category", CATEGORY_LABELS[type.category] ?? type.category],
      ["Size", el.size],
      ["Grade", el.grade],
      ["Treatment", el.treatment],
      ["Length", `${(el.length_mm / 1000).toFixed(2)} m`],
      ["Storey", String(el.storey)],
      ["NZS 3604:2011", type.nzs_ref],
    ];
    this.infoEl.innerHTML =
      rows.map(([k, v]) => `<div class="row"><span>${k}</span><b>${v}</b></div>`)
        .join("") +
      (el.note ? `<div class="warn">⚠ ${el.note}</div>` : "");
  }
}
