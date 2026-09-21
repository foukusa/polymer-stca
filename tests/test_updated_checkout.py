"""Test the *installed updater output* as the next distribution/CI source.

A passing test of only the supplied ZIP missed this failure: legitimate Contact,
copyright and TOML merges left template hashes in the destination manifest.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('_stca_checkout_updater', ROOT / 'scripts/apply_update.py')
U = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(U)


def checkout(path):
    shutil.copytree(ROOT, path, ignore=shutil.ignore_patterns(
        '__pycache__', '*.egg-info', '.pytest_cache', 'build', 'dist', '.git', '.venv'))
    (path / '.git').mkdir()
    (path / '.git/config').write_bytes(b'private git configuration\n')
    (path / 'PRIVATE_measurements.csv').write_bytes(b'material,value\nprivate,1\n')
    return path


def snapshot(path):
    return {p.relative_to(path).as_posix(): p.read_bytes()
            for p in path.rglob('*') if p.is_file()}


def science(path):
    return {p.relative_to(path / 'src').as_posix(): p.read_bytes()
            for p in (path / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts}


def command(source, target, script='apply_update.py', *args):
    return subprocess.run([sys.executable, str(source / 'scripts' / script),
                           '--repo', str(target), *args], capture_output=True, text=True)


def check_source_hashes(repo):
    manifest = json.loads((repo / 'scripts/update_manifest.json').read_text(encoding='utf-8'))
    for group in ('payload_files', 'reference_files'):
        for name, item in manifest[group].items():
            U.verified_payload((repo / name).read_bytes(), item, name)
    return manifest


def customize(repo, crlf=False):
    p = repo / 'README.md'
    p.write_text(p.read_text(encoding='utf-8').replace(
        '## Contact\n', '## Contact\n\nPreserve this laboratory address.\n'), encoding='utf-8')
    p = repo / 'pyproject.toml'
    p.write_text(p.read_text(encoding='utf-8') + '\n[tool.local_ci]\nkeep = true\n', encoding='utf-8')
    p = repo / '.gitignore'
    p.write_text(p.read_text(encoding='utf-8') + '\nPRIVATE_measurements.csv\n', encoding='utf-8')
    for name in ('LICENSE', 'README.md', 'NOTICE'):
        p = repo / name
        p.write_text(p.read_text(encoding='utf-8').replace('Copyright (c) 2025', 'Copyright (c) 2026'), encoding='utf-8')
    if crlf:
        for name in ('README.md', 'LICENSE', 'NOTICE', 'pyproject.toml', '.gitignore'):
            p = repo / name
            p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))


@pytest.mark.parametrize('personalized', [False, True])
@pytest.mark.parametrize('crlf', [False, True])
def test_updated_checkout_can_be_the_next_update_source(tmp_path, personalized, crlf):
    target = checkout(tmp_path / 'published')
    other = checkout(tmp_path / 'next-target')
    if personalized:
        customize(target, crlf=crlf)
    before_science = science(target)
    result = command(ROOT, target, 'apply_update.py', '--update-license', '--apply')
    assert result.returncode == 0, result.stderr
    check_source_hashes(target)
    assert science(target) == before_science
    published = snapshot(target)
    result = command(target, other, 'apply_update.py', '--apply')
    assert result.returncode == 0, result.stderr
    check_source_hashes(other)
    assert snapshot(target) == published  # Using a published source never mutates it.
    before = snapshot(other)
    result = command(target, other, 'apply_update.py', '--apply')
    assert result.returncode == 0, result.stderr
    assert snapshot(other) == before
    if personalized:
        assert 'Preserve this laboratory address.' in (target / 'README.md').read_text(encoding='utf-8')
        assert '[tool.local_ci]' in (target / 'pyproject.toml').read_text(encoding='utf-8')
        assert b'private' in (target / 'PRIVATE_measurements.csv').read_bytes()


@pytest.mark.parametrize('name', ['README.md', 'LICENSE', 'NOTICE', 'pyproject.toml'])
def test_updated_source_still_rejects_later_payload_damage(tmp_path, name):
    source = checkout(tmp_path / 'published')
    target = checkout(tmp_path / 'next-target')
    customize(source)
    assert command(ROOT, source, 'apply_update.py', '--apply').returncode == 0
    check_source_hashes(source)
    p = source / name
    p.write_bytes(p.read_bytes() + b'\nREAL_CONTENT_CHANGE\n')
    before = snapshot(target)
    result = command(source, target, 'apply_update.py', '--apply')
    assert result.returncode == 2
    assert f'Damaged update payload: {name}' in result.stderr
    assert snapshot(target) == before


def test_manifest_builder_only_updates_reference_digests(tmp_path):
    target = checkout(tmp_path / 'checkout')
    rules = json.loads((ROOT / 'scripts/update_manifest.json').read_text(encoding='utf-8'))
    original = json.loads(json.dumps(rules))
    data = (target / 'README.md').read_bytes()
    new = data + b'\nMaintainer note.\n'
    result, guards = U.manifest_for_updated_checkout(target, rules, [('README.md', data, new)])
    published = json.loads(result)
    assert rules == original
    assert published['payload_files'] == original['payload_files']
    assert published['protected_scientific_assets'] == original['protected_scientific_assets']
    assert published['reference_files']['README.md']['new_sha256'] == U.sha(U.lf_text(new))
    assert guards['README.md'] == data
    assert (target / 'README.md').read_bytes() == data


@pytest.mark.parametrize('apply', [False, True])
@pytest.mark.parametrize('crlf', [False, True])
def test_targeted_repair_preserves_docs_models_and_is_idempotent(tmp_path, apply, crlf):
    target = checkout(tmp_path / 'checkout')
    customize(target, crlf=crlf)  # Emulate stale template hashes after a legitimate merge.
    before = snapshot(target)
    result = command(ROOT, target, 'repair_ci.py', *(['--apply'] if apply else []))
    assert result.returncode == 0, result.stderr
    if not apply:
        assert snapshot(target) == before
        assert not list(tmp_path.glob('STCA_CI_backup_*'))
        return
    check_source_hashes(target)
    after = snapshot(target)
    changed = {key for key in before if before[key] != after[key]}
    assert changed == {'scripts/update_manifest.json'}
    result = command(ROOT, target, 'repair_ci.py', '--apply')
    assert result.returncode == 0, result.stderr
    assert snapshot(target) == after
    assert len(list(tmp_path.glob('STCA_CI_backup_*'))) == 1


@pytest.mark.parametrize('name', ['src/stca/scan.py', 'src/stca/assets/ec_low_paper_refit.json'])
def test_targeted_repair_never_blesses_changed_science(tmp_path, name):
    target = checkout(tmp_path / 'checkout')
    customize(target)
    path = target / name
    path.write_bytes(path.read_bytes() + b'\nCHANGED_SCIENCE\n')
    before = snapshot(target)
    result = command(ROOT, target, 'repair_ci.py', '--apply')
    assert result.returncode == 2
    assert name in result.stderr
    assert snapshot(target) == before
    assert not list(tmp_path.glob('STCA_CI_backup_*'))


def test_targeted_repair_refuses_inconsistent_license(tmp_path):
    target = checkout(tmp_path / 'checkout')
    p = target / 'LICENSE'
    p.write_bytes(p.read_bytes() + b'\nAdditional unknown terms.\n')
    before = snapshot(target)
    result = command(ROOT, target, 'repair_ci.py', '--apply')
    assert result.returncode == 2
    assert 'license terms' in result.stderr
    assert snapshot(target) == before


@pytest.mark.skipif(shutil.which('git') is None, reason='Git is not installed')
def test_updated_checkout_real_git_roundtrip_is_valid_source(tmp_path):
    source = checkout(tmp_path / 'working-tree')
    customize(source)
    assert command(ROOT, source, 'apply_update.py', '--apply').returncode == 0
    shutil.rmtree(source / '.git')
    clone = tmp_path / 'clone'
    target = checkout(tmp_path / 'target')
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    def git(*args, cwd=source):
        p = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
    git('init')
    git('config', 'user.name', 'STCA local regression')
    git('config', 'user.email', 'test@example.invalid')
    git('add', '.')
    git('commit', '-m', 'Test actual updater output')
    git('-c', 'core.autocrlf=true', 'clone', '--no-hardlinks', str(source), str(clone), cwd=tmp_path)
    check_source_hashes(clone)
    p = command(clone, target, 'apply_update.py', '--apply')
    assert p.returncode == 0, p.stderr
    check_source_hashes(target)
