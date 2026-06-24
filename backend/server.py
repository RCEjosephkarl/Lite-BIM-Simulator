"""TimberBIM Lite API + static frontend server.

Run from the backend/ directory:
    uvicorn server:app --port 8000
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import (
    FastAPI, File, Form, HTTPException, Query, UploadFile,
)
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import materials
import nzs3604 as nz
from framing import ModelConfig
from imports.csv_plan import parse_csv, rows_to_elements
from imports.schemas import CsvCommitPayload, CsvPlanPayload, VisionCommitPayload
from imports.validators import validate_rows
from manual_inputs import (
    ManualRoofInput,
    ManualTrussInput,
    ManualWallFrameInput,
    generate_roof,
    generate_truss,
    generate_wall,
)
from ml.plan_reader import analyze_image, status as ml_status

app = FastAPI(
    title="TimberBIM Lite", version="2.0",
    description="Lite BIM dashboard for timber-framed residential studies")


def _parse_json_dict(raw: str | None, name: str, warns: list[str]) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        warns.append(f"invalid JSON in {name} - ignored")
        return {}
    if not isinstance(value, dict):
        warns.append(f"{name} is not a JSON object - ignored")
        return {}
    return value


def _config(
    storeys: int, roof: str, wind_zone: str, wind_speed: float | None,
    snow_zone: str, gable_spacing: int, stud_material_overall: str | None,
    stud_spacing_overall: int | None, wall_plies_overall: int | None,
    stud_material_levels: str | None, stud_spacing_levels: str | None,
    wall_plies_levels: str | None, stud_material_segments: str | None,
    stud_spacing_segments: str | None, wall_plies_segments: str | None,
) -> ModelConfig:
    warns: list[str] = []
    return ModelConfig(
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


@app.get("/api/model")
async def get_model(
    storeys: int = Query(1, ge=1, le=3),
    roof: str = Query("gable", pattern="^(gable|hip)$"),
    wind_zone: str = Query("medium"),
    wind_speed: float | None = Query(None, ge=0, le=120),
    snow_zone: str = Query("N0", pattern="^N[0-5]$"),
    gable_spacing: int = Query(600, ge=300, le=1200),
    stud_material_overall: str | None = None,
    stud_spacing_overall: int | None = None,
    wall_plies_overall: int | None = None,
    stud_material_levels: str | None = None,
    stud_spacing_levels: str | None = None,
    wall_plies_levels: str | None = None,
    stud_material_segments: str | None = None,
    stud_spacing_segments: str | None = None,
    wall_plies_segments: str | None = None,
) -> dict:
    # v2.79: settings are persisted as project defaults and returned with the
    # current (empty-by-default) geometry; they no longer regenerate a sample
    # house, so drawn/imported walls survive a settings change.
    return db.model_json(_config(
        storeys, roof, wind_zone, wind_speed, snow_zone, gable_spacing,
        stud_material_overall, stud_spacing_overall, wall_plies_overall,
        stud_material_levels, stud_spacing_levels, wall_plies_levels,
        stud_material_segments, stud_spacing_segments, wall_plies_segments,
    ))


@app.get("/api/materials")
async def get_materials() -> dict:
    return materials.catalogue_json()


@app.get("/api/pricing")
async def get_pricing() -> dict:
    catalogue = materials.catalogue_json()
    rows = [{
        "material": item["display_name"],
        "key": item["key"],
        "category": item["category"],
        "default_size": item["default_size_mm"],
        "nzd_per_linear_metre": item["default_nzd_per_lm"],
        "confidence": item["price_confidence"],
        "source_name": item["price_source_name"],
        "source_date": item["price_source_date"],
        "source_url": item["price_source_url"],
        "notes": item["pricing_notes"],
    } for item in catalogue["materials"]]
    return {
        "rows": rows, "currency": "NZD", "snapshot": catalogue["snapshot"],
        "disclaimer": "Estimating only - not supplier quote (NZD).",
    }


@app.get("/api/cost-summary")
async def get_cost_summary() -> dict:
    return db.cost_summary()


@app.get("/api/warnings")
async def get_warnings() -> dict:
    return db.warnings_json()


@app.get("/api/bom.json")
async def get_bom_json() -> dict:
    return db.bom_json()


@app.get("/api/bom.csv")
async def get_bom() -> Response:
    return Response(
        content=db.bom_csv(), media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="timber_bom_nzs3604.csv"'})


def _preview_response(elements: list[dict], warnings: list[str]) -> dict:
    prepared = []
    for index, element in enumerate(elements, start=1):
        item = db._prepare_element(element)  # canonical API element contract
        item["id"] = -index
        item["editable"] = True
        if isinstance(item["warnings"], str):
            item["warnings"] = json.loads(item["warnings"])
        prepared.append(item)
    return {
        "elements": prepared,
        "types": [
            {"code": code, "name": values[0], "category": values[1],
             "nzs_ref": values[2], "color_hex": values[3]}
            for code, values in nz.ELEMENT_TYPES.items()
        ],
        "metadata": {
            "temporary": True, "member_count": len(prepared),
            "lineal_metres": round(sum(
                e["length_mm"] * e["plies"] for e in prepared) / 1000, 2),
            "estimated_cost_nzd": round(sum(
                e["length_mm"] * e["plies"]
                * (e["unit_price_nzd_per_lm"] or 0)
                for e in prepared) / 1000, 2),
            "warnings": list(dict.fromkeys(warnings)),
        },
    }


@app.post("/api/import/csv-plan/validate")
async def validate_csv_plan(
    file: UploadFile = File(...),
    units: Literal["mm", "metres", "feet_inches"] = Form("mm"),
) -> dict:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file")
    result = parse_csv(await file.read(), units)
    result["file_name"] = file.filename
    result["units"] = "mm"
    return result


@app.post("/api/import/csv-plan/preview")
async def preview_csv_plan(payload: CsvPlanPayload) -> dict:
    validation = validate_rows(payload.rows, payload.units)
    if validation["errors"]:
        raise HTTPException(422, {"message": "Fix invalid rows before preview",
                                  **validation})
    batch_id = f"csv-preview-{uuid.uuid4().hex[:10]}"
    elements, warnings = rows_to_elements(
        validation["normalized_entities"], "csv_preview", batch_id)
    return {
        **_preview_response(elements, warnings),
        "validation": validation, "batch_id": batch_id,
    }


@app.post("/api/import/csv-plan/commit")
async def commit_csv_plan(payload: CsvCommitPayload) -> dict:
    validation = validate_rows(payload.rows, payload.units)
    if validation["errors"]:
        raise HTTPException(422, {"message": "Fix invalid rows before commit",
                                  **validation})
    batch_id = f"csv-{uuid.uuid4().hex[:10]}"
    elements, warnings = rows_to_elements(
        validation["normalized_entities"], "csv_import", batch_id)
    if payload.mode == "append_to_sample_geometry":
        db.append_elements(
            elements, "csv_import", batch_id, payload.file_name,
            len(payload.rows), len(validation["normalized_entities"]),
            len(payload.rows) - len(validation["normalized_entities"]),
            len(warnings))
    else:
        db.replace_geometry(
            elements, "csv_import", batch_id, payload.file_name,
            len(payload.rows), len(warnings))
    return {"batch_id": batch_id, "model": db.model_json()}


@app.post("/api/manual/wall-frame/preview")
async def preview_manual_wall(spec: ManualWallFrameInput) -> dict:
    source_id = spec.input_id or f"wall-preview-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_wall(spec, "csv_preview", source_id)
    for element in elements:
        element["source"] = "csv_preview"
    return _preview_response(elements, warnings)


@app.post("/api/manual/wall-frame/commit")
async def commit_manual_wall(spec: ManualWallFrameInput) -> dict:
    source_id = spec.input_id or f"manual-wall-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_wall(spec, "manual_wall", source_id)
    db.append_elements(
        elements, "manual_wall", source_id, spec.segment_label, 1, 1, 0,
        len(warnings))
    return {"source_id": source_id, "model": db.model_json()}


class ManualWallsPayload(BaseModel):
    walls: list[ManualWallFrameInput]


@app.post("/api/manual/walls/preview")
async def preview_manual_walls(payload: ManualWallsPayload) -> dict:
    """Bulk preview for the 2D plan editor — one ManualWallFrameInput per drawn
    wall. Reuses generate_wall(); nothing is written to the DB."""
    elements: list[dict] = []
    warnings: list[str] = []
    for index, spec in enumerate(payload.walls, start=1):
        source_id = spec.input_id or f"wall-preview-{index}"
        els, warns = generate_wall(spec, "csv_preview", source_id)
        for element in els:
            element["source"] = "csv_preview"
        elements.extend(els)
        warnings.extend(warns)
    return _preview_response(elements, warnings)


@app.post("/api/manual/walls/commit")
async def commit_manual_walls(payload: ManualWallsPayload) -> dict:
    """Bulk commit for the 2D plan editor — builds every drawn wall's frame."""
    if not payload.walls:
        raise HTTPException(422, "Draw at least one wall before committing")
    batch_id = f"manual-walls-{uuid.uuid4().hex[:10]}"
    elements: list[dict] = []
    warnings: list[str] = []
    for index, spec in enumerate(payload.walls, start=1):
        els, warns = generate_wall(
            spec, "manual_wall", spec.input_id or f"{batch_id}-{index}")
        elements.extend(els)
        warnings.extend(warns)
    db.append_elements(
        elements, "manual_wall", batch_id, "2D plan editor",
        len(payload.walls), len(payload.walls), 0, len(warnings))
    return {"batch_id": batch_id, "model": db.model_json()}


@app.post("/api/roof/preview")
async def preview_roof(spec: ManualRoofInput) -> dict:
    source_id = spec.input_id or f"roof-preview-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_roof(spec, "vision_preview", source_id)
    return _preview_response(elements, warnings)


@app.post("/api/roof/commit")
async def commit_roof(spec: ManualRoofInput) -> dict:
    source_id = spec.input_id or f"manual-roof-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_roof(spec, "manual_truss", source_id)
    db.append_elements(
        elements, "manual_truss", source_id, spec.roof_label, 1, 1, 0,
        len(warnings))
    return {"source_id": source_id, "model": db.model_json()}


@app.post("/api/manual/truss/preview")
async def preview_manual_truss(spec: ManualTrussInput) -> dict:
    source_id = spec.input_id or f"truss-preview-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_truss(spec, "vision_preview", source_id)
    return _preview_response(elements, warnings)


@app.post("/api/manual/truss/commit")
async def commit_manual_truss(spec: ManualTrussInput) -> dict:
    source_id = spec.input_id or f"manual-truss-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_truss(spec, "manual_truss", source_id)
    db.append_elements(
        elements, "manual_truss", source_id, spec.truss_label, 1, 1, 0,
        len(warnings))
    return {"source_id": source_id, "model": db.model_json()}


@app.get("/api/ml/status")
async def get_ml_status() -> dict:
    return ml_status()


@app.post("/api/import/vision-plan/analyze")
async def analyze_vision_plan(
    files: list[UploadFile] = File(default=[]),
    manifest: UploadFile | None = File(default=None),
) -> dict:
    manifest_rows: dict[str, dict] = {}
    if manifest:
        try:
            text = (await manifest.read()).decode("utf-8-sig")
            manifest_rows = {
                row.get("file_name", ""): row
                for row in csv.DictReader(io.StringIO(text))
            }
        except (UnicodeDecodeError, csv.Error) as exc:
            raise HTTPException(400, f"Invalid manifest CSV: {exc}") from exc
    if not files:
        current = ml_status()
        return {
            "status": "no_images", "proposals": [],
            "warnings": current["warnings"] + [
                "Upload PNG, JPG/JPEG, or WEBP plan images."
            ],
        }
    results = []
    proposals = []
    warnings = []
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            warnings.append(f"{file.filename}: unsupported image type")
            continue
        meta = manifest_rows.get(file.filename or "", {})
        result = analyze_image(
            await file.read(), meta.get("drawing_id") or file.filename or "plan",
            int(meta.get("level") or 1),
            float(meta["scale_mm_per_px"])
            if meta.get("scale_mm_per_px") else None)
        results.append({"file_name": file.filename, **result})
        proposals.extend(result["proposals"])
        warnings.extend(result["warnings"])
    return {
        "status": (
            "proposal_ready" if proposals else "model_not_configured"),
        "proposals": proposals, "drawings": results,
        "warnings": list(dict.fromkeys(warnings)),
        "review_required": True,
    }


@app.post("/api/import/vision-plan/commit")
async def commit_vision_plan(payload: VisionCommitPayload) -> dict:
    accepted = [
        proposal for proposal in payload.proposals
        if proposal.get("accepted") and float(proposal.get("confidence", 0)) >= 0.25
    ]
    if not accepted:
        raise HTTPException(422, "No reviewed proposals were accepted")
    # Reviewed proposals use the same explicit wall/opening/truss row contract.
    validation = validate_rows(accepted, "mm")
    if validation["errors"]:
        raise HTTPException(
            422, {"message": "Edit AI proposals into valid geometry", **validation})
    batch_id = f"vision-{uuid.uuid4().hex[:10]}"
    elements, warnings = rows_to_elements(
        validation["normalized_entities"], "vision_import", batch_id)
    confidence = min(float(p.get("confidence", 1)) for p in accepted)
    for element in elements:
        element["confidence"] = confidence
    if payload.mode == "append_to_sample_geometry":
        db.append_elements(
            elements, "vision_import", batch_id, payload.file_name,
            len(payload.proposals), len(accepted),
            len(payload.proposals) - len(accepted), len(warnings))
    else:
        db.replace_geometry(
            elements, "vision_import", batch_id, payload.file_name,
            len(payload.proposals), len(warnings))
    return {"batch_id": batch_id, "model": db.model_json()}


@app.get("/api/import/batches")
async def get_import_batches() -> dict:
    return {"batches": db.import_batches()}


@app.delete("/api/import/batches/{batch_id}")
async def remove_import_batch(batch_id: str) -> dict:
    return {"batch_id": batch_id, "deleted_elements": db.delete_batch(batch_id),
            "model": db.model_json()}


class ProjectRegenerateOptions(BaseModel):
    preserve_manual: bool = True
    preserve_imports: bool = True
    replace_geometry: bool = False


@app.post("/api/project/reset")
async def reset_project() -> dict:
    return db.reset_project()


@app.post("/api/project/regenerate")
async def regenerate_project(options: ProjectRegenerateOptions) -> dict:
    db.rebuild(
        db.current_config(),
        preserve_manual=options.preserve_manual and not options.replace_geometry,
        preserve_imports=options.preserve_imports and not options.replace_geometry,
    )
    return db.model_json()


DIST = Path(__file__).parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
