"""Offline snapshot/restore commands. Run from backend/: python manage_db.py --help."""

from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
import json
from contextlib import closing
from pathlib import Path

import db
import projects
from migrations import backup_database, backup_name


def restore_database(snapshot: Path, destination: Path, expected_project_id: str | None = None) -> Path | None:
    """Restore a validated snapshot atomically; the server must be stopped."""
    snapshot, destination = snapshot.resolve(), destination.resolve()
    if snapshot == destination:
        raise ValueError("Choose a separate snapshot file")
    if any(Path(str(destination) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise RuntimeError("SQLite sidecar files exist. Stop all database users before restoring.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".restore-", delete=False) as handle:
        staging = Path(handle.name)
    staging.unlink()
    try:
        backup_database(snapshot, staging)
        with closing(sqlite3.connect(staging)) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"elements", "element_types", "model_meta"} <= tables:
                raise ValueError("Snapshot is not a TimberBIM database")
            state = con.execute("SELECT value FROM model_meta WHERE key='project'").fetchone()
            if expected_project_id is not None and state and json.loads(state[0]).get("project_id") != expected_project_id:
                raise ValueError("Snapshot belongs to another home; choose that home's project ID")
        previous = backup_database(destination, backup_name(destination, "before-restore")) if destination.exists() else None
        os.replace(staging, destination)
        return previous
    finally:
        staging.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Create a consistent SQLite snapshot")
    backup.add_argument("--output", type=Path)
    backup.add_argument("--project-id", default="default")
    restore = commands.add_parser("restore", help="Restore a snapshot while the server is stopped")
    restore.add_argument("snapshot", type=Path)
    restore.add_argument("--confirm-replace", action="store_true", required=True)
    restore.add_argument("--project-id", default="default")
    args = parser.parse_args()
    location = projects.path(db.DB_PATH, args.project_id)
    if args.command == "backup":
        print(backup_database(location, args.output or backup_name(location, "manual")))
    else:
        previous = restore_database(args.snapshot, location, args.project_id)
        print(f"Restored {location}; previous snapshot: {previous or 'new database'}")


if __name__ == "__main__":
    main()
