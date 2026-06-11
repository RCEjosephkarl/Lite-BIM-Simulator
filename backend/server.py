"""TimberBIM Lite API + static frontend server.

Run from the backend/ directory:
    uvicorn server:app --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

import db
from framing import ModelConfig

app = FastAPI(title="TimberBIM Lite", version="1.1",
              description="Lite BIM for NZS 3604:2011 timber-framed houses")


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
) -> dict:
    """Full framing model (regenerates the SQLite DB when parameters change)."""
    cfg = ModelConfig(storeys=storeys, roof=roof, wind_zone=wind_zone,
                      wind_speed=wind_speed, snow_zone=snow_zone,
                      gable_spacing=gable_spacing).normalised()
    return db.model_json(cfg)


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
