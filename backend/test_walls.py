"""Shared framing must fit panels and leave every rotated opening void clear."""
import csv
import math
from pathlib import Path

import pytest

import framing
from imports.csv_plan import parse_csv
from manual_inputs import ManualOpening, ManualWallFrameInput, generate_wall
from test_projects import headers, home, scope
from test_smoke import client
from walls import panel_layout
from imports.validators import number


def wall(angle=0, plies=1, length=9000):
    angle = math.radians(angle)
    return ManualWallFrameInput(segment_id="Logical-wall", start_x_mm=12000, start_z_mm=-3000,
        end_x_mm=12000+length*math.cos(angle), end_z_mm=-3000+length*math.sin(angle),
        panelize=True, plies=plies, exterior=False, load_bearing=False,
        openings=[ManualOpening(opening_id="Door", opening_type="door", start_offset_mm=1200,
                                width_mm=900,height_mm=2100,sill_height_mm=0),
                  ManualOpening(opening_id="Window",start_offset_mm=4200,width_mm=1800,
                                height_mm=1200,sill_height_mm=900)])


@pytest.mark.parametrize("angle", [0,37,90])
@pytest.mark.parametrize("plies", [1,3])
def test_all_members_avoid_opening_voids_in_rotated_panelized_walls(angle, plies):
    spec = wall(angle, plies)
    members,_ = generate_wall(spec,source_id="wall")
    direction = (math.cos(math.radians(angle)),math.sin(math.radians(angle)))
    panels = panel_layout(spec,45)
    for member in members:
        center = (member["cx"]-spec.start_x_mm)*direction[0]+(member["cy"]-spec.start_z_mm)*direction[1]
        vertical = member["pitch"] > math.pi/4
        half_x = member["h_mm"]/2 if vertical else member["length_mm"]/2
        half_z = member["length_mm"]/2 if vertical else member["h_mm"]/2
        left,right = center-half_x,center+half_x
        bottom,top = member["cz"]-half_z,member["cz"]+half_z
        assert left >= -.001 and right <= 9000.001
        panel = panels[int(member["panel_id"].split('P')[-1])-1]
        assert left >= panel[0]-.001 and right <= panel[1]+.001
        for opening in spec.openings:
            crosses_x = min(right,opening.start_offset_mm+opening.width_mm)-max(left,opening.start_offset_mm) > .001
            crosses_z = min(top,opening.sill_height_mm+opening.height_mm)-max(bottom,opening.sill_height_mm) > .001
            assert not (crosses_x and crosses_z), (member,opening)
    assert len({member["physical_member_id"] for member in members}) == len(members)
    assert all(member["exterior"] is False and member["load_bearing"] is False for member in members)


def test_panel_joint_has_two_adjacent_distinct_end_studs_not_duplicate_boxes():
    spec = wall()
    members,_ = generate_wall(spec)
    joints = [member for member in members if member["joint_id"]]
    assert len(joints) == 2
    assert joints[0]["joint_id"] == joints[1]["joint_id"]
    assert joints[0]["physical_member_id"] != joints[1]["physical_member_id"]
    assert math.dist((joints[0]["cx"],joints[0]["cy"]),(joints[1]["cx"],joints[1]["cy"])) == pytest.approx(45)


def test_parallel_wall_plies_increase_volume_and_boards_without_consuming_opening_width():
    one,_ = generate_wall(wall(plies=1),source_id="wall")
    three,_ = generate_wall(wall(plies=3),source_id="wall")
    assert len(one) == len(three)
    for first,second in zip(one,three):
        assert second["cx"] == first["cx"] and second["cy"] == first["cy"]
        assert second["h_mm"] == first["h_mm"]
        assert second["w_mm"] == 3*first["w_mm"]
        assert second["plies"] == 3


def test_tall_wall_uses_interchangeable_three_metre_panels_and_warns():
    spec = ManualWallFrameInput(end_x_mm=7000,wall_height_mm=5500,panelize=True)
    members,warnings = generate_wall(spec)
    assert len(panel_layout(spec,45)) == 3
    assert all(right-left <= 3000 for left,right in panel_layout(spec,45))
    assert any("tall-wall" in warning for warning in warnings)
    assert all(member["engineering_status"] == "unchecked" for member in members)


def test_generated_and_manual_walls_use_the_same_members_and_rules():
    import geometry
    opening = geometry.Opening(1200,1200,900,2100,"window")
    source = geometry.Wall(0,0,3600,0,True,[opening])
    generated = []
    framing.frame_wall(generated,source,1,600,0,segment_id="Same",segment_label="Same")
    manual,_ = generate_wall(ManualWallFrameInput(segment_id="Same",segment_label="Same",end_x_mm=3600,panelize=True,
        openings=[ManualOpening(opening_id="Same:O001",start_offset_mm=1200,width_mm=1200,height_mm=1200)]),
        source="generated",source_id="Same")
    assert generated == manual


def test_bundled_long_wall_csv_validates_previews_and_commits_to_another_home():
    root = Path(__file__).parent.parent
    content = (root/'examples/walls_openings_trusses.csv').read_bytes()
    validation = parse_csv(content)
    assert validation["can_preview"],validation["errors"]
    model = home("Original", "sample")
    payload = {"rows":validation["rows"],"units":"mm","file_name":"walls_openings_trusses.csv"}
    preview = client.post('/api/import/csv-plan/preview',params=scope(model),json=payload)
    assert preview.status_code == 200,preview.text
    response = client.post('/api/import/csv-plan/commit',params=scope(model),json={**payload,"mode":"new_project_from_csv"},
                           headers=headers(model,preview.json(),"long-wall-home"))
    assert response.status_code == 200,response.text
    imported = response.json()['model']
    assert len(imported['elements']) == len(preview.json()['elements'])
    assert len(imported['meta']['frame_segments']) == 2
    assert all(segment['panel_count'] == 2 for segment in imported['meta']['frame_segments'])
    assert len({member['truss_id'] for member in imported['elements'] if member['truss_id']}) == 8
    assert client.get('/api/model',params=scope(model)).json() == model


@pytest.mark.parametrize("filename,units", [("plan_mm.csv","mm"),("plan_metres.csv","metres"),("plan_feet_inches.csv","feet_inches")])
def test_unit_examples_validate_preview_and_commit(filename, units):
    root = Path(__file__).parent.parent
    validation = parse_csv((root/'examples'/filename).read_bytes(),units)
    assert validation['can_preview'],validation['errors']
    model = home(filename)
    payload = {"rows":validation['normalized_entities'],"units":"mm"}
    preview = client.post('/api/import/csv-plan/preview',params=scope(model),json=payload)
    assert preview.status_code == 200,preview.text
    commit = client.post('/api/import/csv-plan/commit',params=scope(model),json={**payload,"mode":"replace_sample_geometry"},
                         headers=headers(model,preview.json(),filename))
    assert commit.status_code == 200,commit.text
    assert len(commit.json()['model']['elements']) == len(preview.json()['elements'])
    if units == 'feet_inches':
        assert validation['rows'][0]['start_x_mm'] == -762


def test_negative_feet_inches_sign_applies_to_the_whole_measurement():
    assert number("-2' 6\"",'feet_inches') == -762
    assert number("-0' 6\"",'feet_inches') == pytest.approx(-152.4)
    assert number('-6″','feet_inches') == pytest.approx(-152.4)
    with pytest.raises(ValueError,match='finite'): number(1e308,'metres')
