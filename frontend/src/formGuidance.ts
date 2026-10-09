import type { OpeningDraft } from "./drafts";

export interface FieldIssue { path:(string|number)[]; message:string }
export class FormInputError extends Error {
  readonly issues:FieldIssue[];
  constructor(issues:FieldIssue[]){super(issues.map(i=>i.message).join("; "));this.issues=issues;}
}
export function validationIssues(detail:unknown): FieldIssue[] {
  if(!Array.isArray(detail))return [];
  return detail.flatMap(item=>{
    if(!item||typeof item!=="object"||typeof item.msg!=="string"||!Array.isArray(item.loc))return [];
    const path=item.loc.filter((p:unknown)=>typeof p==="string"||typeof p==="number");
    if(["body","query","path"].includes(path[0]))path.shift();
    return [{path,message:item.msg.replace(/^Value error, /,"")}];
  });
}
const numeric=(value:string|boolean|undefined):number|null=>typeof value==="string"&&value.trim()!==""&&Number.isFinite(Number(value))?Number(value):null;
export function wallDraftSummary(values:Record<string,string|boolean>,openings:OpeningDraft[]):{text:string;issues:FieldIssue[]} {
  const coordinates=["start_x_mm","start_z_mm","end_x_mm","end_z_mm"].map(k=>numeric(values[k]));
  const height=numeric(values.wall_height_mm),issues:FieldIssue[]=[];
  let text="Enter wall coordinates to see span and direction.";
  if(coordinates.every(v=>v!==null)){
    const [ax,ay,bx,by]=coordinates as number[];
    const span=Math.hypot(bx-ax,by-ay),angle=(Math.atan2(by-ay,bx-ax)*180/Math.PI+360)%360;
    text=`Draft span ${span.toFixed(1)} mm · direction ${angle.toFixed(1)}° from east${height===null?"":` · height ${height} mm`}.`;
    if(span<300)issues.push({path:["end_x_mm"],message:"Wall must be at least 300 mm long. Adjust either end coordinate."});
  }
  openings.forEach((opening,index)=>{
    const sill=numeric(opening.sill_height_mm),clear=numeric(opening.height_mm),head=numeric(opening.head_height_mm);
    if(sill!==null&&clear!==null){
      const expected=sill+clear;
      if(head!==null&&Math.abs(head-expected)>.01)
        issues.push({path:["openings",index,"head_height_mm"],message:`Head must equal sill + clear height (${expected} mm). Clear the head field to derive it automatically.`});
      if(height!==null&&(head??expected)>height)
        issues.push({path:["openings",index,"head_height_mm"],message:`Opening head (${head??expected} mm) exceeds wall height (${height} mm). Adjust the sill, clear height or wall height.`});
    }
  });
  return {text,issues};
}
export function trussDraftSummary(values:Record<string,string|boolean>):string {
  const quantity=numeric(values.quantity),spacing=numeric(values.spacing_mm),span=numeric(values.span_mm),pitch=numeric(values.pitch_deg);
  if(quantity===null||spacing===null)return "Enter quantity and spacing to see layout length.";
  const layout=(quantity-1)*spacing;
  return `Draft layout length ${layout.toFixed(1)} mm between first and last origins${span===null?"":` · span ${span} mm`}${pitch===null?"":` · pitch ${pitch}°`}. `+
    (values.truss_type==="custom"?"Custom CSV defines node elevations and physical members.":"Template webs are generated automatically; geometry remains subject to supplier review.");
}

type Stage="Draft"|"Validated"|"Previewed"|"Committed";
type Control=HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement;
export interface FormGroup {title:string;fields:string[];hint?:string}

/** Groups existing controls and associates local/server feedback with their fields. */
export class FormGuidance {
  private root:HTMLElement;
  private form:HTMLFormElement;
  private kind:"wall"|"truss";
  private summary:HTMLElement;
  private derived:HTMLOutputElement;
  private steps:HTMLOListElement;
  private status:HTMLElement;
  private attempted=false;
  private stage:Stage="Draft";
  private currentIssues:FieldIssue[]=[];
  constructor(root:HTMLElement,form:HTMLFormElement,kind:"wall"|"truss",groups:FormGroup[]){
    this.root=root;this.form=form;this.kind=kind;
    form.className="guided-form";form.noValidate=true;
    groups.forEach((group,index)=>{
      const section=document.createElement("fieldset");section.className="form-section form-grid";
      const legend=document.createElement("legend");legend.textContent=`${index+1}. ${group.title}`;section.append(legend);
      if(group.hint){const hint=document.createElement("p");hint.className="notice full";hint.textContent=group.hint;section.append(hint);}
      for(const name of group.fields){const label=form.querySelector(`[name="${name}"]`)?.closest("label");if(label)section.append(label);}
      form.append(section);
    });
    this.derived=document.createElement("output");this.derived.id=`${kind}-derived`;this.derived.className="derived-values";form.prepend(this.derived);
    this.summary=document.createElement("div");this.summary.id=`${kind}-field-errors`;this.summary.className="form-error-summary";
    this.summary.setAttribute("role","alert");this.summary.hidden=true;root.insertBefore(this.summary,form);
    const review=document.createElement("fieldset");review.className="form-section review-section";
    const legend=document.createElement("legend");legend.textContent="Review and save";review.append(legend);
    this.steps=document.createElement("ol");this.steps.className="review-steps";this.steps.setAttribute("aria-label","Draft progress");
    for(const stage of ["Draft","Validated","Previewed","Committed"]){const step=document.createElement("li");step.dataset.stage=stage;step.textContent=stage;this.steps.append(step);}
    this.status=document.createElement("p");this.status.id=`${kind}-review-stage`;this.status.setAttribute("role","status");review.append(this.steps,this.status);
    const actions=root.querySelector(".button-row")!;const result=root.querySelector(`#${kind}-result`)!;
    result.setAttribute("aria-live","polite");review.append(actions,result);root.append(review);
    this.refreshFields();this.setStage("Draft");
  }
  private controls():Control[]{return Array.from(this.root.querySelectorAll<Control>("input[name],select[name],textarea[name]"));}
  refreshFields():void {
    for(const input of this.controls()){
      const opening=input.closest<HTMLElement>("[data-opening]");
      input.id ||= opening?`${this.kind}-opening-${opening.dataset.opening}-${input.name}`:`${this.form.id}-${input.name}`;
      if(input instanceof HTMLInputElement&&input.type==="number"){
        input.step=["level","quantity","plies","nog_count"].includes(input.name)?"1":"any";
        input.required=!["nog_spacing_mm","head_height_mm"].includes(input.name);
      }
      let feedback=this.root.querySelector<HTMLElement>(`#${input.id}-error`);
      if(!feedback){feedback=document.createElement("span");feedback.id=`${input.id}-error`;feedback.className="field-error";feedback.hidden=true;input.closest("label")!.append(feedback);}
      const described=new Set((input.getAttribute("aria-describedby")??"").split(" ").filter(Boolean));described.add(feedback.id);
      input.setAttribute("aria-describedby",[...described].join(" "));
    }
  }
  private resolve(path:FieldIssue["path"]):Control|null {
    if(path[0]==="openings"&&typeof path[1]==="number")return this.controls().find(input=>
      input.closest<HTMLElement>("[data-opening]")?.dataset.opening===String(path[1])&&input.name===path[2])??null;
    const name=path[0]==="nodes"?"nodes_csv":path[0]==="members"?"members_csv":path[0];
    // Names come from server paths; compare values instead of interpolating selectors.
    return this.controls().find(input=>input.name===name&&!input.closest("[data-opening]"))??null;
  }
  private nativeIssues():FieldIssue[]{
    return this.controls().flatMap(input=>{
      if(input.closest(".custom-truss[hidden]")||input.validity.valid)return [];
      const opening=input.closest<HTMLElement>("[data-opening]");
      const path=opening?["openings",Number(opening.dataset.opening),input.name]:[input.name];
      const label=input.closest("label")?.querySelector("span")?.textContent??input.name;
      return [{path,message:input.validity.valueMissing?`${label} is required.`:input.validationMessage}];
    });
  }
  values():Record<string,string|boolean>{return Object.fromEntries(Array.from(this.form.querySelectorAll<Control>("[name]")).map(input=>
    [input.name,input instanceof HTMLInputElement&&input.type==="checkbox"?input.checked:input.value]));}
  refresh(openings:OpeningDraft[]=[]):void {
    this.refreshFields();
    const values=this.values(),wall=this.kind==="wall"?wallDraftSummary(values,openings):null;
    this.derived.textContent=wall?.text??trussDraftSummary(values);
    this.currentIssues=[...this.nativeIssues(),...(wall?.issues??[])];this.renderIssues();
  }
  validate(openings:OpeningDraft[]=[]):void {
    this.attempted=true;this.refresh(openings);
    if(this.currentIssues.length){this.resolve(this.currentIssues[0].path)?.focus();throw new FormInputError(this.currentIssues);}
  }
  showError(error:unknown,retainedPreview=false):void {
    this.attempted=true;
    const detail=error&&typeof error==="object"&&"detail" in error?error.detail:null;
    const issues=error instanceof FormInputError?error.issues:validationIssues(detail);
    this.currentIssues=issues.length?issues:[{path:[],message:error instanceof Error?error.message:String(error)}];
    this.renderIssues();
    if(issues.length&&error&&typeof error==="object"&&"requestId" in error&&typeof error.requestId==="string")
      this.summary.append(document.createTextNode(`Request reference: ${error.requestId}`));
    this.setStage(retainedPreview?"Previewed":"Draft",retainedPreview?
      "Save failed. The current preview is retained for a retry; preview again if the home has changed.":"Review the errors, then preview again.");
    this.resolve(this.currentIssues[0].path)?.focus();
  }
  private renderIssues():void {
    this.root.querySelectorAll<HTMLElement>(".field-error").forEach(error=>{error.hidden=true;error.textContent="";});
    this.controls().forEach(input=>input.removeAttribute("aria-invalid"));
    const list=document.createElement("ul");
    for(const issue of this.currentIssues){
      const input=this.resolve(issue.path);const item=document.createElement("li");
      if(input){
        input.setAttribute("aria-invalid","true");const feedback=this.root.querySelector<HTMLElement>(`#${input.id}-error`)!;
        feedback.hidden=false;feedback.textContent+=(feedback.textContent?" ":"")+issue.message;
        const link=document.createElement("a");link.href=`#${input.id}`;link.textContent=issue.message;link.addEventListener("click",event=>{event.preventDefault();input.focus();});item.append(link);
      }else item.textContent=issue.message;
      list.append(item);
    }
    this.summary.hidden=!this.attempted||!this.currentIssues.length;
    this.summary.replaceChildren(document.createTextNode("Review these fields before previewing: "),list);
  }
  edited(openings:OpeningDraft[]=[]):void {
    const stale=this.stage==="Previewed";this.setStage("Draft",stale?"Draft changed. The previous preview can no longer be saved.":undefined);this.refresh(openings);
  }
  reset(openings:OpeningDraft[]=[]):void {this.attempted=false;this.setStage("Draft");this.refresh(openings);}
  invalidate():void {if(this.stage==="Previewed")this.setStage("Draft","Preview cleared. Preview again before saving.");}
  success(stage:"Previewed"|"Committed"):void {this.attempted=false;this.currentIssues=[];this.renderIssues();this.setStage(stage);}
  setStage(stage:Stage,detail?:string):void {
    this.stage=stage;
    const stages=["Draft","Validated","Previewed","Committed"];
    for(const step of this.steps.children){
      const item=step as HTMLElement;const active=item.dataset.stage===stage;
      item.toggleAttribute("data-current",active);if(active)item.setAttribute("aria-current","step");else item.removeAttribute("aria-current");
      item.textContent=`${stages.indexOf(item.dataset.stage!)<stages.indexOf(stage)?"✓ ":""}${item.dataset.stage}${active?" (current)":""}`;
    }
    this.status.textContent=detail??{Draft:"Draft only. Saved geometry is unchanged.",Validated:"Geometry validated; review the preview before saving.",Previewed:"Validated preview is ready. Inspect it before committing.",Committed:"Saved to this home's current revision."}[stage];
  }
}
