# From a local STCA project to GitHub and pip install

This guide uses `polymer-stca`, version `0.1.0rc2`, and the placeholder `YOUR_GITHUB_USERNAME`. Substitute the real owner/repository and a PyPI distribution name that is available or controlled by the authorized maintainer. Nothing in this delivery creates an account, repository, public release, or name reservation.

## 1. Understand the two installation routes

| Maintainer action | Installation users can perform |
|---|---|
| Upload this installable source tree to a reachable GitHub repository | `python -m pip install "polymer-stca[chem] @ git+https://github.com/YOUR_GITHUB_USERNAME/polymer-stca.git@v0.1.0rc2"` |
| Build and upload this distribution to PyPI | `python -m pip install "polymer-stca[chem]==0.1.0rc2"` |

A GitHub release alone does not put a Python package on PyPI. Conversely, a local wheel can be installed before either remote service is configured. [pip's official VCS guide](https://pip.pypa.io/en/stable/topics/vcs-support/) and [PyPA's packaging tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/) describe the respective mechanisms.

## 2. Check distribution permission before making the repository public

The repository uses the supplied academic-peer-review notice in `LICENSE`, not an MIT/BSD/Apache or unrestricted academic-use license:

> Commercial use and redistribution require written permission.

Before public GitHub or PyPI distribution, the authorized maintainer must confirm the necessary rights and platform terms. Public package indexes are not private peer-review access controls. A PyPI upload grants the service distribution-related rights under its [Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/); verify compatibility with the institutions' authorization instead of treating a successful upload as permission.

The supplied license is recorded as `LicenseRef-STCA-Academic-Peer-Review`, with `LICENSE` and `NOTICE` included in distribution metadata. The identifier denotes the supplied custom text; it is not a claim that the license is OSI-approved. [PyPA supports custom LicenseRef identifiers](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license).

During restricted review, an access-controlled GitHub repository and an authorized direct install may be more appropriate than a public package index. Citation of the paper is separate from permission to use or redistribute the code.

## 3. Upload the source tree to GitHub

### Correct repository layout

Extract `STCA_GitHub_v0.1.0rc2.zip`. Upload the **contents of `STCA_GitHub/`**, not only the ZIP, and not an extra parent directory:

```text
repository root/
  pyproject.toml
  README.md
  LICENSE
  NOTICE
  src/stca/
  examples/
  tests/
  docs/
  scripts/
  .github/workflows/
```

`pyproject.toml` must be visible at the repository root for the installation commands in this guide. GitHub's **Add file → Upload files** is suitable for the visible project files, but ensure hidden files such as `.github` and `.gitignore` are also included. Git commands avoid accidentally omitting those files.

### Git commands

Install Git and authenticate using your normal GitHub credential manager or SSH setup. Create an **empty** GitHub repository named `polymer-stca`; do not initialize it with a second README or a different license. From inside the extracted `STCA_GitHub` directory:

```bash
git init
git add .
git status
git commit -m "Prepare STCA v0.1.0rc2"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/polymer-stca.git
git push -u origin main
git tag -a v0.1.0rc2 -m "STCA v0.1.0rc2"
git push origin v0.1.0rc2
```

These commands are for a new local repository and new remote. Do not repeat `remote add` over an existing remote; inspect it with `git remote -v`. Review `git status` before committing. Do not commit measurement data without permission, API tokens, `.pypirc`, private keys or account credentials. See [GitHub's official instructions](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

A tag is enough for pinned Git installation; creating a GitHub Release page is optional for that route.

## 4. Users can now install directly from GitHub

### Public repository, tagged version

```bash
python -m pip install "polymer-stca[chem] @ git+https://github.com/YOUR_GITHUB_USERNAME/polymer-stca.git@v0.1.0rc2"
python -m stca --version
python -m stca profiles
```

### Development branch or exact commit

```bash
python -m pip install --upgrade "polymer-stca[chem] @ git+https://github.com/YOUR_GITHUB_USERNAME/polymer-stca.git@main"
```

`main` can change. For scientific reproducibility, replace `main` with a full commit hash, and record that hash with the analysis. Increment the package version for released changes rather than repeatedly editing an existing release tag.

### Repository without local Git on the user's computer

For a public repository and an existing tag, pip can install the source archive:

```bash
python -m pip install "polymer-stca[chem] @ https://github.com/YOUR_GITHUB_USERNAME/polymer-stca/archive/refs/tags/v0.1.0rc2.zip"
```

This is still a GitHub source installation, not a PyPI release.

### Private repository for authorized reviewers

With an SSH key and repository access already configured:

```bash
python -m pip install "polymer-stca[chem] @ git+ssh://git@github.com/YOUR_GITHUB_USERNAME/polymer-stca.git@v0.1.0rc2"
```

Do not embed private tokens in README commands or source files. Another option is to clone using an authorized credential manager and install locally with `python -m pip install ".[chem]"`.

### An extra package directory was uploaded accidentally

Prefer correcting the repository root. When the package is intentionally under `STCA_GitHub/`, pip accepts an explicit subdirectory:

```bash
python -m pip install "polymer-stca[chem] @ git+https://github.com/YOUR_GITHUB_USERNAME/polymer-stca.git@v0.1.0rc2#subdirectory=STCA_GitHub"
```

## 5. Prepare a PyPI release

The package currently declares:

```toml
[project]
name = "polymer-stca"
version = "0.1.0rc2"
license = "LicenseRef-STCA-Academic-Peer-Review"
license-files = ["LICENSE", "NOTICE"]
```

The import remains `from stca import ...`, even when the distribution name must change because of a PyPI name conflict. Do not install an unrelated package with a similar name.

After creating the actual repository, add the following new table to `pyproject.toml`, replacing the placeholder:

```toml
[project.urls]
Repository = "https://github.com/YOUR_GITHUB_USERNAME/polymer-stca"
Issues = "https://github.com/YOUR_GITHUB_USERNAME/polymer-stca/issues"
Documentation = "https://github.com/YOUR_GITHUB_USERNAME/polymer-stca#readme"
```

Also replace the repository placeholders in the README. Its relative documentation links work on GitHub; for a polished PyPI description, change cross-file links such as `docs/API.md` to the actual repository's full HTTPS links or a hosted documentation site before building. Do not insert an invented publication DOI or final author list.

Review the archived profile scope, rights for public distribution, and PyPI project name. Copy `docs/RELEASE_APPROVAL.json.example` to `RELEASE_APPROVAL.json` and set each flag to `true` **only after the corresponding check is genuinely complete**. Then run:

```bash
python scripts/check_public_release.py
```

This script requires Python 3.11 or later and is a release-only gate; it is not run by `pip install`. It does not require a claim of final-paper numerical equivalence. The supplied copy intentionally fails this gate because remote URLs, release authorization and PyPI name control have not been supplied.

### Local build and validation

From a clean working tree and an empty `dist/` directory:

```bash
python -m pip install --upgrade pip build twine
python -m pip install ".[chem,dev]"
python -m pytest -q
python -m build
python -m twine check dist/*
```

This produces:

```text
dist/polymer_stca-0.1.0rc2-py3-none-any.whl
dist/polymer_stca-0.1.0rc2.tar.gz
```

Test the wheel from another directory/environment before publication. The same version number must agree in `pyproject.toml` and `src/stca/model.py`. The archived assets intentionally retain their original import version; do not rewrite their historical provenance just to match a new software release.

## 6. Option A: manual PyPI upload

Create your own PyPI account, verify its email address and enable two-factor authentication. PyPI requires 2FA. Create an API token for uploading; a first upload for a new project may need an account-scoped token because that project does not yet exist. Prefer a project-scoped token after creation, and revoke unneeded broad tokens. [PyPI account/token help](https://pypi.org/help/).

After the previous local checks and permission review, upload exactly the intended version:

```bash
python -m twine upload --username __token__ dist/polymer_stca-0.1.0rc2-py3-none-any.whl dist/polymer_stca-0.1.0rc2.tar.gz
```

When prompted for the password/token, enter your PyPI API token, including its `pypi-` prefix. It is not your GitHub password. Do not put the token into a tracked file, example command or chat message. This is a real public upload command; do not run it merely to test a local build.

A rehearsal on TestPyPI uses a separate account/publisher and an authorized public test release:

```bash
python -m twine upload --repository testpypi --username __token__ dist/polymer_stca-0.1.0rc2-py3-none-any.whl dist/polymer_stca-0.1.0rc2.tar.gz
```

TestPyPI is not a confidential review system, and an upload there does not publish to production PyPI. It may not carry all dependencies. Install dependencies through a trusted source separately, then use `--no-deps` for a controlled TestPyPI check rather than mixing package indexes indiscriminately:

```bash
python -m pip install "numpy>=1.24" "pandas>=2.0" "scipy>=1.10" "rdkit>=2023.9"
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps "polymer-stca==0.1.0rc2"
```

## 7. Option B: GitHub Actions Trusted Publishing

The supplied `.github/workflows/publish.yml.example` is **inactive** until renamed. It uses a release event and an explicit version/tag check, builds/tests in one job, and gives OIDC publishing permission only to the separate publish job.

For a first release, PyPI supports a **pending Trusted Publisher**. In PyPI account settings → Publishing, add a GitHub publisher using:

| PyPI field | Value for this example |
|---|---|
| PyPI project name | `polymer-stca` (must be available or appropriately controlled) |
| GitHub owner | Your real username or organization |
| Repository | `polymer-stca` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

A pending publisher does not reserve the project name. See [PyPI's official first-project instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

Create the GitHub environment named `pypi`; configure required reviewers and deployment rules where available for your account/repository. Rename the template to `.github/workflows/publish.yml`, commit it together with the real URLs and reviewed approval file, then create a new version tag containing those changes. Do not move an already distributed tag; use a new version when necessary.

Create a GitHub Release for that tag and publish it. The workflow checks the tag against `pyproject.toml` and the package version, runs the tests, builds the distributions and uploads the artifact to the publish job. The environment approval, when configured, occurs before publication. The publish action then authenticates through OIDC; no long-lived PyPI token is placed in repository secrets. See [official Trusted Publishing usage](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

For an existing PyPI project, use its Publishing settings instead of a pending publisher. The exact owner/repository/workflow/environment values must match. Check the Actions log and the PyPI project page before announcing availability. No remote workflow execution is claimed in the delivered validation record.

## 8. The user-facing command after successful publication

For this release candidate:

```bash
python -m pip install "polymer-stca[chem]==0.1.0rc2"
python -m stca --version
python -m stca profiles
```

For a later stable release:

```bash
python -m pip install "polymer-stca[chem]"
```

Use `--upgrade` when updating an existing installation. `rc2` denotes a prerelease; use an explicit version or `--pre` when intentionally selecting prereleases rather than relying on normal latest-stable resolution.

## 9. Frequent failures

| Symptom | What to check |
|---|---|
| Name-only `pip install` cannot find the project | GitHub upload is not PyPI publication; also check the actual project name, version, Python version and index |
| Git is not recognized | Install Git, use the archive URL for a public repository, or clone/download and install locally |
| Neither `pyproject.toml` nor `setup.py` found | The project is inside an extra directory or only the ZIP was uploaded |
| `stca` is not recognized | Use `python -m stca` with the interpreter where the package was installed |
| SMILES support requires RDKit | Install the `[chem]` extra or RDKit in the same environment |
| Output exists | Use another output path or explicitly pass `--overwrite` |
| PyPI name or file already exists | Confirm name ownership and publish a new version; do not overwrite or impersonate another project |
| Invalid OIDC publisher | Match owner, repository, `publish.yml`, and `pypi` exactly on the correct index |
| Release gate rejects the project | Supply real URLs and confirm the explicit permission/scope/name checks; do not mark unchecked facts approved |

A successful installation, a green CI run and a PyPI upload are separate software events. None independently validates the scientific rule performance or establishes final-paper numerical reproduction.
