"""Regression tests for the *source* update payload, not just the target tree.

A Windows-style Git checkout must not be mistaken for corrupt update files.
Real payload changes and unknown local source edits must still stop all writes.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    'stca_payload_updater', ROOT / 'scripts/apply_update.py')
assert _SPEC is not None and _SPEC.loader is not None
UPDATER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(UPDATER)


def copy_source(dest: Path) -> Path:
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(
        '__pycache__', '*.egg-info', '.pytest_cache', 'build', 'dist', '.git',
        '.venv'))
    return dest


def target_checkout(dest: Path) -> Path:
    copy_source(dest)
    (dest / '.git').mkdir()
    (dest / '.git/config').write_bytes(b'private git config\n')
    (dest / 'PRIVATE_measurements.csv').write_bytes(b'private,data\r\n')
    return dest


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


def crlf(path: Path) -> None:
    data = path.read_bytes()
    data.decode('utf-8')
    assert b'\x00' not in data
    path.write_bytes(data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))


def convert_payload(source: Path, scope: str) -> None:
    manifest = json.loads((source / 'scripts/update_manifest.json').read_text(
        encoding='utf-8'))
    if scope == 'attributes':
        paths = ['.gitattributes']
    elif scope == 'previously_uncovered':
        paths = ['.gitattributes', 'MANIFEST.in',
                 '.github/workflows/publish.yml.example',
                 'docs/CITATION.cff.template',
                 'docs/RELEASE_APPROVAL.json.example']
    else:
        paths = [relative for relative, item in manifest['payload_files'].items()
                 if item.get('hash_mode') == 'utf8-lf']
        paths += ['README.md', 'LICENSE', 'NOTICE', '.gitignore',
                  'pyproject.toml', 'scripts/update_manifest.json']
    for relative in paths:
        crlf(source / relative)


def run(source: Path, target: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(source / 'scripts/apply_update.py'),
         '--repo', str(target), *args], capture_output=True, text=True)


@pytest.mark.parametrize('scope', ['attributes', 'previously_uncovered', 'all'])
@pytest.mark.parametrize('apply', [False, True])
def test_crlf_source_payload_is_accepted(tmp_path, scope, apply):
    source = copy_source(tmp_path / 'source')
    target = target_checkout(tmp_path / 'target')
    convert_payload(source, scope)
    project = target / 'pyproject.toml'
    project.write_text(project.read_text(encoding='utf-8').replace(
        'version = "1.0"', 'version = "0.0.0"'), encoding='utf-8')
    source_before = snapshot(source)
    target_before = snapshot(target)
    result = run(source, target, *(['--apply'] if apply else []))
    assert result.returncode == 0, result.stderr
    assert snapshot(source) == source_before
    if not apply:
        assert 'DRY RUN ONLY' in result.stdout
        assert snapshot(target) == target_before
        assert not list(tmp_path.glob('STCA_update_backup_*'))
    else:
        assert 'version = "1.0"' in project.read_text(encoding='utf-8')
        assert (target / '.git/config').read_bytes() == target_before['.git/config']
        assert (target / 'PRIVATE_measurements.csv').read_bytes() == target_before[
            'PRIVATE_measurements.csv']
        assert (target / 'LICENSE').read_bytes() == target_before['LICENSE']
        after = snapshot(target)
        repeat = run(source, target, '--apply')
        assert repeat.returncode == 0, repeat.stderr
        assert 'Already at STCA 1.0' in repeat.stdout
        assert snapshot(target) == after


def test_both_source_and_target_crlf_preserve_science_and_are_idempotent(tmp_path):
    source = copy_source(tmp_path / 'source')
    target = target_checkout(tmp_path / 'target')
    convert_payload(source, 'all')
    convert_payload(target, 'all')
    models = {p.name: json.loads(p.read_text(encoding='utf-8'))
              for p in (target / 'src/stca/assets').glob('*.json')}
    result = run(source, target, '--apply')
    assert result.returncode == 0, result.stderr
    assert models == {p.name: json.loads(p.read_text(encoding='utf-8'))
                      for p in (target / 'src/stca/assets').glob('*.json')}
    before = snapshot(target)
    result = run(source, target, '--apply')
    assert result.returncode == 0, result.stderr
    assert 'Already at STCA 1.0' in result.stdout
    assert snapshot(target) == before


@pytest.mark.parametrize('relative', [
    '.gitattributes', 'src/stca/scan.py',
    'src/stca/assets/ec_low_paper_refit.json', 'docs/CITATION.cff.template',
])
def test_real_source_payload_damage_still_blocks_all_writes(tmp_path, relative):
    source = copy_source(tmp_path / 'source')
    target = target_checkout(tmp_path / 'target')
    convert_payload(source, 'all')
    p = source / relative
    p.write_bytes(p.read_bytes() + b'\r\nACTUAL_CONTENT_CHANGE = True\r\n')
    before = snapshot(target)
    result = run(source, target, '--apply')
    assert result.returncode == 2
    assert f'Damaged update payload: {relative}' in result.stderr
    assert snapshot(target) == before
    assert not list(tmp_path.glob('STCA_update_backup_*'))


def test_local_algorithm_edit_is_not_hidden_by_crlf_source(tmp_path):
    source = copy_source(tmp_path / 'source')
    target = target_checkout(tmp_path / 'target')
    convert_payload(source, 'all')
    p = target / 'src/stca/scan.py'
    p.write_bytes(p.read_bytes() + b'\nLOCAL_ALGORITHM_CHANGE = True\n')
    before = snapshot(target)
    result = run(source, target, '--apply')
    assert result.returncode == 2
    assert 'LOCAL_EDIT_CONFLICT: src/stca/scan.py' in result.stderr
    assert snapshot(target) == before
    assert not list(tmp_path.glob('STCA_update_backup_*'))


@pytest.mark.parametrize('mutation', [
    b'line one \r\nline two\r\n',  # whitespace remains significant
    b'line one\rline two\r',      # bare CR is not Git LF/CRLF conversion
    b'line one\r\nline two',      # removed final newline
    b'\xef\xbb\xbfline one\r\nline two\r\n',  # added BOM
    b'line one\r\nline two\r\n\x00',          # NUL
    b'line one\r\nline two\r\n\xff',          # invalid UTF-8
])
def test_text_normalization_does_not_erase_other_changes(mutation):
    original = b'line one\nline two\n'
    item = {'hash_mode': 'utf8-lf',
            'new_sha256': hashlib.sha256(original).hexdigest()}
    assert UPDATER.verified_payload(original, item, 'file.txt') == original
    assert UPDATER.verified_payload(original.replace(b'\n', b'\r\n'),
                                    item, 'file.txt') == original
    with pytest.raises(ValueError, match='Damaged update payload: file.txt'):
        UPDATER.verified_payload(mutation, item, 'file.txt')


def test_binary_payloads_keep_exact_byte_verification():
    original = b'\x00binary\nbytes\xff'
    item = {'hash_mode': 'exact',
            'new_sha256': hashlib.sha256(original).hexdigest(),
            'accepted_sha256': [hashlib.sha256(original).hexdigest()]}
    assert UPDATER.verified_payload(original, item, 'file.bin') == original
    assert UPDATER.accepted(original, item, 'file.bin')
    changed = original.replace(b'\n', b'\r\n')
    with pytest.raises(ValueError, match='Damaged update payload'):
        UPDATER.verified_payload(changed, item, 'file.bin')
    assert not UPDATER.accepted(changed, item, 'file.bin')


def test_undeclared_text_has_no_implicit_hash_normalization():
    original = b'exact bytes\n'
    item = {'new_sha256': hashlib.sha256(original).hexdigest()}
    with pytest.raises(ValueError, match='Damaged update payload'):
        UPDATER.verified_payload(b'exact bytes\r\n', item, 'file.txt')


@pytest.mark.skipif(shutil.which('git') is None, reason='Git is not installed')
def test_real_git_autocrlf_checkout_keeps_manifest_text_digests(tmp_path):
    source = copy_source(tmp_path / 'git-source')
    target = target_checkout(tmp_path / 'target')
    clone = tmp_path / 'git-windows-checkout'
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args, cwd=source):
        result = subprocess.run(['git', *args], cwd=cwd, env=env,
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        return result

    git('init')
    git('config', 'user.name', 'Local STCA test')
    git('config', 'user.email', 'local-test@example.invalid')
    git('config', 'core.autocrlf', 'false')
    git('add', '.')
    git('commit', '-m', 'Test supplied STCA source')
    git('-c', 'core.autocrlf=true', 'clone', '--no-hardlinks',
        str(source), str(clone), cwd=tmp_path)
    manifest = json.loads((clone / 'scripts/update_manifest.json').read_text(
        encoding='utf-8'))
    for relative, item in manifest['payload_files'].items():
        data = (clone / relative).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item['new_sha256'], relative
    result = run(clone, target)
    assert result.returncode == 0, result.stderr
