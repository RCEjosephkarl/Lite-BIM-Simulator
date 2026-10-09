import type { BimModel, PickInfo } from "./types";
import type { ViewPreferences } from "./workspaceState";
import { boundsOf, wallMetrics } from "./memberGeometry";
import { assemblyGroups, assemblyKey, memberSearch } from "./modelHierarchy";
import type { AssemblyGroup, CameraAction } from "./modelHierarchy";

/** Persistent home status, keyboard-accessible assembly browser and inspector. */
export class WorkspaceTools {
  private model: BimModel | null = null;
  private selected: PickInfo | null = null;
  onSelect: (id: number) => void = () => {};
  onView: (view: "iso" | "top" | "front" | "side") => void = () => {};
  onCancel: () => void = () => {};
  onIsolate: (ids: number[] | null) => void = () => {};
  onRecoverView: () => void = () => {};
  onDownloadViewRecovery: () => void = () => {};
  onPatchView: (patch: Partial<ViewPreferences>) => void = () => {};
  onFitSelection: () => void = () => {};
  onBom: (id:number) => void = () => {};
  onCameraAction: (action:CameraAction) => void = () => {};
  private groups:AssemblyGroup[]=[];
  private treeLimit=250;
  private expanded=new Map<string,boolean>();
  private view: ViewPreferences | null = null;
  private recoveryStatus: string | undefined;

  constructor(private root: HTMLElement) {
    root.insertAdjacentHTML("beforeend", `
      <div id="workspace-tools" aria-label="Model tools">
        <div id="home-status" role="status"></div>
        <div id="view-storage-status" role="status"></div>
        <div id="draft-dimensions"></div>
        <div class="view-actions">
          <button id="model-browser-toggle" aria-expanded="false" aria-controls="model-browser">Model browser</button>
          <button data-view="iso" title="Fit the whole model">Fit model</button>
          <button data-view="top">Plan</button><button data-view="front">Front</button><button data-view="side">Side</button>
          <button id="preview-cancel" hidden>Cancel preview</button>
        </div>
        <details id="view-options"><summary>Filters, dimensions and section</summary>
          <div class="view-options-grid">
            <label>Level<select id="view-level"><option value="">All levels</option></select></label>
            <label><input id="view-dimensions" type="checkbox"> Show visible extents (mm)</label>
            <label><input id="view-section" type="checkbox"> Enable section</label>
            <label>Section axis<select id="section-axis"><option value="x">East (X)</option><option value="y">North (plan Z)</option><option value="z">Elevation</option></select></label>
            <label>Position (mm)<input id="section-position" type="number" step="any"></label>
            <label>Keep<select id="section-keep"><option value="lower">Lower coordinates</option><option value="upper">Upper coordinates</option></select></label>
          </div>
          <div class="view-actions"><button id="view-roof-only">Roof only</button><button id="view-all-layers">Show all layers</button></div>
          <fieldset class="camera-actions"><legend>Camera controls</legend>
            <p id="camera-help" class="notice">Focus the model canvas: arrow keys pan, Shift + arrows orbit, + / − zoom, Home fits the model. Tab moves to the next control.</p>
            <div class="view-actions">${["pan-left","pan-right","pan-up","pan-down","orbit-left","orbit-right","orbit-up","orbit-down","zoom-in","zoom-out"].map(action=>`<button data-camera-action="${action}">${action.replace("-"," ")}</button>`).join("")}</div>
          </fieldset>
          <p class="notice">Extents measure the displayed geometry, including section cuts. Fabrication cut lengths are in the inspector and BOM.</p>
        </details>
      </div>
      <section id="model-browser" aria-label="Model browser" hidden>
        <label class="field"><span>Search levels, assemblies or members</span><input id="model-search" type="search"></label>
        <div id="model-browser-list"></div>
      </section>
      <aside id="member-inspector" aria-label="Selection inspector" hidden>
        <div class="view-actions"><button id="selection-fit">Fit selection</button><button id="selection-isolate">Isolate selection</button><button id="selection-bom">BOM for assembly</button><button id="selection-show-all">Show all</button><button id="selection-clear">Clear selection</button></div>
        <div id="member-details"></div>
        <p id="selection-metrics" class="notice"></p>
      </aside>`);
    new ResizeObserver(()=>root.style.setProperty("--tools-bottom",`${root.querySelector("#workspace-tools")!.getBoundingClientRect().height+24}px`))
      .observe(root.querySelector("#workspace-tools")!);
    root.querySelector("#selection-fit")!.addEventListener("click",()=>this.onFitSelection());
    root.querySelector("#selection-bom")!.addEventListener("click",()=>{if(this.selected)this.onBom(this.selected.element.id);});
    root.querySelectorAll<HTMLElement>("[data-camera-action]").forEach(button=>button.addEventListener("click",()=>this.onCameraAction(button.dataset.cameraAction as CameraAction)));
    root.querySelector("#view-roof-only")!.addEventListener("click",()=>this.onPatchView({layers:Object.fromEntries((this.model?.types??[]).map(t=>[t.category,t.category==="roof"]))}));
    root.querySelector("#view-all-layers")!.addEventListener("click",()=>this.onPatchView({layers:{}}));
    root.querySelector<HTMLSelectElement>("#view-level")!.addEventListener("change",event=>
      this.onPatchView({level:(event.target as HTMLSelectElement).value?Number((event.target as HTMLSelectElement).value):null}));
    root.querySelector<HTMLInputElement>("#view-dimensions")!.addEventListener("change",event=>
      this.onPatchView({dimensions:(event.target as HTMLInputElement).checked}));
    const position=root.querySelector<HTMLInputElement>("#section-position")!;
    const axis=root.querySelector<HTMLSelectElement>("#section-axis")!;
    const keep=root.querySelector<HTMLSelectElement>("#section-keep")!;
    const enabled=root.querySelector<HTMLInputElement>("#view-section")!;
    const midpoint=()=>{
      const extent=this.model&&boundsOf(this.model.elements);
      const i={x:0,y:1,z:2}[axis.value as "x"|"y"|"z"];
      position.value=String(extent?(extent.minimum[i]+extent.maximum[i])/2:0);
    };
    const section=()=>{
      const valid=Number.isFinite(position.valueAsNumber);
      position.setCustomValidity(valid?"":"Enter a finite position in millimetres.");
      position.setAttribute("aria-invalid",String(!valid));
      if(!enabled.checked){this.onPatchView({section:null});return;}
      if(valid)this.onPatchView({section:{axis:axis.value as "x"|"y"|"z",position_mm:position.valueAsNumber,keep:keep.value as "lower"|"upper"}});
    };
    enabled.addEventListener("change",()=>{if(enabled.checked&&!this.view?.section)midpoint();section();});
    axis.addEventListener("change",()=>{midpoint();section();});
    position.addEventListener("change",section);keep.addEventListener("change",section);
    root.querySelectorAll<HTMLElement>("[data-view]").forEach(button =>
      button.addEventListener("click", () => this.onView(button.dataset.view as "iso" | "top" | "front" | "side")));
    root.querySelector("#preview-cancel")!.addEventListener("click", () => this.onCancel());
    root.querySelector("#model-browser-toggle")!.addEventListener("click", () => {
      const browser = root.querySelector<HTMLElement>("#model-browser")!;
      browser.hidden = !browser.hidden;
      root.querySelector("#model-browser-toggle")!.setAttribute("aria-expanded", String(!browser.hidden));
      if(!browser.hidden&&matchMedia("(max-width: 600px)").matches)root.querySelector<HTMLElement>("#member-inspector")!.hidden=true;
      if (!browser.hidden) root.querySelector<HTMLInputElement>("#model-search")!.focus();
    });
    root.querySelector("#model-search")!.addEventListener("input", () => {this.treeLimit=250;this.renderTree();});
    root.querySelector("#selection-isolate")!.addEventListener("click", () => {
      if (this.selected) this.onIsolate(this.selected.group.map(member => member.id));
    });
    root.querySelector("#selection-show-all")!.addEventListener("click", () => this.onIsolate(null));
    root.querySelector("#selection-clear")!.addEventListener("click", () => this.onSelect(Number.NaN));
    document.addEventListener("keydown", event => {
      if (event.key !== "Escape"||document.querySelector("dialog[open]")) return;
      const focusInTools=Boolean(document.activeElement?.closest("#model-browser,#member-inspector"));
      root.querySelector<HTMLElement>("#model-browser")!.hidden = true;
      root.querySelector("#model-browser-toggle")!.setAttribute("aria-expanded", "false");
      this.onSelect(Number.NaN);
      if(focusInTools)this.root.querySelector<HTMLButtonElement>("#model-browser-toggle")!.focus();
    });
  }

  syncView(view:ViewPreferences,recovery:string|null,unavailable:boolean): void {
    this.view=view;
    this.root.querySelector<HTMLSelectElement>("#view-level")!.value=view.level===null?"":String(view.level);
    this.root.querySelector<HTMLInputElement>("#view-dimensions")!.checked=view.dimensions;
    this.root.querySelector<HTMLInputElement>("#view-section")!.checked=Boolean(view.section);
    for(const id of ["section-axis","section-position","section-keep"])
      this.root.querySelector<HTMLInputElement|HTMLSelectElement>(`#${id}`)!.disabled=!view.section;
    if(view.section){
      this.root.querySelector<HTMLSelectElement>("#section-axis")!.value=view.section.axis;
      // Leave an invalid live edit intact until the user corrects it.
      const input=this.root.querySelector<HTMLInputElement>("#section-position")!;
      if(document.activeElement!==input&&input.validity.valid)input.value=String(view.section.position_mm);
      this.root.querySelector<HTMLSelectElement>("#section-keep")!.value=view.section.keep;
    }
    this.root.querySelectorAll<HTMLButtonElement>("[data-view]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.view===view.standardView)));
    const target=this.root.querySelector("#view-storage-status")!;
    const status=recovery!==null?"recovery":unavailable?"unavailable":"ok";
    if(status===this.recoveryStatus)return;
    this.recoveryStatus=status;
    if(recovery!==null){
      target.replaceChildren(document.createTextNode("Saved view could not be loaded. Live controls remain available. "));
      const download=document.createElement("button");download.textContent="Download saved view";download.onclick=this.onDownloadViewRecovery;
      const discard=document.createElement("button");discard.textContent="Discard saved view";discard.onclick=this.onRecoverView;
      target.append(download,discard);
    }else target.textContent=unavailable?"View preferences cannot be saved in this browser; live controls remain available.":"";
  }

  setModel(model: BimModel, previewCount = 0): void {
    if(this.model===model)return;
    this.model = model;
    this.groups=assemblyGroups(model.elements);
    this.root.querySelector<HTMLInputElement>("#section-position")!.setCustomValidity("");
    const levels=this.root.querySelector<HTMLSelectElement>("#view-level")!;
    levels.replaceChildren(new Option("All levels",""),...Array.from(new Set(model.elements.map(m=>m.storey))).sort((a,b)=>a-b).map(n=>new Option(`Level ${n}`,String(n))));
    const project = model.meta.project;
    const cost = model.meta.cost_summary;
    this.root.querySelector("#home-status")!.textContent =
      `${project.name} · revision ${project.revision} · ${project.geometry_mode} · ${model.meta.warnings.length} warnings` +
      ` · ${previewCount ? "saved " : ""}cut subtotal US$${cost.grand_total_usd.toFixed(2)}${cost.estimate_complete ? "" : ` · ${cost.coverage.unpriced_board_quantity} unpriced boards`}` +
      (previewCount ? ` · PREVIEW: ${previewCount} temporary members` : "");
    this.root.querySelector<HTMLElement>("#preview-cancel")!.hidden = !previewCount;
    const intent=model.meta.preview_wall_dimensions;
    const dimension=this.root.querySelector("#draft-dimensions")!;
    dimension.replaceChildren();
    if(intent){
      const description=document.createElement("p");description.className="notice";
      description.textContent=`Preview wall intent: span ${intent.span_mm.toFixed(1)} mm · height ${intent.height_mm} mm · direction ${intent.direction_deg.toFixed(1)}° from east · level ${intent.level} · base ${intent.elevation_mm.toFixed(1)} mm.`;
      dimension.append(description);
      for(const opening of intent.openings){
        const line=document.createElement("p");line.className="notice";
        line.textContent=`${opening.opening_id||opening.opening_type}: offset ${opening.start_offset_mm} mm · width ${opening.width_mm} mm · clear height ${opening.height_mm} mm · sill ${opening.sill_height_mm} mm · head ${opening.head_height_mm??opening.sill_height_mm+opening.height_mm} mm.`;
        dimension.append(line);
      }
    }
    this.renderTree();
  }

  showSelection(info: PickInfo | null, details: HTMLElement): void {
    this.selected = info;
    const bom=this.root.querySelector<HTMLButtonElement>("#selection-bom")!;
    bom.disabled=Boolean(!info||info.element.id<0||info.type.category==="concrete");
    bom.title=info?.element.id!<0?"Save this preview before opening its BOM":"Complete saved assembly, including members hidden by view filters";
    this.syncTreeSelection();
    this.root.querySelector<HTMLElement>("#member-inspector")!.hidden = !info;
    if(info&&matchMedia("(max-width: 600px)").matches){
      this.root.querySelector<HTMLElement>("#model-browser")!.hidden=true;
      this.root.querySelector("#model-browser-toggle")!.setAttribute("aria-expanded","false");
    }
    this.root.querySelector("#member-details")!.replaceChildren(
      ...Array.from(details.childNodes, node => node.cloneNode(true)));
    const metric=info?.groupKind==="segment"?wallMetrics(info.group):null;
    this.root.querySelector("#selection-metrics")!.textContent=metric?
      `Wall geometry extent along run: ${metric.span_mm.toFixed(1)} mm · direction ${metric.direction_deg.toFixed(1)}° from east · base ${metric.elevation_mm.toFixed(1)} mm · height ${metric.height_mm.toFixed(1)} mm. Openings and fabrication panels are listed above.`:"";
  }

  closeOverlays():void {
    this.root.querySelector<HTMLElement>("#model-browser")!.hidden=true;
    this.root.querySelector<HTMLElement>("#member-inspector")!.hidden=true;
    this.root.querySelector("#model-browser-toggle")!.setAttribute("aria-expanded","false");
    this.root.querySelector<HTMLDetailsElement>("#view-options")!.open=false;
  }

  private renderTree(): void {
    if (!this.model) return;
    const query = this.root.querySelector<HTMLInputElement>("#model-search")!.value.trim().toLowerCase();
    const list = this.root.querySelector("#model-browser-list")!;
    const labelMatches=(g:AssemblyGroup)=>`${g.label} ${g.sourceId} ${g.branch}`.toLowerCase().includes(query);
    const rows = this.groups.filter(g => !query||labelMatches(g)||g.members.some(m=>memberSearch(m).includes(query)));
    list.replaceChildren();
    const branches=new Map<string,HTMLElement>();
    const branch=(parent:Element,key:string,label:string,open=true):HTMLDetailsElement=>{
      const details=document.createElement("details");details.className="model-tree-branch";
      const summary=document.createElement("summary");summary.textContent=label;details.append(summary);
      details.open=Boolean(query&&open)||(this.expanded.get(key)??open);
      details.addEventListener("toggle",()=>this.expanded.set(key,details.open));parent.append(details);return details;
    };
    for (const group of rows.slice(0, this.treeLimit)) {
      const levelKey=JSON.stringify([group.level]);
      const sourceKey=JSON.stringify([group.level,group.source,group.sourceId]);
      const branchKey=JSON.stringify([group.level,group.source,group.sourceId,group.branch]);
      if(!branches.has(levelKey))branches.set(levelKey,branch(list,levelKey,`Level ${group.level}`));
      if(!branches.has(sourceKey))branches.set(sourceKey,branch(branches.get(levelKey)!,sourceKey,`${group.source} · ${group.sourceId||"sample"}`));
      if(!branches.has(branchKey))branches.set(branchKey,branch(branches.get(sourceKey)!,branchKey,group.branch));
      const parent=branches.get(branchKey)!;
      const button = document.createElement("button");
      button.className = "model-tree-item";
      button.dataset.assemblyKey=group.key;
      button.textContent = `${group.members[0].id<0?"PREVIEW · ":""}${group.label} (${group.members.length} segments)`;
      button.addEventListener("click",event=>{
        this.onSelect(group.members[0].id);
        if(event.detail===0)this.root.querySelector<HTMLButtonElement>("#selection-fit")!.focus();
      });
      parent.appendChild(button);
      const cuts=branch(parent,`cuts:${group.key}`,"Panels and physical members",false);
      let loaded=false;
      const fill=()=>{
        if(loaded||!cuts.open)return;loaded=true;
        const panels=new Map<string,HTMLDetailsElement>();
        const physical=new Map<string,BimModel["elements"]>();
        for(const member of group.members){
          if(query&&!labelMatches(group)&&!memberSearch(member).includes(query))continue;
          const key=JSON.stringify([member.panel_id,member.physical_member_id||member.id]);
          if(!physical.has(key))physical.set(key,[]);physical.get(key)!.push(member);
        }
        const entries=[...physical.values()];let shown=0;
        const more=document.createElement("button");more.textContent="Show more physical members";
        const append=(focusNew=false)=>{
          let firstNew:HTMLButtonElement|undefined;
          for(const members of entries.slice(shown,shown+100)){
            const member=members[0];const panel=member.panel_id||"Members";
            if(!panels.has(panel))panels.set(panel,branch(cuts,`panel:${group.key}:${panel}`,panel));
            const item=document.createElement("button");item.className="model-member-item";
            item.textContent=`${member.member_role||member.type_code} · ${member.physical_member_id||`row ${member.id}`} · ${member.size} (${members.length} segments)`;
            item.onclick=()=>{this.onSelect(member.id);this.root.querySelector<HTMLButtonElement>("#selection-fit")!.focus();};
            panels.get(panel)!.append(item);
            if(!firstNew){firstNew=item;if(focusNew)panels.get(panel)!.open=true;}
          }
          shown=Math.min(entries.length,shown+100);more.hidden=shown===entries.length;cuts.append(more);this.syncTreeSelection();
          if(focusNew)firstNew?.focus();
        };
        more.onclick=()=>append(true);append();
      };
      cuts.addEventListener("toggle",fill);
      if(query&&!labelMatches(group))cuts.open=true;
      fill();
    }
    const note = document.createElement("p");
    note.className = "notice";
    note.textContent = `${rows.length} assemblies/members · showing ${Math.min(rows.length,this.treeLimit)}`;
    list.appendChild(note);
    if(rows.length>this.treeLimit){
      const more=document.createElement("button");more.textContent="Show 250 more assemblies";
      more.onclick=()=>{
        const key=rows[this.treeLimit].key;this.treeLimit+=250;this.renderTree();
        const first=Array.from(list.querySelectorAll<HTMLButtonElement>("[data-assembly-key]")).find(button=>button.dataset.assemblyKey===key);
        if(first){let ancestor=first.parentElement;while(ancestor&&ancestor!==list){if(ancestor instanceof HTMLDetailsElement)ancestor.open=true;ancestor=ancestor.parentElement;}first.focus();}
      };list.append(more);
    }
    this.syncTreeSelection();
  }

  private syncTreeSelection():void {
    const selected=this.selected?assemblyKey(this.selected.element):null;
    this.root.querySelectorAll<HTMLButtonElement>("[data-assembly-key]").forEach(button=>{
      const active=button.dataset.assemblyKey===selected;button.setAttribute("aria-pressed",String(active));
      button.classList.toggle("selected",active);
    });
  }
}
