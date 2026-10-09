"""Structured CSV parsing and conversion to reviewable BIM elements."""

from __future__ import annotations

import csv
import io
from itertools import islice
from typing import Any

from manual_inputs import generate_truss, generate_wall
from .contracts import opening_input, wall_input, truss_input

from .validators import MAX_ROWS, validate_rows


def parse_csv(content: bytes, units: str = "mm") -> dict:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {
            "rows": [], "normalized_entities": [],
            "errors": [{"row": 1, "field": "file", "message": "CSV must be UTF-8 encoded"}],
            "warnings": [], "summary": {
                "wall_count": 0, "opening_count": 0, "truss_count": 0,
                "estimated_total_wall_length_m": 0,
                "error_count": 1, "warning_count": 0,
            }, "can_preview": False,
        }
    try:
        # One look-ahead row proves overflow without materializing the whole file.
        rows = list(islice(csv.DictReader(io.StringIO(text)), MAX_ROWS + 1))
    except csv.Error as exc:
        return {
            "rows": [], "normalized_entities": [],
            "errors": [{"row": 1, "field": "file", "message": f"invalid CSV: {exc}"}],
            "warnings": [], "summary": {
                "wall_count": 0, "opening_count": 0, "truss_count": 0,
                "estimated_total_wall_length_m": 0,
                "error_count": 1, "warning_count": 0,
            }, "can_preview": False,
        }
    if not rows:
        return {
            "rows": [], "normalized_entities": [],
            "errors": [{"row": 1, "field": "rows", "message": "CSV contains no data rows"}],
            "warnings": [], "summary": {
                "wall_count": 0, "opening_count": 0, "truss_count": 0,
                "estimated_total_wall_length_m": 0,
                "error_count": 1, "warning_count": 0,
            }, "can_preview": False,
        }
    return validate_rows(rows, units)


def rows_to_elements(
    rows: list[dict[str, Any]], source: str, source_id: str,
) -> tuple[list[dict], list[str]]:
    """Generate exactly the domain objects checked during row validation."""
    validation = validate_rows(rows, "mm")
    if not validation["can_preview"]:
        raise ValueError("Fix invalid or empty CSV rows before generation")
    valid = validation["normalized_entities"]
    openings_by_wall = {}
    for row in valid:
        if row["type"] == "opening":
            openings_by_wall.setdefault((row["level"], row["wall_segment_id"]), []).append(opening_input(row))
    elements = []
    warnings = [w["message"] for w in validation["warnings"]]
    for row in valid:
        if row["type"] == "wall":
            spec = wall_input(row, openings_by_wall.get((row["level"], row["segment_id"]), []), source_id)
            generated, generated_warnings = generate_wall(spec, source, source_id)
        elif row["type"] == "truss":
            spec = truss_input(row, source_id)
            generated, generated_warnings = generate_truss(spec, source, source_id)
        else:
            continue
        elements.extend(generated)
        warnings.extend(generated_warnings)
    return elements, list(dict.fromkeys(warnings))
