import type { BimElement } from "./types";

export interface AssemblyGroup {
  key: string;
  level: number;
  source: string;
  sourceId: string;
  branch: string;
  label: string;
  members: BimElement[];
}

export function assemblyKey(member: BimElement): string {
  const kind=member.segment_id?"wall":member.truss_id?"truss":member.physical_member_id?"cut":"row";
  return JSON.stringify([member.storey,member.source,member.source_id,kind,
    member.segment_id||member.truss_id||member.physical_member_id||member.id]);
}

export function memberSearch(member:BimElement):string {
  return [member.type_code,member.member_role,member.size,member.panel_id,member.opening_id,
    member.joint_id,member.physical_member_id,member.start_node,member.end_node,member.id].join(" ").toLowerCase();
}

/** Namespace first: equal wall/truss labels in different sources stay distinct. */
export function assemblyGroups(members:BimElement[]):AssemblyGroup[] {
  const groups=new Map<string,AssemblyGroup>();
  for(const member of members){
    const key=assemblyKey(member);
    let group=groups.get(key);
    if(!group){
      const assembly=member.segment_id||member.truss_id||member.physical_member_id||member.id;
      group={key,level:member.storey,source:member.source,sourceId:member.source_id,
        branch:member.segment_id?"Walls":member.truss_id?`Truss layout ${member.layout_id||member.source_id||"generated"}`:"Other members",
        label:`L${member.storey} · ${member.segment_label||member.truss_label||member.type_code} · ${assembly} · ${member.source}`,
        members:[]};groups.set(key,group);
    }
    group.members.push(member);
  }
  return [...groups.values()];
}

export type CameraAction="pan-left"|"pan-right"|"pan-up"|"pan-down"|
  "orbit-left"|"orbit-right"|"orbit-up"|"orbit-down"|"zoom-in"|"zoom-out"|"fit";
export function cameraKey(event:Pick<KeyboardEvent,"key"|"shiftKey"|"altKey"|"ctrlKey"|"metaKey">):CameraAction|null {
  if(event.altKey||event.ctrlKey||event.metaKey)return null;
  const direction:Record<string,string>={ArrowLeft:"left",ArrowRight:"right",ArrowUp:"up",ArrowDown:"down"};
  if(direction[event.key])return `${event.shiftKey?"orbit":"pan"}-${direction[event.key]}` as CameraAction;
  if(event.key==="+"||event.key==="=")return "zoom-in";
  if(event.key==="-"||event.key==="_")return "zoom-out";
  return event.key==="Home"?"fit":null;
}
