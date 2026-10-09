"""Topology, physical endpoints, instance identities and distinct templates."""
import math
from collections import defaultdict
from contextlib import closing

import pytest
from pydantic import ValidationError

import db
from manual_inputs import ManualTrussInput, generate_truss
from trusses import canonical_graph
from test_projects import headers, home, scope
from test_smoke import client


@pytest.mark.parametrize("kind", ["common", "girder", "mono", "scissor", "attic"])
@pytest.mark.parametrize("heel,overhang", [(0,0), (100,450)])
def test_templates_have_connected_webs_roles_and_distinct_instances(kind, heel, overhang):
    spec = ManualTrussInput(truss_type=kind, heel_height_mm=heel, overhang_mm=overhang,
                            quantity=2, truss_id="T", start_x_mm=20000, start_z_mm=-10000, direction_deg=37)
    nodes, graph = canonical_graph(spec)
    members, _ = generate_truss(spec, source_id="layout")
    assert len(members) == len(graph) * 2
    instances = defaultdict(list)
    for member in members:
        instances[member["truss_id"]].append(member)
        assert member["layout_id"] == "T"
        assert member["engineering_status"] == "unchecked"
    assert set(instances) == {"T-001", "T-002"}
    for instance, group in enumerate(instances.values()):
        assert {member["member_role"] for member in group} >= {"top_chord", "bottom_chord", "web"}
        if kind == "girder":
            assert all(member["plies"] == 3 for member in group)
            assert {m["type_code"] for m in group} >= {"truss_top_chord", "truss_bottom_chord", "truss_web"}
        angle = math.radians(spec.direction_deg)
        for member in group:
            half = member["length_mm"] / 2
            vector = (math.cos(member["yaw"])*math.cos(member["pitch"]),
                      math.sin(member["yaw"])*math.cos(member["pitch"]), math.sin(member["pitch"]))
            for sign, identifier in [(-1, member["start_node"]), (1, member["end_node"])]:
                ax, az = nodes[identifier]
                expected = (spec.start_x_mm-math.sin(angle)*instance*spec.spacing_mm+math.cos(angle)*ax,
                            spec.start_z_mm+math.cos(angle)*instance*spec.spacing_mm+math.sin(angle)*ax,
                            2535+az)
                actual = tuple(member[key]+sign*half*component for key, component in zip(("cx","cy","cz"), vector))
                assert actual == pytest.approx(expected, abs=.0001)


def test_common_post_is_vertical_attic_has_a_room_and_scissor_chords_differ():
    common = ManualTrussInput()
    nodes, graph = canonical_graph(common)
    post = next(member for member in graph if member[2] == "king_post")
    assert nodes[post[0]][0] == nodes[post[1]][0] == 0
    attic_nodes, attic = canonical_graph(ManualTrussInput(truss_type="attic"))
    assert attic != graph
    assert attic_nodes["UL"][1] > 0
    for start, end, role, *_ in attic:
        if role != "bottom_chord":
            midpoint = ((attic_nodes[start][0]+attic_nodes[end][0])/2,
                        (attic_nodes[start][1]+attic_nodes[end][1])/2)
            assert not (attic_nodes["FL"][0] < midpoint[0] < attic_nodes["FR"][0]
                        and 0 < midpoint[1] < attic_nodes["UL"][1])
    scissor_nodes, scissor = canonical_graph(ManualTrussInput(truss_type="scissor"))
    assert scissor_nodes["BC"][1] > nodes["BC"][1]
    assert {tuple(sorted(m[:2])) for m in scissor if m[2] == "top_chord"}.isdisjoint(
        {tuple(sorted(m[:2])) for m in scissor if m[2] == "bottom_chord"})


def custom():
    return {"truss_type": "custom", "nodes": [{"id":"L","x":-4500,"y":0}, {"id":"A","x":0,"y":2100},
             {"id":"R","x":4500,"y":0}, {"id":"B","x":0,"y":0}],
            "members": [{"start_node":start,"end_node":end,"element_type":role}
                        for start,end,role in [("L","A","top_chord"),("A","R","top_chord"),
                                               ("L","R","bottom_chord"),("B","A","king_post")]]}


def test_custom_bottom_chord_is_split_at_the_web_attachment():
    nodes, members = canonical_graph(ManualTrussInput(**custom()))
    assert {(m[0],m[1]) for m in members if m[2] == "bottom_chord"} == {("L","B"),("B","R")}


@pytest.mark.parametrize("case", ["no_webs", "unused", "duplicate_position", "duplicate_member", "unknown_role"])
def test_invalid_topology_is_rejected_before_generation(case):
    payload = custom()
    if case == "no_webs":
        payload["members"] = payload["members"][:-1]
        payload["nodes"] = payload["nodes"][:-1]
    elif case == "unused": payload["nodes"].append({"id":"UNUSED","x":200,"y":500})
    elif case == "duplicate_position": payload["nodes"].append({"id":"DUP","x":0,"y":2100})
    elif case == "duplicate_member": payload["members"].append(dict(payload["members"][0]))
    else: payload["members"][0]["element_type"] = "unknown"
    with pytest.raises(ValidationError): ManualTrussInput(**payload)
    response = client.post("/api/manual/truss/preview", json=payload)
    assert response.status_code == 422
    assert not db.DB_PATH.exists()


def test_crossing_without_a_shared_node_is_rejected():
    payload = custom()
    payload["nodes"] += [{"id":"X","x":-2000,"y":1000}, {"id":"Y","x":2000,"y":1000}]
    payload["members"] += [{"start_node":"L","end_node":"X","element_type":"web"},
                           {"start_node":"X","end_node":"Y","element_type":"web"},
                           {"start_node":"Y","end_node":"R","element_type":"web"}]
    with pytest.raises(ValidationError, match="crossing"):
        ManualTrussInput(**payload)


def test_commit_persists_instance_graph_metadata_and_bearing_elevation():
    model = home()
    payload = {"truss_type":"common", "truss_id":"Roof", "quantity":2, "heel_height_mm":100}
    proof = client.post("/api/manual/truss/preview", params=scope(model), json=payload).json()
    result = client.post("/api/manual/truss/commit", params=scope(model), json=payload, headers=headers(model, proof, "trusses"))
    assert result.status_code == 200, result.text
    elements = result.json()["model"]["elements"]
    assert {member["instance_id"] for member in elements} == {result.json()["source_id"]+":001", result.json()["source_id"]+":002"}
    assert all(member["start_node"] and member["end_node"] for member in elements)
    bottom = [member for member in elements if member["member_role"] == "bottom_chord"]
    assert all(member["cz"] == 2535 for member in bottom)
