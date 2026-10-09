"""Validation utilities for drawing-plan CSV rows."""

from __future__ import annotations

import math
import re
import os

from pydantic import ValidationError
from .contracts import opening_input, wall_input, truss_input
from manual_inputs import MAX_MEMBERS, estimated_member_count
from typing import Any

import materials


def finite_json(value):
    """Retain reviewable input text even for non-standard JSON NaN/Infinity."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value), False
    if isinstance(value, list):
        values = [finite_json(item) for item in value]
        return [item for item, _ in values], all(valid for _, valid in values)
    if isinstance(value, dict):
        values = {key: finite_json(item) for key, item in value.items()}
        return {key: item for key, (item, _) in values.items()}, all(valid for _, valid in values.values())
    return value, True

REQUIRED = {
    "wall": (
        "level", "segment_id", "label", "start_x_mm", "start_z_mm",
        "end_x_mm", "end_z_mm", "height_mm",
    ),
    "opening": (
        "level", "wall_segment_id", "opening_id", "opening_type",
        "width_mm", "height_mm",
    ),
    "truss": (
        "level", "truss_id", "label", "span_mm", "pitch_deg", "spacing_mm",
        "quantity", "start_x_mm", "start_z_mm", "direction_deg",
    ),
}

NUMERIC_FIELDS = {
    "level", "start_x_mm", "start_z_mm", "end_x_mm", "end_z_mm",
    "height_mm", "wall_thickness_mm", "stud_spacing_mm", "plies",
    "center_offset_mm", "start_offset_mm", "width_mm", "sill_height_mm",
    "head_height_mm", "span_mm", "pitch_deg", "spacing_mm", "quantity",
    "direction_deg", "overhang_mm", "heel_height_mm", "nog_count", "nog_spacing_mm",
}

POSITIVE_FIELDS = {
    "height_mm", "wall_thickness_mm", "stud_spacing_mm", "plies", "width_mm",
    "span_mm", "pitch_deg", "spacing_mm", "quantity",
}

_FEET_INCHES = re.compile(
    r"^\s*(?:(?P<feet>-?\d+(?:\.\d+)?)\s*['′])?\s*"
    r"(?:(?P<inches>-?\d+(?:\.\d+)?)\s*(?:[\"″]|in)?)?\s*$")


def number(value: Any, units: str) -> float:
    """Parse one dimension and normalize it to millimetres."""
    if isinstance(value, (int, float)):
        n = float(value)
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("value is required")
        if units == "feet_inches" and (any(marker in raw for marker in ("'", "′", '"', '″')) or raw.endswith("in")):
            match = _FEET_INCHES.match(raw)
            if not match:
                raise ValueError("use feet/inches such as 8' 6\"")
            feet = float(match.group("feet") or 0)
            inches = float(match.group("inches") or 0)
            if match.group("feet") is not None:
                if inches < 0:
                    raise ValueError("put a leading minus before feet; inches must be nonnegative")
                negative = match.group("feet").startswith("-")
                result = (-1 if negative else 1) * (abs(feet)*304.8+inches*25.4)
            else:
                result = inches*25.4
            if not math.isfinite(result):
                raise ValueError("must be a finite number")
            return result
        n = float(raw)
    if not math.isfinite(n):
        raise ValueError("must be a finite number")
    result = n * 1000 if units == "metres" else n * 304.8 if units == "feet_inches" else n
    if not math.isfinite(result):
        raise ValueError("converted dimension must be finite")
    return result


MAX_ROWS = int(os.environ.get("TIMBERBIM_MAX_IMPORT_ROWS", "10000"))


def validate_rows(rows: list[dict[str, Any]], units: str = "mm") -> dict:
    errors, warnings, normalized = [], [], []

    def reject(row, message, field="geometry"):
        row["valid"] = False
        row["errors"].append(message)
        errors.append({"row": row["_row"], "field": field, "message": message})

    def domain_check(row, build):
        try:
            return build()
        except ValidationError as exc:
            for issue in exc.errors():
                reject(row, issue["msg"], ".".join(map(str, issue["loc"])) or "geometry")
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            reject(row, str(exc))
        return None

    if not rows:
        errors.append({"row": 1, "field": "rows", "message": "CSV contains no entities"})
    if len(rows) > MAX_ROWS:
        errors.append({"row": 1, "field": "rows", "message": f"CSV exceeds {MAX_ROWS} rows"})
        rows = []
    for index, original in enumerate(rows, start=2):
        row = {str(k).strip().lower(): v for k, v in original.items()
               if k is not None and v is not None and str(v).strip() != ""
               and k not in {"valid", "errors", "warnings", "_row", "length_mm"}}
        kind = str(row.get("type", "")).strip().lower()
        out = {**row, "type": kind, "_row": index, "valid": True,
               "errors": [], "warnings": []}
        normalized.append(out)
        for field, value in row.items():
            converted, valid_json = finite_json(value)
            if not valid_json:
                out[field] = converted
                reject(out, "must contain finite JSON numbers", field)
        if kind not in REQUIRED:
            reject(out, "type must be wall, opening, or truss", "type")
        else:
            for field in REQUIRED[kind]:
                if field not in row:
                    reject(out, f"missing required field: {field}", field)
            if kind == "opening" and not ({"center_offset_mm", "start_offset_mm"} & row.keys()):
                reject(out, "opening requires center_offset_mm or start_offset_mm", "start_offset_mm")
        for field in NUMERIC_FIELDS & row.keys():
            try:
                unit = "mm" if field in {"level", "plies", "quantity", "nog_count", "pitch_deg", "direction_deg"} else units
                n = number(row[field], unit)
                if field in {"level", "plies", "quantity", "nog_count"}:
                    if not n.is_integer():
                        raise ValueError("must be a whole number")
                    n = int(n)
                out[field] = n
                if field in POSITIVE_FIELDS and n <= 0:
                    raise ValueError("must be positive")
            except (TypeError, ValueError, OverflowError) as exc:
                reject(out, f"{field}: {exc}", field)
        if not out["valid"]:
            continue
        if out["level"] > 3:
            out["warnings"].append(f"level {out['level']} is outside the sample model's 1-3 storeys")
        if kind == "wall":
            length = math.hypot(out["end_x_mm"] - out["start_x_mm"], out["end_z_mm"] - out["start_z_mm"])
            if not math.isfinite(length):
                reject(out, "wall length must remain finite after calculation", "geometry")
            else:
                out["length_mm"] = length
                domain_check(out, lambda: wall_input(out, []))
        elif kind == "truss":
            domain_check(out, lambda: truss_input(out))
        material = str(row.get("stud_material") or row.get("material") or "")
        if material and materials.normalise_material_key(material) is None:
            out["warnings"].append(f"material '{material}' is not in the catalogue; kept as custom")

    seen = {}
    for row in normalized:
        if not row["valid"]:
            continue
        field = {"wall": "segment_id", "opening": "opening_id", "truss": "truss_id"}[row["type"]]
        scope = (row["type"], row["level"], row.get("wall_segment_id", ""), row[field])
        if scope in seen:
            reject(row, f"duplicate {field}: {row[field]}", field)
            if seen[scope]["valid"]:
                reject(seen[scope], f"duplicate {field}: {row[field]}", field)
        else:
            seen[scope] = row
    walls = {(r["level"], r["segment_id"]): r for r in normalized if r["type"] == "wall" and r["valid"]}
    openings = {}
    for row in normalized:
        if row["type"] != "opening" or not row["valid"]:
            continue
        key = (row["level"], row["wall_segment_id"])
        wall = walls.get(key)
        if not wall:
            reject(row, "opening references an unknown or invalid wall segment on its level", "wall_segment_id")
            continue
        start = row.get("start_offset_mm")
        if start is None:
            start = row["center_offset_mm"] - row["width_mm"] / 2
        elif "center_offset_mm" in row and not math.isclose(start + row["width_mm"] / 2, row["center_offset_mm"], abs_tol=0.01):
            reject(row, "opening start and center offsets disagree", "center_offset_mm")
            continue
        if start < 0 or start + row["width_mm"] > wall["length_mm"]:
            reject(row, "opening does not fit within its wall segment", "start_offset_mm")
            continue
        row["start_offset_mm"] = start
        spec = domain_check(row, lambda: opening_input(row))
        if spec:
            openings.setdefault(key, []).append(spec)
    for key, wall in walls.items():
        if wall["valid"]:
            domain_check(wall, lambda: wall_input(wall, openings.get(key, [])))
    valid = [r for r in normalized if r["valid"]]
    estimate = 0
    for row in valid:
        if row["type"] == "wall":
            estimate += estimated_member_count(wall_input(row, openings.get((row["level"], row["segment_id"]), [])))
        elif row["type"] == "truss":
            estimate += estimated_member_count(truss_input(row))
    if estimate > MAX_MEMBERS:
        errors.append({"row": 1, "field": "rows", "message": f"CSV would exceed the {MAX_MEMBERS} member generation limit"})
    for row in normalized:
        warnings.extend({"row": row["_row"], "message": message} for message in row["warnings"])
    summary = {
        "wall_count": sum(r["type"] == "wall" for r in valid),
        "opening_count": sum(r["type"] == "opening" for r in valid),
        "truss_count": sum(r["type"] == "truss" for r in valid),
        "estimated_total_wall_length_m": round(sum(r.get("length_mm", 0) for r in valid if r["type"] == "wall") / 1000, 2),
        "error_count": len(errors), "warning_count": len(warnings),
    }
    return {"rows": normalized, "normalized_entities": valid,
            "errors": errors, "warnings": warnings, "summary": summary,
            "can_preview": not errors and bool(valid)}
