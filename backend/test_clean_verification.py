"""Source-only handover must never copy runtime stores or credential files."""
import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('verify_clean',Path(__file__).parent.parent/'scripts'/'verify_clean.py')
verify_clean=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify_clean)


def test_clean_copy_excludes_runtime_secrets_dependencies_and_external_symlinks(tmp_path):
    source=tmp_path/'input';source.mkdir()
    for relative in ['backend/server.py','backend/schema.sql','backend/requirements.lock.txt','frontend/package-lock.json',
                     'frontend/src/main.ts','frontend/tests/workspace.mjs','examples/homes/rectangle.json',
                     'README.md','VERSION','.github/workflows/verify.yml','.env','backend/.env.production',
                     'backend/model.db','backend/model.db.backup-before-restore','backend/model.db.projects/home.db',
                     '.aws/credentials','frontend/node_modules/dependency/index.ts','frontend/dist/assets/main.js',
                     'backend/.venv/config.py','.git/config','backend/__pycache__/cache.py']:
        path=source/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(relative)
    private=tmp_path/'private.py';private.write_text('Private content')
    (source/'backend'/'linked.py').symlink_to(private)
    copied,fingerprint=verify_clean.copy_sources(source,tmp_path/'output')
    assert set(copied)=={'backend/server.py','backend/schema.sql','backend/requirements.lock.txt','frontend/package-lock.json',
                        'frontend/src/main.ts','frontend/tests/workspace.mjs','examples/homes/rectangle.json',
                        'README.md','VERSION','.github/workflows/verify.yml'}
    assert len(fingerprint)==64 and (tmp_path/'output'/'backend'/'server.py').read_text()=='backend/server.py'
    with pytest.raises(ValueError,match='new'):
        verify_clean.copy_sources(source,tmp_path/'output')
    with pytest.raises(ValueError,match='outside'):
        verify_clean.copy_sources(source,source/'nested-copy')
