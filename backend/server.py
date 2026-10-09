"""TimberBIM Lite API + static frontend server.

Run from the backend/ directory:
    uvicorn server:app --port 8000
"""

from __future__ import annotations

import json
import uuid
import hashlib
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Literal
import math
import time

from fastapi import (
    FastAPI, File, Form, HTTPException, Query, UploadFile, Request,
)
from fastapi.responses import Response, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import estimating
import materials
import nzs3604 as nz
import projects
import preview_contract
import home_definition
import home_archive
import review
import diagnostics
from framing import ModelConfig
from imports.csv_plan import parse_csv, rows_to_elements
from imports.schemas import CsvCommitPayload, CsvPlanPayload
from imports.validators import finite_json, validate_rows
from manual_inputs import (
    ManualTrussInput,
    ManualWallFrameInput,
    generate_truss,
    generate_wall,
)
from trusses import canonical_graph

app = FastAPI(
    title="TimberBIM Lite", version=(Path(__file__).parent.parent / "VERSION").read_text().strip(),
    description="Lite BIM workspace for timber-framed residential studies")


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, exc: RequestValidationError):
    # Non-standard JSON NaN/Infinity must not destroy field locations while
    # FastAPI serializes validation errors containing the original input.
    errors, _ = finite_json(jsonable_encoder(exc.errors()))
    return JSONResponse({"detail": errors}, status_code=422)


@app.middleware("http")
async def project_scope(request: Request, call_next):
    identifier = request.query_params.get("project_id", "default")
    scope_token = projects.project_id.set(identifier)
    write_token = None
    read_token = None
    started = time.perf_counter()
    current = {"request_id": uuid.uuid4().hex}
    diagnostic_token = diagnostics.context.set(current)
    status, error_type = 500, None
    failure = None

    def respond(response):
        nonlocal status
        status = response.status_code
        response.headers["X-Request-ID"] = current["request_id"]
        if "project_id" in current:
            response.headers["X-Project-ID"] = identifier
        return response

    try:
        projects.path(db.DB_PATH)  # Validate IDs before touching the filesystem.
        current["project_id"] = identifier
        requested = request.query_params.get("revision")
        read_token = projects.read_revision.set(int(requested) if requested is not None else None)
        current["expected_revision"] = projects.read_revision.get()
        body = bytearray()
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            async for chunk in request.stream():
                if len(body) + len(chunk) > 16 * 1024 * 1024:
                    return respond(JSONResponse({"detail": "Request exceeds the 16 MiB API limit"}, status_code=413))
                body.extend(chunk)
            # Starlette's cached middleware request replays this bounded body to
            # multipart/JSON parsers instead of consuming the network twice.
            request._body = bytes(body)
        revision = request.headers.get("If-Match")
        if revision is not None:
            revision = int(revision.strip('"'))
            current["expected_revision"] = revision
        write_token = projects.write_contract.set({
            "revision": revision, "key": request.headers.get("Idempotency-Key"),
            "digest": hashlib.sha256(request.url.path.encode() + json.dumps(sorted(request.query_params.multi_items())).encode() + bytes(body)).hexdigest()
            if request.method in {"POST", "PUT", "DELETE", "PATCH"} else None,
        })
        command = request.method in {"POST", "PUT", "DELETE", "PATCH"} and not request.url.path.endswith(("/preview", "/validate", "/review", "/initialize")) and request.url.path != "/api/projects"
        if command and identifier != "default" and revision is None:
            return respond(JSONResponse({"detail": "Send If-Match with the current project revision"}, status_code=428))
        response = await call_next(request)
        return respond(response)
    except projects.ProjectConflict as exc:
        failure = exc
        error_type = type(exc).__name__
        return respond(JSONResponse({"detail": str(exc)}, status_code=409))
    except (FileNotFoundError, KeyError) as exc:
        failure = exc
        error_type = type(exc).__name__
        return respond(JSONResponse({"detail": str(exc)}, status_code=404))
    except ValueError as exc:
        failure = exc
        error_type = type(exc).__name__
        return respond(JSONResponse({"detail": str(exc)}, status_code=422))
    except RuntimeError as exc:
        failure = exc
        error_type = type(exc).__name__
        return respond(JSONResponse({"detail": str(exc)}, status_code=503))
    except Exception as exc:
        error_type = type(exc).__name__
        failure = exc
        return respond(JSONResponse({"detail": "Unexpected server error; use the request reference to diagnose it"}, status_code=500))
    finally:
        diagnostics.emit(request, current, status, (time.perf_counter()-started)*1000, error_type, failure)
        diagnostics.context.reset(diagnostic_token)
        if write_token is not None:
            projects.write_contract.reset(write_token)
        if read_token is not None:
            projects.read_revision.reset(read_token)
        projects.project_id.reset(scope_token)


def _preview_proof(result, payload):
    revision = result["project_revision"]
    result["preview_token"] = preview_contract.issue(payload, revision)
    result["project_revision"] = revision
    return result


def _check_preview(request, payload):
    token = request.headers.get("X-Preview-Token")
    # Existing integrations retain the default-project compatibility path.
    # The browser and all named-project commits use the strict contract.
    if not token and projects.project_id.get() == "default":
        return
    revision = preview_contract.verify(token or "", payload)
    contract = projects.write_contract.get()
    contract["revision"] = revision


@app.get("/api/health")
async def health() -> dict:
    result = db.database_health()
    if not result["ready"]:
        raise HTTPException(503, result)
    return {**result, "version": app.version}


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
    wall_treatment: str | None = None,
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
        wall_treatment=wall_treatment,
        override_warnings=warns,
    ).normalised()


@app.get("/api/model")
async def get_model() -> dict:
    return db.model_json()


@app.post("/api/model")
async def update_model(
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
    wall_treatment: str | None = None,
) -> dict:
    return db.update_config(_config(
        storeys, roof, wind_zone, wind_speed, snow_zone, gable_spacing,
        stud_material_overall, stud_spacing_overall, wall_plies_overall,
        stud_material_levels, stud_spacing_levels, wall_plies_levels,
        stud_material_segments, stud_spacing_segments, wall_plies_segments,
        wall_treatment,
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
        "usd_per_linear_metre": item["default_usd_per_lm"],
        "confidence": materials.unit_price_usd_per_lm(item["key"], item["default_size_mm"])[1],
        "source_name": item["price_source_name"],
        "source_date": item["price_source_date"],
        "source_url": item["price_source_url"],
        "source_currency": item["source_currency"],
        "fx_rate": item["fx_rate_to_usd"], "fx_date": item["fx_date"],
        "notes": item["pricing_notes"],
    } for item in catalogue["materials"]]
    return {
        "rows": rows, "fx": catalogue["fx"], "overrides": db.price_overrides(),
        "disclaimer": "Estimating only - not supplier quote.",
    }


class PriceOverrides(BaseModel):
    overrides: dict[str, float]


@app.post("/api/pricing/overrides")
async def override_prices(payload: PriceOverrides) -> dict:
    if any(key not in materials.MATERIALS or not math.isfinite(value) or value < 0
           for key, value in payload.overrides.items()):
        raise HTTPException(422, "Overrides need a known material and a finite nonnegative USD rate per physical board metre")
    return db.update_prices(payload.overrides)


@app.get("/api/cost-summary")
async def get_cost_summary() -> dict:
    return db.cost_summary()


@app.get("/api/warnings")
async def get_warnings() -> dict:
    return db.warnings_json()


@app.get("/api/bom.json")
async def get_bom_json(member_id: int | None = Query(None, gt=0, le=2**63-1)) -> dict:
    return db.bom_json(member_id)


@app.get("/api/bom.csv")
async def get_bom() -> Response:
    return Response(
        content=db.bom_csv(), media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="timber_bom_nzs3604.csv"'})


def _preview_response(elements: list[dict], warnings: list[str], expected_revision: int | None = None,
                      pricing: home_archive.PriceInput | None = None,
                      review_home: dict | None = None, review_params: dict | None = None) -> dict:
    prepared = []
    overrides, revision, saved_at = {}, 0, ""
    params=review_params or asdict(ModelConfig())
    if db.database_health()["status"] != "uninitialized":
        db.require_model()
        with closing(db.connect()) as con:
            con.execute("BEGIN")
            revision = projects.info(con)["revision"]
            if expected_revision is not None and revision != expected_revision:
                raise projects.ProjectConflict("Home changed while generating preview. Reload and preview again.")
            overrides = db._meta_json(con, "price_overrides", {})
            saved_at = db._meta_json(con, "price_overrides_saved_at", "")
            if review_params is None:
                params=db._meta_json(con,"params",{})
    if pricing is not None:
        overrides, saved_at = pricing.overrides, pricing.saved_at
    for index, element in enumerate(elements, start=1):
        item = db._prepare_element(element)  # canonical API element contract
        db._price(item, overrides, saved_at)
        item["id"] = -index
        item["editable"] = True
        if isinstance(item["warnings"], str):
            item["warnings"] = json.loads(item["warnings"])
        prepared.append(item)
    return {
        "project_revision": revision,
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
            **estimating.preview_summary(prepared),
            "frame_segments": db._frame_segments(prepared, []),
            "review": {**review.evaluate(prepared,params,review_home),"project_revision":revision},
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
    content = await file.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "CSV upload exceeds 8 MiB")
    result = parse_csv(content, units)
    result["file_name"] = file.filename
    result["units"] = "mm"
    return diagnostics.validation_result(result)


@app.post("/api/import/csv-plan/preview")
async def preview_csv_plan(payload: CsvPlanPayload) -> dict:
    validation = validate_rows(payload.rows, payload.units)
    if not validation["can_preview"]:
        raise HTTPException(422, {"message": "Fix invalid rows before preview",
                                  **validation})
    batch_id = f"csv-preview-{uuid.uuid4().hex[:10]}"
    elements, warnings = rows_to_elements(
        validation["normalized_entities"], "csv_preview", batch_id)
    return _preview_proof({
        **_preview_response(elements, warnings),
        "validation": validation, "batch_id": batch_id,
    }, {"rows": validation["normalized_entities"], "units": "mm"})


@app.post("/api/import/csv-plan/review")
async def review_csv_plan(payload: CsvPlanPayload) -> dict:
    return diagnostics.validation_result(validate_rows(payload.rows, payload.units))


@app.post("/api/import/csv-plan/commit")
async def commit_csv_plan(payload: CsvCommitPayload, request: Request) -> dict:
    validation = validate_rows(payload.rows, payload.units)
    if not validation["can_preview"]:
        raise HTTPException(422, {"message": "Fix invalid rows before commit",
                                  **validation})
    definition = {"rows": validation["normalized_entities"], "units": "mm"}
    _check_preview(request, definition)
    if payload.mode == "new_project_from_csv":
        contract = dict(projects.write_contract.get())
        key = contract.get("key")
        identifier = (uuid.uuid5(uuid.NAMESPACE_URL, projects.project_id.get() + ":new:" + key).hex
                      if key else uuid.uuid4().hex)
        scope_token = projects.project_id.set(identifier)
        contract["revision"] = 0
        write_token = projects.write_contract.set(contract)
        try:
            if db.current_params() is None:
                creation = {"key": key, "digest": contract.get("digest")} if key else None
                db.create_project(payload.file_name or "Imported home", "custom", creation)
            batch_id = projects.operation_id("csv")
            elements, warnings = rows_to_elements(validation["normalized_entities"], "csv_import", batch_id)
            db.append_elements(elements, "csv_import", batch_id, payload.file_name,
                               len(payload.rows), len(validation["normalized_entities"]), 0,
                               len(warnings), definition=definition)
            return {"batch_id": batch_id, "model": db.model_json()}
        finally:
            projects.write_contract.reset(write_token)
            projects.project_id.reset(scope_token)
    batch_id = projects.operation_id("csv")
    elements, warnings = rows_to_elements(
        validation["normalized_entities"], "csv_import", batch_id)
    if payload.mode == "append_to_sample_geometry":
        db.append_elements(
            elements, "csv_import", batch_id, payload.file_name,
            len(payload.rows), len(validation["normalized_entities"]),
            len(payload.rows) - len(validation["normalized_entities"]),
            len(warnings), definition=definition)
    else:
        db.replace_geometry(
            elements, "csv_import", batch_id, payload.file_name,
            len(payload.rows), len(warnings), definition=definition)
    return {"batch_id": batch_id, "model": db.model_json()}


@app.post("/api/manual/wall-frame/preview")
async def preview_manual_wall(spec: ManualWallFrameInput) -> dict:
    source_id = spec.input_id or f"wall-preview-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_wall(spec, "csv_preview", source_id)
    for element in elements:
        element["source"] = "csv_preview"
    return _preview_proof(_preview_response(elements, warnings), spec.model_dump())


@app.put("/api/import/csv-plan/{batch_id:path}")
async def update_csv_plan(batch_id: str, payload: CsvPlanPayload, request: Request) -> dict:
    validation = validate_rows(payload.rows, payload.units)
    if not validation["can_preview"]:
        raise HTTPException(422, {"message": "Fix invalid rows before updating the batch", **validation})
    definition = {"rows": validation["normalized_entities"], "units": "mm"}
    _check_preview(request, definition)
    _assembly_kind(batch_id, "csv_import")
    elements, warnings = rows_to_elements(definition["rows"], "csv_import", batch_id)
    db.append_elements(elements, "csv_import", batch_id, payload.file_name,
                       len(payload.rows), len(definition["rows"]), 0, len(warnings),
                       definition=definition, update=True)
    return {"batch_id": batch_id, "model": db.model_json()}


@app.post("/api/manual/wall-frame/commit")
async def commit_manual_wall(spec: ManualWallFrameInput, request: Request) -> dict:
    _check_preview(request, spec.model_dump())
    source_id = spec.input_id or projects.operation_id("manual-wall")
    elements, warnings = generate_wall(spec, "manual_wall", source_id)
    db.append_elements(
        elements, "manual_wall", source_id, spec.segment_label, 1, 1, 0,
        len(warnings), definition=spec.model_dump())
    return {"source_id": source_id, "model": db.model_json()}


@app.post("/api/manual/truss/preview")
async def preview_manual_truss(spec: ManualTrussInput) -> dict:
    source_id = spec.input_id or f"truss-preview-{uuid.uuid4().hex[:10]}"
    elements, warnings = generate_truss(spec, "csv_preview", source_id)
    return _preview_proof(_preview_response(elements, warnings), spec.model_dump())


@app.post("/api/manual/truss/commit")
async def commit_manual_truss(spec: ManualTrussInput, request: Request) -> dict:
    _check_preview(request, spec.model_dump())
    source_id = spec.input_id or projects.operation_id("manual-truss")
    elements, warnings = generate_truss(spec, "manual_truss", source_id)
    db.append_elements(
        elements, "manual_truss", source_id, spec.truss_label, 1, 1, 0,
        len(warnings), definition=_truss_definition(spec))
    return {"source_id": source_id, "model": db.model_json()}


@app.get("/api/import/batches")
async def get_import_batches() -> dict:
    return {"batches": db.import_batches()}


@app.delete("/api/import/batches/{batch_id:path}")
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
    db.require_model()
    with closing(db.connect()) as con:
        saved = db._meta_json(con, "home_definition", None)
        if projects.info(con)["geometry_mode"] == "custom" and not saved and not options.replace_geometry:
            raise HTTPException(409, "This home uses custom geometry. Edit its assemblies or explicitly reset to the sample.")
    db.rebuild(
        db.current_config(),
        preserve_manual=options.preserve_manual and not options.replace_geometry,
        preserve_imports=options.preserve_imports and not options.replace_geometry,
        definition=home_definition.HomeDefinition.model_validate(saved) if saved and saved.get("template") == "custom" and not options.replace_geometry else None,
    )
    return db.model_json()


class CreateProject(BaseModel):
    name: str = "New home"
    geometry_mode: Literal["sample", "custom"] = "custom"


@app.get("/api/projects")
async def list_projects() -> dict:
    return {"projects": db.project_list()}


@app.post("/api/projects")
async def create_project(payload: CreateProject) -> dict:
    if not payload.name.strip() or len(payload.name) > 160:
        raise HTTPException(422, "Project name must contain 1–160 characters")
    contract = dict(projects.write_contract.get() or {})
    key = contract.get("key")
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, projects.project_id.get() + ":home:" + key).hex if key else uuid.uuid4().hex
    creation = {"key": key, "digest": contract.get("digest")} if key else None
    contract["revision"] = 0  # The caller's revision belongs to its old home.
    token = projects.project_id.set(identifier)
    write_token = projects.write_contract.set(contract)
    try:
        return db.create_project(payload.name.strip(), payload.geometry_mode, creation)
    finally:
        projects.write_contract.reset(write_token)
        projects.project_id.reset(token)


@app.post("/api/project/initialize")
async def initialize_project() -> dict:
    # Explicit legacy migration/bootstrap, never performed by a read endpoint.
    if projects.project_id.get() != "default" and not projects.path(db.DB_PATH).exists():
        raise HTTPException(404, "Create a named project through /api/projects")
    db.ensure_model()
    return db.model_json()


@app.get("/api/project/revisions")
async def list_revisions() -> dict:
    db.require_model()
    with closing(db.connect()) as con:
        con.execute("BEGIN")
        state = projects.check_read(con)
        return {"project_revision": state["revision"], "revisions": [dict(r) for r in con.execute("SELECT revision,saved_at,action FROM project_revisions ORDER BY revision DESC")]}


@app.post("/api/project/revisions/{revision}/restore")
async def restore_revision(revision: int) -> dict:
    db.require_model()
    with closing(db.connect()) as con:
        projects.restore(con, revision)
    return db.model_json()


@app.get("/api/project/definitions")
async def definitions() -> dict:
    db.require_model()
    with closing(db.connect()) as con:
        con.execute("BEGIN")
        state = projects.check_read(con)
        return {"project_revision": state["revision"], "definitions": [{**dict(r), "payload": json.loads(r["payload"])} for r in con.execute("SELECT * FROM source_definitions")]}


@app.post("/api/project/home/preview")
async def preview_home(definition: home_definition.HomeDefinition) -> dict:
    db.require_model()
    with closing(db.connect()) as con:
        con.execute("BEGIN")
        revision = projects.check_read(con)["revision"]
        cfg = ModelConfig(**db._meta_json(con, "params", {}))
    result = home_definition.generate(definition, cfg)
    return _preview_proof(_preview_response(result.elements, result.warnings, revision,review_home=definition.model_dump()), definition.model_dump())


@app.put("/api/project/home/commit")
async def save_home(definition: home_definition.HomeDefinition, request: Request,
                    preserve_additions: bool = Query(True)) -> dict:
    _check_preview(request, definition.model_dump())
    db.require_model()
    # A supplied definition is explicit geometry, even when adapted from a sample.
    definition = definition.model_copy(update={"template": "custom"})
    db.rebuild(db.current_config(), preserve_manual=preserve_additions,
               preserve_imports=preserve_additions, definition=definition)
    return db.model_json()


@app.get("/api/project/home")
async def get_home_definition() -> dict:
    db.require_model()
    with closing(db.connect()) as con:
        con.execute("BEGIN")
        state = projects.check_read(con)
        return {"project_revision": state["revision"],
                "definition": db._meta_json(con, "home_definition", None)}


@app.get("/api/project/home/examples")
async def home_examples() -> dict:
    folder=Path(__file__).parent.parent/"examples"/"homes"
    return {"examples":[{"id":name,"definition":json.loads((folder/(name+".json")).read_text())}
                        for name in ("rectangle","l_shape","two_level")]}


@app.get("/api/project/archive")
async def export_archive() -> dict:
    return db.export_home_archive()


@app.post("/api/project/archive/preview")
async def preview_archive(archive: home_archive.HomeArchive) -> dict:
    db.require_model()
    with closing(db.connect()) as con:
        revision=projects.check_read(con)["revision"]
    result,_,_=home_archive.generate(archive)
    return _preview_proof(_preview_response(result.elements,result.warnings,revision,archive.pricing,
                                           archive.home.model_dump() if archive.home else None,archive.settings),archive.model_dump())


@app.post("/api/project/archive/commit")
async def commit_archive(archive: home_archive.HomeArchive,request:Request) -> dict:
    _check_preview(request,archive.model_dump())
    return db.import_home_archive(archive)


@app.put("/api/manual/wall-frame/{assembly_id:path}")
async def update_wall(assembly_id: str, spec: ManualWallFrameInput, request: Request) -> dict:
    _check_preview(request, spec.model_dump())
    _assembly_kind(assembly_id, "manual_wall")
    elements, warnings = generate_wall(spec, "manual_wall", assembly_id)
    db.append_elements(elements, "manual_wall", assembly_id, spec.segment_label, 1, 1, 0,
                       len(warnings), definition=spec.model_dump(), update=True)
    return {"source_id": assembly_id, "model": db.model_json()}


@app.put("/api/manual/truss/{assembly_id:path}")
async def update_truss(assembly_id: str, spec: ManualTrussInput, request: Request) -> dict:
    _check_preview(request, spec.model_dump())
    _assembly_kind(assembly_id, "manual_truss")
    elements, warnings = generate_truss(spec, "manual_truss", assembly_id)
    db.append_elements(elements, "manual_truss", assembly_id, spec.truss_label, 1, 1, 0,
                       len(warnings), definition=_truss_definition(spec), update=True)
    return {"source_id": assembly_id, "model": db.model_json()}


def _assembly_kind(identifier: str, kind: str) -> None:
    db.require_model()
    with closing(db.connect()) as con:
        row = con.execute("SELECT kind FROM source_definitions WHERE definition_id=?", (identifier,)).fetchone()
        if not row or row[0] != kind:
            raise HTTPException(404, "Assembly of this kind was not found")


def _truss_definition(spec):
    nodes, members = canonical_graph(spec, include_cuts=True)
    cuts = {}
    for a, b, role, size, material, cut_id, length in members:
        cuts.setdefault(cut_id, {"id": cut_id, "role": role, "size": size,
                                 "material": material, "length_mm": length, "segments": []})["segments"].append([a, b])
    return {**spec.model_dump(), "topology": {
        "schema_version": 2,
        "coordinate_system": "x along span, y above bearing plane, millimetres",
        "nodes": [{"id": identifier, "x": point[0], "y": point[1]} for identifier, point in nodes.items()],
        "members": [{"start_node": a, "end_node": b, "role": role, "size": size, "material": material, "cut_id": cut_id}
                    for a, b, role, size, material, cut_id, _length in members],
        "physical_cuts": list(cuts.values()),
        "engineering_status": "unchecked",
    }}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def unknown_api(path: str) -> None:
    raise HTTPException(404, "API endpoint not found")


DIST = Path(__file__).parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
