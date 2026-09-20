# STCA: Interpretable Polymer Substructure Screening

**Ready-to-use Tg/EC rules, transparent screening, and STCA training on your own data.**

This repository accompanies the manuscript:

> **Interpretable Substructure-Based Screening of Multi-Property Polymer Dielectrics with Prompt-Ready Rules for Rational Design**  
> **Journal:** npj Computational Materials

Distribution name: **`polymer-stca`** · Python import: **`stca`** · Version: **`0.1.0rc2`**

[Installation](#installation) · [Screening](#ready-to-use-tg-and-ec-screening) · [Custom training](#train-stca-on-your-own-data) · [Command line](#command-line-workflows) · [GitHub and PyPI publishing](docs/RELEASING.md) · [Sources](docs/SOURCES.md) · [License](#license)

## Overview

STCA discovers interpretable, signed substructure rules from changes in feature frequency during a property-threshold scan. A frozen rule can then be applied to new structures **without knowing their measured properties**. Each rule is a conjunction of required-present and required-absent features.

The package provides two separate entry points: load an existing Tg/EC rule profile for immediate screening, or discover a new rule family from your own labeled data. It is not a numerical property regressor. A rule match is not a calibrated probability or an experimental performance guarantee.

| Capability | Available in this package |
|---|---|
| High glass-transition temperature, Tg | `tg-high`: Top 30%, 20%, 10% |
| Low electrical conductivity, EC | `ec-low`: Bottom 20%, 15%, 10%, 5% |
| High electrical conductivity, EC | `ec-high`: Top 20%, 15%, 10%, 5% |
| Custom-data training | SMILES and numeric targets, or named binary descriptors and numeric targets |
| Explainable output | Rule signatures, expressions, matched literals, missing required features, forbidden features |
| Model reuse | JSON save/load, with frozen rules, feature definitions and training cutoffs |
| Evaluation | TP, FP, TN, FN, MCC, precision, recall, specificity, F1, coverage and enrichment |
| Interfaces | Python API and `stca` / `python -m stca` command-line interfaces |

**Scope of this preview.** The built-in profiles are the **SI-20260822, Table S17, Tg-core/EC-core** archive recorded in [Sources](docs/SOURCES.md). They are executable rule snapshots, not newly certified final-paper artifacts. Their historical numerical cutoffs are not included. Version 0.1.0rc2 changes documentation, attribution and release tooling; the rule assets and discovery/screening logic are unchanged from rc1. This delivery has not created a GitHub repository or published to PyPI.

The full manuscript title identifies the associated research; this package currently includes Tg and EC profiles, not every property or benchmark discussed in the manuscript. See [Profile scope](docs/PROFILES.md) and [Algorithm](docs/ALGORITHM.md).

## Installation

Python **3.10 or later** is declared. The current local verification environment and actual executed checks are recorded in [VALIDATION.md](VALIDATION.md); a configured CI matrix is not a claim that all platforms have already passed.

All installation and usage examples are subject to [License](#license). Availability of a GitHub URL or a wheel does not extend the permission terms.

### A. Install from the downloaded project

Extract the project ZIP. Open a terminal **inside `STCA_GitHub/`, beside `pyproject.toml`**:

```bash
python -m pip install ".[chem]"
python -m stca --version
python -m stca profiles
```

The `chem` extra installs RDKit for SMILES-to-MACCS conversion. For an explicit binary-feature workflow without SMILES, install only the core:

```bash
python -m pip install .
```

For development and tests:

```bash
python -m pip install -e ".[chem,dev]"
python -m pytest -q
```

A virtual environment is recommended. On Windows PowerShell, using its interpreter directly avoids requiring an activation-policy change:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install ".[chem]"
.venv\Scripts\python.exe -m stca profiles
```

That first command requires Python 3.12 to be installed; choose another installed, supported Python version when appropriate. On Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install ".[chem]"
.venv/bin/python -m stca profiles
```

### B. Install the supplied wheel

From the directory containing the wheel:

```bash
python -m pip install ./polymer_stca-0.1.0rc2-py3-none-any.whl
python -m pip install rdkit
python -m stca --version
```

The second command is unnecessary for binary-feature-only use. Scientific dependencies must already be available or resolvable by pip; the wheel does not bundle an entire Python environment.

### C. Install directly from GitHub after uploading

Replace `foukusa` and the repository name with the actual ones. The repository must contain this project at its root, and the tag must exist. A working Git executable is required:

```bash
python -m pip install "polymer-stca[chem] @ git+https://github.com/foukusa/polymer-stca.git@v0.1.0rc2"
```

This installs from GitHub **without requiring a PyPI release**. An installation pinned to a full commit hash is preferable for exact computational provenance. Private repositories additionally require authorized Git access. See the [official pip VCS documentation](https://pip.pypa.io/en/stable/topics/vcs-support/) and the project's [step-by-step release guide](docs/RELEASING.md).

### D. Install by package name after publishing to PyPI

Only after this exact project has been published under an available, maintainer-controlled name:

```bash
python -m pip install "polymer-stca[chem]==0.1.0rc2"
```

For a future stable release, the ordinary command is:

```bash
python -m pip install "polymer-stca[chem]"
```

**Uploading files to GitHub does not enable a PyPI name-only install.** The explicit version above selects this prerelease; do not assume a name-only install resolves to this preview. Package-name availability has not been established by this delivery. [Publishing instructions](docs/RELEASING.md) cover both manual upload and GitHub Actions Trusted Publishing.

## Ready-to-use Tg and EC screening

### 1. List profiles and load a model

```python
from stca import list_profiles, load_pretrained

print(list_profiles().to_string(index=False))

tg = load_pretrained("tg", direction="high")
ec_low = load_pretrained("ec", direction="low")
ec_high = load_pretrained("ec", direction="high")

# Equivalent explicit profile names:
tg = load_pretrained("tg-high")

print(tg.tiers)
print(tg.rules(tier=0.20).to_string(index=False))
print(tg.provenance)
```

The `ArchivedProfileWarning` is intentional: it identifies the rule snapshot's status, not a failure to load. `load_pretrained("tg-high", warn=False)` suppresses that display but does not change provenance or validation status.

### 2. Screen a list of SMILES

```python
from stca import load_pretrained

# Syntax examples only, not verified high-performance polymer recommendations.
smiles = ["*CC*", "*CCO*", "*c1ccc(cc1)*"]

model = load_pretrained("tg-high")
result = model.screen(smiles, tier=0.20)

print(result[
    ["smiles", "input_valid", "selected", "rule_name",
     "missing_required_present", "unexpected_present"]
].to_string(index=False))
```

SMILES are interpreted **as supplied**: `*` connection atoms are retained, not hydrogen-capped. Salt removal, tautomer normalization, oligomer construction and other chemical standardization are not performed automatically. Apply a documented, consistent representation policy during training and screening.

`tier=0.20` refers to the profile's original top/bottom target fraction; it does **not** force exactly 20% of a new candidate list to pass. Some archived tiers share the same Boolean rule and therefore return identical masks. Unsupported tiers are rejected rather than interpolated.

### 3. Screen a CSV and retain identifiers

Input `candidates.csv` needs a SMILES column; IDs are optional:

```csv
ID,SMILES
candidate_1,*CC*
candidate_2,*CCO*
candidate_3,*c1ccc(cc1)*
```

```python
from pathlib import Path
import pandas as pd
from stca import load_pretrained

candidates = pd.read_csv("candidates.csv").reset_index(drop=True)
model = load_pretrained("ec-low")
result = model.screen(candidates["SMILES"], tier=0.10)

# Positional alignment is explicit; model output does not carry arbitrary IDs.
result.insert(0, "ID", candidates["ID"].to_numpy())
Path("runs").mkdir(exist_ok=True)
result.to_csv("runs/low_ec_screen.csv", index=False)
selected = result.loc[result["selected"].fillna(False)].copy()
selected.to_csv("runs/low_ec_selected.csv", index=False)
```

The command-line equivalent preserves **all** original CSV columns:

```bash
stca screen --profile ec-low --tier 0.10 --input candidates.csv --output runs/low_ec_screen.csv
```

### 4. Interpret the output

| Output field | Meaning |
|---|---|
| `row_position` | Zero-based input row position, not a user-supplied identifier |
| `input_valid` | Whether the structure could be parsed and fingerprinted |
| `selected` | All required-present and required-absent literals match |
| `rule_name`, `rule_signature` | Exact frozen rule used for the decision |
| `matched_literals`, `required_literals` | Counts explaining rule satisfaction; not confidence scores |
| `missing_required_present` | Required-present features that are absent |
| `unexpected_present` | Features present despite a required-absent condition |
| `tier`, `target_direction` | Target fraction and high/low screening direction |
| `profile_kind` | Archived profile or custom source-trained model provenance |

`model.rules(tier=...)` exposes readable Boolean expressions. For MACCS, identifiers such as `K142` are key indices, not atom numbers. The complete fingerprint has 167 positions, with dummy bit 0 and actual keys 1–166. Arbitrary 166-/167-column input is not guessed or silently shifted.

By default, invalid SMILES stop processing. To retain invalid rows without assigning a false decision:

```python
result = model.screen(["*CC*", "not_a_smiles"], tier=0.10, errors="report")
print(result[["input_valid", "selected", "input_error"]])
```

The invalid row has `selected=<NA>`, not `False`. Its parse error is reported. CLI users can pass `--errors report`.

### 5. Combine two rule matches explicitly

```python
from stca import load_pretrained

smiles = ["*CC*", "*CCO*", "*c1ccc(cc1)*"]
tg_result = load_pretrained("tg-high").screen(smiles, tier=0.20)
ec_result = load_pretrained("ec-low").screen(smiles, tier=0.10)
joint_match = tg_result["selected"] & ec_result["selected"]
print(joint_match)
```

This AND operation is a user-defined intersection of two independent rule masks. It is **not** a separately trained or experimentally validated multi-property performance claim.

## Train STCA on your own data

### Data requirements

For SMILES training, each record needs a valid structure and a finite numeric target. A Tg CSV could have `ID,SMILES,Tg`; an EC CSV could have `ID,SMILES,EC`. Units and measurement conditions must be defined consistently. Missing labels, nonnumeric targets, invalid structures and nonpositive raw conductivities are rejected rather than silently repaired.

Use a source/training set to discover and select rules, and a disjoint test set for evaluation. `fit_smiles` records canonical structure identities, and `evaluate_smiles` checks overlap. The CLI also audits a declared `split` and optional group column. This audit does not itself create a chemical-extrapolation split.

### 1. Train high-Tg rules from SMILES

This example uses your actual files `my_tg_train.csv` and `my_tg_test.csv`; they are not bundled measurement datasets:

```python
from pathlib import Path
import pandas as pd
from stca import STCA, ScanConfig

train = pd.read_csv("my_tg_train.csv")
test = pd.read_csv("my_tg_test.csv")
output = Path("runs/my_tg")

trainer = STCA(
    direction="high",
    tiers=(0.30, 0.20, 0.10),
    scan=ScanConfig(mode="value", step=1.0),
    max_rank=10,
    family_size=8,
    target_name="Tg",
    target_unit="degC",
)
model = trainer.fit_smiles(
    train["SMILES"],
    train["Tg"],
    provenance={"dataset_description": "User-supplied Tg training data"},
)

model.save(output / "model.json")
trainer.export_diagnostics(output)
model.rules(tier=0.20).to_csv(output / "rules_top20.csv", index=False)

metrics = model.evaluate_smiles(
    test["SMILES"], test["Tg"], tier=0.20,
)
print(pd.Series(metrics).to_string())
```

`step=1.0` is an explicit custom-training value in degrees Celsius, not a claim about every historical Tg calculation. Choose a step appropriate to your target. `mode="unique"` and `mode="quantile"` are alternative scans with different threshold weighting, not interchangeable numerical replicas.

`fit` and `fit_smiles` return a **`ScreeningModel`**, not the trainer. The fitted model is also accessible as `trainer.model_`. No test labels enter rule discovery or representative selection.

### 2. Train low- or high-EC rules with explicit units

EC is stored internally as `log10(S/cm)`. Supported input declarations are `S/m`, `S/cm`, `log10(S/m)` and `log10(S/cm)`; the unit is never guessed.

```python
import pandas as pd
from stca import STCA, ScanConfig, ec_to_log10_s_cm

train = pd.read_csv("my_ec_train.csv")
test = pd.read_csv("my_ec_test.csv")

# This example assumes raw EC values in S/m in both input files.
y_train = ec_to_log10_s_cm(train["EC"], unit="S/m")
y_test = ec_to_log10_s_cm(test["EC"], unit="S/m")

trainer = STCA(
    direction="low",                # Use "high" to screen the high-EC tail.
    hierarchy="ec_reverse",         # Explicit archived electrical convention.
    tiers=(0.20, 0.15, 0.10, 0.05),
    scan=ScanConfig(mode="value", step=0.01),
    max_rank=35,
    mcc_mode="nonnegative",
    target_name="EC",
    target_unit="log10(S/cm)",
)
model = trainer.fit_smiles(train["SMILES"], y_train)
model.save("runs/my_ec/model.json")
trainer.export_diagnostics("runs/my_ec")

metrics = model.evaluate_smiles(test["SMILES"], y_test, tier=0.10)
print(pd.Series(metrics).to_string())
```

The `ec_reverse` option scans the low-EC hierarchy first; high-EC use swaps its signed roles once. It requires eligible features of both signs. For a different, intentionally generic custom protocol, `hierarchy="direct"` is available; changing that setting changes the discovery protocol.

Already-logarithmic targets must be declared as such. For example, `ec_to_log10_s_cm(values, unit="log10(S/m)")` performs the unit offset without taking a second logarithm.

### 3. Save, reload and screen without retraining

```python
import pandas as pd
from stca import ScreeningModel

model = ScreeningModel.load("runs/my_tg/model.json")
candidates = pd.read_csv("candidates.csv")
result = model.screen(candidates["SMILES"], tier=0.20)
result.to_csv("runs/my_tg/new_candidates.csv", index=False)
print(model.rules(tier=0.20))
```

`save` refuses to overwrite an existing JSON unless `overwrite=True` is explicit. CLI commands similarly require `--overwrite`. JSON loading validates the schema and rule indices; it does not use pickle or execute rule strings.

### 4. Train on custom binary descriptors

Your features may be explicit binary descriptors instead of MACCS. This interface requires 0/1 values, not raw continuous variables:

```python
import pandas as pd
from stca import STCA, ScanConfig

train = pd.read_csv("binary_train.csv")
test = pd.read_csv("binary_test.csv")
features = ["feature_a", "feature_b", "feature_c"]

trainer = STCA(
    direction="high",
    tiers=(0.20,),
    scan=ScanConfig(step=0.25),
    target_name="custom_property",
    target_unit="user_defined_unit",
)
model = trainer.fit(
    train[features], train["target"], groups=train["group_id"],
)
result = model.screen_fingerprints(test[features], tier=0.20)
metrics = model.evaluate(
    test[features], test["target"], tier=0.20, groups=test["group_id"],
)
model.save("runs/custom_binary/model.json")
print(metrics)
```

Named DataFrames are aligned to the saved feature names. Arrays must already follow the saved column order. Define any continuous-to-binary transformations using training data only, and freeze them before test or candidate processing. Supplying composite descriptors does not imply this package is a validated C-STCA release.

### 5. Run complete bundled demonstrations

These commands require no private research dataset:

```bash
python examples/screen_profiles.py
python examples/train_binary_demo.py
python examples/train_smiles_demo.py
```

The two training demos use **explicitly synthetic targets**, not measured Tg/EC values or manuscript benchmark data. They demonstrate fitting, diagnostic export, saving, reloading and disjoint evaluation. The SMILES demo also writes synthetic CSVs under `runs/synthetic_smiles/` for trying the CLI:

```bash
stca train --input runs/synthetic_smiles/data.csv --target synthetic_target --target-name SYNTHETIC_demo --target-unit arbitrary --tiers 0.20 --scan-step 0.25 --split-column split --output-dir runs/synthetic_smiles_cli
```

### 6. Training diagnostics and evaluation semantics

`trainer.export_diagnostics(...)` writes `scan_correlations.csv`, `scan_thresholds.csv` and `candidate_rules.csv`. The candidate table includes source metrics, membership in the retained family and the frozen representative flag. `model.rules(...)` returns each saved tier's family; CLI training additionally writes per-tier rule CSVs, split membership and test metrics when a test split is supplied.

Custom training ranks candidates by source F1, retains a family with available signed-family anchors, and selects a valid representative by source `AS = (MCC + precision + F1) / 3`. The representative is not reselected using the test set. A tier with no valid source rule is stored as abstention and raises `NoValidRuleError` when screening is requested; it is not silently relaxed.

Default evaluation uses the **saved training cutoff**. Positive labels include ties at that cutoff. `cutoff_mode="dataset_relative"` deliberately recomputes a target cutoff from the labeled evaluation set and is a different evaluation definition; it is not the default deployment estimate.

Archived profiles have no verified historical numerical cutoff. To evaluate one, supply a justified explicit cutoff in the stored units, or explicitly choose dataset-relative evaluation:

```python
from stca import load_pretrained

archive = load_pretrained("tg-high")
# Requires your labeled, independent evaluation DataFrame named test.
metrics = archive.evaluate_smiles(
    test["SMILES"], test["Tg"], tier=0.20,
    cutoff_mode="dataset_relative",
)
```

This does not recover a missing historical cutoff or establish original-paper numerical parity.

## Command-line workflows

Every command below also works as `python -m stca ...`, which is useful when the `stca` executable is not on PATH.

### Ready-to-use screening and inspection

```bash
stca profiles
stca inspect --profile tg-high
stca screen --profile tg-high --tier 0.20 --input candidates.csv --output runs/tg_screen.csv
stca screen --profile ec-low --tier 0.10 --input candidates.csv --output runs/ec_low_screen.csv
stca screen --profile ec-high --tier 0.05 --input candidates.csv --output runs/ec_high_screen.csv
```

### Custom Tg training, screening and evaluation

`my_tg_data.csv` must contain `SMILES,Tg,split`, with both `train` and `test` rows and no other split labels. Canonical structures must not cross the split:

```bash
stca train --input my_tg_data.csv --target Tg --target-name Tg --target-unit degC --direction high --tiers 0.30 0.20 0.10 --scan-step 1.0 --split-column split --output-dir runs/custom_tg
stca inspect --model runs/custom_tg/model.json
stca screen --model runs/custom_tg/model.json --tier 0.20 --input candidates.csv --output runs/custom_tg_candidates.csv
stca evaluate --model runs/custom_tg/model.json --input my_tg_test.csv --target Tg --tier 0.20 --output runs/custom_tg_evaluation.json
```

### Custom EC training and evaluation

Here `EC` contains raw values in `S/m`:

```bash
stca train --input my_ec_data.csv --target EC --ec-input-unit "S/m" --target-name EC --target-unit "log10(S/cm)" --direction low --hierarchy ec_reverse --tiers 0.20 0.15 0.10 0.05 --scan-step 0.01 --max-rank 35 --mcc-mode nonnegative --split-column split --output-dir runs/custom_ec
stca evaluate --model runs/custom_ec/model.json --input my_ec_test.csv --target EC --ec-input-unit "S/m" --tier 0.10 --output runs/custom_ec_evaluation.json
```

### Explicit binary columns

```bash
stca train --input binary_data.csv --features feature_a,feature_b,feature_c --target target --target-name custom_property --target-unit arbitrary --tiers 0.20 --scan-step 0.25 --split-column split --group-column group_id --output-dir runs/custom_binary_cli
stca screen --model runs/custom_binary_cli/model.json --features feature_a,feature_b,feature_c --input binary_candidates.csv --tier 0.20 --output runs/binary_screen.csv
```

Use `--smiles-column` for a different structure-column name, `--group-column` for an additional split audit, and `--errors report` for invalid-row reporting during SMILES screening. Run `stca train --help`, `stca screen --help` or `stca evaluate --help` for the implemented options. Without `--split-column`, all input rows are training records and **no held-out evaluation is performed**.

## Repository and source attribution

```text
pyproject.toml             Package metadata, dependencies and entry point
README.md                  English usage guide
LICENSE / NOTICE           Copyright, permission terms and attribution
CITATION.md                Associated manuscript title and citation status
src/stca/                  STCA implementation and three archived rule assets
examples/                  Runnable screening and synthetic training demos
tests/                     Core, CLI and documentation/release checks
docs/                      API, algorithm, source map, profiles and publishing
scripts/                   Legacy adapter and public-release metadata check
.github/workflows/         CI and an inactive PyPI publishing template
```

The scientific implementation is based on the documented thermal and electrical STCA workflows listed in [docs/SOURCES.md](docs/SOURCES.md). The ready-to-use rules are transcribed core-scope SI-20260822 literals. No original measurement database, manuscript, figure set, private credentials or original full research driver is bundled.

This is portable implementation code, not a claim of a byte-for-byte original-workflow port. The numerical scope of [VALIDATION.md](VALIDATION.md) must remain distinct from the scientific provenance of [docs/PROFILES.md](docs/PROFILES.md). All three archived JSON files are retained unchanged from rc1; their internal `package_version` records that original import version.

Please cite the associated manuscript using its verified bibliographic record when available, and record the software version and actual repository commit used. [CITATION.md](CITATION.md) gives the supplied manuscript title without inventing a publication date, DOI or author list. Citation does not replace permission required by the license.

## License

Copyright (c) 2025, The University of Tokyo, University College London

This code is provided for academic peer review purposes under npj Computational Materials submission guidelines. Commercial use and redistribution require written permission.

## Contact

For questions or issues, please contact:

- [wang@hvg.t.u-tokyo.ac.jp](mailto:wang@hvg.t.u-tokyo.ac.jp)
- Laboratory: Kumada-Sato-Fujii-Umemoto Laboratory (URL UTokyo: https://www.hvg.t.u-tokyo.ac.jp/ UCL: https://mdi-group.github.io/)
- Institution: Department of Electrical Engineering & Information Systems, University of Tokyo

## Acknowledgments

We thank the reviewers and editors of npj Computational Materials for their valuable feedback.
