"""UTF-8 repository I/O must work without enabling Python UTF-8 mode.

The cp932 fixture emulates implicit Path text I/O only. It does not claim to be
an operating-system or console-code-page emulation. No STCA model is changed.
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def force_cp932_defaults(monkeypatch):
    """Pass cp932 only where a caller omitted its file encoding."""
    original_read = Path.read_text
    original_write = Path.write_text
    original_open = Path.open

    def read(self, encoding=None, errors=None, **kwargs):
        codec = 'cp932' if encoding in (None, 'locale') else encoding
        return original_read(self, encoding=codec, errors=errors, **kwargs)

    def write(self, data, encoding=None, errors=None, **kwargs):
        codec = 'cp932' if encoding in (None, 'locale') else encoding
        return original_write(self, data, encoding=codec, errors=errors, **kwargs)

    def open_path(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
        if 'b' not in mode and encoding in (None, 'locale'):
            encoding = 'cp932'
        return original_open(self, mode=mode, buffering=buffering, encoding=encoding,
                             errors=errors, newline=newline)

    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(Path, 'write_text', write)
    monkeypatch.setattr(Path, 'open', open_path)


def copy_checkout(target):
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(
        '__pycache__', '*.egg-info', '.pytest_cache', 'build', 'dist', '.git', '.venv'))
    (target / '.git').mkdir()
    (target / '.git/config').write_bytes(b'keep private git configuration\n')
    (target / 'PRIVATE_measurements.csv').write_bytes(b'keep private measurements\n')
    return target


def snapshot(repo):
    return {p.relative_to(repo).as_posix(): p.read_bytes()
            for p in repo.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


def test_all_repository_path_text_calls_have_explicit_encoding():
    # This includes tests: they must not pass on UTF-8 hosts and fail on Windows.
    failures = []
    roots = ('src', 'scripts', 'tests', 'examples')
    for directory in roots:
        for path in sorted((ROOT / directory).rglob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                method = node.func.attr
                if method not in ('read_text', 'write_text'):
                    continue
                position = 0 if method == 'read_text' else 1
                codec = node.args[position] if len(node.args) > position else next(
                    (kw.value for kw in node.keywords if kw.arg == 'encoding'), None)
                explicit = isinstance(codec, ast.Constant) and isinstance(codec.value, str)
                if not explicit or codec.value.casefold().replace('_', '-') not in ('utf-8', 'utf-8-sig'):
                    failures.append(f'{path.relative_to(ROOT).as_posix()}:{node.lineno}')
    assert not failures, 'Implicit/non-UTF-8 repository text I/O: ' + ', '.join(failures)


def test_cp932_regression_fixture_is_sensitive():
    # Not ASCII: the original README's em dash fails under cp932.
    payload = 'STCA \u2014 reproducible screening'.encode('utf-8')
    with pytest.raises(UnicodeDecodeError, match='cp932'):
        payload.decode('cp932')
    assert payload.decode('utf-8') == 'STCA \u2014 reproducible screening'


def test_contact_and_private_data_test_passes_with_cp932_defaults(tmp_path, monkeypatch):
    layout = load_script('tests/test_release_layout.py', '_stca_cp932_layout')
    force_cp932_defaults(monkeypatch)
    layout.test_updater_keeps_git_private_data_contacts_and_urls(tmp_path)


@pytest.mark.parametrize('crlf', [False, True])
def test_updater_non_ascii_ignore_and_contacts_under_cp932(tmp_path, monkeypatch, crlf):
    U = load_script('scripts/apply_update.py', '_stca_cp932_update')
    source = copy_checkout(tmp_path / 'source')
    target = copy_checkout(tmp_path / 'target')
    # Use genuine UTF-8 content that cannot accidentally work as ASCII/cp932.
    note = '\u7814\u7a76\u5ba4 \u2014 STCA \u03bc'
    source_ignore = source / '.gitignore'
    source_ignore.write_bytes(source_ignore.read_bytes() + ('\n' + note + '/\n').encode('utf-8'))
    p = target / 'README.md'
    p.write_text(p.read_text(encoding='utf-8').replace(
        '## Contact\n', '## Contact\n\n' + note + '\n'), encoding='utf-8')
    # The staged source manifest must describe its actual UTF-8 source.
    mp = source / 'scripts/update_manifest.json'
    rules = json.loads(mp.read_text(encoding='utf-8'))
    rules['reference_files']['.gitignore']['new_sha256'] = U.sha(U.lf_text(source_ignore.read_bytes()))
    mp.write_text(json.dumps(rules, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if crlf:
        for name in ('.gitignore', 'README.md', 'scripts/update_manifest.json'):
            p = source / name
            p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    monkeypatch.setattr(U, 'SOURCE', source)
    monkeypatch.setattr(U, 'MANIFEST', mp)
    force_cp932_defaults(monkeypatch)
    assert U.main(['--repo', str(target), '--apply']) == 0
    assert note in (target / 'README.md').read_text(encoding='utf-8')
    assert note + '/' in (target / '.gitignore').read_text(encoding='utf-8')
    manifest = json.loads((target / 'scripts/update_manifest.json').read_text(encoding='utf-8'))
    for group in ('payload_files', 'reference_files'):
        for name, item in manifest[group].items():
            U.verified_payload((target / name).read_bytes(), item, name)
    before = snapshot(target)
    assert U.main(['--repo', str(target), '--apply']) == 0
    assert snapshot(target) == before


def test_encoding_patch_dry_run_and_idempotency(tmp_path):
    target = copy_checkout(tmp_path / 'target')
    script = ROOT / 'scripts/fix_text_encoding.py'
    before = snapshot(target)
    command = [sys.executable, str(script), '--repo', str(target)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert snapshot(target) == before
    assert not list(tmp_path.glob('STCA_UTF8_backup_*'))
    result = subprocess.run(command + ['--apply'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    after = snapshot(target)
    result = subprocess.run(command + ['--apply'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert snapshot(target) == after


@pytest.mark.parametrize('name', ['src/stca/scan.py', 'src/stca/assets/ec_low_paper_refit.json',
                                  'tests/test_release_layout.py'])
def test_encoding_patch_blocks_unknown_edits_without_writes(tmp_path, name):
    target = copy_checkout(tmp_path / 'target')
    p = target / name
    p.write_bytes(p.read_bytes() + b'\nUNKNOWN_LOCAL_CHANGE = True\n')
    before = snapshot(target)
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/fix_text_encoding.py'),
                             '--repo', str(target), '--apply'], capture_output=True, text=True)
    assert result.returncode == 2, result.stderr
    assert snapshot(target) == before
    assert not list(tmp_path.glob('STCA_UTF8_backup_*'))
