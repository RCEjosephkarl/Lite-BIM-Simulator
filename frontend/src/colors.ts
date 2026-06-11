import * as THREE from "three";
import type { BimElement, ColorMode, ElementType } from "./types";

/** Material/treatment palette (mode "material"). */
const MATERIAL_COLORS: Record<string, string> = {
  "SG8|H1.2": "#e3c16f", // kiln-dried framing, boric treated
  "SG8|H3.2": "#5ea36b", // CCA/ACQ treated outdoor timber (green tint)
  "concrete|-": "#9ca3af",
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
    const key = `${el.grade}|${el.treatment}`;
    return new THREE.Color(MATERIAL_COLORS[key] ?? "#d4d4d8");
  }
  // realistic: timber tones with slight per-piece variation
  if (type.category === "concrete") return REALISTIC_CONCRETE.clone();
  const c = REALISTIC_TIMBER.clone();
  const jitter = ((el.id * 2654435761) % 100) / 100; // deterministic hash
  c.offsetHSL(0.01 * (jitter - 0.5), 0.05 * (jitter - 0.5), 0.08 * (jitter - 0.5));
  return c;
}

export const MATERIAL_LEGEND = [
  { label: "SG8 H1.2 (enclosed framing)", hex: "#e3c16f" },
  { label: "SG8 H3.2 (exposed/outdoor)", hex: "#5ea36b" },
  { label: "Concrete (not in BOM)", hex: "#9ca3af" },
];
