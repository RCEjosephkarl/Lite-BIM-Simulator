import { downloadBom, fetchModel } from "./api";
import { Viewer } from "./scene";
import { Panel } from "./ui";
import { DEFAULT_PARAMS } from "./types";
import type { ColorMode, ModelParams } from "./types";

const viewport = document.getElementById("viewport")!;
const panelRoot = document.getElementById("panel")!;

const viewer = new Viewer(viewport);
let mode: ColorMode = "function";
let params: ModelParams = { ...DEFAULT_PARAMS, ...paramsFromUrl() };

/** Seed generation params from the URL, e.g. /?roof=hip&storeys=2&wind_speed=48 */
function paramsFromUrl(): Partial<ModelParams> {
  const q = new URLSearchParams(location.search);
  const out: Partial<ModelParams> = {};
  const storeys = Number(q.get("storeys"));
  if (storeys >= 1 && storeys <= 3) out.storeys = storeys;
  const roof = q.get("roof");
  if (roof === "gable" || roof === "hip") out.roof = roof;
  if (q.get("wind_zone")) out.wind_zone = q.get("wind_zone")!;
  const speed = Number(q.get("wind_speed"));
  if (q.get("wind_speed") && Number.isFinite(speed)) out.wind_speed = speed;
  if (q.get("snow_zone")) out.snow_zone = q.get("snow_zone")!;
  const gs = Number(q.get("gable_spacing"));
  if (gs >= 300 && gs <= 1200) out.gable_spacing = gs;
  return out;
}

const panel = new Panel(panelRoot, {
  onParams(patch) {
    params = { ...params, ...patch };
    void load();
  },
  onColorMode(m) {
    mode = m;
    viewer.setColorMode(m);
  },
  onCategory(category, visible) {
    viewer.setCategoryVisible(category, visible);
  },
  onAutoRotate(on) {
    viewer.setAutoRotate(on);
  },
  onExport() {
    downloadBom();
  },
});

panel.syncParams(params);
viewer.onPick = (el, type) => panel.showElement(el, type);

let loadSeq = 0;
async function load(): Promise<void> {
  const seq = ++loadSeq;
  viewport.classList.add("loading");
  try {
    const model = await fetchModel(params);
    if (seq !== loadSeq) return; // a newer request superseded this one
    viewer.buildModel(model, mode);
    panel.setModel(model);
  } finally {
    if (seq === loadSeq) viewport.classList.remove("loading");
  }
}

void load();
