"""Diagnostics disclose their source assumptions without certifying capacity."""
from contextlib import closing
from copy import deepcopy
import json

import db
import projects
import review
from framing import ModelConfig
from home_definition import HomeDefinition, generate
from manual_inputs import ManualWallFrameInput, ManualTrussInput, generate_wall, generate_truss
from test_home_definition import example,save
from test_projects import home,scope,headers,commit_wall
from test_smoke import client,manual_wall_payload


def checks(model,code):
    return [c for c in model["meta"]["review"]["checks"] if c["code"]==code]


def test_stud_review_uses_whole_timber_model_levels_independent_of_group_order():
    def wall(level):
        return generate_wall(ManualWallFrameInput(level=level,wall_height_mm=2400,
            end_x_mm=3600,stud_spacing_mm=600),source_id=f'wall-level-{level}')[0]
    lower,upper=wall(1),wall(3)
    single=review.evaluate(lower,{"wind_zone":"medium","storeys":3})
    assert next(c for c in single["checks"] if c["code"]=="wall.stud-assumptions")["status"]=="reference_only"
    for members in (lower+upper,list(reversed(upper+lower))):
        assessment=review.evaluate(members,{"wind_zone":"medium","storeys":1})
        wall_checks={c["level"]:c for c in assessment["checks"] if c["code"]=="wall.stud-assumptions"}
        assert wall_checks[1]["status"]=="requires_specific_design"
        assert wall_checks[3]["status"]=="reference_only"
        assert wall_checks[1]["inputs"]["spacing_mm"]==[600]
        assert assessment["profile"]["structural_approval"] is False
    roof,_=generate_truss(ManualTrussInput(level=3),source_id='upper-roof')
    assert next(c for c in review.evaluate(lower+roof,{"wind_zone":"medium"})["checks"]
                if c["code"]=="wall.stud-assumptions")["status"]=="requires_specific_design"
    concrete={**lower[0],"storey":20,"type_code":"slab"}
    assert review.evaluate(lower+[concrete],{"wind_zone":"medium","storeys":3})==single
    assert review.evaluate([],{} )["overall_status"]=="not_evaluated"


def test_bearing_diagnostic_detects_older_half_span_layout_and_missing_supports():
    data=HomeDefinition.model_validate(example())
    actual=generate(data,ModelConfig()).elements
    good=review.evaluate(actual,{},data.model_dump())
    bearings=[c for c in good["checks"] if c["code"]=="truss.bearings"]
    assert len(bearings)==11 and all(c["status"]=="evaluated_within_assumptions" for c in bearings)
    assert good["profile"]["version"]==2
    older=deepcopy(actual)
    for member in older:
        if member.get("truss_id"):member["cy"]-=3000
    bad=review.evaluate(older,{},data.model_dump())
    assert all(c["status"]=="evaluated_within_assumptions" for c in bad["checks"] if c["code"]=="truss.topology")
    assert all(c["status"]=="requires_specific_design" for c in bad["checks"] if c["code"]=="truss.bearings")
    raised=deepcopy(actual)
    for member in raised:
        if member.get("truss_id"):member["cz"]+=40
    mismatch=review.evaluate(raised,{},data.model_dump())
    assert all(c["status"]=="requires_specific_design" for c in mismatch["checks"] if c["code"]=="truss.bearings")
    missing=[m for m in actual if m.get("source_id")!="rectangle-1"]
    incomplete=review.evaluate(missing,{},data.model_dump())
    assert all(c["status"]=="not_evaluated" for c in incomplete["checks"] if c["code"]=="truss.bearings")
    assert good["profile"]["structural_approval"] is False


def test_actual_height_uses_explicit_datum_and_ignores_storey_count_as_proof():
    data=example();data["levels"][0]["elevation_mm"]=20000
    data["roofs"][0]["pitch_deg"]=75
    model,_=save(home(),data)
    height=checks(model,"profile.height")[0]
    assert height["status"]=="requires_specific_design"
    assert height["inputs"]["lowest_level_elevation_mm"]==20000
    assert height["inputs"]["height_above_lowest_level_mm"]>10000
    assert model["meta"]["review"]["profile"]["structural_approval"] is False


def test_connected_webs_pass_geometry_but_still_require_supplier_capacity_review():
    model,preview=save(home(),example())
    topology=checks(model,"truss.topology")
    assert len(topology)==11 and all(c["status"]=="evaluated_within_assumptions" for c in topology)
    assert all(c["status"]=="requires_specific_design" for c in checks(model,"truss.design"))
    assert preview["metadata"]["review"]["profile"]["structural_approval"] is False
    assert all(c["basis_review_status"]=="not_independently_verified" for c in model["meta"]["review"]["checks"])


def test_missing_or_inconsistent_node_geometry_is_not_reported_as_connected():
    data=HomeDefinition.model_validate(example());result=generate(data,ModelConfig())
    members=[m for m in result.elements if m.get("truss_id")=="main-roof:001-001"]
    missing=deepcopy(members);missing[0]["start_node"]=""
    assert review._topology(missing)[0] is None
    broken=deepcopy(members);broken[0]["cz"]+=5
    assert review._topology(broken)[0] is False


def test_unpriced_or_denser_wall_does_not_create_a_capacity_pass():
    model=home()
    accepted,_=commit_wall(model,{**manual_wall_payload(),"stud_material":"Unpriced product","stud_spacing_mm":300,"plies":2})
    wall=checks(accepted["model"],"wall.stud-assumptions")[0]
    assert wall["status"]=="requires_specific_design"
    assert wall["inputs"]["materials"]==["Unpriced product"]
    assert accepted["model"]["meta"]["review"]["overall_status"]!="evaluated_within_assumptions"
    assert checks(accepted["model"],"model.load-path")[0]["status"]=="not_evaluated"


def test_custom_without_level_datum_has_no_height_scope_claim_and_warnings_are_aggregated():
    accepted,_=commit_wall(home(),{**manual_wall_payload(),"stud_spacing_mm":701})
    model=accepted["model"]
    assert checks(model,"profile.height")[0]["status"]=="not_evaluated"
    response=client.get("/api/warnings",params=scope(model))
    assert response.status_code==200,response.text
    payload=response.json()
    assert payload["project_revision"]==model["meta"]["project"]["revision"]
    assert any(w["occurrences"]>1 and w.get("element_id") for w in payload["warnings"])
    assert len(payload["warnings"])<len(model["elements"])
    assert all({"code","severity","status","next_action","occurrences"}<=set(w) for w in payload["warnings"])


def test_review_snapshot_is_stored_with_revision_and_read_only_checks_preserve_database():
    model,_=save(home(),example("two_level"))
    token=projects.project_id.set(scope(model)["project_id"])
    try:
        location=projects.path(db.DB_PATH)
        before=location.read_bytes()
        with closing(db.connect()) as con:
            stored=json.loads(con.execute("SELECT value FROM model_meta WHERE key='review_snapshot'").fetchone()[0])
        assert stored["project_revision"]==model["meta"]["project"]["revision"]
        assert stored==model["meta"]["review"]
        client.get("/api/warnings",params=scope(model))
        client.get("/api/model",params=scope(model))
        assert location.read_bytes()==before
    finally:projects.project_id.reset(token)


def test_exposure_and_unknown_profile_cannot_become_an_implicit_approval():
    model,_=save(home(),example())
    changed=client.post("/api/model",params={**scope(model),"wind_speed":58,"snow_zone":"N5"},json={},headers=headers(model,key="exposure"))
    assert changed.status_code==200,changed.text
    assert checks(changed.json(),"profile.exposure")[0]["status"]=="requires_specific_design"
    data=example();data["rule_profile"]="Other jurisdiction"
    assert client.post("/api/project/home/preview",params=scope(changed.json()),json=data).status_code==422
