import { downloadBom, getBomJson } from "./api";
import type { BomRow } from "./types";

function clean(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]!);
}

export class BomPanel {
  private rows: BomRow[] = [];

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <div class="filter-grid">
        <input id="bom-search" placeholder="Search element, material, segment">
        <select id="bom-category"><option value="">All categories</option></select>
        <select id="bom-storey"><option value="">All storeys</option></select>
      </div>
      <button id="bom-export" class="primary-button">Export CSV</button>
      <div class="table-wrap"><table id="bom-table"></table></div>
      <p id="bom-disclaimer" class="notice"></p>`);
    root.querySelector("#bom-export")!.addEventListener("click", downloadBom);
    root.querySelectorAll("input,select").forEach((element) =>
      element.addEventListener("input", () => this.render()));
  }

  async refresh(): Promise<void> {
    const result = await getBomJson();
    this.rows = result.rows;
    this.root.querySelector("#bom-disclaimer")!.textContent = result.disclaimer;
    this.options();
    this.render();
  }

  private options(): void {
    const categories = [...new Set(this.rows.map((row) => row.category))];
    const storeys = [...new Set(this.rows.map((row) => row.storey))];
    this.root.querySelector<HTMLSelectElement>("#bom-category")!.innerHTML =
      `<option value="">All categories</option>` +
      categories.map((value) => `<option>${clean(value)}</option>`).join("");
    this.root.querySelector<HTMLSelectElement>("#bom-storey")!.innerHTML =
      `<option value="">All storeys</option>` +
      storeys.map((value) => `<option>${value}</option>`).join("");
  }

  private render(): void {
    const search = this.root.querySelector<HTMLInputElement>("#bom-search")!
      .value.toLowerCase();
    const category = this.root.querySelector<HTMLSelectElement>("#bom-category")!
      .value;
    const storey = this.root.querySelector<HTMLSelectElement>("#bom-storey")!
      .value;
    const rows = this.rows.filter((row) =>
      (!category || row.category === category) &&
      (!storey || String(row.storey) === storey) &&
      (!search || `${row.element} ${row.material} ${row.segment} ${row.size}`
        .toLowerCase().includes(search)));
    this.root.querySelector("#bom-table")!.innerHTML = `
      <thead><tr><th>Category</th><th>Element</th><th>Storey</th>
        <th>Segment</th><th>Size</th><th>Material / grade</th>
        <th>Treatment</th><th>Plies</th><th>Total m</th>
        <th>Effective m</th><th>Stock</th><th>Qty</th><th>Cost NZD</th>
      </tr></thead>
      <tbody>${rows.map((row) => `<tr>
        <td>${clean(row.category)}</td><td>${clean(row.element)}</td>
        <td>${row.storey}</td><td>${clean(row.segment || "-")}</td>
        <td>${clean(row.size)}</td><td>${clean(row.material)} / ${clean(row.grade)}</td>
        <td>${clean(row.treatment)}</td><td>${row.plies}</td>
        <td>${row.total_length_m}</td><td>${row.total_effective_length_m}</td>
        <td>${row.stock_length_m} m</td><td>${row.qty}</td>
        <td>${row.total_cost_nzd.toFixed(2)}</td></tr>`).join("")}</tbody>`;
  }
}
