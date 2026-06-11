"""SQLite persistence: rebuild model DB, query elements + BOM CSV."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import framing
import materials
import nzs3604 as nz
from framing import ModelConfig

HERE = Path(__file__).parent
DB_PATH = HERE / "model.db"
SCHEMA = (HERE / "schema.sql").read_text()


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _price(e: dict) -> None:
    """Attach estimating price columns to one generated element (in place)."""
    key = materials.normalise_material_key(e["material"])
    if key is None:  # concrete slab etc. — not priced
        e.update(unit_price_usd_per_lm=None, price_confidence="",
                 price_source_name="", price_source_url="")
        return
    price, conf, src, url, _notes = materials.unit_price_usd_per_lm(
        key, e["size"])
    e.update(unit_price_usd_per_lm=price, price_confidence=conf,
             price_source_name=src, price_source_url=url)


def rebuild(cfg: ModelConfig) -> int:
    """Regenerate the framing model and persist it. Returns element count."""
    res = framing.generate(cfg)
    for e in res.elements:
        _price(e)
    con = connect()
    with con:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT INTO element_types(code, name, category, nzs_ref, color_hex) "
            "VALUES (?, ?, ?, ?, ?)",
            [(code, *vals) for code, vals in nz.ELEMENT_TYPES.items()])
        con.executemany(
            "INSERT INTO elements(type_code, storey, size, grade, treatment, "
            " length_mm, w_mm, h_mm, cx, cy, cz, yaw, pitch, note, material, "
            " plies, segment_id, segment_label, stud_spacing_mm, "
            " unit_price_usd_per_lm, price_confidence, price_source_name, "
            " price_source_url) "
            "VALUES (:type_code, :storey, :size, :grade, :treatment, "
            " :length_mm, :w_mm, :h_mm, :cx, :cy, :cz, :yaw, :pitch, :note, "
            " :material, :plies, :segment_id, :segment_label, "
            " :stud_spacing_mm, :unit_price_usd_per_lm, :price_confidence, "
            " :price_source_name, :price_source_url)",
            res.elements)
        con.executemany("INSERT INTO model_meta(key, value) VALUES (?, ?)",
                        [("params", json.dumps(asdict(cfg))),
                         ("segments", json.dumps(res.segments)),
                         ("gen_warnings", json.dumps(res.warnings)),
                         ("standard", "NZS 3604:2011"),
                         ("units", "mm")])
    con.close()
    return len(res.elements)


def current_params() -> dict | None:
    if not DB_PATH.exists():
        return None
    try:
        con = connect()
        row = con.execute(
            "SELECT value FROM model_meta WHERE key='params'").fetchone()
        con.close()
        return json.loads(row["value"]) if row else None
    except (sqlite3.Error, json.JSONDecodeError):
        return None


def _meta_json(con: sqlite3.Connection, key: str, default):
    row = con.execute("SELECT value FROM model_meta WHERE key=?",
                      (key,)).fetchone()
    try:
        return json.loads(row["value"]) if row else default
    except json.JSONDecodeError:
        return default


def model_json(cfg: ModelConfig) -> dict:
    # canonical JSON round-trip: dict[int, ...] keys become strings, so the
    # stored params compare stably against the requested config
    if current_params() != json.loads(json.dumps(asdict(cfg))):
        rebuild(cfg)
    con = connect()
    types = [dict(r) for r in con.execute("SELECT * FROM element_types")]
    elements = [dict(r) for r in con.execute("SELECT * FROM elements")]
    segments = _meta_json(con, "segments", [])
    warnings = _meta_json(con, "gen_warnings", [])
    costs = cost_summary(con)
    con.close()
    eff = cfg.normalised()
    return {
        "meta": {
            "storeys": eff.storeys,
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
            "warnings": warnings,
            "disclaimer": ("Indicative model for estimating/education. "
                           "Verify all members against NZS 3604:2011 or SED."),
        },
        "types": types,
        "elements": elements,
    }


COST_DISCLAIMER = ("Indicative supply-only material cost estimate from "
                   "public NZ retail prices converted to USD — not a quote. "
                   "See /api/materials for sources and assumptions.")

_COST = "SUM(length_mm * plies * unit_price_usd_per_lm) / 1000.0"
_PRICED = "unit_price_usd_per_lm IS NOT NULL"


def cost_summary(con: sqlite3.Connection | None = None) -> dict:
    """Estimated material cost totals (USD) for the current model."""
    own = con is None
    if own:
        if not DB_PATH.exists():
            rebuild(ModelConfig())
        con = connect()
    grand = con.execute(
        f"SELECT ROUND(COALESCE({_COST}, 0), 2) AS c "
        f"FROM elements WHERE {_PRICED}").fetchone()["c"]
    by_material = [dict(r) for r in con.execute(
        f"SELECT material, ROUND(SUM(length_mm) / 1000.0, 1) AS lineal_m, "
        f" ROUND(SUM(length_mm * plies) / 1000.0, 1) AS effective_lm, "
        f" ROUND({_COST}, 2) AS cost_usd "
        f"FROM elements WHERE {_PRICED} "
        "GROUP BY material ORDER BY cost_usd DESC")]
    by_storey = [dict(r) for r in con.execute(
        f"SELECT storey, ROUND({_COST}, 2) AS cost_usd "
        f"FROM elements WHERE {_PRICED} GROUP BY storey ORDER BY storey")]
    by_segment = [dict(r) for r in con.execute(
        f"SELECT segment_id, segment_label AS label, "
        f" ROUND({_COST}, 2) AS cost_usd "
        f"FROM elements WHERE {_PRICED} AND segment_id <> '' "
        "GROUP BY segment_id, segment_label ORDER BY segment_id")]
    by_element = [dict(r) for r in con.execute(
        "SELECT t.category, t.name AS element, "
        " ROUND(SUM(e.length_mm * e.plies * e.unit_price_usd_per_lm) "
        "       / 1000.0, 2) AS cost_usd "
        "FROM elements e JOIN element_types t ON t.code = e.type_code "
        f"WHERE e.{_PRICED} "
        "GROUP BY t.category, t.name ORDER BY cost_usd DESC")]
    if own:
        con.close()
    return {
        "currency": "USD",
        "grand_total_usd": grand,
        "by_material": by_material,
        "by_storey": by_storey,
        "by_segment": by_segment,
        "by_element": by_element,
        "disclaimer": COST_DISCLAIMER,
    }


def bom_csv() -> str:
    """Bill of materials (timber only) straight from the SQL view."""
    con = connect()
    rows = con.execute("SELECT * FROM bom").fetchall()
    con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    # column order must match the bom view's SELECT (rows written positionally)
    w.writerow(["category", "element", "size", "grade", "treatment",
                "material", "plies", "stock_length_m", "qty",
                "total_length_m", "total_effective_length_m",
                "unit_price_usd_per_lm", "total_cost_usd",
                "price_confidence", "price_source_name", "price_source_url",
                "nzs_3604_2011_ref", "notes", "pricing_notes"])
    for r in rows:
        key = materials.normalise_material_key(r["material"])
        notes = materials.MATERIALS[key].pricing_notes if key else ""
        w.writerow(list(r) + [notes])
    return buf.getvalue()


if __name__ == "__main__":
    print("elements inserted:", rebuild(ModelConfig()))
    print(bom_csv()[:600])
