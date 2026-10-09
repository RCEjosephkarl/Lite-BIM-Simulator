import {
  exportHomeArchive, getHomeDefinition, getHomeExamples, importHomeArchive,
  previewHomeArchive, previewHomeDefinition, saveHomeDefinition, StaleResponseError,
} from "./api";
import type { BimModel, PreviewResult } from "./types";

/** Portable homes share the Imports page, with explicit replacement review. */
export class HomePanel {
  onDraftChange: () => void = () => {};
  onPreview: (preview: PreviewResult) => void = () => {};
  onModel: (model: BimModel) => void = () => {};
  private model: BimModel | null = null;
  private busy = false;
  private pending = false;
  private signature = "";
  private loadEpoch = 0;
  private editor: HTMLTextAreaElement;
  private status: HTMLElement;

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("afterbegin", `
      <section aria-labelledby="home-title" id="home-input">
        <h3 id="home-title">Reusable homes</h3>
        <p>Choose an example, edit the current definition or open a saved home file.
          Preview before saving. New geometry replaces this home's generated geometry.</p>
        <div class="field"><label for="home-example">Example home</label>
          <select id="home-example"><option value="">Choose a design…</option>
            <option value="rectangle">Rectangle · 9 m × 6 m</option>
            <option value="l_shape">L-shaped · two roof zones</option>
            <option value="two_level">Two levels · offset footprint</option></select></div>
        <div class="button-row"><button id="home-current">Edit current definition</button>
          <button id="home-export">Download saved home</button></div>
        <div class="field"><label for="home-file">Open home JSON / portable archive</label>
          <input id="home-file" type="file" accept=".json,application/json"></div>
        <details id="home-editor-details"><summary>Definition editor</summary>
          <p>Millimetres; X = east, plan Z = north, level elevation = up.
            Preserve entity IDs when reordering. Draft edits are temporary until saved.</p>
          <label for="home-editor">Home definition or portable archive</label>
          <textarea id="home-editor" rows="14" spellcheck="false" style="width:100%;box-sizing:border-box;font-family:monospace" aria-describedby="home-definition-status"></textarea>
        </details>
        <div class="field"><label><input id="home-preserve" type="checkbox" checked>
          Keep this home's manual and CSV assemblies when applying a definition</label></div>
        <div class="button-row"><button id="home-preview" disabled>Preview home</button>
          <button id="home-save" class="primary-button" disabled>Save home changes</button></div>
        <p id="home-definition-status" role="status">Saved home downloads include definitions, settings, quotes and source provenance. Archives replace geometry and pricing after confirmation.</p>
      </section>`);
    this.editor=root.querySelector("#home-editor")!;
    this.status=root.querySelector("#home-definition-status")!;
    this.editor.addEventListener("input",()=>this.changed());
    root.querySelector("#home-preserve")!.addEventListener("change",()=>this.changed());
    root.querySelector("#home-current")!.addEventListener("click",()=>void this.current());
    root.querySelector("#home-export")!.addEventListener("click",()=>void this.download());
    root.querySelector("#home-preview")!.addEventListener("click",()=>void this.preview());
    root.querySelector("#home-save")!.addEventListener("click",()=>void this.save());
    root.querySelector<HTMLSelectElement>("#home-example")!.addEventListener("change",event=>void this.example((event.target as HTMLSelectElement).value));
    root.querySelector<HTMLInputElement>("#home-file")!.addEventListener("change",event=>{
      const file=(event.target as HTMLInputElement).files?.[0];if(file)void this.read(file);
    });
  }
  loadProject(): void {
    this.loadEpoch++; this.editor.value=""; this.signature="";
    this.root.querySelector<HTMLInputElement>("#home-file")!.value="";
    this.root.querySelector<HTMLSelectElement>("#home-example")!.value="";
    this.message("Choose a design or open this home's definition. Draft edits are temporary until saved.");
    this.update();
  }
  setModel(model:BimModel): void { this.model=model; this.signature="";this.update(); }
  invalidateForModel(): void { this.signature="";this.update(); }
  setWorkspaceBusy(busy:boolean): void { this.busy=busy;this.update(); }
  private preserve(): boolean { return this.root.querySelector<HTMLInputElement>("#home-preserve")!.checked; }
  private fingerprint(): string { return `${this.editor.value}:${this.preserve()}`; }
  private payload(): Record<string,unknown> {
    const value=JSON.parse(this.editor.value);
    if(!value || typeof value!=="object" || Array.isArray(value))throw new Error("A home file must contain a JSON object.");
    return value;
  }
  private changed(): void { this.signature="";this.onDraftChange();this.update(); }
  private show(value:unknown): void {
    this.editor.value=JSON.stringify(value,null,2);
    this.root.querySelector<HTMLDetailsElement>("#home-editor-details")!.open=true;
    this.changed();this.message("Definition loaded. Review geometry and preview before saving.");
  }
  private message(text:string,error=false): void { this.status.textContent=text;this.status.className=error?"message error":"message"; }
  private update(): void {
    const blocked=this.busy||this.pending;
    this.root.querySelectorAll<HTMLInputElement|HTMLButtonElement|HTMLSelectElement|HTMLTextAreaElement>("#home-input input,#home-input button,#home-input select,#home-input textarea").forEach(el=>el.disabled=blocked);
    this.root.querySelector<HTMLButtonElement>("#home-preview")!.disabled=blocked||!this.editor.value.trim();
    this.root.querySelector<HTMLButtonElement>("#home-save")!.disabled=blocked||!this.signature||this.signature!==this.fingerprint();
    let archive=false;try{archive="archive_schema_version" in this.payload();}catch{}
    this.root.querySelector<HTMLInputElement>("#home-preserve")!.disabled=blocked||archive;
  }
  private async action(work:()=>Promise<void>): Promise<void> {
    if(this.busy||this.pending)return;
    this.pending=true;this.update();
    try{await work();}catch(error){if(!(error instanceof StaleResponseError))this.message((error as Error).message,true);}
    finally{this.pending=false;this.update();}
  }
  private async current(): Promise<void> {
    await this.action(async()=>{
      const result=await getHomeDefinition();
      if(!result.definition)throw new Error("This home uses individual assemblies. Download a portable archive to preserve and reuse all of them.");
      this.show(result.definition);
    });
  }
  private async example(id:string): Promise<void> {
    if(!id)return;
    await this.action(async()=>{
      const result=await getHomeExamples();const chosen=result.examples.find(item=>item.id===id);
      if(!chosen)throw new Error("Example home was not found.");this.show(chosen.definition);
    });
  }
  private async read(file:File): Promise<void> {
    const epoch=this.loadEpoch;
    await this.action(async()=>{
      if(file.size>16*1024*1024)throw new Error("Home file exceeds the 16 MiB limit. Split large source assemblies before importing.");
      const value=JSON.parse(await file.text());if(epoch===this.loadEpoch)this.show(value);
    });
  }
  private async download(): Promise<void> {
    await this.action(async()=>{
      const archive=await exportHomeArchive();
      const url=URL.createObjectURL(new Blob([JSON.stringify(archive,null,2)+"\n"],{type:"application/json"}));
      const a=document.createElement("a");a.href=url;a.download="timberbim-home.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      this.message("Saved home downloaded with definitions, design settings, quote overrides and source provenance.");
    });
  }
  private async preview(): Promise<void> {
    this.changed();
    await this.action(async()=>{
      const payload=this.payload();const archive="archive_schema_version" in payload;
      const result=archive?await previewHomeArchive(payload):await previewHomeDefinition(payload);
      this.signature=this.fingerprint();
      this.onPreview({...result,replace_all:archive||!this.preserve(),replace_generated:!archive&&this.preserve()});
      this.message(`${result.metadata.member_count} proposed members; ${result.metadata.cut_quantity} physical cuts. ${result.metadata.warnings.join("; ")} Review the replacement before saving.`);
    });
  }
  private async save(): Promise<void> {
    if(!this.signature||this.signature!==this.fingerprint())return;
    const payload=this.payload();const archive="archive_schema_version" in payload;
    const affected=archive||!this.preserve()?this.model?.elements.length??0:this.model?.elements.filter(e=>e.source==="generated").length??0;
    if(!confirm(`Replace ${affected} saved members in this home${archive?" and its pricing":""}? The current revision will remain available to restore.`))return;
    await this.action(async()=>{
      const model=archive?await importHomeArchive(payload):await saveHomeDefinition(payload,this.preserve());
      this.signature="";this.onModel(model);this.message("Home saved. Reopen or regenerate this design from its persisted definition.");
    });
  }
}
