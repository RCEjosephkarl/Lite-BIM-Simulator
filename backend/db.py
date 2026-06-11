"""SQLite persistence: rebuild model DB, query elements + BOM CSV."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import framing
import nzs3604 as nz
from framing import ModelConfig

HERE = Path(__file__).parent
DB_PATH = HERE / "model.db"
SCHEMA = (HERE / "schema.sql").read_text()


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def rebuild(cfg: ModelConfig) -> int:
    """Regenerate the framing model and persist it. Returns element count."""
    els = framing.generate(cfg)
    con = connect()
    with con:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT INTO element_types(code, name, category, nzs_ref, color_hex) "
            "VALUES (?, ?, ?, ?, ?)",
            [(code, *vals) for code, vals in nz.ELEMENT_TYPES.items()])
        con.executemany(
            "INSERT INTO elements(type_code, storey, size, grade, treatment, "
            " length_mm, w_mm, h_mm, cx, cy, cz, yaw, pitch, note) "
            "VALUES (:type_code, :storey, :size, :grade, :treatment, "
            " :length_mm, :w_mm, :h_mm, :cx, :cy, :cz, :yaw, :pitch, :note)",
            els)
        con.executemany("INSERT INTO model_meta(key, value) VALUES (?, ?)",
                        [("params", json.dumps(asdict(cfg))),
                         ("standard", "NZS 3604:2011"),
                         ("units", "mm")])
    con.close()
    return len(els)


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


def model_json(cfg: ModelConfig) -> dict:
    if current_params() != asdict(cfg):
        rebuild(cfg)
    con = connect()
    types = [dict(r) for r in con.execute("SELECT * FROM element_types")]
    elements = [dict(r) for r in con.execute("SELECT * FROM elements")]
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
            "units": "mm",
            "standard": "NZS 3604:2011",
            "warnings": eff.warnings(),
            "disclaimer": ("Indicative model for estimating/education. "
                           "Verify all members against NZS 3604:2011 or SED."),
        },
        "types": types,
        "elements": elements,
    }


def bom_csv() -> str:
    """Bill of materials (timber only) straight from the SQL view."""
    con = connect()
    rows = con.execute("SELECT * FROM bom").fetchall()
    con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["category", "element", "size", "grade", "treatment",
                "stock_length_m", "qty", "total_length_m",
                "nzs_3604_2011_ref", "notes"])
    for r in rows:
        w.writerow(list(r))
    return buf.getvalue()


if __name__ == "__main__":
    print("elements inserted:", rebuild(ModelConfig()))
    print(bom_csv()[:600])
