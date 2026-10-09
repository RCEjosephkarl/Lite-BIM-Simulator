"""Extreme input must fail before allocation/mutation, with reviewable errors."""
import json
import math

import pytest
from pydantic import ValidationError

import db
import framing
import home_definition as homes
import imports.csv_plan as csv_plan
import imports.validators as validators
import manual_inputs
from manual_inputs import ManualTrussInput, ManualWallFrameInput
from test_smoke import client
from test_validation import WALL, TRUSS


@pytest.mark.parametrize('row', [
    {**WALL,'start_x_mm':-1e308,'end_x_mm':1e308},
    {**WALL,'stud_size':str(int(1e308))+'x45','plies':3},
    {**TRUSS,'start_x_mm':1e308},
    {**TRUSS,'spacing_mm':1e308,'quantity':3},
    {**TRUSS,'truss_type':'girder','web_size':'90x'+str(int(1e308))},
])
def test_derived_overflow_agrees_across_review_preview_and_commit_without_mutation(row):
    result=validators.validate_rows([row])
    assert result['can_preview'] is False and result['errors'][0]['row']==2
    json.dumps(result,allow_nan=False)
    for route in ('review','preview','commit'):
        response=client.post('/api/import/csv-plan/'+route,json={'rows':[row]})
        assert response.status_code==(200 if route=='review' else 422),response.text
        if route=='review':assert response.json()['can_preview'] is False
        assert response.headers['X-Request-ID']
    assert not db.DB_PATH.exists()


@pytest.mark.parametrize('payload', [{'start_x_mm':1e308},{'spacing_mm':1e308,'quantity':3}])
def test_manual_truss_rejects_nonfinite_or_collapsed_placement_before_generation(payload):
    with pytest.raises(ValidationError):ManualTrussInput(**payload)
    for route in ('preview','commit'):
        assert client.post('/api/manual/truss/'+route,json=payload).status_code==422
    assert not db.DB_PATH.exists()


@pytest.mark.parametrize('value', [float('nan'),float('inf'),float('-inf')])
def test_nonstandard_json_numbers_return_finite_errors_even_in_unknown_cells(value):
    rows=[{**WALL,'start_x_mm':value},{**WALL,'segment_id':'OTHER','extra':{'nested':[value]}}]
    result=validators.validate_rows(rows);json.dumps(result,allow_nan=False)
    assert not result['can_preview'] and all(not row['valid'] for row in result['rows'])
    raw=json.dumps({'rows':rows})  # Deliberately exercise Python JSON's NaN/Infinity extensions.
    response=client.post('/api/import/csv-plan/review',content=raw,headers={'Content-Type':'application/json'})
    assert response.status_code==200,response.text
    assert response.json()['can_preview'] is False
    assert len(response.json()['errors'])>=2
    assert not db.DB_PATH.exists()


@pytest.mark.parametrize('value', [float('nan'),float('inf'),float('-inf')])
@pytest.mark.parametrize('route,field', [('truss/preview','span_mm'),
    ('truss/commit','span_mm'),('wall-frame/preview','end_x_mm')])
def test_manual_nonstandard_numbers_preserve_field_locations_in_json_errors(route,field,value):
    response=client.post('/api/manual/'+route,content=json.dumps({field:value}),
                         headers={'Content-Type':'application/json'})
    assert response.status_code==422,response.text
    errors=response.json()['detail'];json.dumps(errors,allow_nan=False)
    assert isinstance(errors,list) and any(error['loc']==['body',field] for error in errors)
    assert response.headers['X-Request-ID'] and not db.DB_PATH.exists()


@pytest.mark.parametrize('content,field', [(b'\xff','file'),(b'type,level\n','rows'),
    (b'type,label\nwall,'+b'x'*140000,'file')])
def test_csv_parser_failures_have_row_and_field_locations(content,field):
    result=csv_plan.parse_csv(content)
    assert not result['can_preview']
    assert result['errors'][0]['row']==1 and result['errors'][0]['field']==field
    json.dumps(result,allow_nan=False)


def test_csv_reader_stops_after_one_over_limit_and_accepts_the_exact_limit(monkeypatch):
    monkeypatch.setattr(csv_plan,'MAX_ROWS',3);monkeypatch.setattr(validators,'MAX_ROWS',3)
    consumed=[]
    def reader(_stream):
        for i in range(4):
            consumed.append(i);yield {**WALL,'segment_id':f'W{i}'}
        raise AssertionError('CSV reader consumed past its bounded look-ahead')
    monkeypatch.setattr(csv_plan.csv,'DictReader',reader)
    result=csv_plan.parse_csv(b'ignored by instrumented reader')
    assert len(consumed)==4 and not result['can_preview']
    assert result['errors'][0]['field']=='rows' and '3 rows' in result['errors'][0]['message']
    result=validators.validate_rows([{**WALL,'segment_id':f'W{i}'} for i in range(3)])
    assert result['can_preview'],result['errors']


def test_wall_and_combined_csv_member_bounds_fail_before_generation(monkeypatch):
    monkeypatch.setattr(manual_inputs,'MAX_MEMBERS',100)
    with pytest.raises(ValidationError,match='generation limit'):
        ManualWallFrameInput(nog_spacing_mm=.000001)
    one=validators.validate_rows([WALL]);assert one['can_preview']
    monkeypatch.setattr(validators,'MAX_MEMBERS',50)
    result=validators.validate_rows([WALL,{**WALL,'segment_id':'SECOND'}])
    assert not result['can_preview'] and result['errors'][-1]['field']=='rows'
    assert result['summary']['wall_count']==2


def test_large_split_and_porch_are_rejected_before_materializing_member_lists():
    with pytest.raises(ValueError,match='generation budget'):framing._split(0,1e100)
    with pytest.raises(ValidationError,match='generation budget'):
        homes.Porch(id='P',level_id='L',post_xs_mm=[0,1e100],front_y_mm=0,back_y_mm=3000,
                    minimum_x_mm=0,maximum_x_mm=1e100)
    with pytest.raises(ValidationError,match='remain finite'):
        homes.Support(id='S',start_mm=(-1e308,0),end_mm=(1e308,0))


def test_split_accepts_existing_budget_exactly_and_rejects_one_more_piece(monkeypatch):
    monkeypatch.setattr(framing,'MAX_MEMBERS',100)
    assert len(framing._split(0,100*framing.MAX_PIECE))==100
    with pytest.raises(ValueError,match='generation budget'):
        framing._split(0,100*framing.MAX_PIECE+1)


@pytest.mark.parametrize('shape',['gable','hip'])
def test_roof_spacing_that_cannot_advance_raises_instead_of_looping(shape):
    options=dict(units='mm')
    args=[[],(1e20,0,1e20+200000,6000,'x'),1,2535,900]
    if shape=='gable':args.append(600)
    with pytest.raises(ValueError,match='cannot advance'):
        getattr(framing,'frame_'+shape+'_roof')(*args,**options)


def test_porch_spacing_that_cannot_advance_raises_instead_of_looping():
    porch=homes.Porch(id='P',level_id='L',post_xs_mm=[1e20,1e20+200000],
        front_y_mm=0,back_y_mm=3000,minimum_x_mm=1e20,maximum_x_mm=1e20+200000)
    with pytest.raises(ValueError,match='cannot advance'):
        homes.generate(homes.HomeDefinition(levels=[{'id':'L','number':1}],porches=[porch]),framing.ModelConfig())


@pytest.mark.parametrize('coordinate', [1e12,-1e12])
def test_floor_area_and_rotated_generation_are_translation_invariant(coordinate):
    def definition(offset):
        return homes.HomeDefinition(levels=[{'id':'L','number':1}],floors=[{
            'id':'F','level_id':'L','boundary_mm':[(offset,offset),(offset+9000,offset),
              (offset+9000,offset+6000),(offset,offset+6000)],'joist_direction_deg':30,
            'holes_mm':[[(offset+3000,offset+1500),(offset+4500,offset+1500),
              (offset+4500,offset+3000),(offset+3000,offset+3000)]],
            'supports':[{'id':'S','start_mm':(offset+4500,offset),'end_mm':(offset+4500,offset+6000)}]}])
    expected=homes.generate(definition(0),framing.ModelConfig()).elements
    actual=homes.generate(definition(coordinate),framing.ModelConfig()).elements
    assert len(actual)==len(expected)>0
    for before,after in zip(expected,actual):
        assert after['type_code']==before['type_code']
        for key in ('length_mm','w_mm','h_mm','cz','yaw','pitch'):assert after[key]==before[key]
        for key in ('cx','cy'):assert after[key]-coordinate==pytest.approx(before[key],abs=.11)
        assert all(math.isfinite(after[key]) for key in ('length_mm','cx','cy','cz'))


def test_api_body_limit_counts_streamed_chunks_and_preserves_the_project():
    limit=16*1024*1024
    assert client.post('/api/project/initialize').status_code==200
    before=db.DB_PATH.read_bytes()
    async def stream(overflow):
        yield b' '*(limit//2);yield b' '*(limit-limit//2)
        if overflow:yield b'x'
    for overflow,expected in ((False,404),(True,413)):
        response=client.post('/api/unknown-resource-test',content=stream(overflow))
        assert response.status_code==expected,response.text
        assert response.headers['X-Request-ID']
    assert db.DB_PATH.read_bytes()==before


def test_csv_upload_limit_rejects_one_extra_byte_before_parser(monkeypatch):
    parsed=[]
    def parser(content, units):
        parsed.append((len(content),units))
        return validators.validate_rows([WALL],units)
    monkeypatch.setattr(__import__('server'),'parse_csv',parser)
    limit=8*1024*1024
    exact=client.post('/api/import/csv-plan/validate',files={'file':('large.csv',b'x'*limit,'text/csv')})
    assert exact.status_code==200 and exact.json()['can_preview']
    assert parsed==[(limit,'mm')]
    response=client.post('/api/import/csv-plan/validate',files={'file':('large.csv',b'x'*(limit+1),'text/csv')})
    assert response.status_code==413 and '8 MiB' in response.text and response.headers['X-Request-ID']
    assert parsed==[(limit,'mm')], 'oversized upload must not reach CSV parsing'
    assert not db.DB_PATH.exists()
