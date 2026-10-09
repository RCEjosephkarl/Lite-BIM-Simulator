import {
  ApiError, commitCsvPlan, deleteImportBatch, reviewCsvPlan,
  getImportBatches, getDefinitions, updateCsvPlan, uploadCsvPlanPreview, uploadCsvPlanValidate, StaleResponseError,
} from "./api";
import type {
  BimModel, CsvValidationResult, PreviewResult, AssemblyDefinition,
} from "./types";

const escapeHtml = (value: unknown) => String(value ?? "").replace(
  /[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]!);

export class ImportsPanel {
  private validation: CsvValidationResult | null = null;
  private fileName = "";
  private file: File | null = null;
  private previewSignature = "";
  private pending = false;
  private workspaceBusy = false;
  private editId: string | null = null;
  onEdit: (definition: AssemblyDefinition, fileName: string) => void = () => {};
  onEditTarget: (id: string | null) => void = () => {};
  loadProject(): void {
    this.editId = null; this.validation = null; this.file = null; this.fileName = "";
    this.root.querySelector<HTMLInputElement>("#csv-file")!.value = "";
    this.root.querySelector("#csv-table")!.replaceChildren();
    this.root.querySelector("#csv-summary")!.replaceChildren();
    this.updateEditStatus(); this.invalidateForModel();
  }
  async editBatch(id: string, definition: { rows: CsvValidationResult["rows"]; units: "mm" }, fileName: string): Promise<void> {
    this.onDraftChange(); this.editId = id; this.file = null; this.fileName = fileName;
    this.root.querySelector<HTMLSelectElement>("#csv-units")!.value = "mm";
    this.validation = { rows: structuredClone(definition.rows), normalized_entities: [], errors: [], warnings: [],
      summary: { wall_count: 0, opening_count: 0, truss_count: 0,
        estimated_total_wall_length_m: 0, error_count: 0, warning_count: 0 }, can_preview: false };
    this.updateEditStatus(); this.invalidateForModel();
    this.onEditTarget(id);
    await this.reviewRows();
  }
  private updateEditStatus(): void {
    this.root.querySelector("#csv-edit-status")!.textContent = this.editId
      ? `Editing CSV batch ${this.editId}. Save replaces only this batch; other assemblies remain. Row edits are temporary until saved.` : "New CSV import";
    this.root.querySelector<HTMLButtonElement>("#csv-edit-exit")!.hidden = !this.editId;
    this.root.querySelector("#csv-commit")!.textContent = this.editId ? "Save batch changes" : "Commit to model";
  }
  onDraftChange: () => void = () => {};
  setWorkspaceBusy(busy: boolean): void { this.workspaceBusy = busy; this.updateActions(); }
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};

  invalidateForModel(): void {
    this.previewSignature = "";
    this.updateActions();
  }

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <div data-import-panel="csv">
        <p id="csv-edit-status" role="status">New CSV import</p><button id="csv-edit-exit" hidden>Exit CSV editing</button>
        <label id="csv-drop" class="drop-zone">
          <strong>Drop a plan CSV here</strong>
          <span>or choose a file</span>
          <input id="csv-file" type="file" accept=".csv,text/csv">
        </label>
        <div class="field"><label for="csv-units">Input units</label>
          <select id="csv-units"><option value="mm">Millimetres</option>
            <option value="metres">Metres</option>
            <option value="feet_inches">Feet / inches</option></select></div>
        <div id="csv-summary" class="message-list" aria-live="polite"></div>
        <div class="table-wrap"><table id="csv-table" aria-label="CSV plan review"></table></div>
        <div class="field"><label for="csv-mode">Commit mode</label>
          <select id="csv-mode">
            <option value="append_to_sample_geometry">Append to sample geometry</option>
            <option value="replace_sample_geometry">Replace sample geometry</option>
            <option value="new_project_from_csv">New project from CSV</option>
          </select></div>
        <div class="button-row">
          <button id="csv-review" class="secondary-button" disabled>Validate edited rows</button>
          <button id="csv-preview" class="secondary-button" disabled>Preview in model</button>
          <button id="csv-commit" class="primary-button" disabled>Commit to model</button>
        </div>
      </div>
      <h3>Committed batches</h3>
      <div id="import-batches" class="message-list">Loading batches...</div>`);
    this.bind();
    void this.refreshBatches();
  }

  private bind(): void {
    this.root.querySelector("#csv-edit-exit")!.addEventListener("click", () => {
      this.onDraftChange(); this.loadProject(); this.onEditTarget(null);
    });
    const input = this.root.querySelector<HTMLInputElement>("#csv-file")!;
    input.addEventListener("change", () => {
      if (input.files?.[0]) void this.validate(input.files[0]);
    });
    const drop = this.root.querySelector<HTMLElement>("#csv-drop")!;
    drop.addEventListener("dragover", (event) => {
      event.preventDefault(); drop.classList.add("dragging");
    });
    drop.addEventListener("dragleave", () => drop.classList.remove("dragging"));
    drop.addEventListener("drop", (event) => {
      event.preventDefault(); drop.classList.remove("dragging");
      const file = event.dataTransfer?.files[0];
      if (file) void this.validate(file);
    });
    this.root.querySelector("#csv-preview")!.addEventListener("click",
      () => void this.previewCsv());
    this.root.querySelector("#csv-review")!.addEventListener("click",
      () => void this.reviewRows());
    this.root.querySelector("#csv-units")!.addEventListener("change", () => {
      if (this.file) void this.validate(this.file);
    });
    this.root.querySelector("#csv-commit")!.addEventListener("click",
      () => void this.commitCsv());
    this.root.querySelector("#csv-mode")!.addEventListener("change", () => {
      this.invalidateForModel(); this.onDraftChange();
      this.message("#csv-summary", "Commit mode changed. Preview again before committing.", "warning");
    });
  }

  private async validate(file: File): Promise<void> {
    if (this.pending) return;
    this.file = file;
    this.editId = null; this.onEditTarget(null); this.updateEditStatus();
    this.fileName = file.name;
    this.validation = null;
    this.previewSignature = "";
    this.onDraftChange();
    this.setPending(true);
    const units = this.root.querySelector<HTMLSelectElement>("#csv-units")!
      .value as "mm" | "metres" | "feet_inches";
    try {
      this.validation = await uploadCsvPlanValidate(file, units);
      this.renderCsv();
    } catch (error) {
      this.message("#csv-summary", (error as Error).message, "error");
    } finally { this.setPending(false); }
  }

  private renderCsv(): void {
    if (!this.validation) return;
    const summary = this.validation.summary;
    this.root.querySelector("#csv-summary")!.innerHTML = `
      <div class="message ${summary.error_count ? "error" : "success"}">
        ${summary.wall_count} walls, ${summary.opening_count} openings,
        ${summary.truss_count} trusses, ${summary.estimated_total_wall_length_m} m wall
        length. ${summary.error_count} errors, ${summary.warning_count} warnings.
      </div>`;
    const ignored = new Set(["valid", "errors", "warnings", "_row"]);
    const columns = [...new Set(this.validation.rows.flatMap(
      (row) => Object.keys(row).filter((key) => !ignored.has(key))))];
    this.root.querySelector("#csv-table")!.innerHTML = `
      <thead><tr><th scope="col">Row</th>${columns.map((column) =>
        `<th scope="col">${escapeHtml(column)}</th>`).join("")}<th scope="col">Validation</th><th scope="col">Actions</th></tr></thead>
      <tbody>${this.validation.rows.map((row, index) => `
        <tr class="${row.valid ? "" : "invalid"}" data-row-index="${index}">
          <td>${escapeHtml(row._row ?? index + 2)}</td>
          ${columns.map((column) => `<td contenteditable="true"
            role="textbox" aria-multiline="false" tabindex="0" aria-label="Row ${escapeHtml(row._row??index+2)} · ${escapeHtml(column)}"
            aria-describedby="csv-row-${index}-validation" aria-invalid="${!row.valid}"
            data-field="${escapeHtml(column)}">${escapeHtml(row[column])}</td>`).join("")}
          <td id="csv-row-${index}-validation">${escapeHtml([...(row.errors ?? []), ...(row.warnings ?? [])].join("; "))}</td>
          <td><button class="table-delete" aria-label="Delete row ${escapeHtml(row._row??index+2)}">Delete</button></td>
        </tr>`).join("")}</tbody>`;
    this.root.querySelectorAll<HTMLElement>("#csv-table [contenteditable]").forEach(
      (cell) => cell.addEventListener("input", () => {
        const tr = cell.closest<HTMLElement>("tr")!;
        const row = this.validation!.rows[Number(tr.dataset.rowIndex)];
        const raw = cell.textContent?.trim() ?? "";
        row[cell.dataset.field!] = /^-?\d+(?:\.\d+)?$/.test(raw)
          ? Number(raw) : raw;
        this.invalidatePreview();
      }));
    this.root.querySelectorAll<HTMLButtonElement>("#csv-table .table-delete").forEach(
      (button) => button.addEventListener("click", () => {
        const index = Number(button.closest<HTMLElement>("tr")!.dataset.rowIndex);
        this.validation!.rows.splice(index, 1);
        this.invalidatePreview();
        this.renderCsv();
        (this.root.querySelector<HTMLElement>(`#csv-table [data-row-index="${Math.min(index,this.validation!.rows.length-1)}"] [data-field]`)
          ??this.root.querySelector<HTMLInputElement>("#csv-file"))!.focus();
      }));
    this.updateActions();
  }

  private signature(): string {
    return JSON.stringify(this.validation?.rows ?? []);
  }

  private updateActions(): void {
    const pending = this.pending || this.workspaceBusy;
    const rows = Boolean(this.validation?.rows.length);
    this.root.querySelector<HTMLButtonElement>("#csv-review")!.disabled = pending || !rows;
    this.root.querySelector<HTMLButtonElement>("#csv-preview")!.disabled = pending || !this.validation?.can_preview;
    this.root.querySelector<HTMLButtonElement>("#csv-commit")!.disabled = pending || !rows || !this.previewSignature || this.previewSignature !== this.signature();
    this.root.querySelector<HTMLInputElement>("#csv-file")!.disabled = pending;
    this.root.querySelector<HTMLSelectElement>("#csv-units")!.disabled = pending;
    this.root.querySelector<HTMLSelectElement>("#csv-mode")!.disabled = pending || Boolean(this.editId);
    this.root.querySelector<HTMLSelectElement>("#csv-units")!.disabled = pending || Boolean(this.editId);
    this.root.querySelector<HTMLButtonElement>("#csv-edit-exit")!.disabled = pending;
    this.root.querySelectorAll<HTMLElement>("#csv-table [data-field]").forEach(
      cell => {cell.contentEditable = pending ? "false" : "true";cell.setAttribute("aria-disabled",String(pending));cell.tabIndex=pending?-1:0;});
    this.root.querySelectorAll<HTMLButtonElement>("#csv-table .table-delete").forEach(
      button => button.disabled = pending);
    this.root.querySelectorAll<HTMLButtonElement>("[data-delete-batch]").forEach(button => button.disabled = pending);
    this.root.querySelectorAll<HTMLButtonElement>("[data-edit-batch]").forEach(button => button.disabled = pending || button.dataset.editReady !== "true");
  }

  private setPending(pending: boolean): void {
    this.pending = pending;
    this.updateActions();
  }

  private invalidatePreview(): void {
    this.previewSignature = "";
    if (this.validation) this.validation.can_preview = false;
    this.updateActions();
    this.onDraftChange();
    this.message("#csv-summary", "Rows edited. Validate and preview the current rows before committing.", "warning");
  }

  private validationError(error: unknown): void {
    if (error instanceof StaleResponseError) return;
    if (error instanceof ApiError && error.detail && typeof error.detail === "object" && "rows" in error.detail) {
      this.validation = error.detail as CsvValidationResult;
      this.renderCsv();
    }
    this.message("#csv-summary", (error as Error).message, "error");
  }

  private async reviewRows(): Promise<void> {
    if (!this.validation || this.pending) return;
    this.previewSignature = "";
    this.setPending(true);
    try {
      this.validation = await reviewCsvPlan(this.validation.rows);
      this.renderCsv();
    } catch (error) { this.validationError(error); }
    finally { this.setPending(false); }
  }

  private async previewCsv(): Promise<void> {
    if (!this.validation || this.pending) return;
    this.previewSignature = "";
    this.setPending(true);
    try {
      const result = await uploadCsvPlanPreview(
        this.validation.rows, this.fileName);
      this.validation = result.validation;
      this.previewSignature = this.signature();
      this.renderCsv();
      this.onPreview({ ...result, replace_source_id: this.editId ?? undefined, replace_source_type: "csv_import" });
      this.message("#csv-summary", `Preview: ${result.metadata.cut_quantity} cuts / ${result.metadata.physical_board_quantity} boards · priced cut subtotal US$${result.metadata.estimated_cost_usd.toFixed(2)} · stock US$${result.metadata.estimated_stock_cost_usd.toFixed(2)} · ${result.metadata.unpriced_cut_quantity} unpriced cuts.`, result.metadata.estimate_complete ? "success" : "warning");
    } catch (error) {
      this.validationError(error);
    } finally { this.setPending(false); }
  }

  private async commitCsv(): Promise<void> {
    if (!this.validation || this.pending) return;
    if (!this.previewSignature || this.previewSignature !== this.signature()) {
      this.message("#csv-summary", "Preview the current rows before committing.", "error");
      return;
    }
    const mode = this.root.querySelector<HTMLSelectElement>("#csv-mode")!.value;
    if (!this.editId && mode === "replace_sample_geometry" &&
        !confirm("Replace this home's current geometry with the reviewed CSV? The prior revision will remain available in Settings.")) return;
    this.setPending(true);
    try {
      const result = await (this.editId ? updateCsvPlan(this.editId, this.validation.rows, this.fileName)
        : commitCsvPlan(this.validation.rows, mode, this.fileName));
      this.onModel(result.model);
      this.previewSignature = "";
      this.message("#csv-summary", `${this.editId ? "Updated" : "Committed"} import batch ${result.batch_id}.`,
        "success");
      await this.refreshBatches();
    } catch (error) {
      this.validationError(error);
    } finally { this.setPending(false); }
  }

  private message(selector: string, text: string, kind: string): void {
    this.root.querySelector(selector)!.innerHTML =
      `<div class="message ${kind}">${escapeHtml(text)}</div>`;
  }

  async refreshBatches(): Promise<void> {
    const target = this.root.querySelector("#import-batches")!;
    try {
      const [result, definitions] = await Promise.all([getImportBatches(), getDefinitions()]);
      const editable = new Map(definitions.definitions.map(definition => [definition.definition_id, definition]));
      target.innerHTML = result.batches.length
        ? result.batches.map((batch) => `<div class="batch-row">
            <span><strong>${escapeHtml(batch.source_type)}</strong><br>
              ${escapeHtml(batch.file_name || batch.batch_id)}<br>
              ${batch.accepted_count} accepted, ${batch.warning_count} warnings
            </span>
            <button class="secondary-button" data-edit-batch="${escapeHtml(batch.batch_id)}" data-edit-ready="${editable.has(batch.batch_id)}" ${editable.has(batch.batch_id) ? "" : 'disabled title="Saved definition is unavailable; review/recreate legacy geometry"'}>Edit</button>
            <button class="table-delete" data-delete-batch="${escapeHtml(
              batch.batch_id)}">Delete</button></div>`).join("")
        : `<div class="message">No committed import/manual batches.</div>`;
      target.querySelectorAll<HTMLButtonElement>("[data-edit-batch]").forEach(button => button.addEventListener("click", () => {
        const definition = editable.get(button.dataset.editBatch!)!;
        this.onEdit(definition, result.batches.find(batch => batch.batch_id === definition.definition_id)?.file_name ?? "");
      }));
      target.querySelectorAll<HTMLButtonElement>("[data-delete-batch]").forEach(
        (button) => button.addEventListener("click", async () => {
          if (!confirm(`Delete batch ${button.dataset.deleteBatch}?`)) return;
          button.disabled = true;
          try {
            const deleted = await deleteImportBatch(button.dataset.deleteBatch!);
            this.onModel(deleted.model);
            await this.refreshBatches();
          } catch (error) { this.message("#csv-summary", (error as Error).message, "error"); }
          finally { button.disabled = false; }
        }));
      this.updateActions();
    } catch (error) {
      if (error instanceof StaleResponseError) return;
      target.textContent = `Could not load batches: ${(error as Error).message}`;
    }
  }
}
