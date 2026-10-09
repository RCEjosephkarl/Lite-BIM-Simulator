import type { BimElement } from "./types";
import type { SectionState } from "./workspaceState";

export type Point3 = [number, number, number];
export interface Bounds3 { minimum: Point3; maximum: Point3 }
export function memberEndpoints(m:BimElement): [Point3,Point3] {
  const dx=Math.cos(m.yaw)*Math.cos(m.pitch)*m.length_mm/2;
  const dy=Math.sin(m.yaw)*Math.cos(m.pitch)*m.length_mm/2;
  const dz=Math.sin(m.pitch)*m.length_mm/2;
  return [[m.cx-dx,m.cy-dy,m.cz-dz],[m.cx+dx,m.cy+dy,m.cz+dz]];
}
export function memberCorners(m:BimElement): Point3[] {
  const cy=Math.cos(m.yaw),sy=Math.sin(m.yaw),cp=Math.cos(m.pitch),sp=Math.sin(m.pitch);
  const along=[cy*cp*m.length_mm/2,sy*cp*m.length_mm/2,sp*m.length_mm/2];
  const across=[-sy*m.w_mm/2,cy*m.w_mm/2,0];
  const up=[-cy*sp*m.h_mm/2,-sy*sp*m.h_mm/2,cp*m.h_mm/2];
  return Array.from({length:8},(_,i)=>[m.cx,m.cy,m.cz].map((n,k)=>n+((i&1)?1:-1)*along[k]
    +((i&2)?1:-1)*across[k]+((i&4)?1:-1)*up[k]) as Point3);
}
export function clippedCorners(m:BimElement,section:SectionState|null): Point3[] {
  const points=memberCorners(m);if(!section)return points;
  const axis={x:0,y:1,z:2}[section.axis],sign=section.keep==="upper"?1:-1;
  const distance=(p:Point3)=>sign*(p[axis]-section.position_mm);
  const kept=points.filter(p=>distance(p)>=-.000001);
  for(let i=0;i<8;i++)for(const bit of [1,2,4]){
    const j=i^bit;if(j<=i)continue;
    const a=points[i],b=points[j],da=distance(a),db=distance(b);
    if((da<0&&db>0)||(da>0&&db<0)){
      const t=da/(da-db);kept.push(a.map((n,k)=>n+t*(b[k]-n)) as Point3);
    }
  }
  return kept;
}
export function boundsOf(members:BimElement[],section:SectionState|null=null): Bounds3|null {
  const minimum:Point3=[Infinity,Infinity,Infinity],maximum:Point3=[-Infinity,-Infinity,-Infinity];
  for(const m of members)for(const p of clippedCorners(m,section))for(let k=0;k<3;k++){
    minimum[k]=Math.min(minimum[k],p[k]);maximum[k]=Math.max(maximum[k],p[k]);
  }
  return Number.isFinite(minimum[0])?{minimum,maximum}:null;
}
export function sectionContains(point:Point3,section:SectionState|null): boolean {
  if(!section)return true;
  const coordinate=point[{x:0,y:1,z:2}[section.axis]];
  return section.keep==="upper"?coordinate>=section.position_mm-.001:coordinate<=section.position_mm+.001;
}
export function wallMetrics(members:BimElement[]): {span_mm:number;direction_deg:number;elevation_mm:number;height_mm:number}|null {
  const horizontal=members.find(m=>m.segment_id&&Math.abs(m.pitch)<.01);
  if(!horizontal)return null;
  const cy=Math.cos(horizontal.yaw),sy=Math.sin(horizontal.yaw);
  let low=Infinity,high=-Infinity;
  for(const m of members)for(const p of memberCorners(m)){
    const station=p[0]*cy+p[1]*sy;low=Math.min(low,station);high=Math.max(high,station);
  }
  const bounds=boundsOf(members)!;
  return {span_mm:high-low,direction_deg:((horizontal.yaw*180/Math.PI)%360+360)%360,
    elevation_mm:bounds.minimum[2],height_mm:bounds.maximum[2]-bounds.minimum[2]};
}
