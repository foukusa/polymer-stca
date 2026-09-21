# Update the existing GitHub Desktop checkout

**Destination: `D:\hongo\polymer-stca`**

`STCA_1.0_GitHub_Documentation.zip` has no enclosing project directory. Its root contains
`pyproject.toml`, `README.md`, `LICENSE`, `src/`, `tests/`, `scripts/`, `docs/`
and `.github/`. Do not create another `polymer-stca` inside the existing checkout.

Use a staging directory for the guarded updater rather than extracting with
blind overwrite. Save the ZIP in your Downloads folder, then paste this into
PowerShell (not a Python `>>>` prompt):

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Repo = "D:\hongo\polymer-stca"
    $Zip = Join-Path $env:USERPROFILE "Downloads\STCA_1.0_GitHub_Documentation.zip"
    $Stage = Join-Path $env:TEMP ("STCA_update_" + [guid]::NewGuid().ToString("N"))
    if (-not (Test-Path -LiteralPath "$Repo\pyproject.toml")) { throw "Project root not found: $Repo" }
    if (-not (Test-Path -LiteralPath "$Repo\.git")) { throw "Not the GitHub Desktop checkout: $Repo" }
    if (-not (Test-Path -LiteralPath $Zip -PathType Leaf)) { throw "Download the source ZIP first: $Zip" }
    Expand-Archive -LiteralPath $Zip -DestinationPath $Stage
    python "$Stage\scripts\apply_update.py" --repo "$Repo" --update-license
    if ($LASTEXITCODE -ne 0) { throw "Preflight failed; repository not changed." }
    python "$Stage\scripts\apply_update.py" --repo "$Repo" --update-license --apply
    if ($LASTEXITCODE -ne 0) { throw "Update failed; inspect the reported conflict." }
    Set-Location -LiteralPath $Repo
    python -m pip install ".[chem,dev]"
    if ($LASTEXITCODE -ne 0) { throw "Installation failed." }
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; do not publish." }
    python -m stca --version
    if ($LASTEXITCODE -ne 0) { throw "Version check failed." }
}
```

The updater leaves `.git`, raw inputs, private results and unlisted files alone.
It preserves contact details and project URLs. The explicit `--update-license`
option migrates the known peer-review-only license to the supplied academic-use
terms and updates NOTICE, while retaining the institutional copyright line.
Unknown local license or notice changes stop preflight for manual review.
Without this option, existing matching academic-use terms are preserved.
Existing source edits must match a recognized input; unrecognized edits stop the
entire preflight before any repository file is changed. Recognized obsolete
package documentation is backed up before retirement, not silently deleted.
Backups are created alongside the checkout as `STCA_update_backup_<timestamp>`.
The process does not stage a Git commit, push, upload data or publish to PyPI.

After tests complete, review the changes in GitHub Desktop, commit and click
**Push origin**. The suggested commit message is `Prepare STCA 1.0`.
