# STCA: Interpretable Polymer Substructure Screening

**Screen new polymers with frozen Tg/EC rules, or fit the same documented STCA recipe to labeled data.**

Associated manuscript:

> **Interpretable Substructure-Based Screening of Multi-Property Polymer Dielectrics with Prompt-Ready Rules for Rational Design**  
> **Journal:** npj Computational Materials

Distribution: `polymer-stca` | Import: `stca` | Version: **1.0** | Python: **3.10+**

[Installation](#installation) · [Screening](#screen-with-existing-rules) · [Training](#train-with-the-same-protocol) · [Verified results](docs/VERIFIED_RESULTS.md) · [Sources](docs/SOURCES.md) · [Publishing](docs/RELEASING.md) · [License](#license)

## Verified STCA protocols

The author-supplied result archives support an actual structure-to-rule refit. On their recorded Tg-core/EC-core protocol, the package regenerated MACCS fingerprints, refitted STCA, recovered **11/11 historical final rules**, and matched **1,251 archived rule/scope metric records**. Six frozen model artifacts were exported by actual fitting: three `paper` models and three matched `source_locked` models. They include their training recipes and measured training cutoffs, rather than just transcribed winning conditions.

The electrical primary families are bundled as **prefix lengths**, not frozen winning MACCS keys. Low-EC tiers use 6, 6, 6 and 7 candidate templates; high-EC tiers use 8 each. A fit still learns the positive/negative rankings from the supplied source data. The trained rules are not replaced with reference answers.

**Meaning of equality:** the same labeled data, structure representation, split, recipe and selection scope reproduce the paired pretrained artifact. Different data, or a different named protocol, need not produce the same rule. `STCA()` remains the generic source-only estimator. `STCA.for_profile()` and `load_pretrained()` default to the same **`paper`** recipe.

**Scientific scope:** here `paper` specifically identifies the archived **core-scope representative-selection calculation**. It uses historical inter/extra/all labels for selection. Its historical extra result is **not an untouched-test estimate**. The supplementary source-only and alternative-split analyses are not relabeled as this protocol. See the qualifications in [Verified results](docs/VERIFIED_RESULTS.md), including the EC split reconstruction and nonidentical historical thermal correlation coefficients.

## Installation

The source ZIP has **no enclosing project directory**. Its root contains
`pyproject.toml`, `README.md`, `src/`, `tests/` and `.github/` directly.
The maintainer's existing GitHub Desktop checkout is `D:\hongo\polymer-stca`.
Do not create another `polymer-stca/` inside that directory.

```powershell
Set-Location "D:\hongo\polymer-stca"
python -m pip install ".[chem]"
python -m stca --version
```

The version command reports `1.0`. To update an existing checkout safely, stage
this ZIP outside the checkout and use `scripts/apply_update.py`; it backs up
changed files, leaves `.git` and local research data untouched, and refuses
unrecognized source edits. See [local update instructions](docs/LOCAL_UPDATE.md).

From any downloaded source copy, enter the folder that directly contains `pyproject.toml`:

```bash
python -m pip install ".[chem]"
python -m stca --version
python -m stca profiles
```

Or install the supplied wheel and chemistry dependency:

```bash
python -m pip install "./polymer_stca-1.0-py3-none-any.whl[chem]"
```

Only after the corresponding version has actually been published to PyPI:

```bash
python -m pip install "polymer-stca[chem]==1.0"
```

Only after the source has been pushed and tag `v1.0` created on GitHub, installation from that tag is available:

```bash
python -m pip install "polymer-stca[chem] @ https://github.com/foukusa/polymer-stca/archive/refs/tags/v1.0.zip"
```

This delivery does not itself push a commit, create a tag, grant distribution permission or upload to PyPI. The package supports explicit binary descriptors without RDKit; install `.` without `[chem]` for that workflow. Development tools, including the conditional Python 3.10 `tomli` dependency, are installed with `.[chem,dev]`.

## Screen with existing rules

No training data, measured candidate properties, original core scripts or `morgen` files are needed. Screening only generates candidate fingerprints and applies the already frozen conjunction.

```python
from stca import load_pretrained

smiles = ["*CC*", "*CCO*", "*c1ccc(cc1)*"]  # Format examples, not validated designs.
model = load_pretrained("tg-high")
result = model.screen(smiles, tier=0.20)
print(result[["smiles", "input_valid", "selected", "rule_name",
              "missing_required_present", "unexpected_present"]])
print(model.rules(tier=0.20))
```

The same interface accepts `ec-low` and `ec-high`. High Tg supports Top 30%, 20%, 10%; low/high EC support Bottom/Top 20%, 15%, 10%, 5%. A tier identifies a target regime; it does **not** require selecting exactly that percentage of every candidate pool. EC tiers can share an identical frozen rule. `selected` is a structural match, **not** a numerical property prediction, probability, or guarantee of experimental performance.

For a CSV with `ID,SMILES`:

```bash
python -m stca screen --profile tg-high --tier 0.20 --input candidates.csv --output tg_screen.csv
python -m stca screen --profile ec-low --tier 0.10 --input candidates.csv --output ec_low_screen.csv
python -m stca screen --profile ec-high --tier 0.10 --input candidates.csv --output ec_high_screen.csv
```

Input ID columns are retained. Invalid SMILES raise an error by default; `--errors report` retains them as invalid with an unknown selection status, not a false all-zero fingerprint.

```python
import pandas as pd
from stca import load_pretrained

candidates = pd.read_csv("candidates.csv")
tg = load_pretrained("tg-high").screen(candidates["SMILES"], tier=0.20)
ec = load_pretrained("ec-low").screen(candidates["SMILES"], tier=0.10)
tg.insert(0, "ID", candidates["ID"].to_numpy())
tg["also_matches_low_ec"] = tg["selected"] & ec["selected"]
tg.to_csv("joint_screen.csv", index=False)
```

A joint match combines two structural conditions; it is not a separately validated joint-property model.

## Train with the same protocol

### A. Exact archived core-recipe reconstruction

The simplest way to avoid a recipe mismatch is `pretrained.new_trainer()`. It reads the stored training configuration **only**, never the saved winner, fitted rankings or reference scores.

The following example expects two real CSVs with `PID,SMILES,EC`. The EC values must already be `log10(S/cm)`:

```python
import pandas as pd
from stca import load_pretrained, SelectionData
from stca.chemistry import maccs_from_smiles, MACCS_NAMES, MACCS_SPEC

source = pd.read_csv("ec_source.csv")
selection = pd.read_csv("ec_selection.csv")
X, _ = maccs_from_smiles(source["SMILES"])
Xs, _ = maccs_from_smiles(selection["SMILES"])

pretrained = load_pretrained("ec-low", protocol="paper")
trainer = pretrained.new_trainer()
custom = trainer.fit(
    X, source["EC"].to_numpy(),
    feature_names_=MACCS_NAMES,
    feature_spec=MACCS_SPEC,
    groups=source["PID"].astype(str).to_numpy(),
    selection_data=SelectionData(
        Xs, selection["EC"].to_numpy(),
        selection["PID"].astype(str).to_numpy(),
        name="explicit_selection_data",
    ),
    acknowledge_selection_labels=True,
)
custom.save("custom_ec_paper.json")
trainer.export_diagnostics("ec_paper_diagnostics")
```

The selection CSV is **used to choose the representative rule**. Do not call it an untouched final test set. An omitted selection set or missing acknowledgement causes an explicit error; the package does not silently change protocols. High Tg and high EC use the same recipe API with their own profiles.

For original conductivity in S/m rather than log10(S/cm), first apply the explicit conversion to both source and selection labels:

```python
from stca import ec_to_log10_s_cm
source["EC"] = ec_to_log10_s_cm(source["EC"], unit="S/m")
selection["EC"] = ec_to_log10_s_cm(selection["EC"], unit="S/m")
```

Equivalent one-command training:

```bash
python -m stca train-profile --profile ec-low --protocol paper --input ec_source.csv --selection-input ec_selection.csv --target EC --ec-input-unit "log10(S/cm)" --group-column PID --acknowledge-selection-labels --output-dir ec_paper_fit
```

This command automatically applies the verified scan step, reverse-scan convention and bundled candidate-family recipe; users do not select a core script or manually enter the prefix lengths.

### B. Source-only training for a separate deployment evaluation

Choose `source_locked` **on both sides** when no external selection labels should enter fitting:

```python
import pandas as pd
from stca import STCA, load_pretrained

source = pd.read_csv("tg_source.csv")
trainer = STCA.for_profile("tg-high", protocol="source_locked")
custom = trainer.fit_smiles(source["SMILES"], source["Tg"])
custom.save("custom_tg_source_only.json")

paired_reference = load_pretrained("tg-high", protocol="source_locked")
```

```bash
python -m stca train-profile --profile ec-low --protocol source_locked --input ec_source.csv --target EC --ec-input-unit "log10(S/cm)" --output-dir ec_source_fit
```

This source-only reference is **not the archived core winner**, and no claim is made that it improves held-out accuracy. It exists so source-only and core-scope results cannot be accidentally compared as though they came from the same selection protocol. For arbitrary custom binary descriptors or unrestricted source-only families, use `STCA(...)` or `train-profile --protocol generic`.

### C. Binary descriptors and frozen reuse

```python
import pandas as pd
from stca import STCA, ScanConfig, ScreeningModel

train = pd.read_csv("binary_train.csv")
features = ["feature_a", "feature_b", "feature_c"]
trainer = STCA(direction="high", tiers=(0.20,),
               scan=ScanConfig(step=0.25), max_rank=3)
model = trainer.fit(train[features], train["target"])
model.save("binary_model.json")

model = ScreeningModel.load("binary_model.json")
new_data = pd.read_csv("binary_candidates.csv")
print(model.screen_fingerprints(new_data[features], tier=0.20))
```

Features must be explicit 0/1 columns. The package does not silently bin continuous variables. Different data can produce different rankings, rules, or an explicit no-valid-rule abstention.

## Evaluate without training again

```bash
python -m stca evaluate --model ec_paper_fit/model.json --input untouched_test.csv --target EC --ec-input-unit "log10(S/cm)" --group-column PID --tier 0.20 --output test_metrics.json
```

`fixed_train` uses the numeric cutoff stored at fit time. `dataset_relative` defines labels by each evaluation set's own percentile; it is not interchangeable with a fixed-threshold claim. Paper core scores use the latter for inter, extra and all.

The verified pretrained artifacts store PID hashes for overlap checks. When evaluating these artifacts, supply matching PID identities through `groups=...` or `--group-column PID`; canonical SMILES must not be silently compared to PID hashes. Evaluating known source/selection records requires explicit `allow_overlap=True` / `--allow-overlap` and is reported as retrospective reassessment. Ordinary unlabeled `screen()` needs neither PID nor measured targets.

Use disjoint structural/material groups for a new independent generalization study. PID disjointness alone is not proof of molecular disjointness or literature-source independence.

## Reproduce the supplied research results

Place the five author-supplied ZIPs together in a **private directory outside the repository**. Then run:

```bash
python -m stca verify-results --reference-dir "D:/hongo/STCA_reference_archives" --output "D:/hongo/STCA_verified_1.0"
```

No core script, manual scan parameters or original `morgen` files are needed for this check. It reads the actual structure/property tables and reference family tables in the supplied output archives, regenerates MACCS, fits six models, refits them again from saved recipes, and compares the fitted outputs. It also checks 1,251 archived rule/scope metric rows independently.

`final_rule_parity.csv` records the 11 paper and 11 paired source-only tier checks. `archived_rule_metric_parity.csv`, `candidate_family_parity.csv`, `scan_reference_audit.csv`, `recipe_roundtrip.csv` and `status.json` expose the individual checks and limitations. `PRIVATE_per_material_predictions.csv` includes source record IDs and must **not** be committed to a public repository. This is a core-parity test, not a rerun of every supplementary bootstrap, alternative split or cross-property analysis.

`python -m stca paper-audit` is a much smaller **static** check of the legacy SI literals. It does not execute the real-data refit; it should not be presented as new numerical evidence.

## Development and publication

```bash
python -m pip install ".[chem,dev]"
python -m pytest -q
python -m build
python -m twine check --strict dist/*
```

See [VALIDATION.md](VALIDATION.md) for executed environments and checks, and [RELEASING.md](docs/RELEASING.md) for TestPyPI/PyPI instructions. A CI configuration is not a claim that the corresponding remote job has passed. No raw scientific inputs are needed or bundled for public CI.

The small synthetic examples in `examples/train_binary_demo.py` and `examples/train_smiles_demo.py` test software behavior only. They are not the real measurements used for the documented scientific refit.

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
