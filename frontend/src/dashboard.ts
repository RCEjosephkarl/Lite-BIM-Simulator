import { downloadBom, getDashboardSummary, regenerateProject } from "./api";
import type { BimModel, DashboardSummary } from "./types";

export class Dashboard {
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    this.root.insertAdjacentHTML("beforeend", `
      <div id="dashboard-cards" class="summary-grid"></div>
      <div class="button-row">
        <button id="dashboard-regenerate" class="primary-button">
          Regenerate model</button>
        <button id="dashboard-bom" class="secondary-button">
          Download BOM CSV</button>
      </div>
      <p class="notice">Regeneration preserves imports and manual additions.</p>`);
    root.querySelector("#dashboard-bom")!.addEventListener("click", downloadBom);
    root.querySelector("#dashboard-regenerate")!.addEventListener("click",
      async () => {
        const model = await regenerateProject(true, true);
        this.onModel(model);
        await this.refresh();
      });
  }

  async refresh(): Promise<void> {
    const target = this.root.querySelector("#dashboard-cards")!;
    try {
      const summary = await getDashboardSummary();
      target.innerHTML = this.cards(summary);
    } catch (error) {
      target.textContent = `Dashboard unavailable: ${(error as Error).message}`;
    }
  }

  private cards(summary: DashboardSummary): string {
    const entries: [string, string][] = [
      ["Storeys", String(summary.storeys)],
      ["Roof type", summary.roof_type],
      ["Wind", summary.wind_speed === null ? summary.wind_zone
        : `${summary.wind_zone} / ${summary.wind_speed} m/s`],
      ["Snow zone", summary.snow_zone],
      ["Total elements", summary.total_elements.toLocaleString()],
      ["Wall frame", `${summary.wall_frame_lineal_m.toFixed(1)} m`],
      ["Roof / truss", `${summary.roof_truss_lineal_m.toFixed(1)} m`],
      ["Estimated cost", `US$${summary.estimated_material_cost_usd
        .toLocaleString(undefined, { maximumFractionDigits: 0 })}`],
      ["Warnings", String(summary.warning_count)],
    ];
    return entries.map(([label, value]) => `
      <article class="summary-card"><span>${label}</span><strong>${value}</strong>
      </article>`).join("");
  }
}
