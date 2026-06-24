import { downloadBom, getDashboardSummary, regenerateProject } from "./api";
import type { BimModel, DashboardSummary } from "./types";

export class Dashboard {
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    this.root.classList.add("hud");
    this.root.innerHTML = `
      <div class="hud-header">
        <h2>Model dashboard</h2>
        <button id="hud-toggle" class="hud-toggle"
                aria-label="Collapse dashboard" title="Collapse dashboard">–</button>
      </div>
      <div class="hud-body">
        <div id="dashboard-cards" class="summary-grid"></div>
        <div class="button-row">
          <button id="dashboard-regenerate" class="primary-button">
            Regenerate model</button>
          <button id="dashboard-bom" class="secondary-button">
            Download BOM CSV</button>
        </div>
        <p class="notice">Regeneration preserves imports and manual additions.</p>
      </div>`;
    const toggle = root.querySelector<HTMLButtonElement>("#hud-toggle")!;
    toggle.addEventListener("click", () => {
      const collapsed = this.root.classList.toggle("collapsed");
      toggle.textContent = collapsed ? "+" : "–";
      const label = collapsed ? "Expand dashboard" : "Collapse dashboard";
      toggle.setAttribute("aria-label", label);
      toggle.title = label;
    });
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
      ["Estimated cost", `NZ$${summary.estimated_material_cost_nzd
        .toLocaleString(undefined, { maximumFractionDigits: 0 })}`],
      ["Warnings", String(summary.warning_count)],
    ];
    return entries.map(([label, value]) => `
      <article class="summary-card"><span>${label}</span><strong>${value}</strong>
      </article>`).join("");
  }
}
