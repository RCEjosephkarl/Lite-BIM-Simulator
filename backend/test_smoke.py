"""Backend smoke tests — run from backend/: python -m pytest test_smoke.py"""

from __future__ import annotations

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

import db
import materials
from framing import CUSTOM_SPACING_NOTE, STUD_LIKE
from server import app

client = TestClient(app)

WALL_CODES = {"stud", "trimmer_stud", "jack_stud", "plate_bottom",
              "plate_top", "nog", "lintel", "sill_trimmer"}
NON_WALL_CODES = {"joist", "blocking", "ceiling_joist", "rafter",
                  "hip_rafter", "jack_rafter", "gable_stud", "ridge",
                  "fascia", "post", "beam", "slab"}


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Keep the dev model.db out of the tests' way."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")


def get_model(params: dict | None = None) -> dict:
    r = client.get("/api/model", params=params or {})
    assert r.status_code == 200, r.text
    return r.json()


def of_type(model: dict, codes: set[str], storey: int | None = None) -> list:
    return [e for e in model["elements"]
            if e["type_code"] in codes
            and (storey is None or e["storey"] == storey)]


def test_default_model_backwards_compatible():
    m = get_model()
    assert m["meta"]["storeys"] == 1
    assert len(m["elements"]) > 500
    for e in of_type(m, WALL_CODES):
        assert e["material"] == "SG8"
        assert e["grade"] == "SG8" or e["type_code"] == "lintel"
        assert e["plies"] == 1
        assert e["segment_id"]
    # default studs keep their original 45 mm breadth
    studs = of_type(m, {"stud"})
    assert studs and all(e["h_mm"] == 45 for e in studs)
    assert m["meta"]["frame_segments"][0]["segment_id"] == "G-EXT-001"
    assert m["meta"]["warnings"] == []


def test_old_params_still_work():
    m = get_model({"storeys": 2, "roof": "hip", "wind_speed": 48,
                   "snow_zone": "N3", "gable_spacing": 400})
    assert m["meta"]["roof"] == "hip"
    assert m["meta"]["storeys"] == 2
    assert m["elements"]


def test_overall_overrides_apply_to_all_walls():
    m = get_model({"stud_material_overall": "sg10",
                   "stud_spacing_overall": 400,
                   "wall_plies_overall": 2})
    stud_like = of_type(m, STUD_LIKE | {"gable_stud"})
    assert stud_like
    assert all(e["material"] == "SG10" for e in stud_like)
    studs = of_type(m, {"stud"})
    assert all(e["stud_spacing_mm"] == 400 for e in studs)
    assert all(e["h_mm"] == 90 for e in studs)  # 2-ply visual width
    plates = of_type(m, {"plate_top"})
    assert all(e["plies"] == 2 and e["h_mm"] == 45 for e in plates)
    assert CUSTOM_SPACING_NOTE in m["meta"]["warnings"]


def test_level_override_beats_overall():
    m = get_model({"storeys": 2, "stud_material_overall": "sg10",
                   "stud_material_levels": json.dumps({"2": "hyspan"})})
    assert all(e["material"] == "SG10"
               for e in of_type(m, {"stud"}, storey=1))
    assert all(e["material"] == "HySPAN"
               for e in of_type(m, {"stud"}, storey=2))


def test_segment_override_beats_level_and_overall():
    m = get_model({"stud_material_overall": "sg10",
                   "stud_material_levels": json.dumps({"1": "hychord"}),
                   "stud_material_segments":
                       json.dumps({"G-EXT-001": "glulam"})})
    seg = [e for e in of_type(m, {"stud"})
           if e["segment_id"] == "G-EXT-001"]
    rest = [e for e in of_type(m, {"stud"})
            if e["segment_id"] != "G-EXT-001"]
    assert seg and all(e["material"] == "Glulam" for e in seg)
    assert rest and all(e["material"] == "HyCHORD" for e in rest)
    segs = {s["segment_id"]: s for s in m["meta"]["frame_segments"]}
    assert segs["G-EXT-001"]["material"] == "Glulam"
    assert segs["G-EXT-002"]["material"] == "HyCHORD"


def test_non_wall_elements_unaffected_by_plies():
    m = get_model({"storeys": 2, "wall_plies_overall": 3})
    non_wall = of_type(m, NON_WALL_CODES)
    assert non_wall
    assert all(e["plies"] == 1 for e in non_wall)
    assert all(e["plies"] == 3 for e in of_type(m, WALL_CODES))


def test_bom_cost_multiplies_by_plies():
    get_model({"wall_plies_overall": 2})  # load the model into the DB
    r = client.get("/api/bom.csv")
    assert r.status_code == 200
    rows = list(csv.DictReader(io.StringIO(r.text)))
    stud_rows = [x for x in rows if x["element"] == "Wall stud"]
    assert stud_rows
    for x in stud_rows:
        assert x["size"] == "2/90x45"
        total = float(x["total_length_m"])
        eff = float(x["total_effective_length_m"])
        assert eff == pytest.approx(2 * total, abs=0.02)
        assert float(x["total_cost_usd"]) == pytest.approx(
            eff * float(x["unit_price_usd_per_lm"]), abs=0.25)
    lintels = [x for x in rows if x["element"] == "Lintel"]
    assert lintels
    assert all(not x["size"].startswith("2/2/") for x in lintels)
    assert all(x["plies"] == "2" for x in lintels)


def test_materials_endpoint_complete():
    r = client.get("/api/materials")
    assert r.status_code == 200
    cat = r.json()
    mats = {m["key"]: m for m in cat["materials"]}
    assert set(mats) == {"sg8", "sg10", "prolam", "glulam",
                         "hychord", "hyspan", "hy90"}
    for m in mats.values():
        assert m["display_name"]
        assert m["category"] in ("sawn_timber", "glulam", "lvl")
        assert m["default_usd_per_lm"] > 0
        assert m["price_confidence"] in ("high", "medium", "low")
        for f in ("price_source_name", "price_source_url",
                  "price_source_date", "source_currency", "source_unit",
                  "fx_source", "fx_date", "pricing_notes"):
            assert m[f], f"{m['key']}.{f} empty"
        assert m["source_price"] > 0 and m["fx_rate_to_usd"] > 0
    assert cat["disclaimers"]


def test_cost_summary_consistent():
    m = get_model()
    cs = m["meta"]["cost_summary"]
    assert cs["currency"] == "USD"
    assert cs["grand_total_usd"] > 0
    by_mat = sum(x["cost_usd"] for x in cs["by_material"])
    assert by_mat == pytest.approx(cs["grand_total_usd"], abs=0.5)
    assert cs["by_segment"] and cs["by_storey"] and cs["by_element"]
    r = client.get("/api/cost-summary")
    assert r.status_code == 200
    assert r.json()["grand_total_usd"] == cs["grand_total_usd"]


def test_invalid_inputs_warn_not_fail():
    m = get_model({"stud_spacing_overall": 5000})
    assert any("clamped" in w for w in m["meta"]["warnings"])
    studs = of_type(m, {"stud"})
    assert all(e["stud_spacing_mm"] == 1200 for e in studs)

    m = get_model({"stud_material_levels": "not-json"})
    assert any("invalid JSON in stud_material_levels" in w
               for w in m["meta"]["warnings"])

    m = get_model({"stud_material_segments": json.dumps({"ZZZ": "sg10"})})
    assert any("unknown frame segment 'ZZZ'" in w
               for w in m["meta"]["warnings"])

    m = get_model({"stud_material_overall": "kryptonite"})
    assert any("unknown stud material 'kryptonite'" in w
               for w in m["meta"]["warnings"])
    assert all(e["material"] == "SG8" for e in of_type(m, {"stud"}))


def test_unit_price_handles_lintel_prefix_and_sed():
    base, *_ = materials.unit_price_usd_per_lm("sg8", "140x45")
    double, *_ = materials.unit_price_usd_per_lm("sg8", "2/140x45")
    sed, *_ = materials.unit_price_usd_per_lm("sg8", "2/290x45 (SED)")
    assert double == pytest.approx(2 * base, abs=0.01)
    assert sed > 0
