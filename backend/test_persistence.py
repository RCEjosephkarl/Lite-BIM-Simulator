"""Regression tests for migration, rollback, recovery, and non-mutating health."""

import json
import sqlite3
from contextlib import closing

import pytest

import db
import framing
import migrations
from framing import ModelConfig
from manual_inputs import ManualWallFrameInput, generate_wall
from manage_db import restore_database
from test_smoke import client


def seed():
    db.rebuild(ModelConfig())
    members, _ = generate_wall(ManualWallFrameInput(end_x_mm=3600))
    db.append_elements(members, "manual_wall", "preserved-wall")
    return db.model_json(), db.import_batches()


def raw_state():
    with closing(db.connect()) as con:
        return {table: [tuple(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in ("elements", "element_types", "model_meta", "import_batches", "source_definitions", "project_revisions", "operations")}


def test_generation_failure_leaves_project_unchanged(monkeypatch):
    seed()
    before = raw_state()
    original = framing.generate

    def invalid(config):
        generated = original(config)
        generated.elements[0]["length_mm"] = 0
        return generated

    monkeypatch.setattr(framing, "generate", invalid)
    with pytest.raises(ValueError, match="positive"):
        db.rebuild(ModelConfig(roof="hip"))
    assert raw_state() == before


def test_insert_failure_rolls_back_all_tables(monkeypatch):
    seed()
    before = raw_state()
    insert = db._insert_elements

    def fail_after_insert(con, members):
        insert(con, members)
        raise sqlite3.IntegrityError("injected late insert failure")

    monkeypatch.setattr(db, "_insert_elements", fail_after_insert)
    with pytest.raises(sqlite3.IntegrityError):
        db.rebuild(ModelConfig(roof="hip"), preserve_manual=False)
    assert raw_state() == before


def test_successful_regeneration_preserves_manual_ids_and_batches():
    before, batches = seed()
    manual = [e for e in before["elements"] if e["source"] == "manual_wall"]
    db.rebuild(ModelConfig(roof="hip"))
    after = db.model_json()
    assert after["meta"]["roof"] == "hip"
    assert [e for e in after["elements"] if e["source"] == "manual_wall"] == manual
    assert db.import_batches() == batches


def test_migration_failure_rolls_back_and_backup_is_restorable(monkeypatch):
    seed()
    with closing(db.connect()) as con, con:
        con.execute("PRAGMA user_version=0")
    before = raw_state()
    apply = migrations._apply_schema

    def fail_after_ddl(con):
        apply(con)
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(migrations, "_apply_schema", fail_after_ddl)
    with pytest.raises(RuntimeError, match="injected"):
        db.ensure_schema()
    assert raw_state() == before
    backups = list(db.DB_PATH.parent.glob("test.db.backup-v0-*"))
    assert len(backups) == 1
    with closing(db.connect()) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0
    restore_database(backups[0], db.DB_PATH)
    assert raw_state() == before
    monkeypatch.setattr(migrations, "_apply_schema", apply)
    db.ensure_schema()
    assert raw_state() == before
    assert db.database_health()["schema_version"] == migrations.SCHEMA_VERSION


def test_legacy_placement_columns_migrate_without_replacing_members():
    with closing(db.connect()) as con, con:
        con.execute("CREATE TABLE elements (id INTEGER PRIMARY KEY, type_code TEXT, storey INTEGER, size TEXT, grade TEXT, treatment TEXT, length_mm REAL, w_mm REAL, h_mm REAL, cx REAL, cy REAL, cz REAL, yaw REAL, pitch REAL)")
        con.execute("INSERT INTO elements VALUES (42,'stud',1,'90x45','SG10','H1.2',2400,90,45,100,200,1200,0,1.570796)")
    db.ensure_schema()
    with closing(db.connect()) as con:
        row = dict(con.execute("SELECT * FROM elements WHERE id=42").fetchone())
        assert row["length_mm"] == 2400
        assert row["material"] == "SG10"
        assert row["source"] == "generated"
        assert row["warnings"] == "[]"
    assert len(list(db.DB_PATH.parent.glob("test.db.backup-v0-*"))) == 1


def test_unreadable_or_corrupt_metadata_never_triggers_rebuild():
    seed()
    with closing(db.connect()) as con, con:
        con.execute("UPDATE model_meta SET value='invalid json' WHERE key='params'")
    before = raw_state()
    with pytest.raises(RuntimeError, match="corrupt"):
        db.ensure_model()
    assert raw_state() == before


def test_missing_metadata_with_members_is_reported_not_overwritten():
    seed()
    with closing(db.connect()) as con, con:
        con.execute("DELETE FROM model_meta WHERE key='params'")
    before = raw_state()
    with pytest.raises(RuntimeError, match="metadata is missing"):
        db.ensure_model()
    assert raw_state() == before


def test_future_schema_is_rejected_without_writes():
    seed()
    with closing(db.connect()) as con, con:
        con.execute("PRAGMA user_version=999")
    before = raw_state()
    with pytest.raises(RuntimeError, match="newer"):
        db.ensure_schema()
    assert raw_state() == before


def test_missing_estimating_view_is_not_reported_ready_or_rebuilt():
    seed()
    with closing(db.connect()) as con, con:
        con.execute("DROP VIEW cutting_pieces")
    before = raw_state()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "incompatible"
    assert client.get("/api/model").status_code == 503
    assert raw_state() == before


def test_health_does_not_initialize_or_migrate():
    assert client.get("/api/health").json()["status"] == "uninitialized"
    assert not db.DB_PATH.exists()
    seed()
    with closing(db.connect()) as con, con:
        con.execute("PRAGMA user_version=0")
    before = raw_state()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "migration_required"
    assert raw_state() == before
    assert not list(db.DB_PATH.parent.glob("test.db.backup-*"))


def test_snapshot_includes_wal_and_restore_retains_previous_revision(tmp_path):
    seed()
    snapshot = tmp_path / "snapshot.db"
    with closing(db.connect()) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("UPDATE model_meta SET value=? WHERE key='params'", (json.dumps({"roof": "hip"}),))
        con.commit()
        migrations.backup_database(db.DB_PATH, snapshot)
    expected = raw_state()
    db.rebuild(ModelConfig())
    previous = raw_state()
    backup = restore_database(snapshot, db.DB_PATH)
    assert raw_state() == expected
    with closing(sqlite3.connect(backup)) as con:
        assert [tuple(r) for r in con.execute("SELECT * FROM elements ORDER BY 1")] == previous["elements"]


def test_fractional_stock_length_is_never_shorter_than_cut():
    db.rebuild(ModelConfig())
    with closing(db.connect()) as con, con:
        con.execute("UPDATE elements SET length_mm=3000.1 WHERE type_code='stud'")
    rows = [r for r in db.bom_rows() if r["element"] == "Wall stud"]
    assert rows and all(r["stock_length_m"] == 3.3 for r in rows)


def test_api_package_and_release_versions_match():
    from pathlib import Path
    from server import app
    root = Path(__file__).parent.parent
    version = (root / "VERSION").read_text().strip()
    assert app.version == version
    assert json.loads((root / "frontend/package.json").read_text())["version"] == version
    assert json.loads((root / "frontend/package-lock.json").read_text())["version"] == version
