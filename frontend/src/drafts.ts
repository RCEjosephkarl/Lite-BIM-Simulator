/** Versioned local drafts preserve unfinished forms, never commit readiness. */
import type { ManualOpening } from "./types";
export type DraftKind = "wall" | "truss";
export type FieldRules = Record<string, { type: "text" | "number" | "boolean" | "choice"; choices?: string[] }>;
export type OpeningDraft = Omit<ManualOpening,"start_offset_mm"|"width_mm"|"height_mm"|"sill_height_mm"|"head_height_mm"> & {
  start_offset_mm:string; width_mm:string; height_mm:string; sill_height_mm:string; head_height_mm:string;
};
export function openingDraft(value:ManualOpening): OpeningDraft {
  return {...value,start_offset_mm:String(value.start_offset_mm),width_mm:String(value.width_mm),height_mm:String(value.height_mm),
    sill_height_mm:String(value.sill_height_mm),head_height_mm:value.head_height_mm===null?"":String(value.head_height_mm)};
}
export interface SavedDraft {
  schema_version: 2;
  kind: DraftKind;
  project_id: string;
  saved_at: string;
  assembly_id?: string;
  fields: Record<string, string | boolean>;
  openings: OpeningDraft[];
}
const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown) => typeof value === "number" && Number.isFinite(value);
const csv = (value: unknown) => `"${String(value).replace(/"/g, '""')}"`;

function openingList(value: unknown, rawFields=false): SavedDraft["openings"] {
  if (!Array.isArray(value) || value.length > 1024) throw new Error("Invalid opening list");
  const numeric = ["start_offset_mm", "width_mm", "height_mm", "sill_height_mm"];
  return value.map(item => {
    if (!object(item) || !["door", "window", "garage", "custom"].includes(String(item.opening_type))
      || typeof item.opening_id !== "string" || typeof item.lintel_size !== "string"
      || typeof item.notes !== "string" || numeric.some(key => rawFields?
        !(typeof item[key]==="string"&&(item[key]===""||Number.isFinite(Number(item[key])))):!finite(item[key]))
      || !(rawFields?(typeof item.head_height_mm==="string"&&(item.head_height_mm===""||Number.isFinite(Number(item.head_height_mm)))):
        item.head_height_mm === null || finite(item.head_height_mm))) throw new Error("Invalid saved opening fields");
    const keys = ["opening_id", "opening_type", ...numeric, "head_height_mm", "lintel_size", "notes"];
    if (Object.keys(item).some(key => !keys.includes(key))) throw new Error("Unknown saved opening field");
    return rawFields?item as unknown as OpeningDraft:openingDraft(item as unknown as ManualOpening);
  });
}

export function decodeDraft(raw: string, kind: DraftKind, projectId: string, rules: FieldRules, assemblyId: string | null = null): { draft: SavedDraft; migrated: boolean } {
  if (raw.length > 2*1024*1024) throw new Error("Saved draft exceeds the recovery size limit");
  const value: unknown = JSON.parse(raw);
  if (!object(value)) throw new Error("Saved draft must be an object");
  const legacy = value.schema_version === undefined;
  const migrated = value.schema_version !== 2;
  if (legacy && assemblyId) throw new Error("Legacy draft has no assembly identity");
  let fields: Record<string, unknown>;
  let openings: SavedDraft["openings"] = [];
  if (legacy) {
    // Earlier releases saved flat values and optional parsed custom CSV.
    if (kind === "wall") openings = openingList(value.openings);
    else {
      if (!Array.isArray(value.nodes) || !Array.isArray(value.members)) throw new Error("Invalid legacy truss draft");
      if (value.nodes.length > 1024 || value.members.length > 2048) throw new Error("Legacy truss draft exceeds the recovery size limit");
      if (value.nodes.some(node => !object(node) || typeof node.id !== "string" || !finite(node.x) || !finite(node.y))
        || value.members.some(member => !object(member) || ["start_node", "end_node", "element_type", "size", "material"].some(key => typeof member[key] !== "string")))
        throw new Error("Invalid legacy custom truss data");
    }
    fields = Object.fromEntries(Object.entries(value).filter(([key]) => Object.hasOwn(rules, key)));
    if (kind === "truss") {
      const nodes = value.nodes as Record<string, unknown>[], members = value.members as Record<string, unknown>[];
      if (nodes.length && !Object.hasOwn(fields, "nodes_csv")) fields.nodes_csv = nodes.map(node => [node.id, node.x, node.y].map(csv).join(",")).join("\n");
      if (members.length && !Object.hasOwn(fields, "members_csv")) fields.members_csv = members.map(member => [member.start_node, member.end_node, member.element_type, member.size, member.material].map(csv).join(",")).join("\n");
    }
  } else {
    if (value.schema_version !== 1 && value.schema_version !== 2) throw new Error("Saved draft version is not supported");
    if (value.kind !== kind || value.project_id !== projectId) throw new Error("Saved draft belongs to a different form or home");
    if ((value.assembly_id ?? null) !== assemblyId) throw new Error("Saved draft belongs to a different assembly");
    if (typeof value.saved_at !== "string" || !Number.isFinite(Date.parse(value.saved_at))) throw new Error("Saved draft date is invalid");
    if (!object(value.fields)) throw new Error("Saved form fields are invalid");
    fields = value.fields;
    if (kind === "wall") openings = openingList(value.openings,value.schema_version===2);
    else if (!Array.isArray(value.openings) || value.openings.length) throw new Error("Unexpected truss opening data");
  }
  const normalized: SavedDraft["fields"] = {};
  for (const [key, original] of Object.entries(fields)) {
    if (!Object.hasOwn(rules, key)) throw new Error(`Unknown saved field: ${key}`);
    const rule = rules[key];
    const field = legacy && typeof original === "number" && finite(original) ? String(original) : original;
    if (rule.type === "boolean") {
      if (typeof field !== "boolean") throw new Error(`Saved ${key} must be a checkbox value`);
    } else {
      if (typeof field !== "string") throw new Error(`Saved ${key} must be text`);
      if (rule.type === "number" && field !== "" && !Number.isFinite(Number(field))) throw new Error(`Saved ${key} must be finite or unfinished`);
      if (rule.type === "choice" && !rule.choices?.includes(field)) throw new Error(`Saved ${key} has an unknown option`);
    }
    normalized[key] = field as string | boolean;
  }
  return { migrated, draft: { schema_version: 2, kind, project_id: projectId,
    saved_at: legacy ? new Date().toISOString() : value.saved_at as string, fields: normalized, openings,
    ...(assemblyId ? { assembly_id: assemblyId } : {}) } };
}
