import { decodeDraft } from "./drafts";
import type { DraftKind, FieldRules, SavedDraft } from "./drafts";
import { message, storage } from "./dom";

/** Small DOM adapter: recover raw data without ever restoring a preview token. */
export class FormDraftStorage {
  private status: HTMLElement;
  private rules: FieldRules = {};
  private assemblyId: string | null = null;
  setAssembly(id: string | null): void { this.assemblyId = id; }
  constructor(root: HTMLElement, private form: HTMLFormElement, private kind: DraftKind) {
    this.status = document.createElement("div");
    this.status.id = `${kind}-draft-status`;
    this.status.setAttribute("aria-live", "polite");
    root.insertBefore(this.status, form);
    for (const input of this.controls()) {
      this.rules[input.name] = { type: input instanceof HTMLSelectElement ? "choice"
        : input instanceof HTMLInputElement && input.type === "checkbox" ? "boolean"
        : input instanceof HTMLInputElement && input.type === "number" ? "number" : "text",
        ...(input instanceof HTMLSelectElement ? { choices: Array.from(input.options, option => option.value) } : {}) };
    }
  }
  private controls(): (HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement)[] {
    return Array.from(this.form.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input[name],select[name],textarea[name]"));
  }
  private key(id: string): string {
    return `timberbim.manual${this.kind === "wall" ? "Wall" : "Truss"}Draft.${id}` +
      (this.assemblyId ? `.assembly.${encodeURIComponent(this.assemblyId)}` : "");
  }
  save(id: string, openings: SavedDraft["openings"] = []): void {
    const fields = Object.fromEntries(this.controls().map(input => [input.name,
      input instanceof HTMLInputElement && input.type === "checkbox" ? input.checked : input.value]));
    const draft: SavedDraft = { schema_version: 2, kind: this.kind, project_id: id,
      saved_at: new Date().toISOString(), fields, openings,
      ...(this.assemblyId ? { assembly_id: this.assemblyId } : {}) };
    if (!storage.setItem(this.key(id), JSON.stringify(draft)))
      message(this.status, "Browser storage is unavailable. Your live draft remains on this page; copy it before leaving.", "warning");
  }
  restore(id: string): SavedDraft["openings"] | null {
    for (const input of this.controls()) {
      if (input instanceof HTMLSelectElement) this.rules[input.name].choices = Array.from(input.options, option => option.value);
    }
    this.status.replaceChildren();
    const key = this.key(id);
    const priorRecovery = storage.keys(`${key}.recovery.`).at(-1);
    const primary = storage.getItem(key);
    const raw = primary ?? (priorRecovery ? storage.getItem(priorRecovery) : null);
    if (!raw) return null;
    try {
      const { draft, migrated } = decodeDraft(raw, this.kind, id, this.rules, this.assemblyId);
      for (const input of this.controls()) {
        const value = draft.fields[input.name];
        if (value === undefined) continue;
        if (input instanceof HTMLInputElement && input.type === "checkbox") input.checked = value as boolean;
        else input.value = String(value);
      }
      if (migrated) {
        storage.setItem(key, JSON.stringify(draft));
        message(this.status, "Saved draft migrated to the current format. Preview it before committing.", "success");
      }
      return draft.openings;
    } catch (error) {
      // Keep the original under a recovery key before any subsequent edits.
      const recoveryKey = !primary && priorRecovery ? priorRecovery : `${key}.recovery.${Date.now()}`;
      const retained = !primary && priorRecovery ? true : storage.setItem(recoveryKey, raw);
      if (retained) storage.removeItem(key);
      message(this.status, `${(error as Error).message}. Default form opened; saved data is available for recovery.`, "warning");
      const download = document.createElement("button");
      download.textContent = "Download saved draft";
      download.addEventListener("click", () => {
        const link = document.createElement("a");
        const url = URL.createObjectURL(new Blob([raw], { type: "application/json" }));
        link.href = url; link.download = `${this.kind}-${id}-draft-recovery.json`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
      const discard = document.createElement("button");
      discard.textContent = "Discard saved draft";
      discard.addEventListener("click", () => {
        storage.removeItem(retained ? recoveryKey : key);
        this.status.replaceChildren();
      });
      this.status.append(download, discard);
      return null;
    }
  }
  reset(id: string): void {
    const key = this.key(id);
    storage.removeItem(key);
    storage.keys(`${key}.recovery.`).forEach(item => storage.removeItem(item));
    this.status.replaceChildren();
  }
}
