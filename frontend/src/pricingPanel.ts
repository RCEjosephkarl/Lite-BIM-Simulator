import { getPricing } from "./api";
import type { PricingRow } from "./types";

const STORAGE_KEY = "timberbim.priceOverrides";

export class PricingPanel {
  private rows: PricingRow[] = [];
  private overrides: Record<string, number> = JSON.parse(
    localStorage.getItem(STORAGE_KEY) || "{}");

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <p class="callout">Estimating only - not supplier quote.</p>
      <div class="table-wrap"><table id="pricing-table"></table></div>`);
  }

  async refresh(): Promise<void> {
    const result = await getPricing();
    this.rows = result.rows;
    this.render();
  }

  private render(): void {
    this.root.querySelector("#pricing-table")!.innerHTML = `
      <thead><tr><th>Material</th><th>Category</th><th>Default size</th>
        <th>USD / lm</th><th>Session override</th><th>Confidence</th>
        <th>Source</th><th>Date</th><th>Notes</th></tr></thead>
      <tbody>${this.rows.map((row) => `<tr>
        <td>${row.material}</td><td>${row.category}</td>
        <td>${row.default_size}</td><td>${row.usd_per_linear_metre.toFixed(2)}</td>
        <td><input class="price-override" data-key="${row.key}" type="number"
          min="0" step="0.01" value="${this.overrides[row.key] ?? ""}"
          placeholder="${row.usd_per_linear_metre.toFixed(2)}"></td>
        <td>${row.confidence}</td>
        <td><a href="${row.source_url}" target="_blank" rel="noopener">${row.source_name}</a></td>
        <td>${row.source_date}</td><td>${row.notes}</td></tr>`).join("")}</tbody>`;
    this.root.querySelectorAll<HTMLInputElement>(".price-override").forEach(
      (input) => input.addEventListener("change", () => {
        const value = Number(input.value);
        if (input.value && Number.isFinite(value)) this.overrides[input.dataset.key!] = value;
        else delete this.overrides[input.dataset.key!];
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this.overrides));
      }));
  }
}
