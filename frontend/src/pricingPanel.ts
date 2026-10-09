import { getPricing, savePriceOverrides, StaleResponseError } from "./api";
import { escapeHtml, message, safeUrl } from "./dom";
import type { BimModel, PricingRow } from "./types";
import { addTableWorkspace } from "./tableWorkspace";

export class PricingPanel {
  private rows: PricingRow[] = [];
  private overrides: Record<string, number> = {};
  private pending = false;
  private workspaceBusy = false;
  private ready = false;
  setWorkspaceBusy(busy: boolean): void { this.workspaceBusy = busy; this.updatePending(); }
  private updatePending(): void {
    this.root.querySelectorAll<HTMLInputElement | HTMLButtonElement>(".price-override,#pricing-save").forEach(control =>
      control.disabled = this.pending || this.workspaceBusy || !this.ready);
  }
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <p class="callout">Estimating only - not supplier quote.</p>
      <p class="notice">Project overrides are USD per physical board metre for all sizes of that material. Clear an override to use size-specific catalogue estimates. Unsupported sizes remain unpriced.</p>
      <p class="notice">Catalogue prices are frozen historical estimates; the source and currency conversion dates are preserved with each priced member. Treatment/section mismatches reduce confidence. Review current supplier prices before ordering.</p>
      <button id="pricing-save" class="primary-button">Save project prices</button>
      <div id="pricing-feedback" aria-live="polite"></div>
      <div class="table-wrap"><table id="pricing-table" aria-label="Price catalogue and project overrides"></table></div>`);
    root.querySelector("#pricing-save")!.addEventListener("click", () => void this.save());
    addTableWorkspace(root, "Pricing", "pricing");
  }

  async refresh(): Promise<void> {
    this.ready = false; this.updatePending();
    try {
      const result = await getPricing();
      this.rows = result.rows;
      this.overrides = result.overrides;
      this.ready = true;
      this.render();
      this.updatePending();
    } catch (error) {
      if (error instanceof StaleResponseError) return;
      message(this.root.querySelector("#pricing-feedback")!, `Pricing unavailable: ${(error as Error).message}`);
    }
  }

  private render(): void {
    this.root.querySelector("#pricing-table")!.innerHTML = `
      <thead><tr><th scope="col">Material</th><th scope="col">Category</th><th scope="col">Default size</th>
        <th scope="col">USD / lm</th><th scope="col">Project override</th><th scope="col">Confidence</th>
        <th scope="col">Source</th><th scope="col">Date</th><th scope="col">Currency / FX</th><th scope="col">Notes</th></tr></thead>
      <tbody>${this.rows.map((row) => `<tr>
        <td>${escapeHtml(row.material)}</td><td>${escapeHtml(row.category)}</td>
        <td>${escapeHtml(row.default_size)}</td><td>${row.usd_per_linear_metre.toFixed(2)}</td>
        <td><input class="price-override" data-key="${row.key}" type="number"
          aria-label="${escapeHtml(row.material)} project price per board metre" min="0" step="0.01" value="${this.overrides[row.key] ?? ""}"
          placeholder="${row.usd_per_linear_metre.toFixed(2)}"></td>
        <td>${escapeHtml(row.confidence)}</td>
        <td><a href="${escapeHtml(safeUrl(row.source_url))}" target="_blank" rel="noopener">${escapeHtml(row.source_name)}</a></td>
        <td>${escapeHtml(row.source_date)}</td><td>${escapeHtml(row.source_currency)} → USD · ${row.fx_rate} · ${escapeHtml(row.fx_date)}</td><td>${escapeHtml(row.notes)}</td></tr>`).join("")}</tbody>`;
    this.root.querySelectorAll<HTMLInputElement>(".price-override").forEach(
      (input) => input.addEventListener("change", () => {
        const value = Number(input.value);
        if (input.value && Number.isFinite(value) && value >= 0) this.overrides[input.dataset.key!] = value;
        else delete this.overrides[input.dataset.key!];
        message(this.root.querySelector("#pricing-feedback")!, "Unsaved prices. Save to update this home's model, BOM and exports.", "warning");
      }));
  }

  private async save(): Promise<void> {
    if (this.pending || this.workspaceBusy || !this.ready) return;
    this.pending = true; this.updatePending();
    try {
      const model = await savePriceOverrides(this.overrides);
      this.onModel(model);
      message(this.root.querySelector("#pricing-feedback")!, "Project prices saved; totals and exports updated.", "success");
    } catch (error) { message(this.root.querySelector("#pricing-feedback")!, (error as Error).message); }
    finally { this.pending = false; this.updatePending(); }
  }
}
