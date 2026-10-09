"""Project scope, optimistic writes, and bounded undo snapshots.

Each home has an independent SQLite file. ContextVars isolate concurrent ASGI
requests; the legacy database remains the explicitly named default project.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import uuid
import diagnostics

project_id = ContextVar("project_id", default="default")
write_contract = ContextVar("write_contract", default=None)
read_revision = ContextVar("read_revision", default=None)


class ProjectConflict(ValueError):
    pass


def path(base, identifier=None):
    identifier = identifier or project_id.get()
    if identifier == "default":
        return base
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Project ID must be default or a 32-character UUID")
    return base.parent / (base.name + ".projects") / (identifier + ".db")


def info(con):
    row = con.execute("SELECT value FROM model_meta WHERE key='project'").fetchone()
    if not row:
        raise RuntimeError("Project identity is missing; migrate or restore the database")
    try:
        state = json.loads(row[0])
    except (ValueError, TypeError):
        raise RuntimeError("Project identity is corrupt; restore a snapshot") from None
    if not isinstance(state, dict) or type(state.get("revision")) is not int or state["revision"] < 0 or state.get("geometry_mode") not in {"sample", "custom", "mixed"}:
        raise RuntimeError("Project identity/revision is invalid; restore a snapshot")
    if state.get("project_id") != project_id.get():
        raise RuntimeError("Database identity does not match the selected home; restore its own snapshot")
    diagnostics.observed_revision(state["project_id"], state["revision"])
    return state


def check_read(con):
    state = info(con)
    expected = read_revision.get()
    if expected is not None and expected != state["revision"]:
        raise ProjectConflict(f"Requested revision {expected}, current revision {state['revision']}. Reload before exporting.")
    return state


def save_info(con, value):
    con.execute("INSERT INTO model_meta VALUES ('project',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(value),))


def initial_info(name="Sample home", mode="sample"):
    return {"project_id": project_id.get(), "name": name, "revision": 0,
            "geometry_mode": mode, "definition_schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat()}


SNAPSHOT_TABLES = ("elements", "model_meta", "import_batches", "source_definitions")


def snapshot(con):
    return {table: [dict(row) for row in con.execute(f"SELECT * FROM {table}")]
            for table in SNAPSHOT_TABLES}


@contextmanager
def mutation(con, action, fingerprint=None):
    """Check, snapshot, change, and advance the revision in one transaction.

    Yield False for a replay of the same operation. Reject reuse of its key for
    a different request. Snapshots retain the most recent 20 prior revisions.
    """
    con.execute("BEGIN IMMEDIATE")
    try:
        state = info(con)
        contract = write_contract.get() or {}
        key = contract.get("key")
        digest = contract.get("digest") or hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()
        if key:
            previous = con.execute("SELECT digest FROM operations WHERE operation_key=?", (key,)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise ProjectConflict("Idempotency key was already used for different input")
                yield False
                con.rollback()
                return
        expected = contract.get("revision")
        if expected is not None and expected != state["revision"]:
            raise ProjectConflict(f"Project changed: expected revision {expected}, current revision {state['revision']}. Reload and preview again.")
        if con.execute("SELECT 1 FROM model_meta WHERE key='params'").fetchone():
            con.execute("INSERT OR REPLACE INTO project_revisions VALUES (?,?,?,?)",
                        (state["revision"], datetime.now(timezone.utc).isoformat(), action,
                         json.dumps(snapshot(con))))
        yield True
        updated = info(con)
        updated["revision"] = state["revision"] + 1
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_info(con, updated)
        if con.execute("SELECT 1 FROM model_meta WHERE key='params'").fetchone():
            import review
            params=json.loads(con.execute("SELECT value FROM model_meta WHERE key='params'").fetchone()[0])
            home_row=con.execute("SELECT value FROM model_meta WHERE key='home_definition'").fetchone()
            assessment=review.evaluate([dict(row) for row in con.execute("SELECT * FROM elements")],params,
                                       json.loads(home_row[0]) if home_row else None)
            assessment["project_revision"]=updated["revision"]
            con.execute("INSERT INTO model_meta VALUES ('review_snapshot',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (json.dumps(assessment),))
        if key:
            con.execute("INSERT INTO operations VALUES (?,?,?)", (key, digest, updated["revision"]))
        con.execute("DELETE FROM project_revisions WHERE revision NOT IN (SELECT revision FROM project_revisions ORDER BY revision DESC LIMIT 20)")
        con.commit()
    except BaseException:
        con.rollback()
        raise


def operation_id(prefix):
    contract = write_contract.get() or {}
    key = contract.get("key")
    return prefix + "-" + (uuid.uuid5(uuid.NAMESPACE_URL, project_id.get() + ":" + key).hex
                            if key else uuid.uuid4().hex)


def restore(con, revision):
    row = con.execute("SELECT snapshot FROM project_revisions WHERE revision=?", (revision,)).fetchone()
    if not row:
        raise KeyError("Revision is unavailable (only the last 20 snapshots are retained)")
    saved = json.loads(row[0])
    with mutation(con, f"restore revision {revision}") as apply:
        if not apply:
            return
        current = info(con)
        for table in SNAPSHOT_TABLES:
            con.execute(f"DELETE FROM {table}")
            rows = saved[table]
            if rows:
                columns = list(rows[0])
                con.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                [[row[col] for col in columns] for row in rows])
        restored = info(con)
        restored["project_id"] = current["project_id"]
        save_info(con, restored)
