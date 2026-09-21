# GitHub and PyPI release guide — STCA 1.0

Package: `polymer-stca` · Import: `stca` · Version: **1.0**

Repository: https://github.com/foukusa/polymer-stca

Existing GitHub Desktop checkout: **`D:\hongo\polymer-stca`**

## Repository layout and local update

`STCA_1.0_GitHub.zip` contains the repository files at the ZIP root. The resulting
checkout must have `D:\hongo\polymer-stca\pyproject.toml` and
`D:\hongo\polymer-stca\src\stca`. There is no second enclosing project directory.
Keep `.git` and local/private data. Follow [LOCAL_UPDATE.md](LOCAL_UPDATE.md) for a
staged update with conflict checking and backups. Do not initialize another Git
repository and do not use a directory-mirroring command that deletes other files.

After local verification, use GitHub Desktop to review changes, commit to the
intended branch and **Push origin**. Neither editing local files nor committing
alone updates the remote repository. Once the actual source commit is published,
create a tag/release named `v1.0` for a reproducible source installation:

```bash
python -m pip install "polymer-stca[chem] @ https://github.com/foukusa/polymer-stca/archive/refs/tags/v1.0.zip"
```

That command is available only after the tag exists and the installer has access
to the repository. Pushing to GitHub does not by itself register a PyPI package.

## Test and build locally on Windows

Use PowerShell in the real checkout. Python 3.10.6 is supported by the configured
development dependencies. The following commands use a dedicated environment,
without an activation step:

```powershell
Set-Location "D:\hongo\polymer-stca"
$ErrorActionPreference = "Stop"
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Previous command failed." } }
python -m venv .venv
Check-Exit
$P = (Resolve-Path ".\.venv\Scripts\python.exe").Path
& $P -m pip install --upgrade pip
Check-Exit
& $P -m pip install ".[chem,dev]"
Check-Exit
& $P -m pip check
Check-Exit
& $P -m pytest -q
Check-Exit
& $P -m stca --version
Check-Exit
& $P -m stca paper-audit
Check-Exit

# A fresh output directory prevents accidentally uploading unrelated files.
$Dist = Join-Path $env:TEMP ("STCA_build_" + [guid]::NewGuid().ToString("N"))
& $P -m build --outdir $Dist
Check-Exit
$Wheel = Join-Path $Dist "polymer_stca-1.0-py3-none-any.whl"
$Sdist = Join-Path $Dist "polymer_stca-1.0.tar.gz"
& $P -m twine check --strict $Wheel $Sdist
Check-Exit
```

The version command must print `1.0`. `paper-audit` is a static SI rule check;
for a fresh real-data refit, use the separately retained author result ZIPs:

```powershell
& $P -m stca verify-results --reference-dir "D:\hongo\STCA_reference_archives" --output "D:\hongo\STCA_verified_1.0"
Check-Exit
```

Use a new, empty output path for each verification. This last command reads
private data but does not publish it. See `VERIFIED_RESULTS.md` for protocol and
selection-label boundaries.

## Install the built wheel in a separate environment

Continue in the same PowerShell window so `$P`, `$Wheel` and `$Sdist` are defined:

```powershell
$CheckDir = Join-Path $env:TEMP ("STCA_install_" + [guid]::NewGuid().ToString("N"))
& $P -m venv $CheckDir
Check-Exit
$C = Join-Path $CheckDir "Scripts\python.exe"
& $C -m pip install --upgrade pip
Check-Exit
& $C -m pip install "${Wheel}[chem]"
Check-Exit
& $C -m pip check
Check-Exit
& $C -m stca --version
Check-Exit
& $C -m stca profiles
Check-Exit
& $C -m stca paper-audit
Check-Exit
```

For scientific package acceptance, also run the same `verify-results` command
with `$C` and a new output path. A successful import is not a substitute for
rule, label and per-material parity.

## Authorization and metadata

Before any public upload, confirm the supplied `LICENSE`, institutional
permissions, the scientific scope and control of the PyPI project name. A
software version number is not proof of distribution authorization or scientific
validity. Do not replace the license with MIT, Apache or GPL.

The optional local gate reads `RELEASE_APPROVAL.json`. Copy the template only when
an authorized maintainer can truthfully confirm all three conditions:

```powershell
Copy-Item "docs\RELEASE_APPROVAL.json.example" "RELEASE_APPROVAL.json"
# Review/edit this file; do not set confirmations merely to bypass a check.
& $P scripts/check_public_release.py
Check-Exit
```

No approval file or real account token is shipped. The gate can inspect local
metadata; it cannot certify remote ownership or grant permission.

## TestPyPI trial publication

Register at https://test.pypi.org/account/register/ and prepare its own API token.
Never put tokens in repository files or commit history. At the password prompt,
use the TestPyPI token, with username `__token__`:

```powershell
& $P -m twine upload --repository-url https://test.pypi.org/legacy/ --username __token__ $Wheel $Sdist
Check-Exit

# Dependencies were prepared above; fetch only this package from the test index.
& $C -m pip uninstall -y polymer-stca
Check-Exit
& $C -m pip install --no-cache-dir --no-deps --index-url https://test.pypi.org/simple/ "polymer-stca==1.0"
Check-Exit
& $C -m pip check
Check-Exit
& $C -m stca --version
Check-Exit
& $C -m stca paper-audit
Check-Exit
```

Repeat real-data verification with this server-installed package before the
production upload. Do not rebuild different files between trial and production.

## Publish the same verified files to PyPI

Use a separate account/token for https://pypi.org/account/register/. Confirm the
project name is available or under the maintainer's control. GitHub ownership
does not reserve the same PyPI name.

```powershell
& $P -m twine upload --repository-url https://upload.pypi.org/legacy/ --username __token__ $Wheel $Sdist
Check-Exit
```

Only after successful publication is this name-based install command valid:

```bash
python -m pip install "polymer-stca[chem]==1.0"
```

Verify that command in a clean environment and repeat the fixed real-data
regression. PyPI does not allow replacement of an already uploaded filename;
do not try to overwrite a published `1.0` file with different contents.

The optional `.github/workflows/publish.yml.example` remains inactive until
renamed and paired with a correctly authorized PyPI Trusted Publisher. Publishing
configuration is separate from normal testing and local installation.

## Official references

- PyPA project metadata: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- Build and publication: https://packaging.python.org/en/latest/tutorials/packaging-projects/
- TestPyPI: https://packaging.python.org/en/latest/guides/using-testpypi/
- PyPI account and file rules: https://pypi.org/help/
- GitHub Desktop commits and pushes: https://docs.github.com/en/desktop/making-changes-in-a-branch/committing-and-reviewing-changes-to-your-project-in-github-desktop
