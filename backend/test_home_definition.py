"""Reusable saved homes, supports, topology and portable revision contracts."""
from contextlib import closing
from pathlib import Path
import json
import math

import pytest

import db
import projects
import home_definition as homes
from framing import ModelConfig
from test_projects import home, scope, headers, commit_wall
from test_smoke import client
from test_smoke import manual_wall_payload

EXAMPLES=Path(__file__).parent.parent/"examples"/"homes"


def example(name="rectangle"):
    return json.loads((EXAMPLES/(name+".json")).read_text())


def save(model,definition,key="save-home"):
    proof=client.post("/api/project/home/preview",params=scope(model),json=definition)
    assert proof.status_code == 200,proof.text
    response=client.request("PUT","/api/project/home/commit",params=scope(model),json=definition,
                            headers=headers(model,proof.json(),key))
    assert response.status_code == 200,response.text
    return response.json(),proof.json()


@pytest.mark.parametrize("name",["rectangle","l_shape","two_level"])
def test_three_different_homes_save_reload_regenerate_and_export(name):
    original=home()
    saved,preview=save(original,example(name))
    assert saved["meta"]["project"]["geometry_mode"] == "custom"
    assert saved["meta"]["home_definition"]["template"] == "custom"
    assert len(preview["elements"]) == len(saved["elements"])
    assert saved["meta"]["cost_summary"]["grand_total_usd"] == preview["metadata"]["estimated_cost_usd"]
    reloaded=client.get("/api/model",params=scope(saved))
    assert reloaded.json() == saved
    assert any(e["type_code"]=="truss_web" for e in saved["elements"])
    assert not any(e["type_code"] in {"rafter","ridge","ceiling_joist"} for e in saved["elements"])
    regenerated=client.post("/api/project/regenerate",params=scope(saved),json={},headers=headers(saved,key="regenerate"))
    assert regenerated.status_code == 200,regenerated.text
    updated=regenerated.json()
    assert [e["physical_member_id"] for e in updated["elements"]] == [e["physical_member_id"] for e in saved["elements"]]
    archive=client.get("/api/project/archive",params=scope(updated)).json()
    other=home("Copy")
    proof=client.post("/api/project/archive/preview",params=scope(other),json=archive)
    assert proof.status_code == 200,proof.text
    imported=client.post("/api/project/archive/commit",params=scope(other),json=archive,headers=headers(other,proof.json(),"import"))
    assert imported.status_code == 200,imported.text
    copy=imported.json()
    assert len(copy["elements"])==len(updated["elements"])
    assert {k:v for k,v in copy["meta"]["cost_summary"].items() if k!="project"}=={k:v for k,v in updated["meta"]["cost_summary"].items() if k!="project"}
    assert client.get("/api/model",params=scope(updated)).json()==updated


@pytest.mark.parametrize("axis",["x","y"])
def test_roof_instances_have_connected_webs_and_explicit_end_bearings(axis):
    data=example()
    r=data["roofs"][0];r.update(ridge_axis=axis,spacing_mm=1300,first_offset_mm=100,last_offset_mm=5700 if axis=="y" else 8500,
                              bearing_wall_ids=["rectangle-4","rectangle-2"] if axis=="y" else ["rectangle-1","rectangle-3"])
    result=homes.generate(homes.HomeDefinition.model_validate(data),ModelConfig())
    groups={}
    for e in result.elements:
        if e.get("truss_id"):groups.setdefault(e["truss_id"],[]).append(e)
    assert len(groups)==(6 if axis=="y" else 8)
    offsets=[]
    for members in groups.values():
        assert any(e["member_role"]=="web" for e in members)
        graph={}
        for e in members:
            graph.setdefault(e["start_node"],set()).add(e["end_node"])
            graph.setdefault(e["end_node"],set()).add(e["start_node"])
        seen=set();todo=[next(iter(graph))]
        while todo:
            n=todo.pop()
            if n not in seen:seen.add(n);todo.extend(graph[n]-seen)
        assert seen==set(graph)
        offsets.append(members[0]["cx" if axis=="x" else "cy"])
    assert min(offsets)==pytest.approx(100)
    assert max(offsets)==pytest.approx(r["last_offset_mm"])
    assert all(b-a<=1300.01 for a,b in zip(sorted(offsets),sorted(offsets)[1:]))
    assert len({e["physical_member_id"] for members in groups.values() for e in members})>len(groups)


def test_level_and_actual_bearing_wall_elevations_are_used():
    data=example("two_level")
    for w in data["walls"]:
        if w["level_id"]=="upper":w["spec"]["wall_height_mm"]=3000
    result=homes.generate(homes.HomeDefinition.model_validate(data),ModelConfig())
    bottom=[e for e in result.elements if e["type_code"]=="truss_bottom_chord"]
    assert bottom and all(e["cz"]==pytest.approx(7100) for e in bottom)
    first=next(e for e in result.elements if e.get("segment_id")=="upper-1" and e["type_code"]=="plate_bottom")
    assert first["cz"]==pytest.approx(4122.5)


@pytest.mark.parametrize("axis",["x","y"])
@pytest.mark.parametrize("kind",["common","girder","mono","scissor","attic"])
def test_automatic_truss_physical_bearings_match_translated_wall_supports(axis,kind):
    data=example()
    ox,oy=12000,-8500
    data["levels"][0]["elevation_mm"]=1250
    for wall in data["walls"]:
        for field in ("start_x_mm","end_x_mm"):wall["spec"][field]+=ox
        for field in ("start_z_mm","end_z_mm"):wall["spec"][field]+=oy
    for floor in data["floors"]:
        floor["boundary_mm"]=[[x+ox,y+oy] for x,y in floor["boundary_mm"]]
    roof=data["roofs"][0]
    roof.update(ridge_axis=axis,truss_type=kind,
                minimum_mm=[ox,oy],maximum_mm=[ox+9000,oy+6000],
                bearing_wall_ids=["rectangle-1","rectangle-3"] if axis=="x" else ["rectangle-4","rectangle-2"])
    result=homes.generate(homes.HomeDefinition.model_validate(data),ModelConfig())
    groups={}
    for member in result.elements:
        if member.get("truss_id"):groups.setdefault(member["truss_id"],[]).append(member)
    assert groups
    for members in groups.values():
        bearings={}
        for member in members:
            half=member["length_mm"]/2
            delta=(math.cos(member["yaw"])*math.cos(member["pitch"])*half,
                   math.sin(member["yaw"])*math.cos(member["pitch"])*half,math.sin(member["pitch"])*half)
            for field,sign in (("start_node",-1),("end_node",1)):
                if member[field] in {"BL","BR"}:
                    point=tuple(member[c]+sign*d for c,d in zip(("cx","cy","cz"),delta))
                    if member[field] in bearings:assert point==pytest.approx(bearings[member[field]],abs=.001)
                    bearings[member[field]]=point
        assert set(bearings)=={"BL","BR"}
        coordinate=1 if axis=="x" else 0
        assert bearings["BL"][coordinate]==pytest.approx(roof["minimum_mm"][coordinate])
        assert bearings["BR"][coordinate]==pytest.approx(roof["maximum_mm"][coordinate])
        assert bearings["BL"][1-coordinate]==pytest.approx(bearings["BR"][1-coordinate])
        assert bearings["BL"][2]==pytest.approx(4050)
        assert bearings["BR"][2]==pytest.approx(4050)


def test_support_segment_extents_change_only_rows_that_cross_them():
    data=example("two_level")
    result=homes.generate(homes.HomeDefinition.model_validate(data),ModelConfig())
    joists=[e for e in result.elements if e["type_code"]=="joist"]
    assert any(e["length_mm"]==3000 and e["cy"]<2750 for e in joists)
    assert any(e["length_mm"]==6000 and e["cy"]>2750 for e in joists)
    assert not any(e["type_code"]=="blocking" and e["cy"]>2750 for e in result.elements)


def test_rotated_floor_scan_and_hole_boundaries():
    floor={"id":"floor","level_id":"L","boundary_mm":[[0,0],[6000,0],[6000,6000],[0,6000]],
           "holes_mm":[[[2000,2000],[4000,2000],[4000,4000],[2000,4000]]],
           "joist_direction_deg":37,"spacing_mm":450}
    definition=homes.HomeDefinition.model_validate({"levels":[{"id":"L","number":1}],"floors":[floor]})
    result=homes.generate(definition,ModelConfig())
    assert result.elements
    for e in result.elements:
        assert math.degrees(e["yaw"])==pytest.approx(37,abs=.001)
        for t in (-.49,0,.49):
            p=(e["cx"]+math.cos(e["yaw"])*e["length_mm"]*t,e["cy"]+math.sin(e["yaw"])*e["length_mm"]*t)
            assert homes.inside(p,definition.floors[0].boundary_mm)
            assert not homes.inside(p,definition.floors[0].holes_mm[0])


def test_stable_entity_ids_survive_wall_reordering_and_preserve_additions():
    accepted,_=commit_wall(home())
    before=accepted["model"]
    saved,_=save(before,example())
    data=example();data["walls"].reverse()
    after,_=save(saved,data,"reorder-home")
    old={e["physical_member_id"] for e in saved["elements"] if e["source"]=="generated"}
    new={e["physical_member_id"] for e in after["elements"] if e["source"]=="generated"}
    assert old==new
    assert [e for e in after["elements"] if e["source"]=="manual_wall"]==before["elements"]


@pytest.mark.parametrize("change",["duplicate","bad_level","missing_bearing","short_bearing","self_intersection","bad_hole","budget","version"])
def test_invalid_home_definitions_leave_saved_work_untouched(change):
    model=home();data=example()
    if change=="duplicate":data["walls"][1]["id"]=data["walls"][0]["id"]
    if change=="bad_level":data["roofs"][0]["level_id"]="missing"
    if change=="missing_bearing":data["roofs"][0]["bearing_wall_ids"]=["missing","rectangle-3"]
    if change=="short_bearing":data["walls"][0]["spec"]["end_x_mm"]=6000
    if change=="self_intersection":data["floors"][0]["boundary_mm"]=[[0,0],[6000,6000],[0,6000],[6000,0]]
    if change=="bad_hole":data["floors"][0]["holes_mm"]=[[[0,0],[2000,0],[2000,2000],[0,2000]]]
    if change=="budget":data["roofs"][0]["maximum_mm"]=[1e10,6000]
    if change=="version":data["schema_version"]=2
    response=client.post("/api/project/home/preview",params=scope(model),json=data)
    assert response.status_code==422,response.text
    assert client.get("/api/model",params=scope(model)).json()==model


def test_archive_quotes_manual_definition_undo_and_retry_are_atomic():
    source,_=save(home(),example())
    accepted,_=commit_wall(source)
    source=accepted["model"]
    priced=client.post("/api/pricing/overrides",params=scope(source),json={"overrides":{"sg8":9.25}},headers=headers(source,key="price")).json()
    archive=client.get("/api/project/archive",params=scope(priced)).json()
    assert archive["assemblies"][0]["definition"]
    target=home("Target","sample")
    proof=client.post("/api/project/archive/preview",params=scope(target),json=archive).json()
    args={"params":scope(target),"json":archive,"headers":headers(target,proof,"archive-retry")}
    response=client.post("/api/project/archive/commit",**args)
    assert response.status_code==200,response.text
    imported=response.json()
    assert {k:v for k,v in imported["meta"]["cost_summary"].items() if k!="project"}=={k:v for k,v in priced["meta"]["cost_summary"].items() if k!="project"}
    assert client.post("/api/project/archive/commit",**args).json()==imported
    assert len(client.get("/api/project/definitions",params=scope(imported)).json()["definitions"])==1
    restored=client.post(f"/api/project/revisions/{target['meta']['project']['revision']}/restore",params=scope(imported),json={},headers=headers(imported,key="undo-archive"))
    assert restored.status_code==200,restored.text
    assert restored.json()["elements"]==target["elements"]


def test_home_preview_revision_race_cannot_issue_a_valid_stale_proof(monkeypatch):
    model=home()
    original=homes.generate
    def change(definition,cfg):
        with closing(db.connect()) as con,con:
            state=json.loads(con.execute("SELECT value FROM model_meta WHERE key='project'").fetchone()[0]);state["revision"]+=1
            con.execute("UPDATE model_meta SET value=? WHERE key='project'",(json.dumps(state),))
        return original(definition,cfg)
    monkeypatch.setattr(homes,"generate",change)
    response=client.post("/api/project/home/preview",params=scope(model),json=example())
    assert response.status_code==409


def test_home_defaults_level_height_and_persists_stable_opening_ids():
    data=example()
    del data["walls"][0]["spec"]["wall_height_mm"]
    del data["walls"][0]["spec"]["openings"][0]["opening_id"]
    parsed=homes.HomeDefinition.model_validate(data)
    assert parsed.walls[0].spec.wall_height_mm==2800
    ident=parsed.walls[0].spec.openings[0].opening_id
    saved,_=save(home(),data)
    persisted=saved["meta"]["home_definition"]["walls"][0]["spec"]
    assert persisted["openings"][0]["opening_id"]==ident
    assert persisted["wall_height_mm"]==2800


@pytest.mark.parametrize("axis",["x","y"])
def test_rafter_system_uses_explicit_pitch_and_bearing_elevation(axis):
    data=example()
    data["roofs"][0].update(system="rafter",ridge_axis=axis,pitch_deg=31,heel_height_mm=200,
        bearing_wall_ids=["rectangle-4","rectangle-2"] if axis=="y" else ["rectangle-1","rectangle-3"])
    result=homes.generate(homes.HomeDefinition.model_validate(data),ModelConfig())
    rafters=[e for e in result.elements if e["type_code"]=="rafter"]
    assert rafters and all(abs(math.degrees(e["pitch"]))==pytest.approx(31,abs=.001) for e in rafters)
    assert any(e["type_code"]=="ceiling_joist" for e in result.elements)
    assert not any(e["type_code"].startswith("truss_") for e in result.elements)
    gable=[e for e in result.elements if e["type_code"]=="gable_stud"]
    assert gable
    coord="cx" if axis=="x" else "cy"
    assert {e[coord] for e in gable}=={0,9000 if axis=="x" else 6000}


def test_archive_late_insert_failure_rolls_back_every_project_table(monkeypatch):
    saved,_=save(home(),example())
    archive=client.get("/api/project/archive",params=scope(saved)).json()
    target=home("Preserved","sample")
    proof=client.post("/api/project/archive/preview",params=scope(target),json=archive).json()
    original=db._insert_elements
    def fail(con,elements):
        original(con,elements)
        raise RuntimeError("injected archive failure")
    monkeypatch.setattr(db,"_insert_elements",fail)
    response=client.post("/api/project/archive/commit",params=scope(target),json=archive,headers=headers(target,proof,"fail-archive"))
    assert response.status_code==503
    assert client.get("/api/model",params=scope(target)).json()==target


def test_legacy_archive_retains_geometry_and_exposes_recreation_gate():
    accepted,_=commit_wall(home())
    source=accepted["model"]
    token=projects.project_id.set(scope(source)["project_id"])
    try:
        with closing(db.connect()) as con,con:con.execute("DELETE FROM source_definitions")
    finally:projects.project_id.reset(token)
    archive=client.get("/api/project/archive",params=scope(source)).json()
    assert archive["assemblies"][0]["legacy_members"]
    other=home()
    proof=client.post("/api/project/archive/preview",params=scope(other),json=archive)
    assert proof.status_code==200,proof.text
    assert any("legacy geometry" in w for w in proof.json()["metadata"]["warnings"])
    response=client.post("/api/project/archive/commit",params=scope(other),json=archive,headers=headers(other,proof.json(),"legacy-archive"))
    assert response.status_code==200,response.text
    assert len(response.json()["elements"])==len(source["elements"])
    archive["assemblies"][0]["legacy_members"][0]["material"]={"bad":"type"}
    assert client.post("/api/project/archive/preview",params=scope(response.json()),json=archive).status_code==422
    imported=response.json()
    deleted=client.delete("/api/import/batches/"+archive["assemblies"][0]["id"],params=scope(imported),headers=headers(imported,key="legacy-delete"))
    assert deleted.status_code==200,deleted.text
    assert not any("legacy geometry" in w for w in client.get("/api/model",params=scope(imported)).json()["meta"]["warnings"])


def test_manual_assembly_id_matching_home_entity_does_not_replace_or_delete_it():
    saved,_=save(home(),example())
    original=[e for e in saved["elements"] if e["source"]=="generated"]
    payload={**manual_wall_payload(),"input_id":"rectangle-1","segment_id":"rectangle-1","start_z_mm":10000,"end_z_mm":10000}
    accepted,_=commit_wall(saved,payload)
    model=accepted["model"]
    segments=[s for s in model["meta"]["frame_segments"] if s["segment_id"]=="rectangle-1"]
    assert len(segments)==2 and {s["source"] for s in segments}=={"generated","manual_wall"}
    payload["end_x_mm"]=4800
    proof=client.post("/api/manual/wall-frame/preview",params=scope(model),json=payload).json()
    updated=client.request("PUT","/api/manual/wall-frame/rectangle-1",params=scope(model),json=payload,headers=headers(model,proof,"same-id-edit"))
    assert updated.status_code==200,updated.text
    edited=updated.json()["model"]
    assert [e for e in edited["elements"] if e["source"]=="generated"]==original
    archive=client.get("/api/project/archive",params=scope(edited)).json()
    assert client.post("/api/project/archive/preview",params=scope(edited),json=archive).status_code==200
    deleted=client.delete("/api/import/batches/rectangle-1",params=scope(edited),headers=headers(edited,key="same-id-delete"))
    assert deleted.status_code==200,deleted.text
    assert client.get("/api/model",params=scope(edited)).json()["elements"]==original
