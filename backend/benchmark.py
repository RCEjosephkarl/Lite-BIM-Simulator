"""Repeatable local measurements; all persistence lives in a temporary directory."""
from __future__ import annotations

import argparse
import cProfile
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import pstats
try:
    import resource
except ImportError:
    resource = None
import statistics
import tempfile
import time
import tracemalloc

import db
import home_definition
import projects
from framing import ModelConfig
from manual_inputs import ManualTrussInput, generate_truss

ROOT = Path(__file__).resolve().parent.parent


def summary(values):
    ordered = sorted(values)
    return {"samples": len(values), "minimum": ordered[0], "median": statistics.median(ordered),
            "p95": ordered[math.ceil(len(ordered)*.95)-1], "maximum": ordered[-1]}


def measure(operation, repeats):
    values = []
    for _ in range(repeats):
        started = time.perf_counter(); result = operation()
        values.append(round((time.perf_counter()-started)*1000, 3))
    return result, summary(values)


def source_fingerprint():
    paths = list((ROOT/'backend').glob('*.py')) + list((ROOT/'backend'/'imports').glob('*.py'))
    paths += list((ROOT/'frontend'/'src').glob('*')) + list((ROOT/'examples'/'homes').glob('*.json'))
    paths += [ROOT/'VERSION', ROOT/'backend'/'schema.sql', ROOT/'backend'/'requirements.lock.txt', ROOT/'frontend'/'package-lock.json']
    paths += list((ROOT/'frontend'/'tests').glob('*.mjs')) + list((ROOT/'scripts').glob('*.py'))
    digest = hashlib.sha256()
    for path in sorted(path for path in paths if path.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode()); digest.update(b'\0'); digest.update(path.read_bytes()); digest.update(b'\0')
    return digest.hexdigest()


def fixtures():
    for name in ('rectangle', 'l_shape', 'two_level'):
        definition = home_definition.HomeDefinition.model_validate_json((ROOT/'examples'/'homes'/f'{name}.json').read_text())
        yield name, ModelConfig(), definition, None
    yield 'sample_3_storeys', ModelConfig(storeys=3), None, None
    definition = home_definition.HomeDefinition.model_validate_json((ROOT/'examples'/'homes'/'rectangle.json').read_text())
    yield 'rectangle_260_trusses', ModelConfig(), definition, ManualTrussInput(truss_type='common', quantity=260, spacing_mm=100, span_mm=6000)


def profile_model_read():
    """One extra profiled read, kept outside the ordinary timing samples."""
    profiler = cProfile.Profile()
    profiler.runcall(db.model_json)
    stats = pstats.Stats(profiler)
    functions = []
    for (filename, line, name), (primitive, calls, own, cumulative, _callers) in stats.stats.items():
        path = Path(filename)
        display = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
        functions.append({"file": display, "line": line, "function": name,
                          "primitive_calls": primitive, "calls": calls,
                          "own_seconds": own, "cumulative_seconds": cumulative})
    functions.sort(key=lambda item: item['cumulative_seconds'], reverse=True)
    return {"total_calls": stats.total_calls, "primitive_calls": stats.prim_calls,
            "total_profiled_seconds": stats.total_tt, "top_cumulative_functions": functions[:30]}


def run(repeats=3, archives_dir=None, profile_reads=False):
    if not 1 <= repeats <= 20:
        raise ValueError('repeats must be between 1 and 20')
    original_path = db.DB_PATH
    scope_token = projects.project_id.set('default')
    write_token = projects.write_contract.set(None); read_token = projects.read_revision.set(None)
    report = {"benchmark_schema_version": 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
              "application_version": (ROOT/'VERSION').read_text().strip(), "source_fingerprint": source_fingerprint(),
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                  "cpu_affinity_count": len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count(),
                  "fastapi": version('fastapi'), "pydantic": version('pydantic')},
              "timing_unit": "milliseconds", "repeats": repeats, "fixtures": []}
    try:
        with tempfile.TemporaryDirectory(prefix='timberbim-profile-') as temporary:
            for name, cfg, definition, extra in fixtures():
                def generation():
                    generated = home_definition.generate(definition or home_definition.sample_definition(cfg), cfg)
                    if extra:
                        generated.elements.extend(generate_truss(extra, source_id='profile-layout')[0])
                    return generated
                generated, generation_ms = measure(generation, repeats)
                tracemalloc.start()
                try:
                    generation(); _, python_peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                trial = 0
                def persistence():
                    nonlocal trial
                    trial += 1; db.DB_PATH = Path(temporary)/f'{name}-{trial}.db'
                    db.rebuild(cfg, definition=definition)
                    if extra:
                        members, _ = generate_truss(extra, source_id='profile-layout')
                        db.append_elements(members, 'manual_truss', 'profile-layout', definition=extra.model_dump())
                _, pipeline_ms = measure(persistence, repeats)
                model, model_read_ms = measure(db.model_json, repeats)
                encoded, serialization_ms = measure(lambda: json.dumps(model, separators=(',', ':'), allow_nan=False).encode(), repeats)
                bom, bom_read_ms = measure(db.bom_json, repeats)
                archive = db.export_home_archive()
                if archives_dir:
                    target = Path(archives_dir); target.mkdir(parents=True, exist_ok=True)
                    (target/f'{name}.json').write_text(json.dumps(archive))
                result = {"id": name, "member_count": len(model['elements']),
                    "generation_member_count": len(generated.elements), "json_bytes": len(encoded),
                    "bom_rows": len(bom['rows']), "generation_ms": generation_ms, "fresh_database_pipeline_ms": pipeline_ms,
                    "model_read_review_estimate_ms": model_read_ms, "json_serialization_ms": serialization_ms,
                    "bom_navigation_query_ms": bom_read_ms, "generation_python_alloc_peak_bytes": python_peak}
                if profile_reads:
                    result['model_read_cprofile'] = profile_model_read()
                report['fixtures'].append(result)
        # Linux reports KiB; macOS reports bytes. This is cumulative process RSS,
        # distinct from each fixture's traced Python allocation measurement.
        report['process_peak_rss_bytes'] = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if platform.system() == 'Darwin' else 1024)) if resource else None
        return report
    finally:
        db.DB_PATH = original_path
        projects.read_revision.reset(read_token); projects.write_contract.reset(write_token); projects.project_id.reset(scope_token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--archives-dir', type=Path, help='Optional portable inputs for the isolated browser profiler')
    parser.add_argument('--profile-reads', action='store_true', help='Add one cProfile read per fixture, outside timing samples')
    args = parser.parse_args()
    report = json.dumps(run(args.repeats, args.archives_dir, args.profile_reads), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(report+'\n')
    else:
        print(report)


if __name__ == '__main__':
    main()
