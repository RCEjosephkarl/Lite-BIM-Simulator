import type { Viewer } from "./scene";
import type { BimModel } from "./types";

function distribution(values:number[]):{samples:number;minimum:number;median:number;p95:number;maximum:number}|null {
  if(!values.length)return null;
  const sorted=[...values].sort((a,b)=>a-b);
  const mid=Math.floor(sorted.length/2);
  return {samples:sorted.length,minimum:sorted[0],median:sorted.length%2?sorted[mid]:(sorted[mid-1]+sorted[mid])/2,
    p95:sorted[Math.ceil(sorted.length*.95)-1],maximum:sorted.at(-1)!};
}

/** Optional console bridge used by the isolated profiler, never project writes. */
export function installDiagnostics(viewer:Viewer,getModel:()=>BimModel|null,rebuild:()=>void):void {
  const samples:Record<string,number[]>={build_ms:[],selection_ms:[],ray_pick_ms:[],frame_interval_ms:[],render_submit_ms:[]};
  const record=(key:string,time:number)=>{samples[key].push(time);if(samples[key].length>256)samples[key].shift();};
  const timed=<T>(key:string,operation:()=>T):T=>{const start=performance.now();try{return operation();}finally{record(key,performance.now()-start);}};
  const build=viewer.buildModel.bind(viewer),select=viewer.selectElement.bind(viewer),render=viewer.renderer.render.bind(viewer.renderer);
  viewer.buildModel=(...args)=>timed("build_ms",()=>build(...args));
  viewer.selectElement=(...args)=>timed("selection_ms",()=>select(...args));
  let lastFrame:number|undefined,renderCount=0;
  viewer.renderer.render=(...args)=>{
    const now=performance.now();if(lastFrame!==undefined)record("frame_interval_ms",now-lastFrame);lastFrame=now;
    renderCount++;
    timed("render_submit_ms",()=>render(...args));
  };
  const gl=viewer.renderer.getContext(),extension=gl.getExtension("WEBGL_debug_renderer_info");
  let createdBuffers=0,deletedBuffers=0;
  const createBuffer=gl.createBuffer.bind(gl),deleteBuffer=gl.deleteBuffer.bind(gl);
  gl.createBuffer=()=>{const buffer=createBuffer();if(buffer)createdBuffers++;return buffer;};
  gl.deleteBuffer=buffer=>{if(buffer)deletedBuffers++;deleteBuffer(buffer);};
  const bridge={
    reset(){for(const values of Object.values(samples))values.length=0;lastFrame=undefined;},
    rebuild,
    rotate(on:boolean){viewer.setAutoRotate(on);},
    select(id:number){return viewer.selectElement(id);},
    rayPick(id:number){
      const member=getModel()?.elements.find(member=>member.id===id);
      if(!member)throw new Error("Diagnostic member is missing from the displayed model");
      const result=viewer.profileRayPick(member);record("ray_pick_ms",result.time_ms);return result.hit;
    },
    snapshot(){
      const info=viewer.renderer.info;
      return {model_member_count:getModel()?.elements.length??0,render_pending:viewer.renderPending,instanced_meshes:viewer.scene.getObjectByName("diagnostic-model")?.children.length??0,
        timings:Object.fromEntries(Object.entries(samples).map(([key,values])=>[key,distribution(values)])),
        renderer:{geometries:info.memory.geometries,textures:info.memory.textures,programs:info.programs?.length??0,
          draw_calls:info.render.calls,triangles:info.render.triangles,render_count:renderCount,
          explicit_buffer_creates:createdBuffers,explicit_buffer_deletes:deletedBuffers,
          explicit_buffer_balance:createdBuffers-deletedBuffers,
          adapter:gl.getParameter(extension?extension.UNMASKED_RENDERER_WEBGL:gl.RENDERER)},
        camera:viewer.cameraState()};
    },
  };
  (window as unknown as {timberbimDiagnostics:typeof bridge}).timberbimDiagnostics=bridge;
}
