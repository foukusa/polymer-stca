# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
"""Stage STCA 1.0 directly in an existing checkout; dry-run by default.

No network, Git operations, data deletion or automatic publication. Unknown
source edits stop preflight. Only explicitly listed files are changed, with
backups and rollback on write failure. Run from a staged copy outside the target.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

SOURCE = Path(__file__).resolve().parents[1]
MANIFEST = SOURCE / 'scripts/update_manifest.json'
VERSION = '1.0'


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def asthash(content: bytes) -> str | None:
    try:
        tree = ast.parse(content.decode('utf-8-sig'))
        return sha(ast.dump(tree, include_attributes=False).encode())
    except (SyntaxError, UnicodeError):
        return None


def normalized_json(content: bytes) -> str:
    doc = json.loads(content.decode('utf-8-sig'))
    doc.pop('package_version', None)
    return sha(json.dumps(doc, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())


def safe_path(root: Path, relative: str) -> Path:
    rel = PurePosixPath(relative)
    if (rel.is_absolute() or not rel.parts or any(p in ('', '.', '..', '.git') for p in rel.parts)
            or '\\' in relative or ':' in relative):
        raise ValueError(f'Unsafe update path: {relative}')
    path = root.joinpath(*rel.parts)
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'Update path escapes repository: {relative}')
    for item in [path, *path.parents]:
        if item == root:
            break
        if item.is_symlink():
            raise ValueError(f'Refusing symbolic link: {relative}')
        if item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Refusing reparse-point update: {relative}')
    if path.exists() and not path.is_file():
        raise ValueError(f'Expected file, not directory: {relative}')
    return path


def accepted(content: bytes, item: dict, relative: str) -> bool:
    hashes = item.get('accepted_sha256', [])
    if sha(content) in hashes or sha(content.replace(b'\r\n', b'\n')) in hashes:
        return True
    if relative.endswith('.py'):
        value = asthash(content)
        return bool(value and value in item.get('accepted_ast_sha256', []))
    return False


def section_edit(text: str, name: str, edit) -> str:
    pattern = re.compile(r'(?m)^\[' + re.escape(name) + r'\][^\n]*\n')
    match = pattern.search(text)
    if not match:
        raise ValueError(f'Missing [{name}] section; no automatic rewrite attempted.')
    end = re.search(r'(?m)^\[', text[match.end():])
    stop = match.end() + end.start() if end else len(text)
    return text[:match.end()] + edit(text[match.end():stop]) + text[stop:]


def pyproject_edit(text: str) -> str:
    def version(block):
        rx = r'(?m)^(version\s*=\s*")[^"]+("[^\n]*)$'
        if len(re.findall(rx, block)) != 1:
            raise ValueError('Ambiguous project version in pyproject.toml.')
        block = re.sub(rx, lambda m: m[1] + VERSION + m[2], block)
        # A version label is not a production-maturity certification.
        block = re.sub(r'(?m)^\s*"Development Status :: [^"]+",?\s*\n', '', block)
        return block
    text = section_edit(text, 'project', version)
    def dev(block):
        match = re.search(r'(?ms)^dev\s*=\s*\[(.*?)\]', block)
        if not match:
            raise ValueError('Expected an explicit dev dependency array.')
        if 'tomli' in match[1]:
            return block
        content = match[1].rstrip().rstrip(',') + ', "tomli>=2; python_version < \'3.11\'"'
        return block[:match.start(1)] + content + block[match.end(1):]
    text = section_edit(text, 'project.optional-dependencies', dev)
    if not re.search(r'(?m)^\[project\.urls\]', text):
        text += ('\n[project.urls]\nRepository = "https://github.com/foukusa/polymer-stca"\n'
                 'Issues = "https://github.com/foukusa/polymer-stca/issues"\n')
    return text


def md_section(text: str, heading: str) -> str | None:
    match = re.search(r'(?m)^## ' + re.escape(heading) + r'\s*$', text)
    if not match:
        return None
    tail = text[match.end():]
    end = re.search(r'(?m)^## ', tail)
    return tail[:end.start() if end else len(tail)].strip()


def readme_edit(old: str, license_text: str) -> str:
    new = (SOURCE / 'README.md').read_text(encoding='utf-8')
    for heading in ('Contact', 'Acknowledgments'):
        existing, current = md_section(old, heading), md_section(new, heading)
        if existing and current:
            new = new.replace(current, existing, 1)
    section = md_section(new, 'License')
    if not section:
        raise ValueError('Source README has no License section.')
    return new.replace(section, license_text.strip(), 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=r'D:\hongo\polymer-stca')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if repo == SOURCE or SOURCE.is_relative_to(repo):
        raise ValueError('Stage the update outside the target checkout before running this updater.')
    if not (repo / 'pyproject.toml').is_file():
        raise ValueError(f'Not a project root: {repo}')
    if not (repo / '.git').exists():
        raise ValueError(f'No .git entry: choose the actual GitHub Desktop checkout: {repo}')
    rules = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if rules['version'] != VERSION:
        raise ValueError('Update manifest version mismatch.')
    plan = []
    def add(relative, new):
        target = safe_path(repo, relative)
        old = target.read_bytes() if target.exists() else None
        if old != new:
            plan.append((relative, old, new))
    # LICENSE and NOTICE are retained, not rewritten or deleted.
    for relative in ('LICENSE', 'NOTICE'):
        if not safe_path(repo, relative).is_file():
            raise ValueError(f'Missing protected license file: {relative}')
    # Snapshot package labels can change; the scientific JSON must not change.
    for relative, digest in rules['protected_scientific_assets'].items():
        path = safe_path(repo, relative)
        if not path.is_file() or normalized_json(path.read_bytes()) != digest:
            raise ValueError(f'Changed or missing SI rule snapshot: {relative}. No files were changed.')
    for relative, item in rules['payload_files'].items():
        payload = safe_path(SOURCE, relative).read_bytes()
        if sha(payload) != item['new_sha256']:
            raise ValueError(f'Damaged update payload: {relative}')
        target = safe_path(repo, relative)
        if target.exists():
            old = target.read_bytes()
            if old == payload:
                continue
            if not accepted(old, item, relative):
                raise ValueError(f'LOCAL_EDIT_CONFLICT: {relative}. No files were changed; merge this file explicitly.')
        elif item.get('required_existing'):
            raise ValueError(f'Missing required source file: {relative}')
        add(relative, payload)
    for relative, item in rules.get('retired_files', {}).items():
        target = safe_path(repo, relative)
        if target.exists():
            if not accepted(target.read_bytes(), item, relative):
                raise ValueError(f'LOCAL_EDIT_CONFLICT: {relative}. Refusing to retire edited documentation.')
            add(relative, None)
    pp = safe_path(repo, 'pyproject.toml').read_text(encoding='utf-8-sig')
    if not re.search(r'(?m)^name\s*=\s*"polymer-stca"\s*$', pp):
        raise ValueError('Target project name is not polymer-stca.')
    add('pyproject.toml', pyproject_edit(pp).encode())
    old_readme = safe_path(repo, 'README.md').read_text(encoding='utf-8-sig')
    add('README.md', readme_edit(old_readme, (repo / 'LICENSE').read_text(encoding='utf-8-sig')).encode())
    ignore_path = safe_path(repo, '.gitignore')
    ignore = ignore_path.read_text(encoding='utf-8-sig') if ignore_path.exists() else ''
    extra = [line for line in (SOURCE / '.gitignore').read_text().splitlines()
             if line.strip() and not line.startswith('#') and line not in ignore.splitlines()]
    if extra:
        add('.gitignore', (ignore.rstrip() + '\n\n# STCA local/private artifacts\n' + '\n'.join(extra) + '\n').encode())
    add('scripts/update_manifest.json', MANIFEST.read_bytes())
    print(f'STCA {VERSION}\nRepository root: {repo}\nPlanned changes: {len(plan)}')
    for relative, old, new in plan:
        label = 'RETIRE' if new is None else ('ADD' if old is None else 'UPDATE')
        print(f'{label} {relative}')
    print('.git, local data/results, license text, contact details and project URLs are preserved.')
    if not args.apply:
        print('DRY RUN ONLY. Review this plan, then add --apply.')
        return 0
    if not plan:
        print('Already at STCA 1.0. No changes.')
        return 0
    # Recheck all targets before creating the backup or touching the checkout.
    for relative, old, new in plan:
        path = safe_path(repo, relative)
        current = path.read_bytes() if path.exists() else None
        if current != old:
            raise ValueError(f'File changed during preflight: {relative}. Nothing written.')
    backup = repo.parent / ('STCA_update_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir()
    for relative, old, new in plan:
        if old is not None:
            path = backup / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(old)
    (backup / 'manifest.json').write_text(json.dumps({
        'repo': str(repo), 'target_version': VERSION,
        'files': [{'file': r, 'was_new': o is None, 'removed': n is None,
                   'old_sha256': sha(o) if o is not None else None} for r, o, n in plan]
    }, indent=2), encoding='utf-8')
    written = []
    try:
        for relative, old, new in plan:
            path = safe_path(repo, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            written.append((path, old))
            if new is None:
                path.unlink()
            else:
                path.write_bytes(new)
    except Exception:
        for path, old in reversed(written):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise
    print(f'APPLIED directly in {repo}\nBackup: {backup}')
    print('No Git operation, data upload or PyPI publication was performed.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'UPDATE BLOCKED: {exc}', file=sys.stderr)
        raise SystemExit(2)
