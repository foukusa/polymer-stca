# Executed validation — STCA 1.0

Date: 2026-09-21. Existing GitHub Desktop checkout:
**`D:\hongo\polymer-stca`**. The source ZIP places repository files directly at
its root; no additional enclosing project directory is required.

## Documentation and licensing maintenance

The README now focuses on installation, screening, and custom training. It
announces the planned PyPI release, links the maintainer-supplied Code Ocean
DOI, and omits acknowledgments. LICENSE, NOTICE, Python package metadata and
source copyright headers use the non-commercial academic-use terms.

The maintenance check ran **186 tests successfully** in the Linux/Python 3.13.5
runtime, including the README examples, license migration, Git newline handling,
and preservation of private data and local contact information. The existing
scientific package's **20 Python ASTs are unchanged**, and all **13 asset files**
are byte-identical. No new scientific refit was required or claimed.

The Code Ocean URL was supplied by the maintainer. Its landing page and hosted
execution were not verified in this runtime; it is not substituted for the
article DOI. No GitHub push or PyPI upload was performed.

## Retained scientific and package-validation record

| Check | Result |
|---|---|
| Runtime, package metadata, citation and packaged model version fields | 1.0 throughout |
| Source test suite | 148 passed |
| Installed wheel, tests launched outside source directory | 148 passed |
| Fresh refit from the five author-provided result archives | PASS_RULE_FAMILY_SCORE_PARITY |
| Installed-wheel refit from the same archives | PASS_RULE_FAMILY_SCORE_PARITY |
| Paper-protocol final rules | 11 / 11 match |
| Matched source-locked final rules | 11 / 11 match |
| Archived rule/scope metric rows | 1,251 / 1,251 match |
| Saved-recipe refit consistency | 6 / 6 models match |
| Model and family JSON semantics versus the supplied verified artifacts | Unchanged after excluding package-version metadata |
| Update applied to three recognized supplied source trees | All succeed, idempotent; Git config and private-data fixtures preserved |
| Unknown source edits / modified scientific snapshots / wrong target path | Refused before repository writes |
| Source Python 3.10 grammar parsing | Passed; not a Python 3.10 execution test |

The complete test suite includes the new single-version, repository-layout and
safe-updater regression tests, not only the numerical training tests. Source and
wheel refits regenerate fingerprints and train from measured labels; they do not
inject the saved reference winner. Model rules, cutoffs, families and scientific
selection logic were not changed by the requested directory/version alignment.

## Packaging and hash semantics

All model `package_version` fields are 1.0. The three archived SI snapshots keep
all their scientific JSON fields unchanged. Their distributed-file hashes were
therefore updated to identify the actual STCA 1.0 bytes, not misreported as the
byte hashes of differently labeled files. `paper-audit` still independently
checks rule literals and file integrity. It is not itself a fresh numerical fit.

The public ZIP/wheel contain no raw author measurement tables, PID/SMILES tables,
private input archives or per-material evaluation outputs. The aggregate files
in `validation/` record the numerical checks. Versioning and packaging do not
grant public-distribution permission; supplied license terms are retained.

## Environment and limits

The executed environment is Linux, CPython 3.13.5, NumPy 2.3.5, pandas 2.2.3,
SciPy 1.17.0 and RDKit 2025.09.4. The installed-wheel environment reused those
local dependencies via an explicit dependency path; it was not a fresh online
dependency-resolution test. Wheel and source distributions were built with the
installed setuptools build backend. The build/Twine frontend commands documented
for maintainers were not executed here because those frontend tools were not
installed in this runtime.

The PowerShell transcript and GitHub Actions have **not** run on the user's
Windows machine in this session. The Python 3.10.6 CI is provided for that check.
No remote GitHub push or PyPI upload was performed.

The archived core protocol uses historical extra labels in representative
selection, so the parity results are not untouched-test accuracy claims. The EC
split is reconstructed from row order and gated against the archived metrics;
thermal precomputed coefficients are not identical to a fresh scan even though
the used rankings and final results agree. These qualifications, and the SI
analyses not rerun, remain in `docs/VERIFIED_RESULTS.md`.
