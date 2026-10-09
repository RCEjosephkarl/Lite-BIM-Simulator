"""Correlate failures without logging user plans or changing transaction results."""
import asyncio
import json
import logging
import re

import httpx
import pytest

import db
import diagnostics
import projects
import server
from test_projects import commit_wall, home, scope
from test_smoke import client, manual_wall_payload


def events(caplog):
    return [json.loads(record.message) for record in caplog.records if record.name == diagnostics.LOGGER.name]


def test_invalid_csv_with_http_200_has_a_correlated_validation_failure(caplog):
    private = 'PRIVATE_PLAN_LABEL'
    result = client.post('/api/import/csv-plan/validate', files={
        'file': ('PRIVATE_FILENAME.csv', f'type,level,label\nwall,1,{private}\n'.encode(), 'text/csv')},
        headers={'Authorization': 'PRIVATE_CREDENTIAL', 'X-Request-ID': 'UNTRUSTED_ID'})
    assert result.status_code == 200 and not result.json()['can_preview']
    event = events(caplog)[-1]
    assert event['event'] == 'validation_failed' and event['status_code'] == 200
    assert event['route'] == '/api/import/csv-plan/validate' and event['project_id'] == 'default'
    assert event['error_count'] == len(result.json()['errors']) > 0
    assert event['request_id'] == result.headers['X-Request-ID']
    assert re.fullmatch('[0-9a-f]{32}', event['request_id']) and event['duration_ms'] >= 0
    assert all(private not in caplog.text for private in ['PRIVATE_PLAN_LABEL', 'PRIVATE_FILENAME', 'PRIVATE_CREDENTIAL', 'UNTRUSTED_ID'])
    assert not db.DB_PATH.exists()


def test_stale_write_reports_expected_and_observed_revision_without_mutation(caplog):
    initial = home('PRIVATE_HOME_LABEL')
    updated, _ = commit_wall(initial)
    model = updated['model']; location = projects.path(db.DB_PATH, scope(model)['project_id'])
    before = location.read_bytes(); caplog.clear()
    result = client.post('/api/project/reset', params=scope(model), headers={'If-Match': '0'})
    assert result.status_code == 409 and location.read_bytes() == before
    event = events(caplog)[-1]
    assert event['project_id'] == scope(model)['project_id'] == event['observed_project_id']
    assert (event['expected_revision'], event['actual_revision']) == (0, 1)
    assert event['error_type'] == 'ProjectConflict' and event['request_id'] == result.headers['X-Request-ID']
    assert 'PRIVATE_HOME_LABEL' not in caplog.text


def test_early_rejections_log_route_patterns_without_dynamic_identifiers(caplog):
    identifier = 'a'*32
    result = client.delete('/api/import/batches/PRIVATE_BATCH_NAME', params={'project_id': identifier})
    assert result.status_code == 428
    event = events(caplog)[-1]
    assert event['route'] == '/api/import/batches/{batch_id:path}'
    assert event['project_id'] == identifier and 'PRIVATE_BATCH_NAME' not in caplog.text
    result = client.get('/api/PRIVATE_UNKNOWN_PATH', params={'project_id': 'PRIVATE_INVALID_ID'})
    assert result.status_code == 422
    assert events(caplog)[-1]['project_id'] == 'invalid'
    assert 'PRIVATE_UNKNOWN_PATH' not in caplog.text and 'PRIVATE_INVALID_ID' not in caplog.text


def test_unexpected_generation_failure_returns_reference_and_safe_stack(caplog, monkeypatch):
    def broken(*args, **kwargs):
        raise ZeroDivisionError('PRIVATE_PLAN_CONTENT')
    monkeypatch.setattr(server, 'generate_wall', broken)
    result = client.post('/api/manual/wall-frame/preview', json=manual_wall_payload())
    assert result.status_code == 500 and result.headers['X-Request-ID']
    assert 'PRIVATE_PLAN_CONTENT' not in result.text and 'PRIVATE_PLAN_CONTENT' not in caplog.text
    event = events(caplog)[-1]
    assert event['error_type'] == 'ZeroDivisionError' and event['route'] == '/api/manual/wall-frame/preview'
    assert event['frames'][-1]['file'] == 'test_diagnostics.py'
    assert event['frames'][-1]['function'] == 'broken' and event['frames'][-1]['line'] > 0
    assert not db.DB_PATH.exists()


def test_handled_error_keeps_user_feedback_but_omits_exception_text_from_logs(caplog, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError('PRIVATE_HELPFUL_ERROR')
    monkeypatch.setattr(server, 'generate_wall', broken)
    result = client.post('/api/manual/wall-frame/preview', json=manual_wall_payload())
    assert result.status_code == 422 and 'PRIVATE_HELPFUL_ERROR' in result.text
    assert 'PRIVATE_HELPFUL_ERROR' not in caplog.text and events(caplog)[-1]['error_type'] == 'ValueError'


def test_success_logging_is_opt_in_and_logging_failure_does_not_break_requests(caplog, monkeypatch):
    monkeypatch.delenv('TIMBERBIM_LOG_REQUESTS', raising=False)
    caplog.set_level(logging.INFO, logger=diagnostics.LOGGER.name)
    assert client.get('/api/projects').status_code == 200 and not events(caplog)
    monkeypatch.setenv('TIMBERBIM_LOG_REQUESTS', '1')
    result = client.get('/api/projects'); assert result.status_code == 200
    assert events(caplog)[-1]['event'] == 'request_completed'
    assert events(caplog)[-1]['request_id'] == result.headers['X-Request-ID']
    def broken(*args, **kwargs):
        raise RuntimeError('Log sink unavailable')
    monkeypatch.setattr(diagnostics.LOGGER, 'log', broken)
    assert client.get('/api/projects').status_code == 200
    assert diagnostics.context.get() is None and projects.project_id.get() == 'default'


def test_concurrent_failure_contexts_do_not_share_project_or_revision(caplog):
    first, second = home('One'), home('Two')
    first = commit_wall(first)[0]['model']
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as transport:
            return await asyncio.gather(transport.get('/api/bom.json', params={**scope(first), 'revision': 0}),
                                       transport.get('/api/bom.json', params={**scope(second), 'revision': 1}))
    caplog.clear(); results = asyncio.run(run())
    assert all(result.status_code == 409 for result in results)
    by_home = {event['project_id']: event for event in events(caplog)}
    assert (by_home[scope(first)['project_id']]['expected_revision'], by_home[scope(first)['project_id']]['actual_revision']) == (0, 1)
    assert (by_home[scope(second)['project_id']]['expected_revision'], by_home[scope(second)['project_id']]['actual_revision']) == (1, 0)
    assert len({event['request_id'] for event in by_home.values()}) == 2
    assert diagnostics.context.get() is None
