# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

"""Regression tests for the concrete README calls and release-only metadata gate."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from stca import ScreeningModel, __version__, load_pretrained

ROOT = Path(__file__).resolve().parents[1]
TITLE = ("Interpretable Substructure-Based Screening of Multi-Property Polymer "
         "Dielectrics with Prompt-Ready Rules for Rational Design")


def _gate():
    spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts/check_public_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_gate_fixture(root: Path) -> None:
    for name in ("LICENSE", "NOTICE", "CITATION.md"):
        shutil.copy2(ROOT / name, root / name)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture-project"\nversion = "0.0.0"\n'
        'license = "LicenseRef-STCA-Academic-Peer-Review"\n'
        'license-files = ["LICENSE", "NOTICE"]\n'
        'maintainers = [{name = "Fixture", email = "fixture@example.org"}]\n',
        encoding="utf-8",
    )


def test_readme_attribution_and_license_are_consistent():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8").strip()
    assert license_text in readme
    assert TITLE in readme
    assert "npj Computational Materials" in readme
    assert "Nature Computational Science" not in readme
    assert "mailto:wang@hvg.t.u-tokyo.ac.jp" in readme
    assert "Kumada-Sato-Fujii-Umemoto Laboratory" in readme
    assert not re.search(r"[\u4e00-\u9fff]", readme)
    assert not (ROOT / "README_zh.md").exists()


def test_pyproject_license_and_version():
    # Python 3.10 compatibility without adding a toml parser to runtime dependencies.
    content = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in content
    assert 'license = "LicenseRef-STCA-Academic-Peer-Review"' in content
    assert 'license-files = ["LICENSE", "NOTICE"]' in content
    assert 'wang@hvg.t.u-tokyo.ac.jp' in content


def test_readme_list_screen_columns():
    pytest.importorskip("rdkit")
    model = load_pretrained("tg-high", warn=False)
    result = model.screen(["*CC*", "*CCO*", "*c1ccc(cc1)*"], tier=0.20)
    assert len(result[["smiles", "input_valid", "selected", "rule_name",
                       "missing_required_present", "unexpected_present"]]) == 3


def test_readme_csv_id_alignment(tmp_path):
    pytest.importorskip("rdkit")
    candidates = pd.DataFrame({"ID": ["candidate_1", "candidate_2", "candidate_3"],
                               "SMILES": ["*CC*", "*CCO*", "*c1ccc(cc1)*"]})
    result = load_pretrained("ec-low", warn=False).screen(candidates["SMILES"], tier=0.10)
    result.insert(0, "ID", candidates["ID"].to_numpy())
    result.to_csv(tmp_path / "screen.csv", index=False)
    assert pd.read_csv(tmp_path / "screen.csv")["ID"].tolist() == candidates["ID"].tolist()


def test_readme_invalid_row_report():
    pytest.importorskip("rdkit")
    result = load_pretrained("ec-low", warn=False).screen(
        ["*CC*", "not_a_smiles"], tier=0.10, errors="report")
    assert len(result[["input_valid", "selected", "input_error"]]) == 2
    assert pd.isna(result.loc[1, "selected"])
    assert result.loc[1, "input_error"] == "invalid_or_empty_smiles"


def test_readme_joint_mask():
    pytest.importorskip("rdkit")
    smiles = ["*CC*", "*CCO*", "*c1ccc(cc1)*"]
    tg = load_pretrained("tg-high", warn=False).screen(smiles, tier=0.20)
    ec = load_pretrained("ec-low", warn=False).screen(smiles, tier=0.10)
    joint = tg["selected"] & ec["selected"]
    assert len(joint) == 3 and joint.dtype == "boolean"


def test_bundled_synthetic_smiles_demo(tmp_path):
    pytest.importorskip("rdkit")
    run = subprocess.run([sys.executable, str(ROOT / "examples/train_smiles_demo.py")],
                         cwd=tmp_path, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    base = tmp_path / "runs/synthetic_smiles"
    model = ScreeningModel.load(base / "model.json")
    assert model.provenance["n_source_records"] == 24
    metrics = json.loads((base / "metrics.json").read_text())
    assert metrics["n"] == 6
    assert metrics["group_overlap_audit"] == "disjoint"
    assert "SYNTHETIC SOFTWARE DEMO ONLY" in run.stdout
    assert len(pd.read_csv(base / "screen.csv")) == 6


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Release-only tool requires Python 3.11+")
def test_release_gate_keeps_unapproved_fixture_blocked(tmp_path):
    _write_gate_fixture(tmp_path)
    missing = _gate().check(tmp_path)
    assert any("Repository URL" in x for x in missing)
    assert any("public_distribution_authorized" in x for x in missing)


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Release-only tool requires Python 3.11+")
def test_release_gate_accepts_explicit_fixture_not_real_authorization(tmp_path):
    # These values are a temporary software fixture, never a project approval.
    _write_gate_fixture(tmp_path)
    with (tmp_path / "pyproject.toml").open("a", encoding="utf-8") as f:
        f.write('\n[project.urls]\nRepository = "https://github.com/fixture-owner/fixture-repo"\n')
    (tmp_path / "RELEASE_APPROVAL.json").write_text(json.dumps({
        "profile_scope_reviewed": True,
        "public_distribution_authorized": True,
        "pypi_project_name_confirmed": True,
    }))
    assert _gate().check(tmp_path) == []


def test_publish_workflow_permissions_are_separated():
    # The same tests must remain valid after authorized activation of the template.
    p = ROOT / ".github/workflows/publish.yml.example"
    if not p.exists():
        p = ROOT / ".github/workflows/publish.yml"
    text = p.read_text(encoding="utf-8")
    assert "types: [published]" in text
    assert "  build:" in text and "  publish:" in text
    assert "id-token: write" not in text.split("  publish:")[0]
    assert "environment: pypi" in text
