import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { elementColor } from "./colors";
import type {
  BimElement, BimModel, ColorMode, ElementType, PickInfo,
} from "./types";
import type { CameraState, SectionState } from "./workspaceState";
import { boundsOf, clippedCorners, sectionContains } from "./memberGeometry";
import { cameraKey } from "./modelHierarchy";
import type { CameraAction } from "./modelHierarchy";

const MM = 1 / 1000; // backend units are mm; scene units are metres

/** Backend (cx east, cy north, cz up) -> three.js (x, y up, z south). */
function toScene(el: BimElement, v: THREE.Vector3): THREE.Vector3 {
  return v.set(el.cx * MM, el.cz * MM, -el.cy * MM);
}

interface TypeMesh {
  mesh: THREE.InstancedMesh;
  type: ElementType;
  elements: BimElement[]; // index = instanceId
}

const CLICKED_COLOR = new THREE.Color("#ffffff");
const GROUP_COLOR = new THREE.Color("#ffe08a"); // rest of the wall/truss

export class Viewer {
  readonly scene = new THREE.Scene();
  camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  readonly renderer: THREE.WebGLRenderer;
  controls!: OrbitControls;
  onPick: (info: PickInfo | null) => void = () => {};
  onCameraChange: (camera: CameraState) => void = () => {};
  onOrbitStart: () => void = () => {};
  onFit: () => void = () => this.fit();

  private typeMeshes = new Map<string, TypeMesh>();
  private modelGroup = new THREE.Group();
  private mode: ColorMode = "function";
  // highlighted instances; first entry is the clicked member
  private selected: { tm: TypeMesh; id: number }[] = [];
  private raycaster = new THREE.Raycaster();
  private downAt = new THREE.Vector2();
  private layers: Record<string, boolean> = {};
  private section:SectionState|null=null;
  private container:HTMLElement;
  private dimensionGroup = new THREE.Group();
  private dimensionLabels: {element:HTMLSpanElement;position:THREE.Vector3}[] = [];
  private dimensionsEnabled = false;
  private animationFrame: number | null = null;

  get renderPending(): boolean { return this.animationFrame !== null; }

  /** Coalesce scene changes; controls request subsequent damping/rotation frames. */
  private requestRender(): void {
    if (this.animationFrame !== null) return;
    this.animationFrame = requestAnimationFrame(() => {
      this.animationFrame = null;
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
      this.projectDimensionLabels();
      if (this.controls.autoRotate) this.requestRender();
    });
  }

  constructor(container: HTMLElement) {
    this.container=container;
    this.scene.background = new THREE.Color("#cfe2ee");
    this.scene.fog = new THREE.Fog("#cfe2ee", 80, 220);

    this.camera = new THREE.PerspectiveCamera(
      50, container.clientWidth / container.clientHeight, 0.1, 500);
    this.camera.position.set(30, 18, 12);

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.localClippingEnabled=true;
    container.appendChild(this.renderer.domElement);
    this.renderer.domElement.tabIndex=0;
    this.renderer.domElement.setAttribute("role","region");
    this.renderer.domElement.setAttribute("aria-label","3D home model");
    this.renderer.domElement.setAttribute("aria-describedby","camera-help");
    this.renderer.domElement.addEventListener("keydown",event=>{
      const action=cameraKey(event);
      if(action){event.preventDefault();this.cameraAction(action);}
    });

    // orbit-rotate (left drag), pan (right drag), zoom (wheel)
    this.connectControls(new THREE.Vector3(10.7,1.5,-9.1));

    this.addLightsAndGround();
    this.scene.add(this.modelGroup);
    this.modelGroup.name="diagnostic-model";
    this.scene.add(this.dimensionGroup);

    const resize = () => {
      if (!container.clientWidth || !container.clientHeight) return;
      const aspect=container.clientWidth/container.clientHeight;
      if(this.camera instanceof THREE.PerspectiveCamera)this.camera.aspect=aspect;
      else {const half=(this.camera.top-this.camera.bottom)/2;this.camera.left=-half*aspect;this.camera.right=half*aspect;}
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(container.clientWidth, container.clientHeight);
      this.requestRender();
    };
    new ResizeObserver(resize).observe(container);
    this.renderer.domElement.addEventListener("pointerdown", (e) =>
      this.downAt.set(e.clientX, e.clientY));
    this.renderer.domElement.addEventListener("pointerup", (e) => {
      if (this.downAt.distanceTo(new THREE.Vector2(e.clientX, e.clientY)) < 5)
        this.pick(e);
    });

    this.renderer.domElement.addEventListener("webglcontextrestored", () => this.requestRender());
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) this.requestRender();
    });
    this.requestRender();
  }

  private connectControls(target:THREE.Vector3):void {
    const rotating=this.controls?.autoRotate??false;
    this.controls?.dispose();
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.target.copy(target);this.controls.enableDamping=true;this.controls.maxPolarAngle=Math.PI;
    this.controls.autoRotate=rotating;this.controls.autoRotateSpeed=1.5;
    this.controls.addEventListener("change",()=>{
      this.onCameraChange(this.cameraState());
      this.requestRender();
    });
    this.controls.addEventListener("start",()=>this.onOrbitStart());
    this.controls.update();
    this.requestRender();
  }

  cameraAction(action:CameraAction):void {
    if(action==="fit"){this.onFit();return;}
    this.camera.updateMatrixWorld();
    const right=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,0);
    const up=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,1);
    const distance=this.camera.position.distanceTo(this.controls.target);
    if(action.startsWith("zoom")){
      this.camera.zoom=THREE.MathUtils.clamp(this.camera.zoom*Math.exp(action==="zoom-in"?.12:-.12),.05,100);
      this.camera.updateProjectionMatrix();
    }else if(action.startsWith("pan")){
      const height=this.camera instanceof THREE.OrthographicCamera?(this.camera.top-this.camera.bottom)/this.camera.zoom:
        2*distance*Math.tan(THREE.MathUtils.degToRad(this.camera.getEffectiveFOV()/2));
      const direction=action.endsWith("left")||action.endsWith("right")?right:up;
      const sign=action.endsWith("left")||action.endsWith("down")?-1:1;
      const offset=direction.multiplyScalar(sign*height*.05);
      this.camera.position.add(offset);this.controls.target.add(offset);
    }else{
      const axis=action.endsWith("left")||action.endsWith("right")?up:right;
      const angle=(action.endsWith("left")||action.endsWith("up")?1:-1)*.09;
      const rotation=new THREE.Quaternion().setFromAxisAngle(axis,angle);
      const offset=this.camera.position.clone().sub(this.controls.target).applyQuaternion(rotation);
      this.camera.position.copy(this.controls.target).add(offset);
      this.camera.up.applyQuaternion(rotation).normalize();
      this.onOrbitStart();
    }
    this.connectControls(this.controls.target.clone());
    this.onCameraChange(this.cameraState());
  }
  setSection(section:SectionState|null):void {
    this.section=section;
    const normal=section?{x:new THREE.Vector3(1,0,0),y:new THREE.Vector3(0,0,-1),z:new THREE.Vector3(0,1,0)}[section.axis]:null;
    const sign=section?.keep==="lower"?-1:1;
    const plane=normal&&new THREE.Plane(normal.multiplyScalar(sign),-sign*section!.position_mm*MM);
    this.typeMeshes.forEach(({mesh})=>{
      const material=mesh.material as THREE.MeshStandardMaterial;
      material.clippingPlanes=plane?[plane]:[];material.clipShadows=true;material.needsUpdate=true;
    });
    this.requestRender();
  }

  private addLightsAndGround(): void {
    this.scene.add(new THREE.HemisphereLight("#e8f2ff", "#6b7a5e", 0.9));
    const sun = new THREE.DirectionalLight("#fff6e0", 1.6);
    sun.position.set(35, 40, 25);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const cam = sun.shadow.camera;
    cam.left = -30; cam.right = 30; cam.top = 30; cam.bottom = -30;
    cam.near = 5; cam.far = 120;
    sun.shadow.bias = -0.0004;
    this.scene.add(sun);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(300, 300),
      new THREE.MeshStandardMaterial({ color: "#b5c4a1", roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.13;
    ground.receiveShadow = true;
    this.scene.add(ground);

    const grid = new THREE.GridHelper(120, 120, 0x90a080, 0xa6b694);
    grid.position.y = -0.12;
    this.scene.add(grid);
  }

  buildModel(model: BimModel, mode: ColorMode): void {
    this.mode = mode;
    this.selected = [];
    this.modelGroup.clear();
    this.typeMeshes.forEach((tm) => {
      tm.mesh.dispose();
      tm.mesh.geometry.dispose();
      (tm.mesh.material as THREE.Material).dispose();
    });
    this.typeMeshes.clear();

    const byType = new Map<string, BimElement[]>();
    for (const el of model.elements) {
      (byType.get(el.type_code) ?? byType.set(el.type_code, []).get(el.type_code)!)
        .push(el);
    }

    const pos = new THREE.Vector3();
    const quat = new THREE.Quaternion();
    const scl = new THREE.Vector3();
    const mat = new THREE.Matrix4();
    const euler = new THREE.Euler();

    for (const type of model.types) {
      const els = byType.get(type.code);
      if (!els?.length) continue;
      const geo = new THREE.BoxGeometry(1, 1, 1);
      const material = new THREE.MeshStandardMaterial({ roughness: 0.85 });
      const mesh = new THREE.InstancedMesh(geo, material, els.length);
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.name = type.code;
      mesh.visible = this.layers[type.category] !== false;
      els.forEach((el, i) => {
        toScene(el, pos);
        // yaw about vertical, then pitch about the member's horizontal axis
        euler.set(0, el.yaw, el.pitch, "YZX");
        quat.setFromEuler(euler);
        scl.set(el.length_mm * MM, el.h_mm * MM, el.w_mm * MM);
        mat.compose(pos, quat, scl);
        mesh.setMatrixAt(i, mat);
        mesh.setColorAt(i, elementColor(el, type, mode));
      });
      mesh.instanceMatrix.needsUpdate = true;
      this.modelGroup.add(mesh);
      this.typeMeshes.set(type.code, { mesh, type, elements: els });
    }
    this.onPick(null);
    this.setSection(this.section);
  }

  setAutoRotate(on: boolean): void {
    this.controls.autoRotate = on;
    this.controls.autoRotateSpeed = 1.5;
    this.requestRender();
  }

  /** Display-space bounds are deliberately separate from fabrication cuts. */
  setDimensions(enabled:boolean):void {this.dimensionsEnabled=enabled;this.updateDimensions();}
  private updateDimensions():void {
    for(const child of this.dimensionGroup.children){
      const line=child as THREE.LineSegments;line.geometry.dispose();(line.material as THREE.Material).dispose();
    }
    this.dimensionGroup.clear();this.dimensionLabels.forEach(label=>label.element.remove());this.dimensionLabels=[];
    this.requestRender();
    if(!this.dimensionsEnabled)return;
    const members=this.selected.length?this.selected.map(({tm,id})=>tm.elements[id]):
      [...this.typeMeshes.values()].filter(t=>t.mesh.visible).flatMap(t=>t.elements);
    const bounds=boundsOf(members,this.section);if(!bounds)return;
    const low=bounds.minimum,high=bounds.maximum;
    const offset=Math.max(...high.map((v,i)=>v-low[i]),1000)*.04;
    const lines:number[]=[];
    const convert=(p:number[])=>new THREE.Vector3(p[0]*MM,p[2]*MM,-p[1]*MM);
    for(let axis=0;axis<3;axis++){
      const a=[low[0]-offset,low[1]-offset,low[2]-offset],b=[...a];
      a[axis]=low[axis];b[axis]=high[axis];
      const start=convert(a),end=convert(b);lines.push(...start.toArray(),...end.toArray());
      const element=document.createElement("span");element.className="dimension-label";
      element.textContent=`${["East","North","Height"][axis]} extent ${(high[axis]-low[axis]).toFixed(1)} mm`;
      this.container.appendChild(element);this.dimensionLabels.push({element,position:start.clone().lerp(end,.5)});
    }
    const geometry=new THREE.BufferGeometry();geometry.setAttribute("position",new THREE.Float32BufferAttribute(lines,3));
    const line=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:0xffe08a,depthTest:false,transparent:true,opacity:.9}));
    line.renderOrder=10;this.dimensionGroup.add(line);
    this.projectDimensionLabels();
  }
  private projectDimensionLabels():void {
    for(const {element,position} of this.dimensionLabels){
      const p=position.clone().project(this.camera);
      element.hidden=p.z < -1 || p.z > 1 || Math.abs(p.x)>1 || Math.abs(p.y)>1;
      element.style.left=`${(p.x+1)*this.container.clientWidth/2}px`;
      element.style.top=`${(1-p.y)*this.container.clientHeight/2}px`;
    }
  }

  setColorMode(mode: ColorMode): void {
    this.mode = mode;
    this.typeMeshes.forEach(({ mesh, type, elements }) => {
      elements.forEach((el, i) =>
        mesh.setColorAt(i, elementColor(el, type, mode)));
      mesh.instanceColor!.needsUpdate = true;
    });
    this.reapplyHighlight();
    this.requestRender();
  }

  setCategories(layers: Record<string, boolean>): void {
    this.layers = layers;
    this.typeMeshes.forEach((tm) => {
      tm.mesh.visible = layers[tm.type.category] !== false;
    });
    if (this.selected.some(item => !item.tm.mesh.visible)) {
      this.clearHighlight();
      this.onPick(null);
    }
    this.requestRender();
  }

  cameraState(): CameraState {
    return { position: this.camera.position.toArray() as CameraState["position"],
      target: this.controls.target.toArray() as CameraState["target"], near: this.camera.near, far: this.camera.far,
      projection:this.camera instanceof THREE.OrthographicCamera?"orthographic":"perspective",zoom:this.camera.zoom,
      ...(this.camera instanceof THREE.OrthographicCamera?{ortho_height:this.camera.top-this.camera.bottom}:{}),
      up:this.camera.up.toArray() as CameraState["up"] };
  }
  restoreCamera(state: CameraState): void {
    const aspect=this.container.clientWidth/this.container.clientHeight;
    this.camera=state.projection==="orthographic"?new THREE.OrthographicCamera(-state.ortho_height!*aspect/2,state.ortho_height!*aspect/2,state.ortho_height!/2,-state.ortho_height!/2,state.near,state.far)
      :new THREE.PerspectiveCamera(50,aspect,state.near,state.far);
    this.camera.position.fromArray(state.position); this.controls.target.fromArray(state.target);
    this.camera.up.fromArray(state.up??[0,1,0]);this.camera.zoom=state.zoom??1;
    this.camera.near=state.near;this.camera.far=state.far;this.camera.updateProjectionMatrix();
    this.connectControls(new THREE.Vector3().fromArray(state.target));
    const distance=this.camera.position.distanceTo(this.controls.target);
    const fog=this.scene.fog as THREE.Fog;fog.near=distance*1.5;fog.far=state.far;
  }

  fit(view: "iso" | "top" | "front" | "side" = "iso", selectionOnly=false): void {
    if (!this.typeMeshes.size) return;
    const members=selectionOnly?this.selected.map(({tm,id})=>tm.elements[id]):
      [...this.typeMeshes.values()].filter(t=>t.mesh.visible).flatMap(t=>t.elements);
    const extent=boundsOf(members,this.section);if(!extent)return;
    const bounds=new THREE.Box3(new THREE.Vector3(extent.minimum[0]*MM,extent.minimum[2]*MM,-extent.maximum[1]*MM),
      new THREE.Vector3(extent.maximum[0]*MM,extent.maximum[2]*MM,-extent.minimum[1]*MM));
    const center = bounds.getCenter(new THREE.Vector3());
    const radius = Math.max(bounds.getSize(new THREE.Vector3()).length() / 2, 1);
    const aspect=this.container.clientWidth/this.container.clientHeight;
    const halfFov = Math.min(THREE.MathUtils.degToRad(25),Math.atan(Math.tan(THREE.MathUtils.degToRad(25))*aspect));
    const distance = radius / Math.sin(halfFov) * 1.15;
    const direction = { iso: new THREE.Vector3(1, .7, 1), top: new THREE.Vector3(0, 1, 0),
      front: new THREE.Vector3(0, 0, 1), side: new THREE.Vector3(1, 0, 0) }[view].normalize();
    const orthoHalf=radius*1.15/Math.min(1,aspect);
    this.camera=view==="iso"?new THREE.PerspectiveCamera(50,aspect,.01,500)
      :new THREE.OrthographicCamera(-orthoHalf*aspect,orthoHalf*aspect,orthoHalf,-orthoHalf,.01,500);
    if(view==="top")this.camera.up.set(0,0,-1);
    this.camera.position.copy(center).addScaledVector(direction, distance);
    this.camera.near = Math.max(.01, radius / 1000);
    this.camera.far = Math.max(500, distance + radius * 6);
    this.camera.updateProjectionMatrix();
    this.connectControls(center);
    const fog = this.scene.fog as THREE.Fog;
    fog.near = distance + radius * 2;
    fog.far = distance + radius * 6;
  }

  selectElement(elementId: number): boolean {
    this.clearHighlight();
    for (const tm of this.typeMeshes.values()) {
      const index = tm.elements.findIndex(element => element.id === elementId);
      if (index >= 0 && tm.mesh.visible && clippedCorners(tm.elements[index],this.section).length) { this.select(tm, index); return true; }
    }
    this.onPick(null);
    this.updateDimensions();
    return false;
  }

  private pick(e: PointerEvent): void {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const visible = [...this.typeMeshes.values()]
      .filter((t) => t.mesh.visible).map((t) => t.mesh);
    const hits = this.raycaster.intersectObjects(visible, false);
    this.clearHighlight();
    const hit = hits.find((h) => h.instanceId !== undefined && sectionContains([h.point.x/MM,-h.point.z/MM,h.point.y/MM],this.section));
    if (!hit) {
      this.onPick(null);
      this.updateDimensions();
      return;
    }
    const tm = this.typeMeshes.get((hit.object as THREE.InstancedMesh).name)!;
    const id = hit.instanceId!;
    this.select(tm, id);
  }

  /** Real raycast/selection timing for an explicitly enabled profiling session. */
  profileRayPick(member:BimElement):{time_ms:number;hit:boolean} {
    this.camera.updateMatrixWorld();this.scene.updateMatrixWorld();
    const point=toScene(member,new THREE.Vector3()).project(this.camera);
    const bounds=this.renderer.domElement.getBoundingClientRect();
    const event={clientX:bounds.left+(point.x+1)*bounds.width/2,clientY:bounds.top+(1-point.y)*bounds.height/2} as PointerEvent;
    const start=performance.now();this.pick(event);
    return {time_ms:performance.now()-start,hit:this.selected.length>0};
  }

  private select(tm: TypeMesh, id: number): void {
    const el = tm.elements[id];

    // one click selects the whole wall-frame segment / truss the member
    // belongs to; members without either stay a single-element selection
    const groupKind: PickInfo["groupKind"] =
      el.segment_id ? "segment" : el.truss_id ? "truss" : "element";
    const groupId =
      groupKind === "segment" ? el.segment_id :
      groupKind === "truss" ? el.truss_id : "";
    this.selected = [{ tm, id }];
    const group: BimElement[] = [el];
    if (groupKind !== "element") {
      this.typeMeshes.forEach((other) => {
        other.elements.forEach((candidate, i) => {
          if (other === tm && i === id) return;
          const match = groupKind === "segment"
            ? candidate.segment_id === groupId
            : candidate.truss_id === groupId;
          if (match && candidate.storey === el.storey && candidate.source === el.source && candidate.source_id === el.source_id && other.mesh.visible && clippedCorners(candidate,this.section).length) {
            this.selected.push({ tm: other, id: i });
            group.push(candidate);
          }
        });
      });
    }
    this.reapplyHighlight();
    this.onPick({ element: el, type: tm.type, group, groupKind, groupId });
    this.updateDimensions();
  }

  private clearHighlight(): void {
    const touched = new Set<THREE.InstancedMesh>();
    for (const { tm, id } of this.selected) {
      tm.mesh.setColorAt(id, elementColor(tm.elements[id], tm.type, this.mode));
      touched.add(tm.mesh);
    }
    touched.forEach((mesh) => mesh.instanceColor!.needsUpdate = true);
    this.selected = [];
    this.requestRender();
  }

  private reapplyHighlight(): void {
    const touched = new Set<THREE.InstancedMesh>();
    this.selected.forEach(({ tm, id }, index) => {
      tm.mesh.setColorAt(id, index === 0 ? CLICKED_COLOR : GROUP_COLOR);
      touched.add(tm.mesh);
    });
    touched.forEach((mesh) => mesh.instanceColor!.needsUpdate = true);
    this.requestRender();
  }
}
