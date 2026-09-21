"""User-facing README, academic-use terms, and permission-migration regressions."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOI = 'https://doi.org/10.24433/CO.1601774.v1'
LICENSE_ID = 'LicenseRef-STCA-Academic-NonCommercial'
_SPEC = importlib.util.spec_from_file_location('documentation_updater', ROOT / 'scripts/apply_update.py')
UPDATER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(UPDATER)


def test_readme_is_for_users_and_pypi_is_prospective():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert '## Acknowledgments' not in text
    assert '## Acknowledgements' not in text
    assert 'peer review' not in text.lower()
    assert 'Peer-Review' not in text
    assert '1,251' not in text and '11/11' not in text
    assert r'D:\hongo' not in text
    assert 'A **PyPI release is coming soon**' in text
    assert '# Available after the PyPI release' in text
    assert 'python -m pip install ".[chem]"' in text
    assert '## Quick start' in text
    assert '## Train on your own data' in text


def test_capsule_link_not_misidentified_as_paper_doi():
    for name in ('README.md', 'CITATION.md', 'NOTICE', 'docs/SOURCES.md'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert DOI in text, name
        assert 'not the' in text.lower(), name
    assert f'"Code Ocean" = "{DOI}"' in (ROOT / 'pyproject.toml').read_text(encoding='utf-8')


def test_academic_license_is_synchronized():
    terms = (ROOT / 'LICENSE').read_text(encoding='utf-8').strip()
    assert terms in (ROOT / 'README.md').read_text(encoding='utf-8')
    assert 'non-commercial academic research' in terms
    assert 'Commercial use and redistribution' in terms
    assert 'written permission from the copyright holders' in terms
    for name in ('LICENSE', 'NOTICE', 'README.md', 'pyproject.toml'):
        assert 'peer review' not in (ROOT / name).read_text(encoding='utf-8').lower()
    assert LICENSE_ID in (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    for folder in ('src', 'scripts', 'examples', 'tests'):
        for p in (ROOT / folder).rglob('*.py'):
            header = '\n'.join(p.read_text(encoding='utf-8').splitlines()[:4])
            assert 'SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review' not in header, p


def test_documentation_keeps_protocol_selection_boundary():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert 'protocol="source_locked"' in text
    assert 'protocol="paper"' in text
    assert 'not an independent test set' in text
    assert 'same data, representation, split, and selection protocol' in text


def test_readme_local_document_links_resolve():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    links = re.findall(r'\]\(([^)]+)\)', text)
    for link in links:
        if link.startswith(('https:', 'http:', 'mailto:', '#')):
            continue
        assert (ROOT / link.split('#')[0]).is_file(), link


def test_quick_start_and_rule_explanations_execute():
    pytest.importorskip('rdkit')
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    code = re.findall(r'```python\n(.*?)```', text, re.S)
    namespace = {}
    exec(compile(code[0], 'README quick start', 'exec'), namespace)
    exec(compile(code[1], 'README explanations', 'exec'), namespace)
    assert len(namespace['result']) == 3
    for block in code:
        ast.parse(block, feature_version=(3, 10))


def _checkout(path):
    shutil.copytree(ROOT, path, ignore=shutil.ignore_patterns(
        '__pycache__', '*.egg-info', '.pytest_cache', 'build', 'dist', '.git', '.venv'))
    (path / '.git').mkdir()
    (path / '.git/config').write_text('preserved config', encoding='utf-8')
    (path / 'PRIVATE.csv').write_text('private,measurements', encoding='utf-8')
    return path


def _snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def _run(repo, *args, source=ROOT):
    return subprocess.run([sys.executable, str(source / 'scripts/apply_update.py'),
                           '--repo', str(repo), *args], capture_output=True, text=True)


def _legacy_license_fixture(repo):
    # Emulate prior permissions; a test fixture never grants actual rights.
    (repo / 'LICENSE').write_text(UPDATER.LEGACY_LICENSE, encoding='utf-8')
    path = repo / 'pyproject.toml'
    path.write_text(path.read_text(encoding='utf-8').replace(
        LICENSE_ID, UPDATER.LEGACY_LICENSE_ID), encoding='utf-8')


def test_permission_migration_needs_explicit_opt_in(tmp_path):
    repo = _checkout(tmp_path / 'checkout')
    _legacy_license_fixture(repo)
    before = _snapshot(repo)
    result = _run(repo, '--apply')
    assert result.returncode == 2, result.stdout
    assert 'LICENSE_UPDATE_REQUIRED' in result.stderr
    assert _snapshot(repo) == before
    assert not list(tmp_path.glob('STCA_update_backup_*'))


@pytest.mark.parametrize('apply', [False, True])
@pytest.mark.parametrize('crlf', [False, True])
def test_requested_permission_update_is_consistent_and_preserves_contact(tmp_path, apply, crlf):
    repo = _checkout(tmp_path / 'checkout')
    _legacy_license_fixture(repo)
    p = repo / 'LICENSE'
    p.write_text(p.read_text(encoding='utf-8').replace('2025', '2026'), encoding='utf-8')
    p = repo / 'README.md'
    p.write_text(p.read_text(encoding='utf-8').replace(
        '## Contact\n', '## Contact\n\nKeep my laboratory URL.\n') +
        '\n## Acknowledgments\n\nOld text to retire.\n', encoding='utf-8')
    if crlf:
        for name in ['LICENSE', 'NOTICE', 'README.md', 'pyproject.toml']:
            p = repo / name
            p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    before = _snapshot(repo)
    result = _run(repo, '--update-license', *(['--apply'] if apply else []))
    assert result.returncode == 0, result.stderr
    if not apply:
        assert _snapshot(repo) == before
        return
    text = (repo / 'README.md').read_text(encoding='utf-8')
    assert 'Keep my laboratory URL.' in text
    assert '## Acknowledgments' not in text
    assert (repo / 'LICENSE').read_text(encoding='utf-8').strip() in text
    assert 'Copyright (c) 2026' in text
    assert LICENSE_ID in (repo / 'pyproject.toml').read_text(encoding='utf-8')
    assert (repo / 'PRIVATE.csv').read_bytes() == before['PRIVATE.csv']
    assert (repo / '.git/config').read_bytes() == before['.git/config']
    after = _snapshot(repo)
    repeated = _run(repo, '--update-license', '--apply')
    assert repeated.returncode == 0, repeated.stderr
    assert _snapshot(repo) == after


@pytest.mark.parametrize('name', ['LICENSE', 'NOTICE'])
def test_unrecognized_permission_edits_are_not_overwritten(tmp_path, name):
    repo = _checkout(tmp_path / 'checkout')
    p = repo / name
    p.write_text(p.read_text(encoding='utf-8') + '\nUNRECOGNIZED LOCAL TERMS\n', encoding='utf-8')
    before = _snapshot(repo)
    result = _run(repo, '--update-license', '--apply')
    assert result.returncode == 2
    assert f'LOCAL_{name}_CONFLICT' in result.stderr
    assert _snapshot(repo) == before


@pytest.mark.parametrize('name', ['README.md', 'LICENSE', 'NOTICE', 'pyproject.toml'])
def test_source_permission_and_readme_damage_is_detected(tmp_path, name):
    source = _checkout(tmp_path / 'source')
    target = _checkout(tmp_path / 'target')
    p = source / name
    p.write_bytes(p.read_bytes() + b'\nREAL_PAYLOAD_CHANGE\n')
    before = _snapshot(target)
    result = _run(target, '--update-license', '--apply', source=source)
    assert result.returncode == 2
    assert f'Damaged update payload: {name}' in result.stderr
    assert _snapshot(target) == before
