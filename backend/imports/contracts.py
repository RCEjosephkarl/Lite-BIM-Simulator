"""One normalized-row to domain-input mapping for validation and generation."""

from typing import Any

from manual_inputs import ManualOpening, ManualTrussInput, ManualWallFrameInput


def value(row: dict, name: str, default: Any):
    result = row.get(name)
    return default if result is None or result == "" else result


def truthy(raw: Any, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text not in {"1", "true", "yes", "y", "0", "false", "no", "n"}:
        raise ValueError("Boolean must be true/false, yes/no, or 1/0")
    return text in {"1", "true", "yes", "y"}


def opening_input(row: dict) -> ManualOpening:
    return ManualOpening(
        opening_id=row["opening_id"], opening_type=row["opening_type"],
        start_offset_mm=row["start_offset_mm"], width_mm=row["width_mm"],
        height_mm=row["height_mm"], sill_height_mm=value(row, "sill_height_mm", 0),
        head_height_mm=value(row, "head_height_mm", None),
        lintel_size=value(row, "lintel_size", ""), notes=value(row, "notes", ""))


def wall_input(row: dict, openings: list[ManualOpening], source_id: str = "") -> ManualWallFrameInput:
    return ManualWallFrameInput(
        input_id=source_id, level=row["level"], segment_id=row["segment_id"],
        segment_label=row["label"], start_x_mm=row["start_x_mm"],
        start_z_mm=row["start_z_mm"], end_x_mm=row["end_x_mm"],
        end_z_mm=row["end_z_mm"], wall_height_mm=row["height_mm"],
        wall_thickness_mm=value(row, "wall_thickness_mm", 90),
        stud_size=value(row, "stud_size", "90x45"),
        stud_material=value(row, "stud_material", "SG8"),
        plate_material=value(row, "plate_material", "SG8"),
        lintel_material=value(row, "lintel_material", "SG8"),
        panelize=truthy(row.get("panelize"), True),
        stud_spacing_mm=value(row, "stud_spacing_mm", 600),
        plies=value(row, "plies", 1), treatment=value(row, "treatment", "H1.2"),
        bottom_plate_size=value(row, "bottom_plate_size", "90x45"),
        top_plate_size=value(row, "top_plate_size", "90x45"),
        nog_count=value(row, "nog_count", 1),
        nog_spacing_mm=value(row, "nog_spacing_mm", None),
        load_bearing=truthy(row.get("load_bearing"), True),
        exterior=truthy(row.get("exterior"), True), openings=openings)


def truss_input(row: dict, source_id: str = "") -> ManualTrussInput:
    material = value(row, "material", "SG8")
    return ManualTrussInput(
        input_id=source_id, level=row["level"], truss_id=row["truss_id"],
        truss_label=row["label"], span_mm=row["span_mm"],
        pitch_deg=row["pitch_deg"], spacing_mm=row["spacing_mm"],
        quantity=row["quantity"], start_x_mm=row["start_x_mm"],
        start_z_mm=row["start_z_mm"], direction_deg=row["direction_deg"],
        truss_type=value(row, "truss_type", "common"),
        top_chord_size=value(row, "top_chord_size", "140x45"),
        bottom_chord_size=value(row, "bottom_chord_size", "90x45"),
        web_size=value(row, "web_size", "90x45"),
        top_chord_material=value(row, "top_chord_material", material),
        bottom_chord_material=value(row, "bottom_chord_material", material),
        web_material=value(row, "web_material", material),
        treatment=value(row, "treatment", "H1.2"),
        overhang_mm=value(row, "overhang_mm", 450),
        heel_height_mm=value(row, "heel_height_mm", 100))
