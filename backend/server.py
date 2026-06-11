"""TimberBIM Lite API + static frontend server.

Run from the backend/ directory:
    uvicorn server:app --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

import db
import materials
from framing import ModelConfig

app = FastAPI(title="TimberBIM Lite", version="1.2",
              description="Lite BIM for NZS 3604:2011 timber-framed houses")


def _parse_json_dict(raw: str | None, name: str, warns: list[str]) -> dict:
    """Parse a JSON-object query param; malformed input warns, never fails."""
    if not raw:
        return {}
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        warns.append(f"invalid JSON in {name} — ignored")
        return {}
    if not isinstance(d, dict):
        warns.append(f"{name} is not a JSON object — ignored")
        return {}
    return d


@app.get("/api/model")
def get_model(
    storeys: int = Query(1, ge=1, le=3),
    roof: str = Query("gable", pattern="^(gable|hip)$"),
    wind_zone: str = Query("medium"),
    wind_speed: float | None = Query(None, ge=0, le=120,
                                     description="m/s; overrides wind_zone"),
    snow_zone: str = Query("N0", pattern="^N[0-5]$"),
    gable_spacing: int = Query(600, ge=300, le=1200,
                               description="gable-end stud centres, mm"),
    stud_material_overall: str | None = Query(
        None, description="sg8|sg10|prolam|glulam|hychord|hyspan|hy90"),
    stud_spacing_overall: int | None = Query(
        None, description="mm; clamped to 300-1200 with a warning"),
    wall_plies_overall: int | None = Query(
        None, description="wall-frame plies; clamped to 1-6 with a warning"),
    stud_material_levels: str | None = Query(
        None, description='JSON object, e.g. {"2":"hyspan"}'),
    stud_spacing_levels: str | None = Query(
        None, description='JSON object, e.g. {"1":400}'),
    wall_plies_levels: str | None = Query(
        None, description='JSON object, e.g. {"1":2}'),
    stud_material_segments: str | None = Query(
        None, description='JSON object, e.g. {"G-EXT-001":"hy90"}'),
    stud_spacing_segments: str | None = Query(
        None, description='JSON object, e.g. {"G-EXT-001":300}'),
    wall_plies_segments: str | None = Query(
        None, description='JSON object, e.g. {"G-EXT-001":3}'),
) -> dict:
    """Full framing model (regenerates the SQLite DB when parameters change)."""
    warns: list[str] = []
    cfg = ModelConfig(
        storeys=storeys, roof=roof, wind_zone=wind_zone,
        wind_speed=wind_speed, snow_zone=snow_zone,
        gable_spacing=gable_spacing,
        stud_material_overall=stud_material_overall,
        stud_spacing_overall=stud_spacing_overall,
        wall_plies_overall=wall_plies_overall,
        stud_material_levels=_parse_json_dict(
            stud_material_levels, "stud_material_levels", warns),
        stud_spacing_levels=_parse_json_dict(
            stud_spacing_levels, "stud_spacing_levels", warns),
        wall_plies_levels=_parse_json_dict(
            wall_plies_levels, "wall_plies_levels", warns),
        stud_material_segments=_parse_json_dict(
            stud_material_segments, "stud_material_segments", warns),
        stud_spacing_segments=_parse_json_dict(
            stud_spacing_segments, "stud_spacing_segments", warns),
        wall_plies_segments=_parse_json_dict(
            wall_plies_segments, "wall_plies_segments", warns),
        override_warnings=warns,
    ).normalised()
    return db.model_json(cfg)


@app.get("/api/materials")
def get_materials() -> dict:
    """Stud material catalogue with sourced USD/lm estimating prices."""
    return materials.catalogue_json()


@app.get("/api/cost-summary")
def get_cost_summary() -> dict:
    """Estimated material cost totals (USD) for the current model."""
    return db.cost_summary()


@app.get("/api/bom.csv")
def get_bom() -> Response:
    """Bill of materials — timber elements only, from the SQL `bom` view."""
    return Response(
        content=db.bom_csv(),
        media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="timber_bom_nzs3604.csv"'})


DIST = Path(__file__).parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
