"""Profiling must reproduce a portable fixture without changing the open home."""
import json

import benchmark
import db
import home_archive
from framing import ModelConfig
from manual_inputs import ManualTrussInput


def test_profile_isolated_persistence_and_portable_inputs(tmp_path, monkeypatch):
    db.rebuild(ModelConfig())
    original_path=db.DB_PATH; before=original_path.read_bytes()
    _, cfg, definition, _=next(benchmark.fixtures())
    monkeypatch.setattr(benchmark, 'fixtures', lambda: iter([('portable', cfg, definition,
                       ManualTrussInput(quantity=3, truss_type='common'))]))
    report=benchmark.run(1, tmp_path/'archives', profile_reads=True)
    assert db.DB_PATH == original_path and original_path.read_bytes() == before
    fixture=report['fixtures'][0]
    archive=home_archive.HomeArchive.model_validate_json((tmp_path/'archives'/'portable.json').read_text())
    generated, _, _=home_archive.generate(archive)
    assert fixture['member_count'] == fixture['generation_member_count'] == len(generated.elements)
    assert fixture['json_bytes']>0 and fixture['bom_rows']>0 and fixture['generation_python_alloc_peak_bytes']>0
    for field in ('generation_ms','fresh_database_pipeline_ms','model_read_review_estimate_ms','json_serialization_ms','bom_navigation_query_ms'):
        assert fixture[field]['samples'] == 1 and fixture[field]['median'] >= 0
    assert len(report['source_fingerprint']) == 64
    profile=fixture['model_read_cprofile']
    assert profile['total_calls']>=profile['primitive_calls']>0 and profile['total_profiled_seconds']>=0
    assert any(function['file']=='backend/review.py' and function['function']=='evaluate'
               for function in profile['top_cumulative_functions'])
    assert all(not function['file'].startswith('/') for function in profile['top_cumulative_functions'])
    json.dumps(report, allow_nan=False)
