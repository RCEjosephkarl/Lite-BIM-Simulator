"""Saved BOM navigation must preserve physical cuts and scoped identities."""
from contextlib import closing
import sqlite3

import pytest

import db
import estimating
import projects
from test_estimating import commit_truss
from test_projects import commit_wall, home, scope
from test_smoke import client, manual_wall_payload
from test_trusses import custom


def selected(model, anchor):
    response = client.get('/api/bom.json', params={**scope(model), 'member_id': anchor})
    assert response.status_code == 200, response.text
    return response.json()


def test_navigation_metadata_preserves_whole_home_bom_and_csv_read_only():
    model = client.post('/api/project/initialize').json()
    before = db.DB_PATH.read_bytes()
    expected = db.bom_rows()
    csv_before = db.bom_csv()
    result = client.get('/api/bom.json').json()
    assert result['scope'] is None
    assert [{k: v for k, v in row.items() if k not in
             {'member_ids', 'effective_length_m', 'estimated_cost_usd'}} for row in result['rows']] == expected
    ids = [member_id for row in result['rows'] for member_id in row['member_ids']]
    timber = {e['id'] for e in model['elements'] if e['material'] != 'concrete'}
    assert len(ids) == len(set(ids)) == len(timber) and set(ids) == timber
    assert db.bom_csv() == csv_before and 'member_ids' not in csv_before.splitlines()[0]
    assert db.DB_PATH.read_bytes() == before


@pytest.mark.parametrize('payload', [
    {**custom(), 'quantity': 3},
    {'truss_type': 'girder', 'quantity': 3, 'bottom_chord_size': '2/90x45'},
])
def test_selected_instance_counts_full_chords_once_and_excludes_other_instances(payload):
    model, _ = commit_truss(home(), payload)
    anchor = next(e for e in model['elements'] if e['member_role'] == 'bottom_chord')
    result = selected(model, anchor['id'])
    members = [e for e in model['elements'] if e['truss_id'] == anchor['truss_id']]
    ids = {i for row in result['rows'] for i in row['member_ids']}
    assert ids == {e['id'] for e in members}
    assert result['scope']['kind'] == 'truss' and result['scope']['assembly_id'] == anchor['truss_id']
    cuts = estimating.cutting_pieces(members)
    assert sum(r['qty'] for r in result['rows']) == len(cuts)
    assert sum(r['physical_qty'] for r in result['rows']) == sum(e['board_multiplier'] for e in cuts)
    bottom = next(r for r in result['rows'] if r['element'] == 'Truss bottom chord')
    assert bottom['qty'] == 1
    assert bottom['physical_qty'] == (6 if payload.get('truss_type') == 'girder' else 1)
    assert bottom['stock_length_m'] == 9
    assert len(bottom['member_ids']) == 2  # One connected chord, two placed segments.


def test_equal_wall_ids_and_source_ids_in_different_namespaces_do_not_mix():
    first, _ = commit_wall(home('Collision', 'sample'), manual_wall_payload())
    model = first['model']
    anchor = next(e for e in model['elements'] if e['source'] == 'manual_wall')
    location = projects.path(db.DB_PATH, scope(model)['project_id'])
    with closing(sqlite3.connect(location)) as con, con:
        con.execute("UPDATE elements SET source_id=?, segment_id=?, segment_label='Same label' "
                    "WHERE source='generated' AND segment_id<>''", (anchor['source_id'], anchor['segment_id']))
    result = selected(model, anchor['id'])
    ids = {i for row in result['rows'] for i in row['member_ids']}
    assert ids == {e['id'] for e in model['elements'] if e['source'] == 'manual_wall'}
    assert result['scope']['source'] == 'manual_wall'
    assert result['scope']['source_id'] == anchor['source_id']


def test_selection_is_revision_checked_and_never_initializes_or_mutates():
    assert client.get('/api/bom.json?member_id=1').status_code == 404
    assert not db.DB_PATH.exists()
    first, _ = commit_wall(home())
    model = first['model']; anchor = model['elements'][0]['id']
    location = projects.path(db.DB_PATH, scope(model)['project_id'])
    before = location.read_bytes()
    assert client.get('/api/bom.json', params={**scope(model), 'member_id': anchor,
                      'revision': model['meta']['project']['revision']-1}).status_code == 409
    for bad, code in [('NaN', 422), ('0', 422), ('-1', 422), ('9'*40, 422), ('9999999', 404)]:
        assert client.get('/api/bom.json', params={**scope(model), 'member_id': bad}).status_code == code
    assert location.read_bytes() == before


def test_concrete_is_excluded_and_empty_homes_have_no_navigation_rows():
    model = home('Empty')
    assert client.get('/api/bom.json', params=scope(model)).json()['rows'] == []
    model = home('Concrete', 'sample')
    anchor = next(e['id'] for e in model['elements'] if e['material'] == 'concrete')
    assert client.get('/api/bom.json', params={**scope(model), 'member_id': anchor}).status_code == 422
