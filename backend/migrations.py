"""Forward-only SQLite migrations, with a recoverable pre-upgrade snapshot."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import nzs3604 as nz
import bom_queries
import projects

SCHEMA_VERSION = 5
SCHEMA = (Path(__file__).parent / "schema.sql").read_text()

# Legacy v1.0 members already have all placement fields. Later releases added
# metadata; add those columns without recreating tables or renumbering members.
LEGACY_ADDITIONS = {
    "note": "TEXT NOT NULL DEFAULT ''",
    "material": "TEXT NOT NULL DEFAULT 'SG8'",
    "plies": "INTEGER NOT NULL DEFAULT 1",
    "segment_id": "TEXT DEFAULT ''",
    "segment_label": "TEXT DEFAULT ''",
    "stud_spacing_mm": "INTEGER",
    "unit_price_usd_per_lm": "REAL",
    "price_confidence": "TEXT DEFAULT ''",
    "price_source_name": "TEXT DEFAULT ''",
    "price_source_url": "TEXT DEFAULT ''",
    "source": "TEXT NOT NULL DEFAULT 'generated'",
    "source_id": "TEXT NOT NULL DEFAULT ''",
    "editable": "INTEGER NOT NULL DEFAULT 0",
    "confidence": "REAL",
    "warnings": "TEXT NOT NULL DEFAULT '[]'",
    "truss_id": "TEXT NOT NULL DEFAULT ''",
    "truss_label": "TEXT NOT NULL DEFAULT ''",
    "pitch_deg": "REAL",
    "span_mm": "REAL",
    "spacing_mm": "REAL",
    "layout_id": "TEXT NOT NULL DEFAULT ''",
    "instance_id": "TEXT NOT NULL DEFAULT ''",
    "truss_type": "TEXT NOT NULL DEFAULT ''",
    "member_role": "TEXT NOT NULL DEFAULT ''",
    "start_node": "TEXT NOT NULL DEFAULT ''",
    "end_node": "TEXT NOT NULL DEFAULT ''",
    "engineering_status": "TEXT NOT NULL DEFAULT 'unchecked'",
    "panel_id": "TEXT NOT NULL DEFAULT ''",
    "joint_id": "TEXT NOT NULL DEFAULT ''",
    "opening_id": "TEXT NOT NULL DEFAULT ''",
    "physical_member_id": "TEXT NOT NULL DEFAULT ''",
    "exterior": "INTEGER",
    "load_bearing": "INTEGER",
    "cut_length_mm": "REAL",
    "price_source_date": "TEXT NOT NULL DEFAULT ''",
    "price_currency": "TEXT NOT NULL DEFAULT 'USD'",
    "price_source_currency": "TEXT NOT NULL DEFAULT ''",
    "price_fx_rate": "REAL",
    "price_fx_date": "TEXT NOT NULL DEFAULT ''",
    "price_fx_source": "TEXT NOT NULL DEFAULT ''",
    "pricing_notes": "TEXT NOT NULL DEFAULT ''",
}
CORE_COLUMNS = {
    "id", "type_code", "storey", "size", "grade", "treatment", "length_mm",
    "w_mm", "h_mm", "cx", "cy", "cz", "yaw", "pitch",
}


def statements(script: str):
    """Execute individual statements inside our transaction, never executescript."""
    pending = ""
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise RuntimeError("Incomplete schema statement")


def backup_database(path: Path, destination: Path) -> Path:
    """Use SQLite's snapshot API so committed WAL data is included."""
    path, destination = path.resolve(), destination.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")
    if destination == path or destination.exists():
        raise ValueError("Backup destination must be a new file")
    # Reserve the destination without overwriting an existing snapshot.
    destination.touch(exist_ok=False)
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup failed SQLite integrity check")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def backup_name(path: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return path.with_name(f"{path.name}.backup-{label}-{stamp}-{uuid.uuid4().hex[:6]}")


def _apply_schema(con: sqlite3.Connection) -> None:
    existing = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "elements" in existing:
        columns = {r[1] for r in con.execute("PRAGMA table_info(elements)")}
        missing = CORE_COLUMNS - columns
        if missing:
            raise RuntimeError(f"Unsupported member schema; missing {sorted(missing)}")
        for name, definition in LEGACY_ADDITIONS.items():
            if name not in columns:
                con.execute(f"ALTER TABLE elements ADD COLUMN {name} {definition}")
        if "material" not in columns:
            con.execute("UPDATE elements SET material=grade")
    elif existing & {"model_meta", "element_types", "import_batches"}:
        raise RuntimeError("Incomplete database: elements table is missing")
    con.execute("DROP VIEW IF EXISTS bom")
    con.execute("DROP VIEW IF EXISTS cutting_pieces")
    for statement in statements(SCHEMA):
        con.execute(statement)
    con.execute("CREATE VIEW cutting_pieces AS " + bom_queries.cutting_select())
    con.execute("CREATE VIEW bom AS " + bom_queries.bom_select())
    con.executemany(
        "INSERT INTO element_types(code,name,category,nzs_ref,color_hex) VALUES (?,?,?,?,?) "
        "ON CONFLICT(code) DO UPDATE SET name=excluded.name, category=excluded.category, "
        "nzs_ref=excluded.nzs_ref, color_hex=excluded.color_hex",
        [(code, *values) for code, values in nz.ELEMENT_TYPES.items()])
    if not con.execute("SELECT 1 FROM model_meta WHERE key='project'").fetchone():
        generated = con.execute("SELECT COUNT(*) FROM elements WHERE source='generated'").fetchone()[0]
        additions = con.execute("SELECT COUNT(*) FROM elements WHERE source<>'generated'").fetchone()[0]
        mode = 'mixed' if generated and additions else 'custom' if additions else 'sample'
        projects.save_info(con, projects.initial_info(mode=mode))


def migrate(con: sqlite3.Connection, path: Path) -> None:
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"Database schema {version} is newer than supported {SCHEMA_VERSION}")
    if version == SCHEMA_VERSION:
        return
    has_data = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
    if has_data:
        backup_database(path, backup_name(path, f"v{version}"))
    con.execute("BEGIN IMMEDIATE")
    try:
        _apply_schema(con)
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        con.commit()
    except BaseException:
        con.rollback()
        raise
