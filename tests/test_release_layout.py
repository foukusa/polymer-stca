"""STCA 1.0 metadata, flat repository layout and guarded-local-update tests."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
from importlib.resources import files

import pytest
from stca import __version__, load_pretrained

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent():
    assert __version__ == '1.0'
    assert 'version = "1.0"' in (ROOT / 'pyproject.toml').read_text(encoding="utf-8")
    assert 'version: "1.0"' in (ROOT / 'docs/CITATION.cff.template').read_text(encoding="utf-8")
    assert 'version **1.0**' in (ROOT / 'CITATION.md').read_text(encoding="utf-8") or 'version 1.0' in (ROOT / 'CITATION.md').read_text(encoding="utf-8")


@pytest.mark.parametrize('protocol', ['paper', 'source_locked', 'legacy_snapshot'])
@pytest.mark.parametrize('profile', ['tg-high', 'ec-low', 'ec-high'])
def test_packaged_model_version(profile, protocol):
    assert load_pretrained(profile, protocol=protocol, warn=False).artifact['package_version'] == '1.0'


def test_repository_has_no_extra_project_directory():
    assert (ROOT / 'pyproject.toml').is_file()
    assert (ROOT / 'src/stca/model.py').is_file()
    assert not (ROOT / 'polymer-stca').exists()
    assert not (ROOT / 'STCA_GitHub').exists()
    assert r'D:\hongo\polymer-stca' in (ROOT / 'docs/LOCAL_UPDATE.md').read_text(encoding="utf-8")


def test_current_public_docs_use_one_release_label():
    for path in [*ROOT.glob('*.md'), *ROOT.glob('docs/*.md')]:
        text = path.read_text(encoding='utf-8')
        assert not re.search(r'0\.1\.0rc\d|\brc[1-4]\b|polymer-stca-main|release_check', text, re.I), path
    receipt = json.loads(files('stca').joinpath('assets/verified_refit_summary.json').read_text(encoding="utf-8"))
    assert receipt['package_version'] == '1.0'


def checkout(tmp_path):
    dest = tmp_path / 'checkout'
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(
        '__pycache__', '*.egg-info', '.pytest_cache', 'build', 'dist', '.git', '.venv'))
    (dest / '.git').mkdir()
    (dest / '.git/config').write_text('preserve git configuration', encoding="utf-8")
    (dest / 'PRIVATE_measurements.csv').write_text('private input', encoding="utf-8")
    return dest


def run_update(repo, *options, source=ROOT):
    return subprocess.run([sys.executable, str(source / 'scripts/apply_update.py'),
                           '--repo', str(repo), *options], text=True, capture_output=True)


def content_snapshot(repo):
    return {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file()}


def test_updater_dry_run_is_read_only(tmp_path):
    repo = checkout(tmp_path)
    p = repo / 'pyproject.toml'
    p.write_text(p.read_text(encoding="utf-8").replace('version = "1.0"', 'version = "0.0.0"'), encoding="utf-8")
    before = content_snapshot(repo)
    result = run_update(repo)
    assert result.returncode == 0, result.stderr
    assert 'DRY RUN ONLY' in result.stdout
    assert content_snapshot(repo) == before


def test_updater_keeps_git_private_data_contacts_and_urls(tmp_path):
    repo = checkout(tmp_path)
    p = repo / 'README.md'
    p.write_text(p.read_text(encoding="utf-8").replace('## Contact\n', '## Contact\n\nPreserve my laboratory contact notes.\n'), encoding="utf-8")
    p = repo / 'pyproject.toml'
    p.write_text(p.read_text(encoding="utf-8").replace('version = "1.0"', 'version = "0.0.0"') + '\n[tool.my_local]\nvalue = "keep"\n', encoding="utf-8")
    p = repo / 'LICENSE'
    p.write_text(p.read_text(encoding="utf-8").replace('2025', '2026'), encoding="utf-8")
    before = {name: (repo / name).read_bytes() for name in ['.git/config', 'PRIVATE_measurements.csv', 'LICENSE', 'NOTICE']}
    result = run_update(repo, '--apply')
    assert result.returncode == 0, result.stderr
    assert all((repo / name).read_bytes() == data for name, data in before.items())
    assert 'Preserve my laboratory contact notes.' in (repo / 'README.md').read_text(encoding="utf-8")
    assert (repo / 'LICENSE').read_text(encoding="utf-8").strip() in (repo / 'README.md').read_text(encoding="utf-8")
    assert '[tool.my_local]' in (repo / 'pyproject.toml').read_text(encoding="utf-8")
    assert 'version = "1.0"' in (repo / 'pyproject.toml').read_text(encoding="utf-8")
    assert not (repo / 'polymer-stca').exists()
    backups = list(tmp_path.glob('STCA_update_backup_*'))
    assert len(backups) == 1
    assert (backups[0] / 'pyproject.toml').is_file()
    after = content_snapshot(repo)
    repeat = run_update(repo, '--apply')
    assert repeat.returncode == 0, repeat.stderr
    assert 'Already at STCA 1.0' in repeat.stdout
    assert content_snapshot(repo) == after


def test_updater_unknown_source_change_blocks_all_writes(tmp_path):
    repo = checkout(tmp_path)
    p = repo / 'src/stca/scan.py'
    p.write_text(p.read_text(encoding="utf-8") + '\nLOCAL_ALGORITHM_CHANGE = True\n', encoding="utf-8")
    before = content_snapshot(repo)
    result = run_update(repo, '--apply')
    assert result.returncode == 2 and 'LOCAL_EDIT_CONFLICT' in result.stderr
    assert content_snapshot(repo) == before
    assert not list(tmp_path.glob('STCA_update_backup_*'))


def test_updater_changed_snapshot_blocks_all_writes(tmp_path):
    repo = checkout(tmp_path)
    p = repo / 'src/stca/assets/tg_high_si20260822.json'
    doc = json.loads(p.read_text(encoding="utf-8")); doc['direction'] = 'low'; p.write_text(json.dumps(doc), encoding="utf-8")
    before = content_snapshot(repo)
    result = run_update(repo, '--apply')
    assert result.returncode == 2 and 'SI rule snapshot' in result.stderr
    assert content_snapshot(repo) == before


def test_updater_accepts_windows_line_endings(tmp_path):
    repo = checkout(tmp_path)
    for path in repo.rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.json', '.toml', '.md'):
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    result = run_update(repo, '--apply')
    assert result.returncode == 0, result.stderr


def test_updater_refuses_non_git_directory(tmp_path):
    repo = checkout(tmp_path); shutil.rmtree(repo / '.git')
    before = content_snapshot(repo)
    result = run_update(repo, '--apply')
    assert result.returncode == 2 and 'GitHub Desktop checkout' in result.stderr
    assert content_snapshot(repo) == before


def test_updater_refuses_inplace_staging():
    result = run_update(ROOT)
    assert result.returncode == 2 and 'Stage the update outside' in result.stderr
