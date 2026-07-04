import {
  commitCsvPlan, deleteImportBatch,
  getImportBatches, uploadCsvPlanPreview, uploadCsvPlanValidate,
} from "./api";
import type {
  BimModel, CsvValidationResult, PreviewResult,
} from "./types";

const escapeHtml = (value: unknown) => String(value ?? "").replace(
  /[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]!);

export class ImportsPanel {
  private validation: CsvValidationResult | null = null;
  private fileName = "";
  onPreview: (result: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <div data-import-panel="csv">
        <label id="csv-drop" class="drop-zone">
          <strong>Drop a plan CSV here</strong>
          <span>or choose a file</span>
          <input id="csv-file" type="file" accept=".csv,text/csv">
        </label>
        <div class="field"><label for="csv-units">Input units</label>
          <select id="csv-units"><option value="mm">Millimetres</option>
            <option value="metres">Metres</option>
            <option value="feet_inches">Feet / inches</option></select></div>
        <div id="csv-summary" class="message-list"></div>
        <div class="table-wrap"><table id="csv-table"></table></div>
        <div class="field"><label for="csv-mode">Commit mode</label>
          <select id="csv-mode">
            <option value="append_to_sample_geometry">Append to sample geometry</option>
            <option value="replace_sample_geometry">Replace sample geometry</option>
            <option value="new_project_from_csv">New project from CSV</option>
          </select></div>
        <div class="button-row">
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
    this.root.querySelector("#csv-commit")!.addEventListener("click",
      () => void this.commitCsv());
  }

  private async validate(file: File): Promise<void> {
    this.fileName = file.name;
    const units = this.root.querySelector<HTMLSelectElement>("#csv-units")!
      .value as "mm" | "metres" | "feet_inches";
    try {
      this.validation = await uploadCsvPlanValidate(file, units);
      this.renderCsv();
    } catch (error) {
      this.message("#csv-summary", (error as Error).message, "error");
    }
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
      <thead><tr><th>Row</th>${columns.map((column) =>
        `<th>${escapeHtml(column)}</th>`).join("")}<th>Validation</th><th></th></tr></thead>
      <tbody>${this.validation.rows.map((row, index) => `
        <tr class="${row.valid ? "" : "invalid"}" data-row-index="${index}">
          <td>${row._row ?? index + 2}</td>
          ${columns.map((column) => `<td contenteditable="true"
            data-field="${column}">${escapeHtml(row[column])}</td>`).join("")}
          <td>${escapeHtml([...(row.errors ?? []), ...(row.warnings ?? [])].join("; "))}</td>
          <td><button class="table-delete" aria-label="Delete row">Delete</button></td>
        </tr>`).join("")}</tbody>`;
    this.root.querySelectorAll<HTMLElement>("#csv-table [contenteditable]").forEach(
      (cell) => cell.addEventListener("blur", () => {
        const tr = cell.closest<HTMLElement>("tr")!;
        const row = this.validation!.rows[Number(tr.dataset.rowIndex)];
        const raw = cell.textContent?.trim() ?? "";
        row[cell.dataset.field!] = /^-?\d+(?:\.\d+)?$/.test(raw)
          ? Number(raw) : raw;
      }));
    this.root.querySelectorAll<HTMLButtonElement>(".table-delete").forEach(
      (button) => button.addEventListener("click", () => {
        const index = Number(button.closest<HTMLElement>("tr")!.dataset.rowIndex);
        this.validation!.rows.splice(index, 1);
        this.renderCsv();
      }));
    this.root.querySelector<HTMLButtonElement>("#csv-preview")!.disabled =
      !this.validation.rows.length;
    this.root.querySelector<HTMLButtonElement>("#csv-commit")!.disabled =
      !this.validation.rows.length;
  }

  private async previewCsv(): Promise<void> {
    if (!this.validation) return;
    try {
      const result = await uploadCsvPlanPreview(
        this.validation.rows, this.fileName);
      this.validation = result.validation;
      this.renderCsv();
      this.onPreview(result);
    } catch (error) {
      this.message("#csv-summary", (error as Error).message, "error");
    }
  }

  private async commitCsv(): Promise<void> {
    if (!this.validation) return;
    const mode = this.root.querySelector<HTMLSelectElement>("#csv-mode")!.value;
    if (mode !== "append_to_sample_geometry" &&
        !confirm("This will replace the current model geometry. Continue?")) return;
    try {
      const result = await commitCsvPlan(
        this.validation.rows, mode, this.fileName);
      this.onModel(result.model);
      this.message("#csv-summary", `Committed import batch ${result.batch_id}.`,
        "success");
      await this.refreshBatches();
    } catch (error) {
      this.message("#csv-summary", (error as Error).message, "error");
    }
  }

  private message(selector: string, text: string, kind: string): void {
    this.root.querySelector(selector)!.innerHTML =
      `<div class="message ${kind}">${escapeHtml(text)}</div>`;
  }

  async refreshBatches(): Promise<void> {
    const target = this.root.querySelector("#import-batches")!;
    try {
      const result = await getImportBatches();
      target.innerHTML = result.batches.length
        ? result.batches.map((batch) => `<div class="batch-row">
            <span><strong>${escapeHtml(batch.source_type)}</strong><br>
              ${escapeHtml(batch.file_name || batch.batch_id)}<br>
              ${batch.accepted_count} accepted, ${batch.warning_count} warnings
            </span>
            <button class="table-delete" data-delete-batch="${escapeHtml(
              batch.batch_id)}">Delete</button></div>`).join("")
        : `<div class="message">No committed import/manual batches.</div>`;
      target.querySelectorAll<HTMLButtonElement>("[data-delete-batch]").forEach(
        (button) => button.addEventListener("click", async () => {
          if (!confirm(`Delete batch ${button.dataset.deleteBatch}?`)) return;
          const deleted = await deleteImportBatch(button.dataset.deleteBatch!);
          this.onModel(deleted.model);
          await this.refreshBatches();
        }));
    } catch (error) {
      target.textContent = `Could not load batches: ${(error as Error).message}`;
    }
  }
}
