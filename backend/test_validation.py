"""User-facing import/geometry validation must agree with generated members."""

import math

import pytest
from pydantic import ValidationError

import db
from imports.csv_plan import rows_to_elements
from imports.validators import validate_rows
from manual_inputs import ManualOpening, ManualTrussInput, ManualWallFrameInput, generate_wall
from test_smoke import client, manual_wall_payload


WALL = {"type": "wall", "level": 1, "segment_id": "W1", "label": "Wall", "start_x_mm": 0,
        "start_z_mm": 0, "end_x_mm": 3600, "end_z_mm": 0, "height_mm": 2535}
OPENING = {"type": "opening", "level": 1, "wall_segment_id": "W1", "opening_id": "O1",
           "opening_type": "window", "width_mm": 1200, "height_mm": 1200,
           "sill_height_mm": 900, "head_height_mm": 2100, "center_offset_mm": 1800}
TRUSS = {"type": "truss", "level": 1, "truss_id": "T1", "label": "Truss", "span_mm": 9000,
         "pitch_deg": 25, "spacing_mm": 900, "quantity": 1, "start_x_mm": 0,
         "start_z_mm": 0, "direction_deg": 0}


@pytest.mark.parametrize("change", [
    {"treatment": "H9"}, {"end_x_mm": 9000, "panelize": False}, {"height_mm": 3500, "panelize": False},
    {"stud_size": "-90x45"}, {"stud_size": "90x0"}, {"top_plate_size": "nonsense"},
    {"level": 1.5}, {"stud_spacing_mm": 0}, {"start_x_mm": "nan"},
    {"nog_spacing_mm": 0.000001}, {"load_bearing": "not a boolean"},
])
def test_invalid_wall_has_row_errors_in_validation_and_422_in_preview(change):
    rows = [{**WALL, **change}]
    validation = validate_rows(rows)
    assert not validation["can_preview"]
    assert all(e["row"] == 2 and e["field"] for e in validation["errors"])
    response = client.post("/api/import/csv-plan/preview", json={"rows": rows})
    assert response.status_code == 422


def test_empty_csv_replacement_cannot_erase_model():
    client.post("/api/project/initialize")
    before = db.model_json()
    response = client.post("/api/import/csv-plan/commit", json={"rows": [], "mode": "replace_sample_geometry"})
    assert response.status_code == 422
    assert db.model_json() == before


def test_blank_start_offset_uses_center_and_preview_commit_geometry_agree():
    rows = [WALL, {**OPENING, "start_offset_mm": ""}]
    validated = validate_rows(rows)
    assert validated["can_preview"], validated["errors"]
    assert validated["rows"][1]["start_offset_mm"] == 1200
    generated, _ = rows_to_elements(validated["rows"], "csv_preview", "test")
    response = client.post("/api/import/csv-plan/preview", json={"rows": rows})
    assert response.status_code == 200
    assert len(response.json()["elements"]) == len(generated)


def test_explicit_zero_truss_overhang_and_heel_are_preserved():
    rows = [{**TRUSS, "overhang_mm": 0, "heel_height_mm": 0}]
    validation = validate_rows(rows)
    assert validation["can_preview"]
    members, _ = rows_to_elements(validation["rows"], "csv_preview", "test")
    top = [m for m in members if m["type_code"] == "truss_top_chord"]
    assert sum(m["length_mm"] for m in top) == pytest.approx(9000 / math.cos(math.radians(25)), abs=0.01)
    assert next(m for m in members if m["type_code"] == "truss_bottom_chord")["cz"] == 2535


def test_duplicate_ids_and_opening_level_mismatch_are_rejected():
    assert not validate_rows([WALL, WALL])["can_preview"]
    assert not validate_rows([WALL, {**OPENING, "level": 2}])["can_preview"]
    # Equal labels/IDs on distinct levels are a valid namespace, not duplicates.
    assert validate_rows([WALL, {**WALL, "level": 2}])["can_preview"]


@pytest.mark.parametrize("opening", [
    {**OPENING, "opening_type": "not-a-window"},
    {**OPENING, "head_height_mm": 2500},
    {**OPENING, "head_height_mm": 1900},
    {**OPENING, "width_mm": 5000},
    {**OPENING, "start_offset_mm": 600},
])
def test_opening_validation_rejects_invalid_or_conflicting_geometry(opening):
    assert not validate_rows([WALL, opening])["can_preview"]


def test_rotated_manual_wall_nogs_do_not_enter_opening():
    spec = ManualWallFrameInput(end_x_mm=0, end_z_mm=3600, openings=[ManualOpening(
        start_offset_mm=1200, width_mm=1200, height_mm=1200, sill_height_mm=900, head_height_mm=2100)])
    members, _ = generate_wall(spec)
    for member in members:
        if member["type_code"] == "nog":
            assert not (member["cy"] - member["length_mm"] / 2 < 2400
                        and member["cy"] + member["length_mm"] / 2 > 1200
                        and 900 < member["cz"] < 2100)


def test_overlapping_openings_are_rejected_before_manual_generation():
    opening = ManualOpening(start_offset_mm=1200, width_mm=1200, height_mm=1200)
    with pytest.raises(ValidationError, match="overlap"):
        ManualWallFrameInput(end_x_mm=3600, openings=[opening, opening])


def test_zero_length_custom_truss_fails_preview_and_commit_without_db_mutation():
    payload = {"truss_type": "custom", "nodes": [{"id": "A", "x": 0, "y": 0}, {"id": "B", "x": 0, "y": 0}],
               "members": [{"start_node": "A", "end_node": "B"}]}
    for route in ("preview", "commit"):
        assert client.post(f"/api/manual/truss/{route}", json=payload).status_code == 422
    assert not db.DB_PATH.exists()


def test_nonfinite_manual_coordinates_and_negative_sections_are_rejected():
    response = client.post("/api/manual/wall-frame/preview", json={**manual_wall_payload(), "top_plate_size": "-90x45"})
    assert response.status_code == 422
    with pytest.raises(ValidationError):
        ManualTrussInput(start_x_mm=float("inf"))


def test_meter_normalization_preserves_zero_coordinates():
    row = {**WALL, "end_x_mm": 3.6, "height_mm": 2.535}
    validation = validate_rows([row], "metres")
    assert validation["can_preview"]
    assert validation["rows"][0]["end_x_mm"] == 3600
    assert validation["rows"][0]["start_x_mm"] == 0
