"""Check saw-cut identity, physical quantities, stock costs and price evidence."""
import csv
import io
from collections import defaultdict
from contextlib import closing

import pytest

import db
import estimating
import materials
import migrations
from framing import ModelConfig
from manual_inputs import ManualTrussInput, generate_truss
from test_projects import commit_wall, headers, home, scope
from test_smoke import client, manual_wall_payload
from test_trusses import custom


def commit_truss(model, payload):
    preview = client.post('/api/manual/truss/preview', params=scope(model), json=payload)
    assert preview.status_code == 200, preview.text
    result = client.post('/api/manual/truss/commit', params=scope(model), json=payload,
                         headers=headers(model, preview.json(), 'physical-truss'))
    assert result.status_code == 200, result.text
    return result.json()['model'], preview.json()


def test_continuous_custom_chord_has_one_nine_metre_cut_per_instance():
    model, preview = commit_truss(home(), {**custom(), 'quantity': 2})
    elements = model['elements']
    bottom = [e for e in elements if e['member_role'] == 'bottom_chord']
    assert len(bottom) == 4  # Four connected graph boxes, two saw cuts.
    assert len({e['physical_member_id'] for e in bottom}) == 2
    assert all(e['cut_length_mm'] == 9000 for e in bottom)
    assert len({e['physical_member_id'] for e in elements}) == 8
    summary = preview['metadata']
    assert summary['member_count'] == 10
    assert summary['cut_quantity'] == summary['physical_board_quantity'] == 8
    rows = client.get('/api/bom.json', params=scope(model)).json()['rows']
    row = next(r for r in rows if r['element'] == 'Truss bottom chord')
    assert row['qty'] == row['physical_qty'] == 2
    assert row['stock_length_m'] == 9
    assert row['stock_board_m'] == row['cut_board_m'] == 18
    assert 'special order' in row['notes']
    assert summary['estimated_stock_cost_usd'] > summary['estimated_cost_usd']
    assert model['meta']['cost_summary']['special_order_board_quantity'] == 2
    definition = client.get('/api/project/definitions', params=scope(model)).json()['definitions'][0]['payload']
    assert definition['topology']['schema_version'] == 2
    assert len(definition['topology']['physical_cuts']) == 4
    assert client.get('/api/model', params=scope(model)).json()['elements'] == elements


@pytest.mark.parametrize('kind,top_cuts,bottom_cuts', [
    ('common', 2, 1), ('girder', 2, 1), ('mono', 1, 1), ('scissor', 2, 2), ('attic', 2, 1),
])
def test_template_chord_connections_do_not_prescribe_extra_cuts(kind, top_cuts, bottom_cuts):
    spec = ManualTrussInput(truss_type=kind, heel_height_mm=100, overhang_mm=450)
    members, _ = generate_truss(spec, source_id='cut-check')
    cuts = estimating.cutting_pieces(members)
    assert sum(m['member_role'] == 'top_chord' for m in cuts) == top_cuts
    assert sum(m['member_role'] == 'bottom_chord' for m in cuts) == bottom_cuts
    groups = defaultdict(list)
    for member in members:
        groups[member['physical_member_id']].append(member)
    for group in groups.values():
        assert sum(e['length_mm'] for e in group) == pytest.approx(group[0]['cut_length_mm'])


def test_assembly_and_section_plies_multiply_independently_and_reconcile():
    payload = {'truss_type': 'girder', 'quantity': 2, 'heel_height_mm': 0, 'overhang_mm': 0,
               'bottom_chord_size': '2/90x45'}
    model, preview = commit_truss(home(), payload)
    rows = client.get('/api/bom.json', params=scope(model)).json()['rows']
    bottom = next(r for r in rows if r['element'] == 'Truss bottom chord')
    assert (bottom['qty'], bottom['plies'], bottom['section_plies'], bottom['physical_qty']) == (2, 3, 2, 12)
    assert bottom['size'] == '6/90x45' and bottom['section_size'] == '2/90x45'
    assert bottom['cut_board_m'] == 12*9
    assert all(e['w_mm'] == 270 for e in model['elements'] if e['member_role'] == 'bottom_chord')
    stock_cost = sum(r['stock_length_m']*r['qty']*r['plies']*r['unit_price_usd_per_lm'] for r in rows)
    cut_cost = sum(e['length_mm']*e['plies']*e['unit_price_usd_per_lm']/1000 for e in model['elements'])
    summary = model['meta']['cost_summary']
    assert summary['grand_total_usd'] == pytest.approx(cut_cost, abs=.05)
    assert summary['stock_total_usd'] == pytest.approx(stock_cost, abs=.05)
    assert summary['coverage']['physical_board_quantity'] == sum(r['physical_qty'] for r in rows)
    assert preview['metadata']['estimated_cost_usd'] == pytest.approx(summary['grand_total_usd'], abs=.05)
    assert preview['metadata']['estimated_stock_cost_usd'] == pytest.approx(summary['stock_total_usd'], abs=.05)
    exported = list(csv.DictReader(io.StringIO(client.get('/api/bom.csv', params=scope(model)).text)))
    assert sum(int(r['physical_qty']) for r in exported) == summary['coverage']['physical_board_quantity']
    assert sum(float(r['stock_cost_usd']) for r in exported) == summary['stock_total_usd']


def test_unpriced_rows_and_export_are_missing_values_not_zero_costs():
    accepted, preview = commit_wall(home(), {**manual_wall_payload(), 'stud_material': 'SG10', 'stud_size': '240x90', 'plies': 2})
    model = accepted['model']
    rows = client.get('/api/bom.json', params=scope(model)).json()['rows']
    missing = [r for r in rows if not r['estimate_complete']]
    assert missing and all(r['total_cost_usd'] is r['stock_cost_usd'] is None for r in missing)
    coverage = model['meta']['cost_summary']['coverage']
    assert coverage['unpriced_cut_quantity'] == sum(r['qty'] for r in missing)
    assert coverage['unpriced_board_quantity'] == sum(r['physical_qty'] for r in missing)
    assert preview['metadata']['estimate_complete'] is False
    exported = list(csv.DictReader(io.StringIO(client.get('/api/bom.csv', params=scope(model)).text)))
    assert all(r['total_cost_usd'] == r['stock_cost_usd'] == '' for r in exported if r['estimate_complete'] == '0')
    assert model['meta']['cost_summary']['grand_total_usd'] == pytest.approx(sum(r['total_cost_usd'] or 0 for r in rows), abs=.01)


def test_price_scope_and_currency_evidence_survive_override_and_undo():
    accepted, _ = commit_wall(home(), {**manual_wall_payload(), 'treatment': 'H3.2'})
    model = accepted['model']
    assert all(e['price_confidence'] == 'low' for e in model['elements'])
    assert all('treatment H3.2' in e['pricing_notes'] for e in model['elements'])
    assert all(e['price_source_currency'] == 'NZD' and e['price_currency'] == 'USD' for e in model['elements'])
    assert all(e['price_fx_rate'] == materials.FX_RATE_NZD_USD and e['price_fx_date'] == materials.FX_DATE for e in model['elements'])
    assert materials.unit_price_usd_per_lm('hyspan', '90x45', 'H1.2')[1] == 'low'
    response = client.post('/api/pricing/overrides', params=scope(model), json={'overrides': {'sg8': 0}}, headers=headers(model, key='zero-price'))
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed['meta']['cost_summary']['estimate_complete'] is True
    assert changed['meta']['cost_summary']['grand_total_usd'] == changed['meta']['cost_summary']['stock_total_usd'] == 0
    assert all(e['price_confidence'] == 'user' and e['price_source_currency'] == 'USD' and e['price_fx_rate'] == 1 for e in changed['elements'])
    assert all(e['price_source_date'] and 'all sections/treatments' in e['pricing_notes'] for e in changed['elements'])
    proof = client.post('/api/manual/wall-frame/preview', params=scope(changed), json=manual_wall_payload()).json()
    assert proof['elements'][0]['price_source_date'] == changed['elements'][0]['price_source_date']
    assert proof['metadata']['estimated_cost_usd'] == 0
    restored = client.post(f"/api/project/revisions/{model['meta']['project']['revision']}/restore", params=scope(changed), json={}, headers=headers(changed, key='undo-price'))
    assert restored.status_code == 200, restored.text
    assert restored.json()['elements'] == model['elements']


def test_schema_four_upgrade_preserves_rows_and_flags_unknown_legacy_cuts():
    db.rebuild(ModelConfig())
    members, _ = generate_truss(ManualTrussInput(**custom(), quantity=2), source_id='old-trusses')
    db.append_elements(members, 'manual_truss', 'old-trusses')
    added = {'cut_length_mm', 'price_source_date', 'price_currency', 'price_source_currency',
             'price_fx_rate', 'price_fx_date', 'price_fx_source', 'pricing_notes'}
    with closing(db.connect()) as con, con:
        con.execute('DROP VIEW bom')
        con.execute('DROP VIEW cutting_pieces')
        con.execute("UPDATE elements SET physical_member_id='' WHERE source='manual_truss'")
        for field in added:
            con.execute(f'ALTER TABLE elements DROP COLUMN {field}')
        con.execute('PRAGMA user_version=4')
        old = [dict(r) for r in con.execute('SELECT * FROM elements ORDER BY id')]
    db.ensure_schema()
    assert list(db.DB_PATH.parent.glob('test.db.backup-v4-*'))
    with closing(db.connect()) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 5
        after = [dict(r) for r in con.execute('SELECT * FROM elements ORDER BY id')]
    assert [{k: v for k, v in row.items() if k not in added} for row in after] == old
    assert all(row['price_source_date'] == row['price_source_currency'] == '' and row['price_fx_rate'] is None for row in after)
    rows = [r for r in db.bom_rows() if r['element'] == 'Truss bottom chord']
    assert rows and all(r['cut_identity_status'] == 'legacy_unknown' for r in rows)
    assert sum(r['qty'] for r in rows) == 4
    summary = db.cost_summary()
    assert summary['stock_identity_complete'] is False
    assert summary['coverage']['unknown_cut_identity_quantity'] == 10


def test_disagreement_between_graph_segments_and_cut_definition_is_rejected():
    members, _ = generate_truss(ManualTrussInput(**custom()), source_id='broken-cut')
    members[0]['cut_length_mm'] += 100
    with pytest.raises(ValueError, match='physical cut length'):
        estimating.cutting_pieces(members)
    assert not db.DB_PATH.exists()


def test_derived_price_overflow_rolls_back_the_whole_revision():
    accepted, _ = commit_wall(home())
    model = accepted['model']
    response = client.post('/api/pricing/overrides', params=scope(model),
                           json={'overrides': {'sg8': 1e308}}, headers=headers(model, key='overflow-price'))
    assert response.status_code == 422, response.text
    assert client.get('/api/model', params=scope(model)).json() == model
