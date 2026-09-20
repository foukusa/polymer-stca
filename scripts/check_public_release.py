# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

"""A maintainer metadata/permission gate, not a scientific certification.

This script is not run during installation. It reads local metadata only and
cannot determine ownership of a remote repository or availability of a PyPI name.
"""
from pathlib import Path
import json
import sys
from urllib.parse import urlparse

try:
    import tomllib
except ImportError:
    raise SystemExit("Run this release-only check with Python 3.11 or later.")

PAPER_TITLE = (
    "Interpretable Substructure-Based Screening of Multi-Property Polymer "
    "Dielectrics with Prompt-Ready Rules for Rational Design"
)


def check(root: Path) -> list[str]:
    meta = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    missing = []
    if not (root / "LICENSE").is_file():
        missing.append("maintainer-supplied LICENSE")
    if not meta.get("license") or not meta.get("license-files"):
        missing.append("license expression and license-file metadata")
    contacts = meta.get("maintainers", []) + meta.get("authors", [])
    if not any(c.get("name") and c.get("email") for c in contacts):
        missing.append("verified software maintainer/author name and email")
    repository = meta.get("urls", {}).get("Repository", "")
    parsed = urlparse(repository)
    if (parsed.scheme != "https" or not parsed.netloc or not parsed.path.strip("/")
            or any(s in repository.upper() for s in ("YOUR_", "REPLACE_", "EXAMPLE."))):
        missing.append("actual HTTPS Repository URL in [project.urls]")
    citation = root / "CITATION.md"
    text = citation.read_text(encoding="utf-8") if citation.exists() else ""
    if PAPER_TITLE not in text or "npj Computational Materials" not in text:
        missing.append("associated manuscript title and journal in CITATION.md")
    try:
        approval = json.loads((root / "RELEASE_APPROVAL.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        approval = {}
    if not isinstance(approval, dict):
        approval = {}
    for key, explanation in (
        ("profile_scope_reviewed", "reviewed archive/model scope"),
        ("public_distribution_authorized", "authorization for public distribution under the supplied terms"),
        ("pypi_project_name_confirmed", "available or maintainer-controlled PyPI project name"),
    ):
        if approval.get(key) is not True:
            missing.append(f"RELEASE_APPROVAL.json: {key}=true after confirming {explanation}")
    return missing


def main() -> int:
    missing = check(Path(__file__).resolve().parents[1])
    if missing:
        print("Public release is not approved. Local and authorized GitHub installs are unaffected.")
        print("\n".join("- " + item for item in missing))
        return 2
    print("Maintainer metadata gate passed; remote ownership and scientific performance are not independently certified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
