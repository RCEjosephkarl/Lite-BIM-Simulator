"""Structured CSV parsing and conversion to reviewable BIM elements."""

from __future__ import annotations

import csv
import io
from typing import Any

from manual_inputs import (
    ManualOpening,
    ManualTrussInput,
    ManualWallFrameInput,
    generate_truss,
    generate_wall,
)

from .validators import validate_rows


def parse_csv(content: bytes, units: str = "mm") -> dict:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {
            "rows": [], "normalized_entities": [],
            "errors": [{"row": 1, "message": "CSV must be UTF-8 encoded"}],
            "warnings": [], "summary": {
                "wall_count": 0, "opening_count": 0, "truss_count": 0,
                "estimated_total_wall_length_m": 0,
                "error_count": 1, "warning_count": 0,
            }, "can_preview": False,
        }
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except csv.Error as exc:
        return {
            "rows": [], "normalized_entities": [],
            "errors": [{"row": 1, "message": f"invalid CSV: {exc}"}],
            "warnings": [], "summary": {
                "wall_count": 0, "opening_count": 0, "truss_count": 0,
                "estimated_total_wall_length_m": 0,
                "error_count": 1, "warning_count": 0,
            }, "can_preview": False,
        }
    if not rows:
        return {
            "rows": [], "normalized_entities": [],
            "errors": [{"row": 1, "message": "CSV contains no data rows"}],
            "warnings": [], "summary": {
                "wall_count": 0, "opening_count": 0, "truss_count": 0,
                "estimated_total_wall_length_m": 0,
                "error_count": 1, "warning_count": 0,
            }, "can_preview": False,
        }
    return validate_rows(rows, units)


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def rows_to_elements(
    rows: list[dict[str, Any]], source: str, source_id: str,
) -> tuple[list[dict], list[str]]:
    """Convert validated/edited normalized rows into framing members."""
    validation = validate_rows(rows, "mm")
    valid = validation["normalized_entities"]
    openings_by_wall: dict[str, list[ManualOpening]] = {}
    for row in valid:
        if row["type"] != "opening":
            continue
        sill = float(row.get("sill_height_mm") or 0)
        opening = ManualOpening(
            opening_id=str(row.get("opening_id", "")),
            opening_type=row.get("opening_type", "custom"),
            start_offset_mm=float(row["start_offset_mm"]),
            width_mm=float(row["width_mm"]),
            height_mm=float(row["height_mm"]),
            sill_height_mm=sill,
            head_height_mm=float(row["head_height_mm"])
            if row.get("head_height_mm") not in (None, "") else None,
            lintel_size=str(row.get("lintel_size", "")),
            notes=str(row.get("notes", "")),
        )
        openings_by_wall.setdefault(
            str(row["wall_segment_id"]), []).append(opening)

    elements: list[dict] = []
    warnings = [w["message"] for w in validation["warnings"]]
    for row in valid:
        if row["type"] == "wall":
            spec = ManualWallFrameInput(
                input_id=source_id,
                level=int(row["level"]),
                segment_id=str(row["segment_id"]),
                segment_label=str(row.get("label") or row["segment_id"]),
                start_x_mm=float(row["start_x_mm"]),
                start_z_mm=float(row["start_z_mm"]),
                end_x_mm=float(row["end_x_mm"]),
                end_z_mm=float(row["end_z_mm"]),
                wall_height_mm=float(row["height_mm"]),
                wall_thickness_mm=float(row.get("wall_thickness_mm") or 90),
                stud_size=str(row.get("stud_size") or "90x45"),
                stud_material=str(row.get("stud_material") or "SG8"),
                stud_spacing_mm=float(row.get("stud_spacing_mm") or 600),
                plies=int(row.get("plies") or 1),
                treatment=str(row.get("treatment") or "H1.2"),
                load_bearing=_truthy(row.get("load_bearing"), True),
                exterior=_truthy(row.get("exterior"), True),
                openings=openings_by_wall.get(str(row["segment_id"]), []),
            )
            generated, generated_warnings = generate_wall(spec, source, source_id)
            elements.extend(generated)
            warnings.extend(generated_warnings)
        elif row["type"] == "truss":
            material = str(row.get("material") or "SG8")
            spec = ManualTrussInput(
                input_id=source_id,
                level=int(row["level"]),
                truss_id=str(row["truss_id"]),
                truss_label=str(row.get("label") or row["truss_id"]),
                span_mm=float(row["span_mm"]),
                pitch_deg=float(row["pitch_deg"]),
                spacing_mm=float(row["spacing_mm"]),
                quantity=int(row["quantity"]),
                start_x_mm=float(row["start_x_mm"]),
                start_z_mm=float(row["start_z_mm"]),
                direction_deg=float(row["direction_deg"]),
                truss_type=row.get("truss_type") or "common",
                top_chord_size=str(row.get("top_chord_size") or "140x45"),
                bottom_chord_size=str(row.get("bottom_chord_size") or "90x45"),
                web_size=str(row.get("web_size") or "90x45"),
                top_chord_material=material,
                bottom_chord_material=material,
                web_material=material,
                treatment=str(row.get("treatment") or "H1.2"),
                overhang_mm=float(row.get("overhang_mm") or 450),
                heel_height_mm=float(row.get("heel_height_mm") or 100),
            )
            generated, generated_warnings = generate_truss(
                spec, source, source_id)
            elements.extend(generated)
            warnings.extend(generated_warnings)
    return elements, list(dict.fromkeys(warnings))
