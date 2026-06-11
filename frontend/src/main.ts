import { downloadBom, fetchModel, paramsToQuery } from "./api";
import { Viewer } from "./scene";
import { Panel } from "./ui";
import { DEFAULT_PARAMS } from "./types";
import type { ColorMode, ModelParams } from "./types";

const viewport = document.getElementById("viewport")!;
const panelRoot = document.getElementById("panel")!;

const viewer = new Viewer(viewport);
let mode: ColorMode = "function";
let params: ModelParams = { ...DEFAULT_PARAMS, ...paramsFromUrl() };

/** Parse a JSON-object query param into a string→string/number record. */
function jsonRecord<T extends string | number>(
  raw: string | null,
  kind: "string" | "number",
): Record<string, T> | undefined {
  if (!raw) return undefined;
  try {
    const d: unknown = JSON.parse(raw);
    if (!d || typeof d !== "object" || Array.isArray(d)) return undefined;
    const out: Record<string, T> = {};
    for (const [k, v] of Object.entries(d)) {
      if (kind === "string" && typeof v === "string") out[k] = v as T;
      if (kind === "number" && typeof v === "number" && Number.isFinite(v))
        out[k] = v as T;
    }
    return Object.keys(out).length ? out : undefined;
  } catch {
    return undefined;
  }
}

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

  if (q.get("stud_material_overall"))
    out.stud_material_overall = q.get("stud_material_overall")!;
  const sp = Number(q.get("stud_spacing_overall"));
  if (q.get("stud_spacing_overall") && Number.isFinite(sp))
    out.stud_spacing_overall = sp;
  const pl = Number(q.get("wall_plies_overall"));
  if (q.get("wall_plies_overall") && Number.isFinite(pl))
    out.wall_plies_overall = pl;
  const sm = jsonRecord<string>(q.get("stud_material_levels"), "string");
  if (sm) out.stud_material_levels = sm;
  const ss = jsonRecord<number>(q.get("stud_spacing_levels"), "number");
  if (ss) out.stud_spacing_levels = ss;
  const wp = jsonRecord<number>(q.get("wall_plies_levels"), "number");
  if (wp) out.wall_plies_levels = wp;
  const sms = jsonRecord<string>(q.get("stud_material_segments"), "string");
  if (sms) out.stud_material_segments = sms;
  const sss = jsonRecord<number>(q.get("stud_spacing_segments"), "number");
  if (sss) out.stud_spacing_segments = sss;
  const wps = jsonRecord<number>(q.get("wall_plies_segments"), "number");
  if (wps) out.wall_plies_segments = wps;
  return out;
}

/** Reflect the current design in the URL so it is shareable. */
function syncUrl(p: ModelParams): void {
  const q = paramsToQuery(p);
  const qs = q.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
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
  syncUrl(params);
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
