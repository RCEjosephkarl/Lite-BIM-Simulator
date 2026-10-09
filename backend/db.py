"""SQLite persistence for generated, imported, and manually entered BIM data."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import framing
import estimating
import bom_queries
import materials
import migrations
import nzs3604 as nz
import projects
import home_definition
import review
from framing import ModelConfig

HERE = Path(__file__).parent
DB_PATH = Path(os.environ.get("TIMBERBIM_DB_PATH", str(HERE / "model.db"))).expanduser().resolve()

ELEMENT_COLUMNS = (
    "type_code", "storey", "size", "grade", "treatment", "length_mm",
    "w_mm", "h_mm", "cx", "cy", "cz", "yaw", "pitch", "note",
    "material", "plies", "segment_id", "segment_label", "stud_spacing_mm",
    "unit_price_usd_per_lm", "price_confidence", "price_source_name",
    "price_source_url", "source", "source_id", "editable", "confidence",
    "warnings", "truss_id", "truss_label", "pitch_deg", "span_mm",
    "spacing_mm", "layout_id", "instance_id", "truss_type", "member_role",
    "start_node", "end_node", "engineering_status",
    "panel_id", "joint_id", "opening_id", "physical_member_id", "exterior", "load_bearing",
    "cut_length_mm", "price_source_date", "price_currency", "price_source_currency",
    "price_fx_rate", "price_fx_date", "price_fx_source", "pricing_notes",
)
PRICE_COLUMNS = ("unit_price_usd_per_lm", "price_confidence", "price_source_name",
                 "price_source_url", "price_source_date", "price_currency",
                 "price_source_currency", "price_fx_rate", "price_fx_date",
                 "price_fx_source", "pricing_notes")


def connect() -> sqlite3.Connection:
    location = projects.path(DB_PATH)
    location.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(location)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def ensure_schema() -> None:
    with closing(connect()) as con:
        migrations.migrate(con, projects.path(DB_PATH))


def database_health() -> dict:
    """Inspect readiness without creating, migrating, or regenerating a model."""
    location = projects.path(DB_PATH)
    if not location.exists():
        return {"status": "uninitialized", "ready": True,
                "schema_version": None, "supported_schema_version": migrations.SCHEMA_VERSION}
    try:
        with closing(sqlite3.connect(location.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            columns = {r[1] for r in con.execute("PRAGMA table_info(elements)")}
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            views = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='view'")}
            ready = (version == migrations.SCHEMA_VERSION
                     and set(ELEMENT_COLUMNS) <= columns
                     and {"model_meta", "element_types", "import_batches", "source_definitions", "project_revisions", "operations"} <= tables
                     and {"bom", "cutting_pieces"} <= views)
            return {"status": "ready" if ready else "migration_required" if version < migrations.SCHEMA_VERSION else "incompatible",
                    "ready": ready, "schema_version": version,
                    "supported_schema_version": migrations.SCHEMA_VERSION}
    except sqlite3.Error:
        return {"status": "unreadable", "ready": False,
                "schema_version": None, "supported_schema_version": migrations.SCHEMA_VERSION}


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None


def _price(e: dict, overrides: dict | None = None, saved_at: str = "") -> None:
    """Attach estimating price columns to one element in place."""
    key = materials.normalise_material_key(e.get("material"))
    if key is None:
        e.update(unit_price_usd_per_lm=None, price_confidence="",
                 price_source_name="", price_source_url="", price_source_date="",
                 price_currency="USD", price_source_currency="", price_fx_rate=None,
                 price_fx_date="", price_fx_source="", pricing_notes="No catalogue price; provide a supplier quote or project override.")
        return
    catalogue = materials.MATERIALS[key]
    price, conf, src, url, notes = materials.unit_price_usd_per_lm(
        key, e.get("size", "90x45"), e.get("treatment"))
    provenance = dict(price_source_date=catalogue.price_source_date,
                      price_currency="USD", price_source_currency=catalogue.source_currency,
                      price_fx_rate=catalogue.fx_rate_to_usd, price_fx_date=catalogue.fx_date,
                      price_fx_source=catalogue.fx_source)
    if key in (overrides or {}):
        multiplier = materials.section_plies(e.get("size", ""))
        price, conf, src, url = overrides[key] * multiplier, "user", "Project price override", ""
        notes = "User estimate in USD per physical board metre; applied to all sections/treatments of this material. Supplier scope is unverified."
        provenance.update(price_source_date=saved_at, price_source_currency="USD",
                          price_fx_rate=1.0, price_fx_date="", price_fx_source="No currency conversion")
    e.update(unit_price_usd_per_lm=price, price_confidence=conf,
             price_source_name=src, price_source_url=url, pricing_notes=notes, **provenance)


def _prepare_element(e: dict, default_source: str = "generated") -> dict:
    out = dict(e)
    for column in ("length_mm", "w_mm", "h_mm", "cx", "cy", "cz", "yaw", "pitch"):
        value = out.get(column)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Member {column} must be finite")
        if column in {"length_mm", "w_mm", "h_mm"} and value <= 0:
            raise ValueError(f"Member {column} must be positive")
    if out.get("type_code") not in nz.ELEMENT_TYPES:
        raise ValueError("Unknown member type")
    source = out.get("source") or default_source
    warnings = out.get("warnings", [])
    if isinstance(warnings, str):
        try:
            json.loads(warnings)
        except json.JSONDecodeError:
            warnings = [warnings]
    else:
        warnings = list(warnings or [])
    out.update({
        "source": source,
        "source_id": out.get("source_id")
        or out.get("segment_id") or "generated",
        "editable": int(bool(out.get("editable", source != "generated"))),
        "confidence": out.get("confidence"),
        "warnings": warnings if isinstance(warnings, str)
        else json.dumps(warnings),
        "truss_id": out.get("truss_id", ""),
        "truss_label": out.get("truss_label", ""),
        "pitch_deg": out.get("pitch_deg"),
        "span_mm": out.get("span_mm"),
        "spacing_mm": out.get("spacing_mm"),
        "layout_id": out.get("layout_id", ""),
        "instance_id": out.get("instance_id", ""),
        "truss_type": out.get("truss_type", ""),
        "member_role": out.get("member_role", out.get("type_code", "")),
        "start_node": out.get("start_node", ""),
        "end_node": out.get("end_node", ""),
        "engineering_status": out.get("engineering_status", "unchecked"),
        "panel_id": out.get("panel_id", ""),
        "joint_id": out.get("joint_id", ""),
        "opening_id": out.get("opening_id", ""),
        "physical_member_id": out.get("physical_member_id", ""),
        "exterior": out.get("exterior"),
        "load_bearing": out.get("load_bearing"),
        "note": out.get("note", ""),
        "material": out.get("material") or out.get("grade") or "SG8",
        "plies": int(out.get("plies", 1)),
        "segment_id": out.get("segment_id", ""),
        "segment_label": out.get("segment_label", ""),
        "stud_spacing_mm": out.get("stud_spacing_mm"),
    })
    _price(out)
    return {column: out.get(column) for column in ELEMENT_COLUMNS}


def _insert_elements(con: sqlite3.Connection, elements: Iterable[dict]) -> int:
    rows = [_prepare_element(e) for e in elements]
    estimating.cutting_pieces(rows)
    overrides = _meta_json(con, "price_overrides", {})
    saved_at = _meta_json(con, "price_overrides_saved_at", "")
    for row in rows:
        _price(row, overrides, saved_at)
    estimating.preview_summary(rows)
    if not rows:
        return 0
    names = ", ".join(ELEMENT_COLUMNS)
    values = ", ".join(f":{name}" for name in ELEMENT_COLUMNS)
    con.executemany(
        f"INSERT INTO elements({names}) VALUES ({values})", rows)
    return len(rows)


def rebuild(
    cfg: ModelConfig, preserve_manual: bool = True,
    preserve_imports: bool = True,
    definition: home_definition.HomeDefinition | None = None,
) -> int:
    """Regenerate a definition atomically while optionally preserving additions."""
    cfg = cfg.normalised()
    res = home_definition.generate(definition, cfg) if definition else framing.generate(cfg)
    definition = definition or home_definition.sample_definition(cfg)
    generated = []
    for element in res.elements:
        item = dict(element)
        item.update(
            source="generated",
            source_id=item.get("source_id") or item.get("segment_id") or "sample-model",
            editable=False, confidence=None,
        )
        generated.append(item)
    # Validate all generated members before opening a write transaction.
    for item in generated:
        _prepare_element(item)
    ensure_schema()
    with closing(connect()) as con, projects.mutation(con, "regenerate", asdict(cfg)) as apply:
        if not apply:
            return con.execute("SELECT COUNT(*) FROM elements").fetchone()[0]
        con.executemany(
            "INSERT INTO element_types(code, name, category, nzs_ref, color_hex) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET "
            "name=excluded.name, category=excluded.category, "
            "nzs_ref=excluded.nzs_ref, color_hex=excluded.color_hex",
            [(code, *vals) for code, vals in nz.ELEMENT_TYPES.items()])
        keep = []
        if preserve_manual:
            keep.extend(("manual_wall", "manual_truss"))
        if preserve_imports:
            keep.extend(("csv_import", "vision_import"))
        if keep:
            marks = ",".join("?" for _ in keep)
            con.execute(f"DELETE FROM elements WHERE source NOT IN ({marks})", keep)
            con.execute(f"DELETE FROM import_batches WHERE source_type NOT IN ({marks})", keep)
        else:
            con.execute("DELETE FROM elements")
            con.execute("DELETE FROM import_batches")
        con.execute("DELETE FROM source_definitions WHERE definition_id NOT IN (SELECT batch_id FROM import_batches)")
        _insert_elements(con, generated)
        con.executemany("INSERT INTO model_meta(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        [("params", json.dumps(asdict(cfg))),
                         ("segments", json.dumps(res.segments)),
                         ("gen_warnings", json.dumps(res.warnings)),
                         ("home_definition", definition.model_dump_json()),
                         ("generator_version", json.dumps((HERE.parent/"VERSION").read_text().strip())),
                         ("standard", "NZS 3604:2011"),
                         ("units", "mm")])
        state = projects.info(con)
        additions = con.execute("SELECT COUNT(*) FROM elements WHERE source<>'generated'").fetchone()[0]
        state["geometry_mode"] = ("custom" if definition.template == "custom"
                                  else "mixed" if additions else "sample")
        if definition.template == "custom":
            state["name"] = definition.name
        projects.save_info(con, state)
        count = con.execute("SELECT COUNT(*) FROM elements").fetchone()[0]
    return count


def ensure_model() -> None:
    ensure_schema()
    if current_params() is None:
        with closing(connect()) as con:
            if con.execute("SELECT COUNT(*) FROM elements").fetchone()[0]:
                raise RuntimeError("Project metadata is missing; restore a backup before regeneration")
        rebuild(ModelConfig())


def current_params() -> dict | None:
    if not projects.path(DB_PATH).exists():
        return None
    with closing(connect()) as con:
        if not _table_exists(con, "model_meta"):
            return None
        row = con.execute(
            "SELECT value FROM model_meta WHERE key='params'").fetchone()
        if not row:
            return None
        try:
            params = json.loads(row["value"])
        except json.JSONDecodeError as exc:
            raise RuntimeError("Project parameters are corrupt; restore a backup") from exc
        if not isinstance(params, dict):
            raise RuntimeError("Project parameters must be a JSON object")
        return params


def current_config() -> ModelConfig:
    params = current_params() or {}
    allowed = ModelConfig.__dataclass_fields__.keys()
    return ModelConfig(**{k: v for k, v in params.items() if k in allowed})


def _meta_json(con: sqlite3.Connection, key: str, default):
    row = con.execute("SELECT value FROM model_meta WHERE key=?", (key,)).fetchone()
    try:
        return json.loads(row["value"]) if row else default
    except json.JSONDecodeError:
        return default


def _decode_element(row: sqlite3.Row | dict) -> dict:
    out = dict(row)
    out["editable"] = bool(out.get("editable"))
    for key in ("exterior", "load_bearing"):
        if out.get(key) is not None:
            out[key] = bool(out[key])
    try:
        out["warnings"] = json.loads(out.get("warnings") or "[]")
    except json.JSONDecodeError:
        out["warnings"] = [out.get("warnings")]
    return out


def model_json(cfg: ModelConfig | None = None) -> dict:
    require_model()
    with closing(connect()) as con:
        con.execute("BEGIN")
        state = projects.check_read(con)
        params = json.loads(con.execute("SELECT value FROM model_meta WHERE key='params'").fetchone()[0])
        cfg = ModelConfig(**{k: v for k, v in params.items() if k in ModelConfig.__dataclass_fields__}).normalised()
        types = [dict(r) for r in con.execute("SELECT * FROM element_types")]
        elements = [_decode_element(r) for r in con.execute(
            "SELECT * FROM elements ORDER BY id")]
        segments = _frame_segments(elements, _meta_json(con, "segments", []))
        warnings = _meta_json(con, "gen_warnings", [])
        additions = [
            warning for element in elements if element["source"] != "generated"
            for warning in element["warnings"]
        ]
        costs = cost_summary(con)
        home = _meta_json(con, "home_definition", None)
        assessment=review.evaluate(elements,asdict(cfg),home)
        assessment["project_revision"]=state["revision"]
        actual_storeys = max(
            [eff_storey for eff_storey in (element["storey"] for element in elements)]
            or [cfg.storeys])
    eff = cfg.normalised()
    return {
        "meta": {
            "project": {**state, "schema_version": migrations.SCHEMA_VERSION},
            "params": asdict(cfg),
            "home_definition": home,
            "review": assessment,
            "storeys": max(eff.storeys, actual_storeys),
            "roof": eff.roof,
            "wind_zone": eff.wind_zone,
            "wind_speed": eff.wind_speed,
            "snow_zone": eff.snow_zone,
            "gable_spacing": eff.gable_spacing,
            "stud_spacing_mm": [
                nz.stud_spacing(s, eff.storeys, eff.wind_zone)
                for s in range(1, eff.storeys + 1)],
            "rafter_spacing_mm": nz.rafter_spacing(eff.snow_zone),
            "frame_segments": segments,
            "cost_summary": costs,
            "units": "mm",
            "standard": "NZS 3604:2011",
            "warnings": list(dict.fromkeys(warnings + additions)),
            "disclaimer": (
                "Education, early design and estimating only. Imported/manual "
                "geometry requires qualified review; NZS 3604 or SED governs."
            ),
        },
        "types": types,
        "elements": elements,
    }


def _frame_segments(elements: list[dict], saved: list[dict]) -> list[dict]:
    """Derive active wall metadata inside the same read snapshot, never persist on GET."""
    groups = {}
    for element in elements:
        if element["segment_id"]:
            groups.setdefault((element["source"],element["source_id"], element["storey"], element["segment_id"]), []).append(element)
    baseline = {(item["storey"], item["segment_id"]): item for item in saved}
    result = []
    for (_source, _source_id, storey, segment_id), members in groups.items():
        first = members[0]
        axis = (math.cos(first["yaw"]), math.sin(first["yaw"]))
        bounds = []
        for item in members:
            station = item["cx"]*axis[0] + item["cy"]*axis[1]
            half = item["h_mm"]/2 if abs(item["pitch"]) > math.pi/4 else item["length_mm"]/2
            bounds.extend((station-half, station+half))
        stud = next((item for item in members if item["type_code"] in {"stud", "trimmer_stud", "jack_stud"}), first)
        retained = baseline.get((storey, segment_id), {}) if first["source"] == "generated" else {}
        result.append({**retained, "segment_id": segment_id, "storey": storey,
                       "label": first["segment_label"], "length_mm": max(bounds)-min(bounds),
                       "exterior": first["exterior"], "load_bearing": first["load_bearing"],
                       "openings": len({item["opening_id"] for item in members if item["opening_id"]}),
                       "material": stud["material"], "spacing_mm": stud["stud_spacing_mm"],
                       "plies": stud["plies"], "treatment": stud["treatment"],
                       "panel_count": len({item["panel_id"] for item in members if item["panel_id"]}),
                       "source": first["source"], "source_id": first["source_id"],
                       "engineering_status": "unchecked"})
    return result


COST_DISCLAIMER = (
    "Estimating only - not supplier quote. Public retail prices converted "
    "to USD; excludes delivery, fixings, labour and waste."
)
_COST = "SUM(length_mm * plies * unit_price_usd_per_lm) / 1000.0"
_PRICED = "unit_price_usd_per_lm IS NOT NULL"


def cost_summary(con: sqlite3.Connection | None = None) -> dict:
    if con is None:
        require_model()
        with closing(connect()) as connection:
            connection.execute("BEGIN")
            return cost_summary(connection)
    state = projects.check_read(con)
    coverage = dict(con.execute(
        "SELECT COUNT(*) AS timber_members, "
        "COALESCE(SUM(CASE WHEN e.unit_price_usd_per_lm IS NULL THEN 1 ELSE 0 END),0) AS unpriced_members "
        "FROM elements e JOIN element_types t ON t.code=e.type_code WHERE t.category<>'concrete'").fetchone())
    physical = dict(con.execute(
        "SELECT COUNT(*) AS cut_quantity, COALESCE(SUM(plies*section_plies),0) AS physical_board_quantity, "
        "COALESCE(SUM(CASE WHEN unit_price_usd_per_lm IS NULL THEN 1 ELSE 0 END),0) AS unpriced_cut_quantity, "
        "COALESCE(SUM(CASE WHEN unit_price_usd_per_lm IS NULL THEN plies*section_plies ELSE 0 END),0) AS unpriced_board_quantity, "
        "COALESCE(SUM(CASE WHEN cut_identity_status='legacy_unknown' THEN 1 ELSE 0 END),0) AS unknown_cut_identity_quantity "
        "FROM cutting_pieces").fetchone())
    coverage.update(physical)
    totals = dict(con.execute(
        "SELECT ROUND(COALESCE(SUM(total_cost_usd),0),2) AS cut_cost, "
        "ROUND(COALESCE(SUM(stock_cost_usd),0),2) AS stock_cost, "
        "ROUND(COALESCE(SUM(cut_board_m),0),3) AS cut_board_m, "
        "ROUND(COALESCE(SUM(stock_board_m),0),3) AS stock_board_m, "
        "COALESCE(SUM(CASE WHEN stock_length_m>6 THEN physical_qty ELSE 0 END),0) AS special_order_board_quantity "
        "FROM bom").fetchone())
    by_material = [dict(r) for r in con.execute(
        f"SELECT material, ROUND(SUM(length_mm) / 1000.0, 1) AS lineal_m, "
        f"ROUND(SUM(length_mm * plies) / 1000.0, 1) AS effective_lm, "
        f"ROUND({_COST}, 2) AS cost_usd FROM cutting_pieces WHERE {_PRICED} "
        "GROUP BY material ORDER BY cost_usd DESC")]
    by_storey = [dict(r) for r in con.execute(
        f"SELECT storey, ROUND({_COST}, 2) AS cost_usd "
        f"FROM cutting_pieces WHERE {_PRICED} GROUP BY storey ORDER BY storey")]
    by_segment = [dict(r) for r in con.execute(
        f"SELECT segment AS segment_id, segment_label AS label, ROUND({_COST}, 2) "
        f"AS cost_usd FROM cutting_pieces WHERE {_PRICED} AND segment <> '' "
        "GROUP BY segment, segment_label ORDER BY segment")]
    by_element = [dict(r) for r in con.execute(
        f"SELECT category, element, ROUND({_COST}, 2) AS cost_usd "
        f"FROM cutting_pieces WHERE {_PRICED} GROUP BY category, element ORDER BY cost_usd DESC")]
    return {
        "currency": "USD", "grand_total_usd": totals["cut_cost"],
        "stock_total_usd": totals["stock_cost"],
        "cut_board_m": totals["cut_board_m"], "stock_board_m": totals["stock_board_m"],
        "special_order_board_quantity": totals["special_order_board_quantity"],
        "project": state,
        "estimate_complete": coverage["unpriced_cut_quantity"] == 0,
        "stock_identity_complete": coverage["unknown_cut_identity_quantity"] == 0,
        "coverage": coverage,
        "basis": "priced cut-length subtotal; stock is one rounded blank per physical board, without nesting/offcut reuse",
        "by_material": by_material, "by_storey": by_storey,
        "by_segment": by_segment, "by_element": by_element,
        "disclaimer": COST_DISCLAIMER,
    }


def _bom_rows(member_id: int | None = None, navigation: bool = False) -> tuple[list[dict], dict | None, int]:
    require_model()
    with closing(connect()) as con:
        con.execute("BEGIN")
        projects.check_read(con)
        revision = projects.info(con)["revision"]
        selection = None
        where, args = "1", []
        if member_id is not None:
            anchor = con.execute("SELECT e.*, t.category FROM elements e JOIN element_types t "
                                 "ON e.type_code=t.code WHERE e.id=?", (member_id,)).fetchone()
            if anchor is None:
                raise KeyError("Selected member no longer exists in this home revision")
            if anchor["category"] == "concrete":
                raise ValueError("Concrete is excluded from the timber BOM")
            where = "source=? AND source_id=? AND storey=?"
            args = [anchor["source"], anchor["source_id"], anchor["storey"]]
            if anchor["segment_id"]:
                field, kind = "segment_id", "wall"
            elif anchor["truss_id"]:
                field, kind = "truss_id", "truss"
            elif anchor["physical_member_id"]:
                field, kind = "physical_member_id", "cut"
            else:
                field, kind = "id", "member"
            where += f" AND {field}=?"
            args.append(anchor[field])
            selection = {"member_id": member_id, "source": anchor["source"],
                         "source_id": anchor["source_id"], "storey": anchor["storey"],
                         "kind": kind, "assembly_id": anchor[field],
                         "label": anchor["segment_label"] or anchor["truss_label"] or anchor["type_code"]}
        query = bom_queries.navigation_query(where) if navigation or selection else "SELECT * FROM bom"
        rows = [dict(r) for r in con.execute(query, args)]
        for row in rows:
            if "member_ids_csv" in row:
                row["member_ids"] = sorted(int(value) for value in row.pop("member_ids_csv").split(","))
    return rows, selection, revision


def bom_rows() -> list[dict]:
    return _bom_rows()[0]


def bom_json(member_id: int | None = None) -> dict:
    rows, selection, revision = _bom_rows(member_id, navigation=True)
    for row in rows:
        row["effective_length_m"] = row["total_effective_length_m"]
        row["estimated_cost_usd"] = row["total_cost_usd"]
        row["estimate_complete"] = bool(row["estimate_complete"])
    return {"rows": rows, "scope": selection, "project_revision": revision,
            "currency": "USD", "disclaimer": COST_DISCLAIMER}


def bom_csv() -> str:
    rows = bom_rows()
    buf = io.StringIO()
    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def append_elements(
    elements: list[dict], source_type: str, batch_id: str,
    file_name: str = "", row_count: int = 0, accepted_count: int | None = None,
    rejected_count: int = 0, warning_count: int = 0,
    definition: dict | None = None, update: bool = False,
) -> int:
    ensure_model()
    for element in elements:
        element["source"] = source_type
        element["source_id"] = batch_id
        element["editable"] = True
    con = connect()
    with closing(con), projects.mutation(con, "update assembly" if update else "append", definition or elements) as apply:
        if not apply:
            return 0
        existing = con.execute("SELECT 1 FROM import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        if existing and not update:
            raise projects.ProjectConflict("Assembly ID already exists; use its update endpoint")
        if update:
            if not existing:
                raise KeyError("Assembly does not exist")
            con.execute("DELETE FROM elements WHERE source_id=? AND source=?", (batch_id,source_type))
        count = _insert_elements(con, elements)
        con.execute(
            "INSERT OR REPLACE INTO import_batches("
            "batch_id,source_type,file_name,uploaded_at,row_count,"
            "accepted_count,rejected_count,warning_count"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (batch_id, source_type, file_name,
             datetime.now(timezone.utc).isoformat(), row_count,
             accepted_count if accepted_count is not None else count,
             rejected_count, warning_count))
        if definition is not None:
            con.execute("INSERT OR REPLACE INTO source_definitions VALUES (?,?,?)",
                        (batch_id, source_type, json.dumps(definition)))
        state = projects.info(con)
        if state["geometry_mode"] == "sample":
            state["geometry_mode"] = "mixed"
        projects.save_info(con, state)
    con.close()
    return count


def replace_geometry(elements: list[dict], source_type: str, batch_id: str,
                     file_name: str, row_count: int, warning_count: int,
                     definition: dict | None = None) -> int:
    ensure_model()
    con = connect()
    with closing(con), projects.mutation(con, "replace geometry", definition or elements) as apply:
        if not apply:
            return 0
        con.execute("DELETE FROM elements")
        con.execute("DELETE FROM import_batches")
        con.execute("DELETE FROM source_definitions")
        con.execute("DELETE FROM model_meta WHERE key='home_definition'")
        count = _insert_elements(con, [
            {**e, "source": source_type, "source_id": batch_id, "editable": True}
            for e in elements
        ])
        con.execute(
            "INSERT OR REPLACE INTO import_batches VALUES (?,?,?,?,?,?,?,?)",
            (batch_id, source_type, file_name,
             datetime.now(timezone.utc).isoformat(), row_count,
             count, 0, warning_count))
        con.execute("UPDATE model_meta SET value='[]' WHERE key IN ('segments','gen_warnings')")
        state = projects.info(con)
        state["geometry_mode"] = "custom"
        projects.save_info(con, state)
        if definition is not None:
            con.execute("INSERT INTO source_definitions VALUES (?,?,?)",
                        (batch_id, source_type, json.dumps(definition)))
    con.close()
    return count


def import_batches() -> list[dict]:
    require_model()
    with closing(connect()) as con:
        con.execute("BEGIN")
        projects.check_read(con)
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM import_batches ORDER BY uploaded_at DESC")]
    return rows


def delete_batch(batch_id: str) -> int:
    ensure_model()
    con = connect()
    with closing(con), projects.mutation(con, "delete assembly", batch_id) as apply:
        if not apply:
            return 0
        count = con.execute(
            "DELETE FROM elements WHERE source_id=? AND source<>'generated'", (batch_id,)).rowcount
        con.execute("DELETE FROM import_batches WHERE batch_id=?", (batch_id,))
        con.execute("DELETE FROM source_definitions WHERE definition_id=?", (batch_id,))
    con.close()
    return count


def reset_project() -> dict:
    cfg = current_config()
    rebuild(cfg, preserve_manual=False, preserve_imports=False)
    return model_json(cfg)


def export_home_archive() -> dict:
    """One consistent read of portable inputs; never substitute a sample for custom work."""
    require_model()
    with closing(connect()) as con:
        con.execute("BEGIN")
        state=projects.check_read(con)
        saved=_meta_json(con,"home_definition",None)
        # Older sample databases can be exported through the sample adapter.
        if saved is None and state["geometry_mode"] in {"sample","mixed"}:
            saved=home_definition.sample_definition(ModelConfig(**_meta_json(con,"params",{}))).model_dump()
        definitions={r["definition_id"]:json.loads(r["payload"]) for r in con.execute("SELECT * FROM source_definitions")}
        batches={r["batch_id"]:dict(r) for r in con.execute("SELECT * FROM import_batches")}
        groups={}
        for row in con.execute("SELECT * FROM elements WHERE source<>'generated' ORDER BY id"):
            member=_decode_element(row)
            groups.setdefault(member["source_id"],[]).append(member)
        assemblies=[]
        for ident,members in groups.items():
            batch=batches.get(ident,{})
            assemblies.append(dict(id=ident,kind=members[0]["source"],file_name=batch.get("file_name",""),
                uploaded_at=batch.get("uploaded_at",""),definition=definitions.get(ident),
                legacy_members=members if ident not in definitions else []))
        if saved is None and con.execute("SELECT 1 FROM elements WHERE source='generated'").fetchone():
            raise RuntimeError("Generated geometry has no saved home definition; review and migrate before portable export")
        return dict(archive_schema_version=1,project_revision=state["revision"],name=state["name"],home=saved,
                    settings=_meta_json(con,"params",{}),assemblies=assemblies,
                    pricing=dict(currency="USD",overrides=_meta_json(con,"price_overrides",{}),
                                 saved_at=_meta_json(con,"price_overrides_saved_at","")),
                    source_project=state,generator_version=_meta_json(con,"generator_version","legacy/unknown"),
                    catalogue_snapshot=materials.catalogue_json())


def import_home_archive(archive) -> dict:
    """Full replacement, including quotes and definitions, in one undoable write."""
    import home_archive
    require_model()
    result,batches,home_warnings=home_archive.generate(archive)
    for member in result.elements:_prepare_element(member)
    with closing(connect()) as con,projects.mutation(con,"import home archive",archive.model_dump()) as apply:
        if apply:
            con.execute("DELETE FROM elements")
            con.execute("DELETE FROM import_batches")
            con.execute("DELETE FROM source_definitions")
            meta={"params":archive.settings,"segments":result.segments,"gen_warnings":home_warnings,
                  "generator_version":(HERE.parent/"VERSION").read_text().strip(),
                  "price_overrides":archive.pricing.overrides,"price_overrides_saved_at":archive.pricing.saved_at,
                  "import_provenance":{"source_project":archive.source_project,"generator_version":archive.generator_version,
                                       "catalogue_snapshot":archive.catalogue_snapshot}}
            for key,value in meta.items():
                con.execute("INSERT INTO model_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,json.dumps(value)))
            if archive.home:
                home=archive.home.model_copy(update={"template":"custom"})
                con.execute("INSERT INTO model_meta VALUES ('home_definition',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(home.model_dump_json(),))
            else:con.execute("DELETE FROM model_meta WHERE key='home_definition'")
            _insert_elements(con,result.elements)
            for assembly in archive.assemblies:
                count=len(batches[assembly.id])
                con.execute("INSERT INTO import_batches VALUES (?,?,?,?,?,?,?,?)",
                            (assembly.id,assembly.kind,assembly.file_name,assembly.uploaded_at or datetime.now(timezone.utc).isoformat(),count,count,0,
                             sum(len(e.get("warnings",[])) for e in batches[assembly.id])))
                if assembly.definition is not None:
                    con.execute("INSERT INTO source_definitions VALUES (?,?,?)",(assembly.id,assembly.kind,json.dumps(assembly.definition)))
            state=projects.info(con);state.update(name=archive.name,geometry_mode="custom")
            projects.save_info(con,state)
    return model_json()


def require_model() -> None:
    health = database_health()
    if health["status"] == "uninitialized":
        raise FileNotFoundError("Project is not initialized; create or initialize a project first")
    if not health["ready"]:
        raise RuntimeError("Project needs migration or recovery; use the explicit initialize command")
    if current_params() is None:
        raise RuntimeError("Project metadata is missing; restore a backup")


def update_config(cfg: ModelConfig) -> dict:
    require_model()
    with closing(connect()) as con:
        custom = projects.info(con)["geometry_mode"] == "custom"
        saved = _meta_json(con, "home_definition", None)
    if custom and saved:
        rebuild(cfg, definition=home_definition.HomeDefinition.model_validate(saved))
    elif custom:
        with closing(connect()) as con, projects.mutation(con, "update custom settings", asdict(cfg)) as apply:
            if apply:
                con.execute("UPDATE model_meta SET value=? WHERE key='params'", (json.dumps(asdict(cfg.normalised())),))
    else:
        rebuild(cfg)
    return model_json()


def price_overrides() -> dict:
    if not projects.path(DB_PATH).exists():
        return {}
    with closing(connect()) as con:
        return _meta_json(con, "price_overrides", {})


def update_prices(overrides: dict) -> dict:
    require_model()
    with closing(connect()) as con, projects.mutation(con, "update prices", overrides) as apply:
        if apply:
            con.execute("INSERT INTO model_meta VALUES ('price_overrides',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(overrides),))
            saved_at = datetime.now(timezone.utc).isoformat()
            con.execute("INSERT INTO model_meta VALUES ('price_overrides_saved_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(saved_at),))
            for row in con.execute("SELECT * FROM elements").fetchall():
                item = dict(row)
                _price(item, overrides, saved_at)
                con.execute("UPDATE elements SET " + ",".join(f"{column}=?" for column in PRICE_COLUMNS) + " WHERE id=?",
                            [item[column] for column in PRICE_COLUMNS] + [item["id"]])
            # Keep derived overflow failures inside the transaction, including
            # stock rounding and aggregate amounts, so no broken prices save.
            estimating.preview_summary([dict(row) for row in con.execute("SELECT * FROM elements")])
    return model_json()


def create_project(name: str, mode: str = "sample", creation: dict | None = None) -> dict:
    ensure_schema()
    with closing(connect()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            marker = _meta_json(con, "project_creation", None)
            if marker is not None and marker != creation:
                raise projects.ProjectConflict("Creation key was already used for different home input")
            initialized = con.execute("SELECT 1 FROM model_meta WHERE key='params'").fetchone()
            if initialized:
                if creation is None or marker != creation:
                    raise projects.ProjectConflict("Project already exists")
                con.rollback()
                return model_json()
            if con.execute("SELECT COUNT(*) FROM elements").fetchone()[0]:
                raise RuntimeError("Project metadata is missing; restore a backup before initializing this home")
            if creation is not None:
                con.execute("INSERT INTO model_meta VALUES ('project_creation',?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(creation),))
            state = projects.info(con)
            state.update(name=name, geometry_mode=mode)
            projects.save_info(con, state)
            if mode == "custom":
                con.execute("INSERT INTO model_meta VALUES ('params',?)", (json.dumps(asdict(ModelConfig().normalised())),))
                con.executemany("INSERT INTO model_meta VALUES (?,?)", [("segments", "[]"), ("gen_warnings", "[]")])
            con.commit()
        except BaseException:
            con.rollback()
            raise
    if mode == "sample":
        rebuild(ModelConfig())
    return model_json()


def project_list() -> list[dict]:
    identifiers = ["default"]
    folder = DB_PATH.parent / (DB_PATH.name + ".projects")
    if folder.exists():
        identifiers += [p.stem for p in sorted(folder.glob("*.db")) if len(p.stem) == 32]
    result = []
    for identifier in identifiers:
        token = projects.project_id.set(identifier)
        try:
            location = projects.path(DB_PATH)
            if not location.exists():
                continue
            with closing(sqlite3.connect(location.as_uri() + "?mode=ro", uri=True)) as con:
                result.append(projects.info(con))
        except (sqlite3.Error, RuntimeError, ValueError):
            result.append({"project_id": identifier, "name": "Recovery required", "unavailable": True})
        finally:
            projects.project_id.reset(token)
    return result


def warnings_json() -> dict:
    model = model_json()
    warnings = [{"source": "model", "message": w}
                for w in model["meta"]["warnings"]]
    for element in model["elements"]:
        warnings.extend({
            "source": element["source"], "source_id": element["source_id"],
            "element_id": element["id"], "message": warning,
        } for warning in element["warnings"])
        if (element["unit_price_usd_per_lm"] is None
                and element["material"].lower() != "concrete"):
            warnings.append({
                "source": element["source"], "source_id": element["source_id"],
                "element_id": element["id"],
                "message": f"missing price source for {element['material']}",
            })
    grouped={}
    for warning in warnings:
        key=(warning.get("source"),warning.get("source_id"),warning["message"])
        if key not in grouped:
            grouped[key]={**warning,"occurrences":1,"severity":"warning","code":"model.note",
                          "status":"not_evaluated","next_action":"Review the source assembly and its assumptions",
                          "cause":warning["message"],"entity_id":warning.get("source_id",""),
                          "rule_version":review.PROFILE_VERSION,"rule_reference":"Generation / source note",
                          "basis_review_status":"not_independently_verified"}
        else:grouped[key]["occurrences"]+=1
    assessment=model["meta"]["review"]
    structured=[c for c in assessment["checks"] if c["status"] in {"requires_specific_design","not_evaluated"}]
    deduped=list(grouped.values())+structured
    return {"project_revision":model["meta"]["project"]["revision"],"review":assessment,
            "warnings":deduped,"count":len(deduped)}


if __name__ == "__main__":
    print("elements inserted:", rebuild(ModelConfig()))
    print(bom_csv()[:600])
