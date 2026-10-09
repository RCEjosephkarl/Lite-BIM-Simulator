"""Two-client isolation, stale-write protection, preview contracts and recovery."""
import json
import sqlite3
from contextlib import closing
from urllib.parse import quote
from pathlib import Path

import db
import projects
from concurrent.futures import ThreadPoolExecutor
from migrations import backup_database
from manage_db import restore_database
import pytest
from test_smoke import client, manual_wall_payload


def test_csv_batch_edit_replaces_only_its_assembly_and_undo_restores_definition():
    original = home()
    wall, _ = commit_wall(original)
    model = wall["model"]
    rows = [{"type": "wall", "level": 1, "segment_id": "CSV-W", "label": "Batch wall", "start_x_mm": 0,
             "start_z_mm": 5000, "end_x_mm": 3600, "end_z_mm": 5000, "height_mm": 2535}]
    payload = {"rows": rows, "file_name": "edited.csv"}
    proof = client.post("/api/import/csv-plan/preview", params=scope(model), json=payload).json()
    response = client.post("/api/import/csv-plan/commit", params=scope(model), json=payload,
                           headers=headers(model, proof, "csv-for-edit"))
    assert response.status_code == 200, response.text
    batch_id = response.json()["batch_id"]
    before = response.json()["model"]
    edited = {**payload, "rows": [{**rows[0], "end_x_mm": 4800}]}
    proof = client.post("/api/import/csv-plan/preview", params=scope(before), json=edited).json()
    args = {"params": scope(before), "json": edited, "headers": headers(before, proof, "csv-edit")}
    response = client.request("PUT", f"/api/import/csv-plan/{batch_id}", **args)
    assert response.status_code == 200, response.text
    after = response.json()["model"]
    assert {e["source_id"] for e in after["elements"]} == {batch_id, wall["source_id"]}
    assert [e for e in after["elements"] if e["source_id"] == wall["source_id"]] == model["elements"]
    assert next(s for s in after["meta"]["frame_segments"] if s["segment_id"] == "CSV-W")["length_mm"] == 4800
    assert client.request("PUT", f"/api/import/csv-plan/{batch_id}", **args).json() == response.json()
    assert len(client.get("/api/import/batches", params=scope(after)).json()["batches"]) == 2
    definitions = client.get("/api/project/definitions", params=scope(after)).json()
    assert definitions["project_revision"] == after["meta"]["project"]["revision"]
    saved = next(d for d in definitions["definitions"] if d["definition_id"] == batch_id)
    assert saved["payload"]["rows"][0]["end_x_mm"] == 4800
    restored = client.post(f"/api/project/revisions/{before['meta']['project']['revision']}/restore",
                           params=scope(after), json={}, headers=headers(after, key="undo-csv-edit"))
    assert restored.status_code == 200, restored.text
    assert restored.json()["elements"] == before["elements"]


def test_csv_edit_invalid_or_cross_home_target_preserves_both_homes():
    accepted, _ = commit_wall(home())
    model = accepted["model"]
    other = home("Other edit target")
    payload = {"rows": [{"type": "wall", "level": 1, "segment_id": "W", "label": "Foreign target", "start_x_mm": 0,
                         "start_z_mm": 0, "end_x_mm": 3600, "end_z_mm": 0, "height_mm": 2535}]}
    preview = client.post("/api/import/csv-plan/preview", params=scope(other), json=payload)
    assert preview.status_code == 200, preview.text
    proof = preview.json()
    result = client.request("PUT", f"/api/import/csv-plan/{accepted['source_id']}", params=scope(other),
                            json=payload, headers=headers(other, proof, "foreign-csv-edit"))
    assert result.status_code == 404
    result = client.request("PUT", f"/api/import/csv-plan/{accepted['source_id']}", params=scope(model),
                            json={"rows": []}, headers=headers(model, key="invalid-csv-edit"))
    assert result.status_code == 422
    assert client.get("/api/model", params=scope(model)).json() == model
    assert client.get("/api/model", params=scope(other)).json() == other


def test_existing_manual_source_ids_with_slashes_are_editable():
    identifier = 'Legacy wall / literal <label>'
    accepted, _ = commit_wall(home(), {**manual_wall_payload(), "input_id": identifier})
    model = accepted["model"]
    payload = {**manual_wall_payload(), "input_id": identifier, "end_x_mm": 4200}
    proof = client.post("/api/manual/wall-frame/preview", params=scope(model), json=payload).json()
    result = client.request("PUT", "/api/manual/wall-frame/" + quote(identifier, safe=''),
                            params=scope(model), json=payload, headers=headers(model, proof, "literal-edit"))
    assert result.status_code == 200, result.text
    assert {e["source_id"] for e in result.json()["model"]["elements"]} == {identifier}


@pytest.mark.parametrize("route", ["/api/project/definitions", "/api/project/revisions"])
def test_saved_definition_and_history_reads_reject_an_old_revision(route):
    original = home()
    accepted, _ = commit_wall(original)
    model = accepted["model"]
    assert client.get(route, params={**scope(model), "revision": original["meta"]["project"]["revision"]}).status_code == 409
    assert client.get(route, params={**scope(model), "revision": model["meta"]["project"]["revision"]}).status_code == 200
    assert client.get("/api/model", params=scope(model)).json() == model


@pytest.mark.parametrize("mode", ["custom", "sample"])
def test_new_home_creation_uses_its_own_revision_and_retry_key(mode):
    accepted, _ = commit_wall(home())
    parent = accepted["model"]
    args = {"params": scope(parent), "json": {"name": "Created from another home", "geometry_mode": mode},
            "headers": headers(parent, key="new-home-retry")}
    result = client.post("/api/projects", **args)
    assert result.status_code == 200, result.text
    created = result.json()
    assert scope(created) != scope(parent)
    assert created["meta"]["project"]["geometry_mode"] == mode
    assert client.post("/api/projects", **args).json() == created
    reused = client.post("/api/projects", params=scope(parent), json={"name": "Different name", "geometry_mode": mode},
                         headers=headers(parent, key="new-home-retry"))
    assert reused.status_code == 409
    assert client.get("/api/model", params=scope(parent)).json() == parent
    assert client.get("/api/model", params=scope(created)).json() == created


@pytest.mark.parametrize("mode", ["custom", "sample"])
def test_concurrent_home_creation_retry_creates_one_home(mode):
    parent = home()
    def create():
        return client.post("/api/projects", params=scope(parent), json={"name": "Concurrent home", "geometry_mode": mode},
                           headers=headers(parent, key="concurrent-home"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(), range(2)))
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    assert responses[0].json() == responses[1].json()
    homes = client.get("/api/projects").json()["projects"]
    assert len(homes) == 2


def test_creation_retry_refuses_to_overwrite_geometry_missing_its_metadata():
    parent = home()
    args = {"params": scope(parent), "json": {"name": "Damaged home", "geometry_mode": "sample"},
            "headers": headers(parent, key="damaged-home")}
    created = client.post("/api/projects", **args).json()
    location = projects.path(db.DB_PATH, scope(created)["project_id"])
    with closing(sqlite3.connect(location)) as con, con:
        con.execute("DELETE FROM model_meta WHERE key='params'")
    before = location.read_bytes()
    result = client.post("/api/projects", **args)
    assert result.status_code == 503, result.text
    assert location.read_bytes() == before


def home(name="Test home", mode="custom"):
    response = client.post("/api/projects", json={"name": name, "geometry_mode": mode})
    assert response.status_code == 200, response.text
    return response.json()


def scope(model):
    return {"project_id": model["meta"]["project"]["project_id"]}


def headers(model, proof=None, key="wall-create"):
    result = {"If-Match": str(model["meta"]["project"]["revision"]), "Idempotency-Key": key}
    if proof:
        result["X-Preview-Token"] = proof["preview_token"]
    return result


def commit_wall(model, payload=None, key="wall-create"):
    payload = payload or manual_wall_payload()
    proof = client.post("/api/manual/wall-frame/preview", params=scope(model), json=payload)
    assert proof.status_code == 200, proof.text
    result = client.post("/api/manual/wall-frame/commit", params=scope(model), json=payload,
                         headers=headers(model, proof.json(), key))
    assert result.status_code == 200, result.text
    return result.json(), proof.json()


def test_model_read_never_initializes_or_applies_query_configuration():
    assert client.get("/api/model").status_code == 404
    assert not db.DB_PATH.exists()
    original = client.post("/api/project/initialize").json()
    before = db.DB_PATH.read_bytes()
    result = client.get("/api/model?roof=hip&storeys=3").json()
    assert result == original
    assert db.DB_PATH.read_bytes() == before


def test_two_homes_keep_model_cost_bom_batches_and_definitions_separate():
    first, second = home("First"), home("Second", "sample")
    committed, _ = commit_wall(first)
    first = committed["model"]
    assert all(e["source"] == "manual_wall" for e in first["elements"])
    assert client.get("/api/model", params=scope(second)).json() == second
    first_cost = client.get("/api/cost-summary", params=scope(first)).json()["grand_total_usd"]
    second_cost = client.get("/api/cost-summary", params=scope(second)).json()["grand_total_usd"]
    assert second_cost > first_cost > 0
    assert client.get("/api/import/batches", params=scope(second)).json()["batches"] == []
    assert len(client.get("/api/project/definitions", params=scope(first)).json()["definitions"]) == 1
    assert client.get("/api/project/definitions", params=scope(second)).json()["definitions"] == []
    assert len(client.get("/api/bom.json", params=scope(second)).json()["rows"]) > len(client.get("/api/bom.json", params=scope(first)).json()["rows"])
    assert not db.DB_PATH.exists()


def test_custom_home_settings_do_not_generate_sample_or_retain_sample_segments():
    model, _ = commit_wall(home())
    model = model["model"]
    result = client.post("/api/model", params={**scope(model), "roof": "hip", "storeys": 2}, json={}, headers=headers(model, key="settings"))
    assert result.status_code == 200, result.text
    changed = result.json()
    assert changed["elements"] == model["elements"]
    assert len(changed["meta"]["frame_segments"]) == 1
    assert changed["meta"]["frame_segments"][0]["source"] == "manual_wall"
    assert changed["meta"]["project"]["geometry_mode"] == "custom"
    assert changed["meta"]["roof"] == "hip"
    assert client.post("/api/project/regenerate", params=scope(changed), json={}, headers=headers(changed, key="regenerate")).status_code == 409


def test_missing_revision_stale_revision_and_preview_payload_are_rejected():
    model = home()
    assert client.post("/api/model", params=scope(model)).status_code == 428
    committed, proof = commit_wall(model)
    payload = {**manual_wall_payload(), "end_x_mm": 4000}
    altered = client.post("/api/manual/wall-frame/commit", params=scope(model), json=payload,
                          headers=headers(model, proof, "changed-payload"))
    assert altered.status_code == 409
    stale = client.post("/api/model", params=scope(model), headers=headers(model, key="stale"))
    assert stale.status_code == 409
    assert client.get("/api/model", params=scope(model)).json() == committed["model"]


def test_commit_retry_is_idempotent_and_key_reuse_is_rejected():
    model = home()
    accepted, proof = commit_wall(model)
    retry = client.post("/api/manual/wall-frame/commit", params=scope(model), json=manual_wall_payload(), headers=headers(model, proof))
    assert retry.status_code == 200, retry.text
    assert retry.json() == accepted
    payload = {**manual_wall_payload(), "end_x_mm": 4000}
    new_proof = client.post("/api/manual/wall-frame/preview", params=scope(model), json=payload).json()
    conflict = client.post("/api/manual/wall-frame/commit", params=scope(model), json=payload, headers=headers(accepted["model"], new_proof))
    assert conflict.status_code == 409


def test_cross_project_preview_cannot_commit_and_bad_path_creates_no_files():
    first, second = home("First"), home("Second")
    proof = client.post("/api/manual/wall-frame/preview", params=scope(first), json=manual_wall_payload()).json()
    result = client.post("/api/manual/wall-frame/commit", params=scope(second), json=manual_wall_payload(), headers=headers(second, proof))
    assert result.status_code == 409
    assert client.get("/api/model?project_id=../../escape").status_code == 422
    assert client.get("/api/model", params=scope(second)).json() == second


def test_restore_is_new_revision_and_preserves_definitions_and_ids():
    original, _ = commit_wall(home())
    model = original["model"]
    deleted = client.delete(f"/api/import/batches/{original['source_id']}", params=scope(model), headers=headers(model, key="delete"))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["model"]["elements"] == []
    current = deleted.json()["model"]
    restored = client.post(f"/api/project/revisions/{model['meta']['project']['revision']}/restore", params=scope(current), headers=headers(current, key="restore"))
    assert restored.status_code == 200, restored.text
    restored = restored.json()
    assert restored["elements"] == model["elements"]
    assert restored["meta"]["project"]["revision"] == current["meta"]["project"]["revision"] + 1
    assert len(client.get("/api/project/definitions", params=scope(restored)).json()["definitions"]) == 1


def test_manual_update_replaces_assembly_and_persists_the_source_definition():
    original, _ = commit_wall(home())
    model = original["model"]
    payload = {**manual_wall_payload(), "end_x_mm": 4000}
    proof = client.post("/api/manual/wall-frame/preview", params=scope(model), json=payload).json()
    result = client.request("PUT", f"/api/manual/wall-frame/{original['source_id']}", params=scope(model), json=payload, headers=headers(model, proof, "update"))
    assert result.status_code == 200, result.text
    definitions = client.get("/api/project/definitions", params=scope(model)).json()["definitions"]
    assert len(definitions) == 1 and definitions[0]["payload"]["end_x_mm"] == 4000
    assert {e["source_id"] for e in result.json()["model"]["elements"]} == {original["source_id"]}


def test_new_csv_home_keeps_previous_sample_and_retry_returns_same_home():
    sample = home("Original", "sample")
    rows = [{"type": "wall", "level": 1, "segment_id": "W1", "label": "Imported wall", "start_x_mm": 0, "start_z_mm": 0, "end_x_mm": 3600, "end_z_mm": 0, "height_mm": 2535}]
    proof = client.post("/api/import/csv-plan/preview", params=scope(sample), json={"rows": rows}).json()
    payload = {"rows": rows, "mode": "new_project_from_csv", "file_name": "my-home.csv"}
    args = {"params": scope(sample), "json": payload, "headers": headers(sample, proof, "create-from-csv")}
    response = client.post("/api/import/csv-plan/commit", **args)
    assert response.status_code == 200, response.text
    imported = response.json()
    assert scope(imported["model"]) != scope(sample)
    assert imported["model"]["meta"]["project"]["geometry_mode"] == "custom"
    assert client.get("/api/model", params=scope(sample)).json() == sample
    retry = client.post("/api/import/csv-plan/commit", **args)
    assert retry.status_code == 200 and retry.json() == imported


def test_concurrent_settings_writes_accept_only_one_matching_revision():
    model = home()
    def change(value):
        return client.post("/api/model", params={**scope(model), "storeys": value},
                           headers=headers(model, key=f"settings-{value}"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(change, [2, 3]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    current = client.get("/api/model", params=scope(model)).json()
    assert current["meta"]["project"]["revision"] == 1


def test_download_refuses_stale_revision_and_settings_key_includes_query():
    model = home("Export home", "sample")
    changed = client.post("/api/model", params={**scope(model), "roof": "hip"}, headers=headers(model, key="settings"))
    assert changed.status_code == 200
    assert client.get("/api/bom.csv", params={**scope(model), "revision": model["meta"]["project"]["revision"]}).status_code == 409
    assert client.get("/api/bom.csv", params={**scope(model), "revision": changed.json()["meta"]["project"]["revision"]}).status_code == 200
    reused = client.post("/api/model", params={**scope(model), "roof": "gable"}, headers=headers(changed.json(), key="settings"))
    assert reused.status_code == 409


def test_offline_restore_refuses_a_snapshot_of_another_home(tmp_path):
    first, second = home("First"), home("Second")
    first_path = projects.path(db.DB_PATH, scope(first)["project_id"])
    second_path = projects.path(db.DB_PATH, scope(second)["project_id"])
    snapshot = backup_database(first_path, tmp_path / "first-home.db")
    with pytest.raises(ValueError, match="another home"):
        restore_database(snapshot, second_path, scope(second)["project_id"])
    assert client.get("/api/model", params=scope(second)).json() == second


def test_corrupt_identity_is_reported_without_regeneration():
    model = client.post("/api/project/initialize").json()
    with db.connect() as con:
        con.execute("UPDATE model_meta SET value='[]' WHERE key='project'")
    before = db.DB_PATH.read_bytes()
    assert client.get("/api/model").status_code == 503
    assert client.post("/api/project/initialize").status_code == 503
    assert db.DB_PATH.read_bytes() == before
