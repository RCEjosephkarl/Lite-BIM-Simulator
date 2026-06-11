import * as THREE from "three";
import type { BimElement, ColorMode, ElementType } from "./types";

/** Material palette (mode "material") keyed by material display name. */
const MATERIAL_COLORS: Record<string, string> = {
  SG8: "#e3c16f", // kiln-dried radiata framing
  SG10: "#d9a13f", // higher-grade radiata
  Prolam: "#b07a45", // branded glulam
  Glulam: "#8a5a2b", // generic glue-laminated
  HyCHORD: "#7f8fc9", // LVL (cool tones)
  HySPAN: "#5b6fb5",
  Hy90: "#9b7fc9",
  concrete: "#9ca3af",
};

const REALISTIC_TIMBER = new THREE.Color("#c89f68");
const REALISTIC_CONCRETE = new THREE.Color("#a3a7ad");

export function elementColor(
  el: BimElement,
  type: ElementType,
  mode: ColorMode,
): THREE.Color {
  if (mode === "function") {
    return new THREE.Color(type.color_hex);
  }
  if (mode === "material") {
    const c = new THREE.Color(MATERIAL_COLORS[el.material] ?? "#d4d4d8");
    if (el.treatment === "H3.2") c.offsetHSL(0.08, 0.05, -0.06); // green shift
    return c;
  }
  // realistic: timber tones with slight per-piece variation
  if (type.category === "concrete") return REALISTIC_CONCRETE.clone();
  const c = REALISTIC_TIMBER.clone();
  const jitter = ((el.id * 2654435761) % 100) / 100; // deterministic hash
  c.offsetHSL(0.01 * (jitter - 0.5), 0.05 * (jitter - 0.5), 0.08 * (jitter - 0.5));
  return c;
}

export const MATERIAL_LEGEND = [
  { label: "SG8 (sawn radiata)", hex: MATERIAL_COLORS.SG8 },
  { label: "SG10 (sawn radiata)", hex: MATERIAL_COLORS.SG10 },
  { label: "Prolam (glulam)", hex: MATERIAL_COLORS.Prolam },
  { label: "Glulam (generic)", hex: MATERIAL_COLORS.Glulam },
  { label: "HyCHORD (LVL)", hex: MATERIAL_COLORS.HyCHORD },
  { label: "HySPAN (LVL)", hex: MATERIAL_COLORS.HySPAN },
  { label: "Hy90 (LVL)", hex: MATERIAL_COLORS.Hy90 },
  { label: "H3.2 treated (green shift)", hex: "#5ea36b" },
  { label: "Concrete (not in BOM)", hex: MATERIAL_COLORS.concrete },
];
