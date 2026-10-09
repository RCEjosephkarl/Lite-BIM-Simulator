"""Verify a fresh source copy with fresh dependencies, excluding local data/secrets.

Default setup uses pip/npm and downloads Chromium. Offline caches and an existing
browser are optional overrides, not requirements for a new expert's setup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = {'backend', 'frontend', 'examples', '.github', 'scripts', 'benchmarks'}
SUFFIXES = {'.py', '.ts', '.css', '.html', '.json', '.mjs', '.md', '.sql', '.csv', '.txt', '.yml', '.yaml'}
SKIP = {'.git', '.agents', '.codex', '.aws', '.claude', '.venv', 'venv', 'env', 'node_modules', 'dist', '__pycache__', '.pytest_cache', '.vite'}


def copy_sources(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Clean-source destination must be new')
    if destination.is_relative_to(source):
        raise ValueError('Clean-source destination must be outside its source tree')
    digest = hashlib.sha256(); copied = []
    paths=[]
    for directory, directories, files in os.walk(source):
        parent=Path(directory)
        directories[:]=[name for name in directories if name not in SKIP and not name.endswith('.db.projects')
                        and (parent != source or name in SOURCE_DIRS)]
        paths.extend(parent/name for name in files)
    for path in sorted(paths):
        relative = path.relative_to(source)
        if any(part in SKIP for part in relative.parts) or path.is_symlink() or not path.is_file():
            continue
        if any(part.startswith('.env') and part != '.env.example' for part in relative.parts):
            continue
        if len(relative.parts) == 1:
            allowed = path.suffix == '.md' or path.name in {'VERSION', '.gitignore'}
        else:
            allowed = relative.parts[0] in SOURCE_DIRS and path.suffix in SUFFIXES
        if not allowed:
            continue
        target = destination/relative; target.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_bytes(); target.write_bytes(content)
        digest.update(relative.as_posix().encode()); digest.update(b'\0'); digest.update(content); digest.update(b'\0')
        copied.append(relative.as_posix())
    if not copied:
        raise ValueError('No source files were found')
    return copied, digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--npm-cache', type=Path)
    parser.add_argument('--uv-cache', type=Path, help='Optional uv wheel cache for offline Python setup')
    parser.add_argument('--browser', type=Path, help='Optional existing Chromium executable')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if args.offline and (not args.uv_cache or not args.npm_cache or not args.browser):
        parser.error('Offline verification needs --uv-cache, --npm-cache and --browser')
    report = {'verification_schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'source_kind': 'fresh copy of current worktree; no commit/remote CI claim', 'offline': args.offline, 'steps': []}
    try:
        with tempfile.TemporaryDirectory(prefix='timberbim-clean-') as temporary:
            temporary = Path(temporary); clean = temporary/'source'
            copied, fingerprint = copy_sources(ROOT, clean)
            report.update(copied_files=copied, source_copy_sha256=fingerprint,
                          application_version=(clean/'VERSION').read_text().strip())
            environment = os.environ.copy()
            # Installed environments/caches are external dependencies, never copied
            # application state. Every test/API database remains isolated.
            environment['TIMBERBIM_DB_PATH'] = str(temporary/'unused.db')
            environment['PLAYWRIGHT_BROWSERS_PATH'] = str(temporary/'browsers')
            environment.pop('TIMBERBIM_TEST_FORMS_ONLY', None)
            environment.pop('TIMBERBIM_TEST_NAVIGATION_ONLY', None)
            environment.pop('TIMBERBIM_TEST_RENDERING_ONLY', None)
            environment.pop('TIMBERBIM_TEST_ACCESSIBILITY_ONLY', None)
            environment.pop('TIMBERBIM_ACCESSIBILITY_REPORT', None)
            def run(label, command, cwd=clean):
                print(f'Verifying {label}…', flush=True); started = time.perf_counter()
                result = subprocess.run(command, cwd=cwd, env=environment)
                report['steps'].append({'name': label, 'command': [str(part).replace(str(temporary), '<temporary>') for part in command],
                                        'exit_code': result.returncode, 'duration_seconds': round(time.perf_counter()-started, 3)})
                if result.returncode:
                    raise RuntimeError(f'{label} failed with exit code {result.returncode}')
            run('fresh Python environment', [args.python, '-m', 'venv', str(temporary/'venv')])
            python = temporary/'venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            if args.uv_cache:
                uv = shutil.which('uv')
                if not uv: raise RuntimeError('uv is required only when --uv-cache is supplied')
                install = [uv, 'pip', 'install', '--python', str(python), '--cache-dir', str(args.uv_cache), '-r', 'backend/requirements.lock.txt']
                if args.offline: install.append('--offline')
            else:
                install = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'backend/requirements.lock.txt']
            run('locked Python dependencies', install)
            environment['TIMBERBIM_TEST_PYTHON'] = str(python)
            npm_cache = args.npm_cache or temporary/'npm-cache'
            install = ['npm', 'ci', '--cache', str(npm_cache), '--no-audit', '--no-fund']
            if args.offline: install.append('--offline')
            run('locked frontend dependencies', install, clean/'frontend')
            run('backend regression tests', [str(python), '-m', 'pytest', '-q'], clean/'backend')
            run('production build', ['npm', 'run', 'build'], clean/'frontend')
            run('frontend contracts', ['npm', 'run', 'test:contracts'], clean/'frontend')
            if args.browser:
                environment['TIMBERBIM_TEST_BROWSER'] = str(args.browser.resolve())
            else:
                environment.pop('TIMBERBIM_TEST_BROWSER', None)
                run('Chromium installation', ['npx', 'playwright', 'install', 'chromium'], clean/'frontend')
            run('full isolated browser acceptance', ['npm', 'run', 'test:browser'], clean/'frontend')
            report['environment'] = {name: subprocess.check_output(command, cwd=clean, env=environment, text=True).strip()
                                     for name, command in [('python', [str(python), '--version']), ('node', ['node', '--version']), ('npm', ['npm', '--version'])]}
            if (clean/'backend'/'model.db').exists():
                raise RuntimeError('A test created a database in the clean source tree')
            report['result'] = 'passed'
    except Exception as exc:
        report['result'] = 'failed'; report['failure'] = str(exc)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
