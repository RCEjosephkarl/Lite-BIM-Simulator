"""Backend smoke tests (v2.79) — run from backend/: python -m pytest test_smoke.py

Covers the reworked product: an empty-canvas default, NZD costing, the 2D plan
editor's bulk-wall endpoints, and the three roof styles (gable run, hip rafter,
MiTek hip truss). The optional sample-house generator still lives in framing.py
but is no longer the boot path, so these tests no longer assert sample geometry.
"""

from __future__ import annotations

import asyncio
import csv
import io

import httpx
import pytest

import db
import materials
from server import app

WALL_CODES = {"stud", "trimmer_stud", "jack_stud", "plate_bottom",
              "plate_top", "nog", "lintel", "sill_trimmer"}


class SyncAsgiClient:
    """Small test client that avoids a cross-thread portal in restricted CI."""

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        async def run() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(run())

    def get(self, url, **kw): return self.request("GET", url, **kw)
    def post(self, url, **kw): return self.request("POST", url, **kw)
    def delete(self, url, **kw): return self.request("DELETE", url, **kw)


client = SyncAsgiClient()


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Keep the dev model.db out of the tests' way (fresh empty project each test)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")


def get_model(params: dict | None = None) -> dict:
    r = client.get("/api/model", params=params or {})
    assert r.status_code == 200, r.text
    return r.json()


def codes(model: dict) -> set[str]:
    return {e["type_code"] for e in model["elements"]}


WALL_A = {
    "level": 1, "segment_label": "Front", "start_x_mm": 0, "start_z_mm": 0,
    "end_x_mm": 6000, "end_z_mm": 0, "wall_height_mm": 2535,
    "stud_material": "SG8", "stud_spacing_mm": 600,
    "openings": [{"opening_type": "door", "start_offset_mm": 2400,
                  "width_mm": 900, "height_mm": 1980, "sill_height_mm": 0}],
}
WALL_B = {
    "level": 1, "segment_label": "Side", "start_x_mm": 6000, "start_z_mm": 0,
    "end_x_mm": 6000, "end_z_mm": 5000, "wall_height_mm": 2535,
}


def roof_payload(style: str) -> dict:
    return {"style": style, "length_mm": 9000, "width_mm": 7000,
            "pitch_deg": 25, "spacing_mm": 900, "overhang_mm": 450}


# --------------------------------------------------------------------------
# Empty canvas + settings persistence
# --------------------------------------------------------------------------

def test_default_model_is_empty():
    m = get_model()
    assert m["elements"] == []
    assert m["meta"]["storeys"] == 1
    assert m["meta"]["cost_summary"]["currency"] == "NZD"
    assert m["meta"]["cost_summary"]["grand_total_nzd"] == 0


def test_settings_do_not_wipe_drawn_geometry():
    committed = client.post("/api/manual/walls/commit", json={"walls": [WALL_A]})
    assert committed.status_code == 200, committed.text
    before = len(committed.json()["model"]["elements"])
    assert before > 0
    # changing roof/storeys settings must keep the drawn frame intact
    m = get_model({"roof": "hip", "storeys": 2, "snow_zone": "N3"})
    assert len(m["elements"]) == before
    assert m["meta"]["roof"] == "hip"


def test_project_reset_returns_to_empty_canvas():
    client.post("/api/manual/walls/commit", json={"walls": [WALL_A]})
    r = client.post("/api/project/reset", json={})
    assert r.status_code == 200
    assert r.json()["elements"] == []


# --------------------------------------------------------------------------
# 2D plan editor — bulk walls
# --------------------------------------------------------------------------

def test_bulk_walls_preview_does_not_commit():
    payload = {"walls": [WALL_A, WALL_B]}
    preview = client.post("/api/manual/walls/preview", json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["metadata"]["member_count"] > 0
    assert "estimated_cost_nzd" in preview.json()["metadata"]
    assert get_model()["elements"] == []   # nothing written


def test_bulk_walls_commit_builds_frames_with_opening():
    r = client.post("/api/manual/walls/commit", json={"walls": [WALL_A, WALL_B]})
    assert r.status_code == 200, r.text
    model = r.json()["model"]
    built = codes(model)
    assert {"stud", "plate_bottom", "plate_top"} <= built
    assert "lintel" in built  # from WALL_A's door opening
    assert all(e["source"] == "manual_wall" and e["editable"]
               for e in model["elements"])


def test_bulk_walls_commit_requires_walls():
    r = client.post("/api/manual/walls/commit", json={"walls": []})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Roof styles — gable run, hip rafter, MiTek hip truss
# --------------------------------------------------------------------------

def test_gable_run_roof_makes_standard_trusses():
    r = client.post("/api/roof/commit", json=roof_payload("gable_run"))
    assert r.status_code == 200, r.text
    built = codes(r.json()["model"])
    assert {"truss_top_chord", "truss_bottom_chord", "truss_web"} <= built


def test_hip_rafter_roof_is_stick_framed():
    r = client.post("/api/roof/commit", json=roof_payload("hip_rafter"))
    assert r.status_code == 200, r.text
    built = codes(r.json()["model"])
    assert {"ridge", "hip_rafter", "rafter"} <= built


def test_mitek_hip_truss_system_has_girder_jacks_and_crown():
    r = client.post("/api/roof/commit", json=roof_payload("mitek_hip"))
    assert r.status_code == 200, r.text
    model = r.json()["model"]
    built = codes(model)
    # standard trusses + truncated girder + step-down jacks + crown/creepers
    assert {"truss_top_chord", "truss_girder",
            "truss_jack", "truss_crown"} <= built
    assert all(e["length_mm"] > 0 for e in model["elements"])
    girders = [e for e in model["elements"] if e["type_code"] == "truss_girder"]
    assert girders and all(e["plies"] == 3 for e in girders)


# --------------------------------------------------------------------------
# NZD costing
# --------------------------------------------------------------------------

def test_pricing_endpoint_is_nzd_without_fx():
    r = client.get("/api/pricing")
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "NZD"
    assert body["snapshot"] == "2026-06-22 09:00 NZST"
    assert "fx" not in body
    assert all(row["nzd_per_linear_metre"] > 0 for row in body["rows"])


def test_materials_catalogue_is_nzd_without_fx_fields():
    cat = client.get("/api/materials").json()
    assert cat["currency"] == "NZD"
    mats = {m["key"]: m for m in cat["materials"]}
    assert set(mats) == {"sg8", "sg10", "prolam", "glulam",
                         "hychord", "hyspan", "hy90"}
    for m in mats.values():
        assert m["default_nzd_per_lm"] > 0
        assert m["source_currency"] == "NZD"
        assert m["price_source_date"] == "2026-06-22"
        assert "fx_rate_to_usd" not in m and "fx_date" not in m


def test_unit_price_nzd_handles_lintel_prefix_and_sed():
    base, *_ = materials.unit_price_nzd_per_lm("sg8", "140x45")
    double, *_ = materials.unit_price_nzd_per_lm("sg8", "2/140x45")
    sed, *_ = materials.unit_price_nzd_per_lm("sg8", "2/290x45 (SED)")
    # raw NZD value, no FX conversion
    assert base == pytest.approx(9.44, abs=0.01)
    assert double == pytest.approx(2 * base, abs=0.01)
    assert sed > 0


def test_cost_summary_and_bom_are_nzd_consistent():
    client.post("/api/manual/walls/commit", json={"walls": [WALL_A, WALL_B]})
    cs = client.get("/api/cost-summary").json()
    assert cs["currency"] == "NZD"
    assert cs["grand_total_nzd"] > 0
    by_mat = sum(x["cost_nzd"] for x in cs["by_material"])
    assert by_mat == pytest.approx(cs["grand_total_nzd"], abs=0.5)

    rows = list(csv.DictReader(io.StringIO(client.get("/api/bom.csv").text)))
    studs = [x for x in rows if x["element"] == "Wall stud"]
    assert studs
    for x in studs:
        eff = float(x["total_effective_length_m"])
        assert float(x["total_cost_nzd"]) == pytest.approx(
            eff * float(x["unit_price_nzd_per_lm"]), abs=0.25)


# --------------------------------------------------------------------------
# Removed dashboard + retained CSV / manual / ML surfaces
# --------------------------------------------------------------------------

def test_dashboard_endpoint_is_removed():
    assert client.get("/api/dashboard").status_code == 404


VALID_PLAN_CSV = """type,level,segment_id,label,start_x_mm,start_z_mm,end_x_mm,end_z_mm,height_mm,wall_segment_id,opening_id,opening_type,start_offset_mm,width_mm,sill_height_mm,head_height_mm
wall,1,W-1,Imported wall,0,0,6000,0,2535,,,,,,,
opening,1,,,,,,,1200,W-1,O-1,window,1800,1200,900,2100
"""


def test_csv_validation_accepts_valid_wall_and_opening():
    response = client.post(
        "/api/import/csv-plan/validate",
        files={"file": ("plan.csv", VALID_PLAN_CSV, "text/csv")},
        data={"units": "mm"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["can_preview"]
    assert result["summary"]["wall_count"] == 1
    assert result["summary"]["opening_count"] == 1


def test_csv_validation_rejects_missing_required_columns():
    response = client.post(
        "/api/import/csv-plan/validate",
        files={"file": ("bad.csv", "type,level\nwall,1\n", "text/csv")},
        data={"units": "mm"})
    assert response.status_code == 200
    assert not response.json()["can_preview"]


def test_manual_wall_preview_does_not_commit_then_commit_tracks_source():
    before = len(get_model()["elements"])
    preview = client.post("/api/manual/wall-frame/preview", json=WALL_A)
    assert preview.status_code == 200, preview.text
    assert preview.json()["metadata"]["member_count"] > 0
    assert len(db.model_json()["elements"]) == before

    committed = client.post("/api/manual/wall-frame/commit", json=WALL_A)
    assert committed.status_code == 200, committed.text
    additions = [e for e in committed.json()["model"]["elements"]
                 if e["source"] == "manual_wall"]
    assert additions and all(e["editable"] for e in additions)


def test_manual_truss_preview_returns_chord_and_web_elements():
    response = client.post("/api/manual/truss/preview", json={
        "level": 1, "truss_label": "T1", "span_mm": 9000, "pitch_deg": 25,
        "spacing_mm": 900, "quantity": 2, "truss_type": "common"})
    assert response.status_code == 200, response.text
    built = {e["type_code"] for e in response.json()["elements"]}
    assert {"truss_top_chord", "truss_bottom_chord", "truss_web"} <= built


def test_bom_json_and_ml_status_available_without_ml_dependencies():
    client.post("/api/manual/walls/commit", json={"walls": [WALL_A]})
    bom = client.get("/api/bom.json")
    assert bom.status_code == 200
    assert bom.json()["rows"]
    assert bom.json()["currency"] == "NZD"
    status = client.get("/api/ml/status")
    assert status.status_code == 200
    assert "model_available" in status.json()
