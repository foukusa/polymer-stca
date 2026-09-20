# Local validation — 0.1.0rc2

Date: 2026-09-20.

## Executed checks

| Check | Result |
|---|---|
| Source-tree pytest suite | **64 passed** |
| Same suite against a separately installed wheel, outside the source tree | **64 passed** |
| Same suite after simulated publish-template activation in a disposable fixture | **64 passed**; not real release authorization |
| Wheel build through pip's PEP 517 interface, without build isolation | Passed |
| Wheel install into a separate target directory | Passed |
| Module location and version after installation | Verified: independent installation, `0.1.0rc2` |
| Installed `stca --version`, screening CLI, synthetic training CLI and evaluation CLI | Passed |
| All three bundled example scripts against the installed wheel | Passed |
| Local Git repository, tag, and `pip install ... git+file://...@v0.1.0rc2` | Passed; no remote GitHub access or upload |
| Wheel core metadata validation using `packaging.metadata.Metadata` | Passed |
| `License-Expression`, LICENSE/NOTICE inclusion, wheel RECORD sizes/hashes | Passed |
| Source distribution build and wheel rebuild from the extracted sdist | Passed |
| README local-document links and Python example syntax | Passed |
| Original rc1 vs rc2 package-code AST comparison | Identical except the package version constant |
| Original rc1 vs rc2 archived JSON files | All three byte-for-byte identical |
| Delivered public-release gate | Correctly blocks missing remote URLs and unconfirmed authorization/name/scope flags |

The 54 original tests remain, with 10 additional documented-usage/release tests.
The new tests cover README attribution, version/license metadata, exact output
columns, ID alignment, invalid-input reporting, joint masks, the synthetic SMILES
demo, and release tooling. Temporary positive-approval fixtures exist only inside
local tests; the delivered repository contains **no affirmative release approval**.

## Tested environment

Linux; CPython 3.13.5; NumPy 2.3.5; pandas 2.2.3; SciPy 1.17.0;
RDKit 2025.09.4; pytest 9.0.2; setuptools 82.0.1; packaging 25.0; pip 25.1.1.
Wheel construction used the available setuptools backend and its wheel support.

Installation tests used `--no-deps` with existing scientific dependencies. The
builds used `--no-build-isolation`; this is not a fresh online resolution of the
full dependency set on a pristine operating system. The optional `build` frontend
and `twine` were not available in this runtime, so `python -m build` and
`python -m twine check` were **not executed here**. Their standard commands remain
in the maintainer guide and CI configuration; do not interpret them as local
passes. Wheel metadata was checked separately with `packaging.metadata`.

## Scientific boundaries

The original threshold-frequency, signed-prefix, EC-role, cutoff, rule-freezing,
serialization, group-audit, strict PID, invalid-input and archive-mask tests are
retained. They verify implementation behavior, not original-data performance.

No complete original Tg/EC measurement input/result set was executed for this
update. Original TP/FP/MCC/F1 tables and final-paper numerical reproduction remain
unverified. The three built-in assets retain their SI-20260822 core-scope archive
status and missing historical numeric cutoffs. They were not promoted to final
paper models by this documentation release.

The examples' synthetic targets are software fixtures, not measured material
properties and not scientific benchmarks. Local tests also do not establish
Windows/macOS compatibility or every permitted Python/dependency combination.
Remote CI jobs, PyPI/TestPyPI uploads and GitHub publication were not performed.

## Re-run locally

With online dependency access and the appropriate permission:

```bash
python -m pip install ".[chem,dev]"
python -m pytest -q
python examples/screen_profiles.py
python examples/train_binary_demo.py
python examples/train_smiles_demo.py
python -m build
python -m twine check dist/*
```

Before any public upload, separately review `docs/RELEASING.md`, the real metadata,
license compatibility and public-distribution authorization. A successful local
build does not establish those facts.
