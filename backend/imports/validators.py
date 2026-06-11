"""Validation utilities for drawing-plan CSV rows."""

from __future__ import annotations

import math
import re
from typing import Any

import materials

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
    "direction_deg", "overhang_mm", "heel_height_mm",
}

POSITIVE_FIELDS = {
    "height_mm", "wall_thickness_mm", "stud_spacing_mm", "plies", "width_mm",
    "span_mm", "pitch_deg", "spacing_mm", "quantity",
}

_FEET_INCHES = re.compile(
    r"^\s*(?:(?P<feet>-?\d+(?:\.\d+)?)\s*['′])?\s*"
    r"(?:(?P<inches>\d+(?:\.\d+)?)\s*(?:[\"″]|in)?)?\s*$")


def number(value: Any, units: str) -> float:
    """Parse one dimension and normalize it to millimetres."""
    if isinstance(value, (int, float)):
        n = float(value)
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("value is required")
        if units == "feet_inches" and ("'" in raw or "′" in raw or '"' in raw):
            match = _FEET_INCHES.match(raw)
            if not match:
                raise ValueError("use feet/inches such as 8' 6\"")
            feet = float(match.group("feet") or 0)
            inches = float(match.group("inches") or 0)
            return feet * 304.8 + inches * 25.4
        n = float(raw)
    if not math.isfinite(n):
        raise ValueError("must be a finite number")
    if units == "metres":
        return n * 1000
    if units == "feet_inches":
        return n * 304.8
    return n


def validate_rows(rows: list[dict[str, Any]], units: str = "mm") -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    normalized: list[dict] = []

    for index, original in enumerate(rows, start=2):
        row = {str(k).strip().lower(): v for k, v in original.items()}
        kind = str(row.get("type", "")).strip().lower()
        row_errors: list[str] = []
        row_warnings: list[str] = []
        if kind not in REQUIRED:
            row_errors.append("type must be wall, opening, or truss")
        else:
            for field in REQUIRED[kind]:
                if str(row.get(field, "")).strip() == "":
                    row_errors.append(f"missing required field: {field}")
            if kind == "opening" and not (
                str(row.get("center_offset_mm", "")).strip()
                or str(row.get("start_offset_mm", "")).strip()
            ):
                row_errors.append(
                    "opening requires center_offset_mm or start_offset_mm")

        out = dict(row)
        out["type"] = kind
        for field in NUMERIC_FIELDS:
            if str(row.get(field, "")).strip() == "":
                continue
            try:
                if field in {"level", "plies", "quantity"}:
                    out[field] = int(round(number(row[field], "mm")))
                elif field in {"pitch_deg", "direction_deg"}:
                    out[field] = number(row[field], "mm")
                else:
                    out[field] = number(row[field], units)
                if field in POSITIVE_FIELDS and out[field] <= 0:
                    row_errors.append(f"{field} must be positive")
            except (TypeError, ValueError) as exc:
                row_errors.append(f"{field}: {exc}")

        level = out.get("level")
        if isinstance(level, int) and not 1 <= level <= 3:
            row_warnings.append(
                f"level {level} is outside the sample model's 1-3 storeys")
        if kind == "wall" and not row_errors:
            length = math.hypot(
                out["end_x_mm"] - out["start_x_mm"],
                out["end_z_mm"] - out["start_z_mm"])
            out["length_mm"] = round(length, 2)
            if length < 300:
                row_errors.append("wall length must be at least 300 mm")
        if kind == "truss":
            pitch = out.get("pitch_deg", 0)
            span = out.get("span_mm", 0)
            spacing = out.get("spacing_mm", 0)
            if pitch and not 5 <= pitch <= 60:
                row_warnings.append("truss pitch outside typical 5-60 degrees")
            if span and not 1000 <= span <= 30000:
                row_warnings.append("truss span outside typical 1-30 m range")
            if spacing and not 300 <= spacing <= 2400:
                row_warnings.append("truss spacing outside typical 300-2400 mm")
        material = str(
            row.get("stud_material") or row.get("material") or "").strip()
        if material and materials.normalise_material_key(material) is None:
            row_warnings.append(
                f"material '{material}' is not in the catalogue; kept as custom")

        out["_row"] = index
        out["valid"] = not row_errors
        out["errors"] = row_errors
        out["warnings"] = row_warnings
        normalized.append(out)
        errors.extend({"row": index, "message": msg} for msg in row_errors)
        warnings.extend({"row": index, "message": msg} for msg in row_warnings)

    walls = {
        r.get("segment_id"): r for r in normalized
        if r.get("type") == "wall" and r.get("valid")
    }
    for row in normalized:
        if row.get("type") != "opening" or not row.get("valid"):
            continue
        wall = walls.get(row.get("wall_segment_id"))
        if not wall:
            msg = "opening references an unknown or invalid wall segment"
        else:
            start = row.get("start_offset_mm")
            if start is None:
                start = row.get("center_offset_mm", 0) - row.get("width_mm", 0) / 2
            if start < 0 or start + row.get("width_mm", 0) > wall["length_mm"]:
                msg = "opening does not fit within its wall segment"
            else:
                row["start_offset_mm"] = round(start, 2)
                continue
        row["valid"] = False
        row["errors"].append(msg)
        errors.append({"row": row["_row"], "message": msg})

    valid = [r for r in normalized if r.get("valid")]
    summary = {
        "wall_count": sum(r["type"] == "wall" for r in valid),
        "opening_count": sum(r["type"] == "opening" for r in valid),
        "truss_count": sum(r["type"] == "truss" for r in valid),
        "estimated_total_wall_length_m": round(sum(
            r.get("length_mm", 0) for r in valid if r["type"] == "wall"
        ) / 1000, 2),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return {
        "rows": normalized,
        "normalized_entities": valid,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
        "can_preview": not errors and bool(valid),
    }
