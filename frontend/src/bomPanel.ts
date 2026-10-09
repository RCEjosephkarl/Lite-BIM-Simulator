import { downloadBom, getBomJson, StaleResponseError, currentProjectId, currentProjectRevision } from "./api";
import { escapeHtml } from "./dom";
import { addTableWorkspace } from "./tableWorkspace";
import type { BomRow, BomScope } from "./types";

const money = (value: number | null): string => value === null ? "Unpriced" : value.toFixed(2);
const columns: { key: string; title: string; value: (row: BomRow) => unknown; extra?: boolean }[] = [
  { key: "element", title: "Element", value: r => r.element },
  { key: "category", title: "Category", value: r => r.category, extra: true },
  { key: "storey", title: "Level", value: r => r.storey },
  { key: "segment", title: "Wall", value: r => r.segment || "—" },
  { key: "size", title: "Assembly size", value: r => r.size },
  { key: "material", title: "Material / grade", value: r => `${r.material} / ${r.grade}` },
  { key: "treatment", title: "Treatment", value: r => r.treatment },
  { key: "plies", title: "Assembly × section plies", value: r => `${r.plies} × ${r.section_plies}` },
  { key: "qty", title: "Assembly cuts", value: r => r.qty },
  { key: "physical_qty", title: "Boards", value: r => r.physical_qty },
  { key: "cut_board_m", title: "Cut board m", value: r => r.cut_board_m },
  { key: "stock_length", title: "Stock blank m", value: r => r.stock_length_m },
  { key: "stock_board_m", title: "Stock board m", value: r => r.stock_board_m },
  { key: "cost", title: "Cut USD", value: r => money(r.total_cost_usd) },
  { key: "stock_cost", title: "Stock USD", value: r => money(r.stock_cost_usd) },
  { key: "confidence", title: "Price confidence", value: r => r.price_confidence || "Unknown" },
  { key: "notes", title: "Cut / stock notes", value: r => r.notes || "—" },
  { key: "source", title: "Price source", value: r => r.price_source_name || "Unknown", extra: true },
  { key: "date", title: "Source date", value: r => r.price_source_date || "Unknown", extra: true },
  { key: "fx", title: "Currency / FX", value: r => `${r.price_source_currency || 'Unknown'} → ${r.price_currency} · ${r.price_fx_rate ?? 'unknown rate'} · ${r.price_fx_date || 'no FX date'}`, extra: true },
  { key: "pricing_notes", title: "Pricing assumptions", value: r => r.pricing_notes || "Legacy price provenance unknown", extra: true },
];

export class BomPanel {
  private rows: BomRow[] = [];
  private scope:BomScope|null=null;
  private anchor:number|undefined;
  private context="";
  private request=0;
  onLocate:(ids:number[])=>void=()=>{};

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <p class="notice">Assembly cuts share one physical identity across connected truss segments. Boards = cuts × assembly plies × section plies. Stock uses one blank per board rounded up to 300 mm; offcut reuse is excluded.</p>
      <p id="bom-scope" role="status">Whole home</p>
      <button id="bom-clear-scope" hidden>Show whole-home BOM</button>
      <div class="filter-grid">
        <input id="bom-search" aria-label="Search BOM" placeholder="Search element, material, wall, section">
        <select id="bom-category" aria-label="BOM category"><option value="">All categories</option></select>
        <select id="bom-storey" aria-label="BOM level"><option value="">All levels</option></select>
        <select id="bom-price" aria-label="Price coverage"><option value="">All prices</option><option value="unpriced">Unpriced</option><option value="priced">Priced</option></select>
        <select id="bom-sort" aria-label="Sort BOM"><option value="element">Sort: element</option><option value="qty">Sort: boards ↓</option><option value="stock">Sort: stock length ↓</option><option value="cost">Sort: cut cost ↓</option><option value="material">Sort: material</option></select>
      </div>
      <details><summary>Choose columns</summary><div class="bom-columns">${columns.map(column => `<label><input type="checkbox" data-bom-column="${column.key}" ${column.extra ? "" : "checked"}> ${column.title}</label>`).join("")}</div></details>
      <button id="bom-export" class="primary-button">Export whole-home CSV</button>
      <p id="bom-summary" role="status"></p>
      <div class="table-wrap"><table id="bom-table" aria-label="Bill of materials"></table></div>
      <p id="bom-disclaimer" class="notice"></p>`);
    root.querySelector("#bom-export")!.addEventListener("click", downloadBom);
    root.querySelector("#bom-clear-scope")!.addEventListener("click",()=>{void this.showAssembly();});
    root.querySelectorAll("input,select").forEach(element => element.addEventListener("input", () => this.render()));
    addTableWorkspace(root, "BOM", "bom");
  }

  async refresh(): Promise<void> {
    this.syncContext();
    const ticket=++this.request;
    this.rows=[];this.render();
    this.root.querySelector("#bom-summary")!.textContent="Loading BOM…";
    try {
      const result = await getBomJson(this.anchor);
      if(ticket!==this.request)return;
      this.rows = result.rows;
      this.scope=result.scope;
      this.root.querySelector("#bom-scope")!.textContent=this.scope?
        `Saved ${this.scope.kind}: ${this.scope.label} · ${this.scope.assembly_id} · level ${this.scope.storey} · ${this.scope.source} / ${this.scope.source_id}. Includes the complete assembly, regardless of model view filters.`:"Whole home";
      this.root.querySelector<HTMLButtonElement>("#bom-clear-scope")!.hidden=!this.scope;
      this.root.querySelector("#bom-disclaimer")!.textContent = result.disclaimer;
      this.options();
      this.render();
    } catch (error) {
      if (error instanceof StaleResponseError||ticket!==this.request) return;
      this.rows = [];
      this.root.querySelector("#bom-scope")!.textContent=this.anchor===undefined?"Whole-home BOM unavailable":"Saved assembly BOM unavailable. Clear the scope to return to the whole home.";
      this.root.querySelector("#bom-table")!.replaceChildren();
      this.root.querySelector("#bom-summary")!.textContent = `BOM unavailable: ${(error as Error).message}`;
      this.root.querySelector<HTMLButtonElement>("#bom-clear-scope")!.hidden=this.anchor===undefined;
    }
  }

  syncContext():void {
    const next=`${currentProjectId()}:${currentProjectRevision()}`;
    if(this.context===next)return;
    this.context=next;this.request++;this.anchor=undefined;this.scope=null;this.rows=[];
    this.root.querySelector("#bom-scope")!.textContent="Whole home";
    this.root.querySelector<HTMLButtonElement>("#bom-clear-scope")!.hidden=true;
    this.render();
  }

  async showAssembly(memberId?:number):Promise<void> {
    this.syncContext();this.anchor=memberId;
    this.root.querySelector("#bom-scope")!.textContent=memberId===undefined?"Whole home":"Loading saved assembly…";
    for(const id of ["bom-search","bom-category","bom-storey","bom-price"])
      this.root.querySelector<HTMLInputElement|HTMLSelectElement>(`#${id}`)!.value="";
    await this.refresh();
  }

  private options(): void {
    for (const [id, title, values] of [
      ["bom-category", "All categories", [...new Set(this.rows.map(row => row.category))]],
      ["bom-storey", "All levels", [...new Set(this.rows.map(row => String(row.storey)))]],
    ] as const) {
      const select = this.root.querySelector<HTMLSelectElement>(`#${id}`)!;
      const selected = select.value;
      select.innerHTML = `<option value="">${title}</option>` + values.map(value => `<option>${escapeHtml(value)}</option>`).join("");
      select.value = values.includes(selected) ? selected : "";
    }
  }

  private render(): void {
    const value = (id: string) => this.root.querySelector<HTMLInputElement | HTMLSelectElement>(`#${id}`)!.value;
    const search = value("bom-search").toLowerCase(), category = value("bom-category"), storey = value("bom-storey"), price = value("bom-price");
    const rows = this.rows.filter(row => (!category || row.category === category)
      && (!storey || String(row.storey) === storey)
      && (!price || (price === "unpriced" ? !row.estimate_complete : row.estimate_complete))
      && (!search || `${row.element} ${row.material} ${row.segment} ${row.size}`.toLowerCase().includes(search)));
    const sort = value("bom-sort");
    rows.sort((a, b) => sort === "qty" ? b.physical_qty-a.physical_qty : sort === "stock" ? b.stock_length_m-a.stock_length_m
      : sort === "cost" ? (b.total_cost_usd ?? -1)-(a.total_cost_usd ?? -1)
      : (sort === "material" ? a.material.localeCompare(b.material) : a.element.localeCompare(b.element)));
    const shown = new Set(Array.from(this.root.querySelectorAll<HTMLInputElement>("[data-bom-column]:checked"), input => input.dataset.bomColumn));
    const visible = columns.filter(column => shown.has(column.key));
    const sum = (get: (row: BomRow) => number) => rows.reduce((total, row) => total+get(row), 0);
    const unpriced = sum(row => row.estimate_complete ? 0 : row.physical_qty);
    const unknown = sum(row => row.cut_identity_status === "legacy_unknown" ? row.qty : 0);
    this.root.querySelector("#bom-summary")!.textContent = `${rows.length} of ${this.rows.length} rows · ${sum(r => r.physical_qty)} boards · ${unpriced} unpriced boards · priced cut subtotal US$${sum(r => r.total_cost_usd ?? 0).toFixed(2)} · priced stock subtotal US$${sum(r => r.stock_cost_usd ?? 0).toFixed(2)}` + (unknown ? ` · ${unknown} legacy cut identities unknown` : "");
    this.root.querySelector("#bom-table")!.innerHTML = `
      <thead><tr><th scope="col">Model</th>${visible.map(column => `<th scope="col">${column.title}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row,index) => `<tr class="${row.estimate_complete ? "" : "unpriced"}"><td><button data-bom-locate="${index}" aria-label="Locate ${escapeHtml(row.element)} row ${index+1} in model">Locate in model</button></td>${visible.map(column => `<td>${escapeHtml(String(column.value(row)))}</td>`).join("")}</tr>`).join("")}</tbody>`;
    this.root.querySelectorAll<HTMLButtonElement>("[data-bom-locate]").forEach(button=>button.onclick=()=>{
      const dialog=this.root.querySelector<HTMLDialogElement>("dialog[open]");dialog?.close("navigate");
      this.onLocate(rows[Number(button.dataset.bomLocate)].member_ids);
    });
  }
}
