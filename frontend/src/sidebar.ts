import { getWarnings, resetProject } from "./api";
import type { BimModel, SidebarSection } from "./types";

const SECTIONS: { id: SidebarSection; icon: string; label: string }[] = [
  { id: "specs", icon: "BS", label: "Building Specs" },
  { id: "draw", icon: "DR", label: "Draw Plan (walls + roof)" },
  { id: "bom", icon: "BM", label: "BOM" },
  { id: "pricing", icon: "PR", label: "Pricing" },
  { id: "imports", icon: "IM", label: "Imports / Drawing Plans" },
  { id: "wall", icon: "WF", label: "Manual Wall Frame Input" },
  { id: "truss", icon: "TR", label: "Manual Truss Input" },
  { id: "settings", icon: "ST", label: "Settings / Warnings" },
];

export class Sidebar {
  private active: SidebarSection = "specs";
  private sections = new Map<SidebarSection, HTMLElement>();
  private pinned = localStorage.getItem("timberbim.sidebarPinned") === "true";
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    this.build();
    this.setPinned(this.pinned);
    this.open(this.active);
    void this.refreshWarnings();
  }

  private build(): void {
    this.root.innerHTML = `
      <div class="sidebar-rail">
        <div class="brand-mark" aria-label="TimberBIM Lite">TB</div>
        <nav aria-label="BIM dashboard sections">
          ${SECTIONS.map((section) => `
            <button class="nav-button" data-section="${section.id}"
                    aria-label="${section.label}" title="${section.label}">
              <span class="nav-icon" aria-hidden="true">${section.icon}</span>
              <span class="nav-label">${section.label}</span>
            </button>`).join("")}
        </nav>
        <button id="sidebar-pin" class="pin-button" aria-label="Pin sidebar"
                title="Pin sidebar">
          <span class="nav-icon" aria-hidden="true">PN</span>
          <span class="nav-label">Pin sidebar</span>
        </button>
      </div>
      <div class="sidebar-content">
        <header>
          <h1>Timber<span>BIM</span> Lite</h1>
          <p>Education, early design and estimating workspace</p>
        </header>
        ${SECTIONS.map((section) => `
          <div class="sidebar-section" data-panel="${section.id}" hidden>
            <h2 class="panel-title">${section.label}</h2>
          </div>`).join("")}
      </div>`;
    this.root.querySelectorAll<HTMLElement>("[data-panel]").forEach((element) =>
      this.sections.set(element.dataset.panel as SidebarSection, element));
    this.root.querySelectorAll<HTMLButtonElement>("[data-section]").forEach(
      (button) => button.addEventListener("click", () =>
        this.open(button.dataset.section as SidebarSection)));
    this.root.querySelector("#sidebar-pin")!.addEventListener("click", () =>
      this.setPinned(!this.pinned));

    this.getSection("settings").insertAdjacentHTML("beforeend", `
      <p class="notice">Warnings combine NZS scope notes, custom spacing,
        invalid imports, AI confidence, and missing pricing metadata.</p>
      <div id="settings-warnings" class="message-list">Loading warnings...</div>
      <button id="reset-app" class="danger-button">Reset app state</button>`);
    this.getSection("settings").querySelector("#reset-app")!.addEventListener(
      "click", async () => {
        if (!confirm("Clear the project back to an empty canvas? This removes "
          + "all drawn, manual and imported elements."))
          return;
        const model = await resetProject();
        localStorage.removeItem("timberbim.manualWallDraft");
        localStorage.removeItem("timberbim.manualTrussDraft");
        localStorage.removeItem("timberbim.planEditor");
        this.onModel(model);
        await this.refreshWarnings();
      });
  }

  getSection(section: SidebarSection): HTMLElement {
    return this.sections.get(section)!;
  }

  open(section: SidebarSection): void {
    this.active = section;
    this.sections.forEach((element, id) => element.hidden = id !== section);
    this.root.querySelectorAll<HTMLElement>("[data-section]").forEach((button) =>
      button.classList.toggle("active", button.dataset.section === section));
    this.root.dataset.active = section;
  }

  private setPinned(pinned: boolean): void {
    this.pinned = pinned;
    localStorage.setItem("timberbim.sidebarPinned", String(pinned));
    document.body.classList.toggle("sidebar-pinned", pinned);
    this.root.classList.toggle("pinned", pinned);
    const button = this.root.querySelector<HTMLButtonElement>("#sidebar-pin")!;
    button.setAttribute("aria-label", pinned ? "Unpin sidebar" : "Pin sidebar");
    button.title = pinned ? "Unpin sidebar" : "Pin sidebar";
    button.querySelector(".nav-label")!.textContent =
      pinned ? "Unpin sidebar" : "Pin sidebar";
    window.dispatchEvent(new Event("resize"));
  }

  async refreshWarnings(): Promise<void> {
    const target = this.root.querySelector("#settings-warnings");
    if (!target) return;
    try {
      const result = await getWarnings();
      target.innerHTML = result.warnings.length
        ? result.warnings.map((warning) =>
          `<div class="message warning">${warning.message}</div>`).join("")
        : `<div class="message success">No model warnings.</div>`;
    } catch (error) {
      target.textContent = `Could not load warnings: ${(error as Error).message}`;
    }
  }
}
