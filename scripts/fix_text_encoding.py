# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
"""Repair STCA 1.0 UTF-8 file I/O on non-UTF-8 Windows; dry-run by default.

Run the supplied patch from a staging directory outside the target repository.
Only listed engineering/test files and their manifest are replaced. README,
permissions, .git, data, all STCA algorithms and models are never written.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1]
CHANGED = ('scripts/apply_update.py', 'tests/test_cli.py', 'tests/test_core.py', 'tests/test_documented_usage.py', 'tests/test_protocol_audit.py', 'tests/test_release_layout.py', 'tests/test_verified_profiles.py', 'tests/test_text_encoding.py', 'scripts/fix_text_encoding.py')
REFERENCES = {'README.md', 'LICENSE', 'NOTICE', 'pyproject.toml', '.gitignore'}
DOI = 'https://doi.org/10.24433/CO.1601774.v1'
LICENSE_ID = 'LicenseRef-STCA-Academic-NonCommercial'


def updater_module():
    spec = importlib.util.spec_from_file_location('_stca_utf8_patch', SOURCE / 'scripts/apply_update.py')
    if spec is None or spec.loader is None:
        raise ValueError('Missing repair implementation.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_head(repo):
    try:
        p = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                           capture_output=True, text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else 'UNAVAILABLE'
    except (OSError, subprocess.TimeoutExpired):
        return 'UNAVAILABLE'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=r'D:\hongo\polymer-stca')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if repo == SOURCE or SOURCE.is_relative_to(repo):
        raise ValueError('Extract this repair outside the target repository first.')
    if not (repo / '.git').exists():
        raise ValueError('Choose the actual GitHub Desktop checkout, containing .git.')
    U = updater_module()
    shipped = json.loads((SOURCE / 'scripts/update_manifest.json').read_text(encoding='utf-8'))
    old_manifest_path = U.safe_path(repo, 'scripts/update_manifest.json')
    old_manifest = old_manifest_path.read_bytes()
    current = json.loads(old_manifest.decode('utf-8'))
    if current.get('version') != '1.0' or shipped.get('version') != '1.0':
        raise ValueError('This targeted repair is for STCA 1.0 only.')
    if set(current.get('reference_files', {})) != REFERENCES:
        raise ValueError('Unexpected manifest format; no automatic repair attempted.')
    if set(current.get('payload_files', {})) - set(shipped.get('payload_files', {})):
        raise ValueError('Unexpected tracked source files; no automatic repair attempted.')
    if current.get('protected_scientific_assets') != shipped.get('protected_scientific_assets'):
        raise ValueError('Scientific reference mismatch; no automatic repair attempted.')

    # Strictly check all immutable tracked files against the independently
    # supplied reference manifest. Never bless arbitrary algorithm/model edits.
    guards = {'scripts/update_manifest.json': old_manifest}
    for name, item in shipped['payload_files'].items():
        path = U.safe_path(repo, name)
        data = path.read_bytes() if path.exists() else None
        guards[name] = data
        if name in CHANGED:
            replacement = U.verified_payload(U.safe_path(SOURCE, name).read_bytes(), item, name)
            if data is not None and not U.accepted(data, item, name):
                raise ValueError(f'LOCAL_EDIT_CONFLICT: {name}. No files changed.')
        else:
            if data is None:
                raise ValueError(f'Incomplete checkout: {name}. No files changed.')
            U.verified_payload(data, item, name)
    for name, digest in shipped['protected_scientific_assets'].items():
        if U.normalized_json(U.safe_path(repo, name).read_bytes()) != digest:
            raise ValueError(f'Scientific snapshot changed: {name}. No files changed.')

    # Documents are maintainer-owned. Check their agreed content/permissions
    # before recording the exact present bytes. These checks do not certify
    # provenance or grant new rights; --apply is the maintainer's opt-in.
    docs = {}
    stale = []
    for name in sorted(REFERENCES):
        data = U.safe_path(repo, name).read_bytes()
        guards[name] = data
        text = U.lf_text(data).decode('utf-8')
        docs[name] = text
        expected = current['reference_files'][name]['new_sha256']
        if sha(U.lf_text(data)) != expected:
            stale.append(name)
    pp = docs['pyproject.toml']
    for pattern in (r'(?m)^name\s*=\s*"polymer-stca"\s*$',
                    r'(?m)^version\s*=\s*"1\.0"\s*$',
                    r'(?m)^license\s*=\s*"' + re.escape(LICENSE_ID) + r'"\s*$'):
        if not re.search(pattern, pp):
            raise ValueError('Unexpected project metadata; this patch will not rewrite it.')
    terms = docs['LICENSE'].strip()
    supplied_terms = (SOURCE / 'LICENSE').read_text(encoding='utf-8')
    if U.license_signature(terms) != U.license_signature(supplied_terms):
        raise ValueError('Unrecognized license terms; this patch will not modify permissions.')
    if terms not in docs['README.md']:
        raise ValueError('README and LICENSE disagree. Resolve the wording before applying this patch.')
    notice_sig = sha(U.license_signature(docs['NOTICE']).encode('utf-8'))
    if notice_sig not in shipped['known_notice_signatures']:
        raise ValueError('Unrecognized NOTICE terms; no automatic repair attempted.')
    for name in ('README.md', 'NOTICE', 'pyproject.toml'):
        if DOI not in docs[name]:
            raise ValueError(f'Missing agreed Code Ocean link in {name}. No files changed.')
    if '## Acknowledgments' in docs['README.md'] or '## Acknowledgements' in docs['README.md']:
        raise ValueError('This is not the requested post-review README. No files changed.')

    plan = []
    for name in CHANGED:
        data = U.verified_payload(U.safe_path(SOURCE, name).read_bytes(),
                                  shipped['payload_files'][name], name)
        old = guards[name]
        if old != data:
            plan.append((name, old, data))
    manifest_bytes, _ = U.manifest_for_updated_checkout(repo, shipped, plan)
    if old_manifest != manifest_bytes:
        plan.append(('scripts/update_manifest.json', old_manifest, manifest_bytes))
    print('STCA 1.0: explicit UTF-8 file I/O repair')
    print('Repository:', repo)
    print('Local commit:', git_head(repo))
    print('Stale document hashes:', ', '.join(stale) or 'none')
    for name, old, new in plan:
        print(('ADD ' if old is None else 'UPDATE ') + name)
    print('README, LICENSE, NOTICE, project metadata, .git and all scientific files stay untouched.')
    if not args.apply:
        print('DRY RUN ONLY. Add --apply to back up and repair these engineering files.')
        return 0
    if not plan:
        print('Already repaired; no changes.')
        return 0
    # Check the full inspected state before touching the target, not just the
    # changed engineering files. Backups are outside the Git working tree.
    for name, expected in guards.items():
        path = U.safe_path(repo, name)
        actual = path.read_bytes() if path.exists() else None
        if actual != expected:
            raise ValueError(f'File changed during preflight: {name}. Nothing written.')
    backup = repo.parent / ('STCA_UTF8_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir()
    for name, old, new in plan:
        if old is not None:
            path = backup / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(old)
    (backup / 'repair.json').write_text(json.dumps({
        'repo': str(repo), 'local_commit': git_head(repo), 'stale_document_hashes': stale,
        'files': [{'file': name, 'was_new': old is None} for name, old, new in plan],
        'remote_actions_verified': False,
    }, indent=2) + '\n', encoding='utf-8')
    written = []
    try:
        for name, old, new in plan:
            path = U.safe_path(repo, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            written.append((path, old))
            path.write_bytes(new)
    except BaseException:
        for path, old in reversed(written):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise
    print('APPLIED. Backup:', backup)
    print('No network request, Git commit/push, data upload or PyPI publication was performed.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'UTF8 REPAIR BLOCKED: {exc}', file=sys.stderr)
        raise SystemExit(2)
