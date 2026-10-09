import { createProject, currentProjectId, currentProjectRevision, fetchModel, getProjects, getRevisions, getWarnings, regenerateProject, resetProject, restoreRevision, setProjectContext, StaleResponseError } from "./api";
import { escapeHtml, message, storage } from "./dom";
import type { BimModel, SidebarSection } from "./types";

const SECTIONS: { id: SidebarSection; icon: string; label: string }[] = [
  { id: "specs", icon: "BS", label: "Building Specs" },
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
  private pinned = storage.getItem("timberbim.sidebarPinned") === "true";
  private pending = false;
  private workspaceBusy = false;
  setWorkspaceBusy(busy: boolean): void { this.workspaceBusy = busy; this.updatePending(); }
  private updatePending(): void {
    this.getSection("settings").querySelectorAll<HTMLInputElement | HTMLButtonElement | HTMLSelectElement>("button,select,input").forEach(control =>
      control.disabled = this.pending || this.workspaceBusy);
  }
  onModel: (model: BimModel) => void = () => {};
  onContextChange: () => void = () => {};
  onWarningSelect: (id: number) => void = () => {};
  onPanelOpen: () => void = () => {};

  constructor(private root: HTMLElement) {
    const section = new URLSearchParams(location.search).get("section");
    if (SECTIONS.some(item => item.id === section)) this.active = section as SidebarSection;
    this.build();
    this.setPinned(this.pinned);
    this.open(this.active,Boolean(section));
    void this.refreshWarnings();
  }

  private build(): void {
    this.root.innerHTML = `
      <div class="sidebar-rail">
        <div class="brand-mark" aria-label="TimberBIM Lite">TB</div>
        <nav aria-label="Workspace sections">
          ${SECTIONS.map((section) => `
            <button class="nav-button" data-section="${section.id}"
                    aria-label="${section.label}" title="${section.label}" aria-controls="panel-${section.id}" aria-expanded="false">
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
        <button id="mobile-panel-close" class="secondary-button">Close panel</button>
        <header>
          <h1>Timber<span>BIM</span> Lite</h1>
          <p>Education, early design and estimating workspace</p>
        </header>
        ${SECTIONS.map((section) => `
          <div class="sidebar-section" id="panel-${section.id}" role="region" aria-label="${section.label}" data-panel="${section.id}" hidden>
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
    this.root.querySelector("#mobile-panel-close")!.addEventListener("click",()=>{
      this.setPinned(false);this.root.querySelector<HTMLButtonElement>(`[data-section="${this.active}"]`)!.focus();
    });
    matchMedia("(max-width: 600px)").addEventListener("change",()=>this.syncNavigation());
    document.addEventListener("keydown",event=>{
      if(event.key==="Escape"&&!document.querySelector("dialog[open]")&&matchMedia("(max-width: 600px)").matches&&(this.pinned||this.root.classList.contains("mobile-open"))){
        this.setPinned(false);this.root.querySelector<HTMLButtonElement>(`[data-section="${this.active}"]`)!.focus();
      }
    });

    this.getSection("settings").insertAdjacentHTML("beforeend", `
      <label class="field"><span>Saved home</span><select id="project-select" aria-label="Saved home"></select></label>
      <div id="project-status" class="notice"></div>
      <label class="field"><span>New home name</span><input id="project-name" value="New home" maxlength="160"></label>
      <label class="field"><span>Starting geometry</span><select id="project-mode"><option value="custom">Empty custom home</option><option value="sample">Sample home</option></select></label>
      <button id="project-create" class="primary-button">Create home</button>
      <label class="field"><span>Restore prior revision</span><select id="project-revision" aria-label="Restore prior revision"></select></label>
      <button id="project-restore" class="secondary-button">Restore selected revision</button>
      <div id="project-feedback" class="message-list" aria-live="polite"></div>
      <p class="notice">Warnings combine NZS scope notes, custom spacing,
        invalid imports, and missing pricing metadata.</p>
      <div id="settings-warnings" class="message-list">Loading warnings...</div>
      <div id="rule-review" class="message-list"></div>
      <button id="regenerate-model" class="primary-button">Regenerate model</button>
      <p class="notice">Regeneration preserves imports and manual additions.</p>
      <button id="reset-app" class="danger-button">Reset app state</button>`);
    this.getSection("settings").querySelector("#regenerate-model")!
      .addEventListener("click", async () => {
        await this.command(() => regenerateProject(true, true));
      });
    this.getSection("settings").querySelector("#reset-app")!.addEventListener(
      "click", async () => {
        if (!confirm("Clear all imported/manual elements and restore the sample model?"))
          return;
        await this.command(() => resetProject());
      });
    this.root.querySelector("#project-select")!.addEventListener("change", async () => {
      const previous = currentProjectId();
      const previousRevision = currentProjectRevision();
      const id = this.root.querySelector<HTMLSelectElement>("#project-select")!.value;
      this.onContextChange();
      setProjectContext(id);
      await this.command(async () => {
        try { return await fetchModel(); }
        catch (error) { setProjectContext(previous, previousRevision); throw error; }
      });
    });
    this.root.querySelector("#project-create")!.addEventListener("click", () => void this.command(() =>
      createProject(this.root.querySelector<HTMLInputElement>("#project-name")!.value,
        this.root.querySelector<HTMLSelectElement>("#project-mode")!.value as "sample" | "custom")));
    this.root.querySelector("#project-restore")!.addEventListener("click", () => {
      const value = this.root.querySelector<HTMLSelectElement>("#project-revision")!.value;
      if (!value || !confirm(`Restore this home to revision ${value}? Its current geometry and definitions will be saved as another revision.`)) return;
      void this.command(() => restoreRevision(Number(value)));
    });
  }

  private async command(action: () => Promise<BimModel>): Promise<void> {
    const target = this.root.querySelector("#project-feedback")!;
    this.pending = true; this.updatePending();
    try {
      const model = await action();
      this.onModel(model);
      message(target, `Opened ${model.meta.project.name} · revision ${model.meta.project.revision}`, "success");
      await this.refreshWarnings();
    } catch (error) { message(target, (error as Error).message); }
    finally { this.pending = false; this.updatePending(); }
  }

  async refreshProjects(model: BimModel): Promise<void> {
    try {
      const [homes, history] = await Promise.all([getProjects(), getRevisions()]);
      this.root.querySelector("#project-select")!.innerHTML = homes.projects.map(home =>
        `<option value="${escapeHtml(home.project_id)}" ${home.project_id === currentProjectId() ? "selected" : ""} ${home.unavailable ? "disabled" : ""}>${escapeHtml(home.name)}</option>`).join("");
      this.root.querySelector("#project-status")!.textContent =
        `${model.meta.project.geometry_mode} geometry · revision ${model.meta.project.revision}`;
      this.root.querySelector("#project-revision")!.innerHTML = '<option value="">Select a revision</option>' + history.revisions.map(item =>
        `<option value="${item.revision}">${item.revision} · ${escapeHtml(item.action)}</option>`).join("");
      this.root.querySelector<HTMLButtonElement>("#reset-app")!.textContent = `Restore sample (${model.elements.length} current members)`;
      this.updatePending();
    } catch (error) {
      if (error instanceof StaleResponseError) return;
      message(this.root.querySelector("#project-feedback")!, `Could not load homes/history: ${(error as Error).message}`);
    }
  }

  getSection(section: SidebarSection): HTMLElement {
    return this.sections.get(section)!;
  }

  open(section: SidebarSection,expand=true): void {
    this.active = section;
    if(expand)this.root.classList.add("mobile-open");
    this.sections.forEach((element, id) => element.hidden = id !== section);
    this.root.querySelectorAll<HTMLElement>("[data-section]").forEach((button) =>
      button.classList.toggle("active", button.dataset.section === section));
    this.root.dataset.active = section;
    this.syncNavigation();
    const url = new URL(location.href);
    url.searchParams.set("section", section);
    history.replaceState(null, "", url.pathname + url.search);
    if(expand)this.onPanelOpen();
  }

  close():void {this.setPinned(false);}

  private setPinned(pinned: boolean): void {
    this.pinned = pinned;
    storage.setItem("timberbim.sidebarPinned", String(pinned));
    document.body.classList.toggle("sidebar-pinned", pinned);
    this.root.classList.toggle("pinned", pinned);
    if(!pinned)this.root.classList.remove("mobile-open");
    this.syncNavigation();
    const button = this.root.querySelector<HTMLButtonElement>("#sidebar-pin")!;
    button.setAttribute("aria-label", pinned ? "Unpin sidebar" : "Pin sidebar");
    button.title = pinned ? "Unpin sidebar" : "Pin sidebar";
    button.querySelector(".nav-label")!.textContent =
      pinned ? "Unpin sidebar" : "Pin sidebar";
    window.dispatchEvent(new Event("resize"));
  }
  private syncNavigation(): void {
    const expanded=!matchMedia("(max-width: 600px)").matches||this.pinned||this.root.classList.contains("mobile-open");
    this.root.querySelectorAll<HTMLElement>("[data-section]").forEach(button=>{
      const active=button.dataset.section===this.active;
      button.setAttribute("aria-current",active?"page":"false");button.setAttribute("aria-expanded",String(active&&expanded));
    });
  }

  async refreshWarnings(): Promise<void> {
    const target = this.root.querySelector("#settings-warnings");
    if (!target) return;
    try {
      const result = await getWarnings();
      target.innerHTML = result.warnings.length
        ? result.warnings.map((warning) =>
          `<div class="message ${warning.severity === "warning" ? "warning" : "notice"}"><strong>${escapeHtml(warning.code)} · ${escapeHtml(warning.status.replaceAll("_"," "))}</strong><p>${escapeHtml(warning.message)}${warning.occurrences>1?` (${warning.occurrences} occurrences)`:""}</p>
          <p>${escapeHtml(warning.next_action)}</p>${warning.element_id!=null?`<button data-warning-member="${warning.element_id}">Inspect assembly</button>`:""}</div>`).join("")
        : `<div class="message success">No model warnings.</div>`;
      target.querySelectorAll<HTMLButtonElement>("[data-warning-member]").forEach(button=>button.addEventListener("click",()=>this.onWarningSelect(Number(button.dataset.warningMember))));
      const review=result.review;
      this.root.querySelector("#rule-review")!.innerHTML=`<h3>Rule applicability</h3><p>${escapeHtml(review.profile.jurisdiction)} · ${escapeHtml(review.profile.id)} v${review.profile.version}</p>
        <p>${escapeHtml(review.overall_status.replaceAll("_"," "))} · basis ${escapeHtml(review.profile.review_status.replaceAll("_"," "))}</p>
        <p>${escapeHtml(review.disclaimer)}</p><details><summary>All ${review.checks.length} checks and assumptions</summary>${review.checks.map(check=>`<div class="message"><strong>${escapeHtml(check.code)} · ${escapeHtml(check.status.replaceAll("_"," "))}</strong><p>${escapeHtml(check.message)}</p><p>${escapeHtml(check.rule_reference)} · rule v${check.rule_version}</p><p>${escapeHtml(check.assumptions)}</p></div>`).join("")}</details>`;
    } catch (error) {
      if (error instanceof StaleResponseError) return;
      target.textContent = `Could not load warnings: ${(error as Error).message}`;
    }
  }
}
