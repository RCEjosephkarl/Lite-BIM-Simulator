import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { elementColor } from "./colors";
import type { BimElement, BimModel, ColorMode, ElementType } from "./types";

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

export class Viewer {
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly renderer: THREE.WebGLRenderer;
  readonly controls: OrbitControls;
  onPick: (el: BimElement | null, type: ElementType | null) => void = () => {};

  private typeMeshes = new Map<string, TypeMesh>();
  private modelGroup = new THREE.Group();
  private mode: ColorMode = "function";
  private selected: { mesh: THREE.InstancedMesh; id: number } | null = null;
  private raycaster = new THREE.Raycaster();
  private downAt = new THREE.Vector2();

  constructor(container: HTMLElement) {
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
    container.appendChild(this.renderer.domElement);

    // orbit-rotate (left drag), pan (right drag), zoom (wheel)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(10.7, 1.5, -9.1);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02;

    this.addLightsAndGround();
    this.scene.add(this.modelGroup);

    addEventListener("resize", () => {
      this.camera.aspect = container.clientWidth / container.clientHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(container.clientWidth, container.clientHeight);
    });
    this.renderer.domElement.addEventListener("pointerdown", (e) =>
      this.downAt.set(e.clientX, e.clientY));
    this.renderer.domElement.addEventListener("pointerup", (e) => {
      if (this.downAt.distanceTo(new THREE.Vector2(e.clientX, e.clientY)) < 5)
        this.pick(e);
    });

    const animate = () => {
      requestAnimationFrame(animate);
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
    };
    animate();
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
    this.selected = null;
    this.modelGroup.clear();
    this.typeMeshes.forEach((tm) => {
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
  }

  setAutoRotate(on: boolean): void {
    this.controls.autoRotate = on;
    this.controls.autoRotateSpeed = 1.5;
  }

  setColorMode(mode: ColorMode): void {
    this.mode = mode;
    this.typeMeshes.forEach(({ mesh, type, elements }) => {
      elements.forEach((el, i) =>
        mesh.setColorAt(i, elementColor(el, type, mode)));
      mesh.instanceColor!.needsUpdate = true;
    });
    this.reapplyHighlight();
  }

  setCategoryVisible(category: string, visible: boolean): void {
    this.typeMeshes.forEach((tm) => {
      if (tm.type.category === category) tm.mesh.visible = visible;
    });
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
    const hit = hits.find((h) => h.instanceId !== undefined);
    if (!hit) {
      this.onPick(null, null);
      return;
    }
    const tm = this.typeMeshes.get((hit.object as THREE.InstancedMesh).name)!;
    const id = hit.instanceId!;
    this.selected = { mesh: tm.mesh, id };
    tm.mesh.setColorAt(id, new THREE.Color("#ffffff"));
    tm.mesh.instanceColor!.needsUpdate = true;
    this.onPick(tm.elements[id], tm.type);
  }

  private clearHighlight(): void {
    if (!this.selected) return;
    const tm = this.typeMeshes.get(this.selected.mesh.name)!;
    tm.mesh.setColorAt(this.selected.id,
      elementColor(tm.elements[this.selected.id], tm.type, this.mode));
    tm.mesh.instanceColor!.needsUpdate = true;
    this.selected = null;
  }

  private reapplyHighlight(): void {
    if (!this.selected) return;
    this.selected.mesh.setColorAt(this.selected.id, new THREE.Color("#ffffff"));
    this.selected.mesh.instanceColor!.needsUpdate = true;
  }
}
