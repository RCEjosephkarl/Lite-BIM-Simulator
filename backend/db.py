"""SQLite persistence for generated, imported, and manually entered BIM data."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import framing
import materials
import nzs3604 as nz
from framing import ModelConfig

HERE = Path(__file__).parent
DB_PATH = HERE / "model.db"
SCHEMA = (HERE / "schema.sql").read_text()

ELEMENT_COLUMNS = (
    "type_code", "storey", "size", "grade", "treatment", "length_mm",
    "w_mm", "h_mm", "cx", "cy", "cz", "yaw", "pitch", "note",
    "material", "plies", "segment_id", "segment_label", "stud_spacing_mm",
    "unit_price_nzd_per_lm", "price_confidence", "price_source_name",
    "price_source_url", "source", "source_id", "editable", "confidence",
    "warnings", "truss_id", "truss_label", "pitch_deg", "span_mm",
    "spacing_mm",
)


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None


def _price(e: dict) -> None:
    """Attach estimating price columns to one element in place."""
    key = materials.normalise_material_key(e.get("material"))
    if key is None:
        e.update(unit_price_nzd_per_lm=None, price_confidence="",
                 price_source_name="", price_source_url="")
        return
    price, conf, src, url, _notes = materials.unit_price_nzd_per_lm(
        key, e.get("size", "90x45"))
    e.update(unit_price_nzd_per_lm=price, price_confidence=conf,
             price_source_name=src, price_source_url=url)


def _prepare_element(e: dict, default_source: str = "generated") -> dict:
    out = dict(e)
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
) -> int:
    """Regenerate sample geometry while optionally preserving additions."""
    preserved: list[dict] = []
    batches: list[dict] = []
    if DB_PATH.exists():
        try:
            old = connect()
            if _table_exists(old, "elements"):
                columns = {
                    r["name"] for r in old.execute("PRAGMA table_info(elements)")
                }
                if "source" in columns:
                    clauses = []
                    if preserve_manual:
                        clauses.append("source IN ('manual_wall','manual_truss')")
                    if preserve_imports:
                        clauses.append(
                            "source IN ('csv_import','vision_import')")
                    if clauses:
                        preserved = [dict(r) for r in old.execute(
                            "SELECT * FROM elements WHERE " + " OR ".join(clauses))]
            if _table_exists(old, "import_batches"):
                for row in old.execute("SELECT * FROM import_batches"):
                    item = dict(row)
                    is_manual = item["source_type"] in {
                        "manual_wall", "manual_truss"}
                    if ((is_manual and preserve_manual)
                            or (not is_manual and preserve_imports)):
                        batches.append(item)
            old.close()
        except sqlite3.Error:
            preserved = []
            batches = []

    res = framing.generate(cfg)
    generated = []
    for element in res.elements:
        item = dict(element)
        item.update(
            source="generated",
            source_id=item.get("segment_id") or "sample-model",
            editable=False, confidence=None, warnings=[],
        )
        generated.append(item)

    con = connect()
    with con:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT INTO element_types(code, name, category, nzs_ref, color_hex) "
            "VALUES (?, ?, ?, ?, ?)",
            [(code, *vals) for code, vals in nz.ELEMENT_TYPES.items()])
        count = _insert_elements(con, generated)
        count += _insert_elements(con, preserved)
        if batches:
            con.executemany(
                "INSERT INTO import_batches("
                "batch_id,source_type,file_name,uploaded_at,row_count,"
                "accepted_count,rejected_count,warning_count"
                ") VALUES (:batch_id,:source_type,:file_name,:uploaded_at,"
                ":row_count,:accepted_count,:rejected_count,:warning_count)",
                batches)
        con.executemany("INSERT INTO model_meta(key, value) VALUES (?, ?)",
                        [("params", json.dumps(asdict(cfg))),
                         ("segments", json.dumps(res.segments)),
                         ("gen_warnings", json.dumps(res.warnings)),
                         ("standard", "NZS 3604:2011"),
                         ("units", "mm")])
    con.close()
    return count


def ensure_model() -> None:
    schema_ok = False
    if DB_PATH.exists():
        try:
            con = connect()
            columns = {
                row["name"] for row in con.execute("PRAGMA table_info(elements)")
            }
            schema_ok = {"source", "source_id", "warnings"} <= columns
            con.close()
        except sqlite3.Error:
            schema_ok = False
    if current_params() is None or not schema_ok:
        rebuild(ModelConfig())


def current_params() -> dict | None:
    if not DB_PATH.exists():
        return None
    try:
        con = connect()
        if not _table_exists(con, "model_meta"):
            con.close()
            return None
        row = con.execute(
            "SELECT value FROM model_meta WHERE key='params'").fetchone()
        con.close()
        return json.loads(row["value"]) if row else None
    except (sqlite3.Error, json.JSONDecodeError):
        return None


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
    try:
        out["warnings"] = json.loads(out.get("warnings") or "[]")
    except json.JSONDecodeError:
        out["warnings"] = [out.get("warnings")]
    return out


def model_json(cfg: ModelConfig | None = None) -> dict:
    cfg = (cfg or current_config()).normalised()
    ensure_model()
    canonical = json.loads(json.dumps(asdict(cfg)))
    if current_params() != canonical:
        rebuild(cfg)
    con = connect()
    types = [dict(r) for r in con.execute("SELECT * FROM element_types")]
    elements = [_decode_element(r) for r in con.execute(
        "SELECT * FROM elements ORDER BY id")]
    segments = _meta_json(con, "segments", [])
    warnings = _meta_json(con, "gen_warnings", [])
    additions = [
        warning for element in elements if element["source"] != "generated"
        for warning in element["warnings"]
    ]
    costs = cost_summary(con)
    actual_storeys = max(
        [eff_storey for eff_storey in (element["storey"] for element in elements)]
        or [cfg.storeys])
    con.close()
    eff = cfg.normalised()
    return {
        "meta": {
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


COST_DISCLAIMER = (
    "Estimating only - not supplier quote. Public NZ retail prices in NZD "
    "(GST-inclusive); excludes delivery, fixings, labour and waste."
)
_COST = "SUM(length_mm * plies * unit_price_nzd_per_lm) / 1000.0"
_PRICED = "unit_price_nzd_per_lm IS NOT NULL"


def cost_summary(con: sqlite3.Connection | None = None) -> dict:
    own = con is None
    if own:
        ensure_model()
        con = connect()
    assert con is not None
    grand = con.execute(
        f"SELECT ROUND(COALESCE({_COST}, 0), 2) AS c "
        f"FROM elements WHERE {_PRICED}").fetchone()["c"]
    by_material = [dict(r) for r in con.execute(
        f"SELECT material, ROUND(SUM(length_mm) / 1000.0, 1) AS lineal_m, "
        f"ROUND(SUM(length_mm * plies) / 1000.0, 1) AS effective_lm, "
        f"ROUND({_COST}, 2) AS cost_nzd FROM elements WHERE {_PRICED} "
        "GROUP BY material ORDER BY cost_nzd DESC")]
    by_storey = [dict(r) for r in con.execute(
        f"SELECT storey, ROUND({_COST}, 2) AS cost_nzd "
        f"FROM elements WHERE {_PRICED} GROUP BY storey ORDER BY storey")]
    by_segment = [dict(r) for r in con.execute(
        f"SELECT segment_id, segment_label AS label, ROUND({_COST}, 2) "
        f"AS cost_nzd FROM elements WHERE {_PRICED} AND segment_id <> '' "
        "GROUP BY segment_id, segment_label ORDER BY segment_id")]
    by_element = [dict(r) for r in con.execute(
        "SELECT t.category, t.name AS element, "
        "ROUND(SUM(e.length_mm * e.plies * e.unit_price_nzd_per_lm) "
        "/ 1000.0, 2) AS cost_nzd FROM elements e "
        "JOIN element_types t ON t.code=e.type_code "
        f"WHERE e.{_PRICED} GROUP BY t.category,t.name ORDER BY cost_nzd DESC")]
    if own:
        con.close()
    return {
        "currency": "NZD", "grand_total_nzd": grand,
        "by_material": by_material, "by_storey": by_storey,
        "by_segment": by_segment, "by_element": by_element,
        "disclaimer": COST_DISCLAIMER,
    }


def bom_rows() -> list[dict]:
    ensure_model()
    con = connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM bom")]
    con.close()
    return rows


def bom_json() -> dict:
    rows = bom_rows()
    for row in rows:
        row["effective_length_m"] = row["total_effective_length_m"]
        row["estimated_cost_nzd"] = row["total_cost_nzd"]
        key = materials.normalise_material_key(row["material"])
        row["pricing_notes"] = (
            materials.MATERIALS[key].pricing_notes if key else
            "No catalogue match - add a session override."
        )
    return {"rows": rows, "currency": "NZD", "disclaimer": COST_DISCLAIMER}


def bom_csv() -> str:
    rows = bom_rows()
    buf = io.StringIO()
    if not rows:
        return ""
    fieldnames = list(rows[0].keys()) + ["pricing_notes"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        key = materials.normalise_material_key(row["material"])
        writer.writerow({
            **row,
            "pricing_notes": (
                materials.MATERIALS[key].pricing_notes if key else ""),
        })
    return buf.getvalue()


def append_elements(
    elements: list[dict], source_type: str, batch_id: str,
    file_name: str = "", row_count: int = 0, accepted_count: int | None = None,
    rejected_count: int = 0, warning_count: int = 0,
) -> int:
    ensure_model()
    for element in elements:
        element["source"] = source_type
        element["source_id"] = batch_id
        element["editable"] = True
    con = connect()
    with con:
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
    con.close()
    return count


def replace_geometry(elements: list[dict], source_type: str, batch_id: str,
                     file_name: str, row_count: int, warning_count: int) -> int:
    ensure_model()
    con = connect()
    with con:
        con.execute("DELETE FROM elements")
        con.execute("DELETE FROM import_batches")
        count = _insert_elements(con, [
            {**e, "source": source_type, "source_id": batch_id, "editable": True}
            for e in elements
        ])
        con.execute(
            "INSERT OR REPLACE INTO import_batches VALUES (?,?,?,?,?,?,?,?)",
            (batch_id, source_type, file_name,
             datetime.now(timezone.utc).isoformat(), row_count,
             count, 0, warning_count))
    con.close()
    return count


def import_batches() -> list[dict]:
    ensure_model()
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM import_batches ORDER BY uploaded_at DESC")]
    con.close()
    return rows


def delete_batch(batch_id: str) -> int:
    ensure_model()
    con = connect()
    with con:
        count = con.execute(
            "DELETE FROM elements WHERE source_id=?", (batch_id,)).rowcount
        con.execute("DELETE FROM import_batches WHERE batch_id=?", (batch_id,))
    con.close()
    return count


def reset_project() -> dict:
    cfg = current_config()
    rebuild(cfg, preserve_manual=False, preserve_imports=False)
    return model_json(cfg)


def warnings_json() -> dict:
    model = model_json()
    warnings = [{"source": "model", "message": w}
                for w in model["meta"]["warnings"]]
    for element in model["elements"]:
        warnings.extend({
            "source": element["source"], "source_id": element["source_id"],
            "element_id": element["id"], "message": warning,
        } for warning in element["warnings"])
        if (element["unit_price_nzd_per_lm"] is None
                and element["material"].lower() != "concrete"):
            warnings.append({
                "source": element["source"], "source_id": element["source_id"],
                "element_id": element["id"],
                "message": f"missing price source for {element['material']}",
            })
    deduped = list({json.dumps(w, sort_keys=True): w for w in warnings}.values())
    return {"warnings": deduped, "count": len(deduped)}


def dashboard() -> dict:
    model = model_json()
    con = connect()
    lengths = {
        r["category"]: r["lineal_m"] for r in con.execute(
            "SELECT t.category, ROUND(SUM(e.length_mm*e.plies)/1000.0,2) "
            "AS lineal_m FROM elements e JOIN element_types t "
            "ON t.code=e.type_code GROUP BY t.category")
    }
    con.close()
    return {
        "storeys": model["meta"]["storeys"],
        "roof_type": model["meta"]["roof"],
        "wind_zone": model["meta"]["wind_zone"],
        "wind_speed": model["meta"]["wind_speed"],
        "snow_zone": model["meta"]["snow_zone"],
        "total_elements": len(model["elements"]),
        "wall_frame_lineal_m": lengths.get("wall", 0),
        "roof_truss_lineal_m": lengths.get("roof", 0),
        "estimated_material_cost_nzd":
            model["meta"]["cost_summary"]["grand_total_nzd"],
        "warning_count": len(warnings_json()["warnings"]),
    }


if __name__ == "__main__":
    print("elements inserted:", rebuild(ModelConfig()))
    print(bom_csv()[:600])
