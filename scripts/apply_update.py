# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
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
LICENSE_ID = 'LicenseRef-STCA-Academic-NonCommercial'
LEGACY_LICENSE_ID = 'LicenseRef-STCA-Academic-Peer-Review'
LEGACY_LICENSE = (
    'Copyright (c) 2025, The University of Tokyo, University College London\n\n'
    'This code is provided for academic peer review purposes under npj '
    'Computational Materials submission guidelines. Commercial use and '
    'redistribution require written permission.\n'
)
COPYRIGHT_LINE = re.compile(
    r'^Copyright \(c\) ([0-9]{4}(?:[-–][0-9]{4})?), '
    r'The University of Tokyo, University College London$', re.MULTILINE)



def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def lf_text(content: bytes) -> bytes:
    """Canonicalize CRLF only, for manifest-declared UTF-8 text.

    Do not strip whitespace, a BOM, or standalone CR bytes: those are content
    changes, not Git's LF/CRLF conversion. Binary payloads never use this path.
    """
    content.decode('utf-8')  # Reject invalid UTF-8 rather than guess an encoding.
    if b'\x00' in content:
        raise ValueError('NUL byte in a manifest-declared text payload.')
    return content.replace(b'\r\n', b'\n')


def verified_payload(content: bytes, item: dict, relative: str) -> bytes:
    """Check the shipped digest without rejecting a Windows text checkout.

    The distributed reference text is LF. Only entries explicitly marked
    utf8-lf permit CRLF -> LF before hashing. All other bytes remain significant,
    and exact/binary entries retain byte-for-byte verification.
    """
    mode = item.get('hash_mode', 'exact')
    try:
        if mode == 'utf8-lf':
            checked = lf_text(content)
        elif mode == 'exact':
            checked = content
        else:
            raise ValueError(f'Unknown payload hash mode: {mode}')
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f'Damaged update payload: {relative}') from exc
    if sha(checked) != item['new_sha256']:
        raise ValueError(f'Damaged update payload: {relative}')
    return checked


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
    if sha(content) in hashes:
        return True
    if item.get('hash_mode') == 'utf8-lf':
        try:
            if sha(lf_text(content)) in hashes:
                return True
        except (UnicodeError, ValueError):
            return False
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
        license_rx = r'(?m)^(license\s*=\s*")([^"\n]+)("[^\n]*)$'
        licenses = re.findall(license_rx, block)
        if len(licenses) != 1 or licenses[0][1] not in (LICENSE_ID, LEGACY_LICENSE_ID):
            raise ValueError('Unrecognized license metadata; merge pyproject.toml explicitly.')
        block = re.sub(license_rx, lambda m: m[1] + LICENSE_ID + m[3], block)
        block = block.replace(
            'Interpretable STCA rule screening with archived Tg/EC profiles and custom-data training',
            'Interpretable polymer screening with pretrained Tg/EC rules and custom-data training')
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
    def urls(block):
        expected = 'https://doi.org/10.24433/CO.1601774.v1'
        rx = r'(?m)^"Code Ocean"\s*=\s*"([^"\n]+)"[^\n]*$'
        values = re.findall(rx, block)
        if len(values) > 1 or (values and values[0] != expected):
            raise ValueError('Conflicting Code Ocean URL; merge pyproject.toml explicitly.')
        if not values:
            return block.rstrip() + '\n"Code Ocean" = "' + expected + '"\n\n'
        return block
    return section_edit(text, 'project.urls', urls)


def md_section(text: str, heading: str) -> str | None:
    match = re.search(r'(?m)^## ' + re.escape(heading) + r'\s*$', text)
    if not match:
        return None
    tail = text[match.end():]
    end = re.search(r'(?m)^## ', tail)
    return tail[:end.start() if end else len(tail)].strip()


def readme_edit(old: str, license_text: str) -> str:
    new = (SOURCE / 'README.md').read_text(encoding='utf-8')
    for heading in ('Contact',):
        existing, current = md_section(old, heading), md_section(new, heading)
        if existing and current:
            new = new.replace(current, existing, 1)
    section = md_section(new, 'License')
    if not section:
        raise ValueError('Source README has no License section.')
    return new.replace(section, license_text.strip(), 1)


def license_signature(text: str) -> str:
    """Compare known terms without changing the maintainer's copyright year."""
    text = text.replace('\r\n', '\n').strip()
    if len(COPYRIGHT_LINE.findall(text)) != 1:
        raise ValueError('Expected the supplied institutional copyright line.')
    return COPYRIGHT_LINE.sub(
        'Copyright (c) YEAR, The University of Tokyo, University College London', text)


def license_plan(repo: Path, rules: dict, update_license: bool):
    current = safe_path(repo, 'LICENSE').read_bytes()
    notice = safe_path(repo, 'NOTICE').read_bytes()
    supplied = (SOURCE / 'LICENSE').read_text(encoding='utf-8')
    actual = current.decode('utf-8-sig').replace('\r\n', '\n')
    desired = license_signature(supplied)
    actual_signature = license_signature(actual)
    if not update_license:
        if actual_signature != desired:
            raise ValueError(
                'LICENSE_UPDATE_REQUIRED: review the supplied academic-use LICENSE '
                'and add --update-license to migrate the previous permission terms. '
                'No files were changed.')
        return current, notice
    if actual_signature not in (desired, license_signature(LEGACY_LICENSE)):
        raise ValueError('LOCAL_LICENSE_CONFLICT: unrecognized terms; merge LICENSE explicitly.')
    copyright_line = COPYRIGHT_LINE.search(actual).group(0)
    updated = COPYRIGHT_LINE.sub(lambda _: copyright_line, supplied).encode('utf-8')
    notice_signature = sha(license_signature(notice.decode('utf-8-sig')).encode('utf-8'))
    if notice_signature not in rules['known_notice_signatures']:
        raise ValueError('LOCAL_NOTICE_CONFLICT: unrecognized NOTICE edits; merge it explicitly.')
    new_notice = COPYRIGHT_LINE.sub(
        lambda _: copyright_line, (SOURCE / 'NOTICE').read_text(encoding='utf-8'))
    return updated, new_notice.encode('utf-8')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=r'D:\hongo\polymer-stca')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--update-license', action='store_true',
                        help='Explicitly apply the maintainer-supplied academic-use LICENSE/NOTICE.')
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
    # Specially merged documents are checked just like ordinary payload text.
    for relative, item in rules.get('reference_files', {}).items():
        verified_payload(safe_path(SOURCE, relative).read_bytes(), item, relative)
    plan = []
    def add(relative, new):
        target = safe_path(repo, relative)
        old = target.read_bytes() if target.exists() else None
        if old != new:
            plan.append((relative, old, new))
    # Permission changes require explicit opt-in; unknown terms are never replaced.
    for relative in ('LICENSE', 'NOTICE'):
        if not safe_path(repo, relative).is_file():
            raise ValueError(f'Missing protected license file: {relative}')
    license_bytes, notice_bytes = license_plan(repo, rules, args.update_license)
    add('LICENSE', license_bytes)
    add('NOTICE', notice_bytes)
    # Snapshot package labels can change; the scientific JSON must not change.
    for relative, digest in rules['protected_scientific_assets'].items():
        path = safe_path(repo, relative)
        if not path.is_file() or normalized_json(path.read_bytes()) != digest:
            raise ValueError(f'Changed or missing SI rule snapshot: {relative}. No files were changed.')
    for relative, item in rules['payload_files'].items():
        payload = verified_payload(
            safe_path(SOURCE, relative).read_bytes(), item, relative)
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
    add('README.md', readme_edit(old_readme, license_bytes.decode('utf-8-sig')).encode())
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
    print('.git, local data/results, contact details and existing project URLs are preserved.')
    print('Academic-use LICENSE/NOTICE migration explicitly enabled.' if args.update_license
          else 'Existing academic-use LICENSE and NOTICE are preserved.')
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
