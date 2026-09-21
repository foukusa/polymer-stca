# STCA: Interpretable Polymer Substructure Screening

**Screen polymer candidates with interpretable substructure rules, or learn new rules from your own data.**

STCA connects polymer structure to property-specific screening criteria. It identifies combinations of substructures that should be present or absent, making each screening decision easy to inspect and use in materials design. The package includes pretrained rules for glass-transition temperature (**Tg**) and electrical conductivity (**EC**), together with tools for custom training, batch screening, and model export.

**Related paper**  
*Interpretable Substructure-Based Screening of Multi-Property Polymer Dielectrics with Prompt-Ready Rules for Rational Design*  
npj Computational Materials

**STCA 1.0** · Python **3.10+** · Package `polymer-stca` · Import `stca`

[Installation](#installation) · [Quick start](#quick-start) · [Custom training](#train-on-your-own-data) · [Online reproduction](#online-reproduction) · [Documentation](#documentation) · [License](#license)

## Online reproduction

For online reproduction of the study, use the **recommended Code Ocean release**:

**[Open STCA on Code Ocean — doi:10.24433/CO.1601774.v1](https://doi.org/10.24433/CO.1601774.v1)**

The GitHub package is intended for local screening, custom-data training, and integration into your own workflows. The Code Ocean DOI identifies the linked research capsule, not the journal article.

## Installation

A **PyPI release is coming soon**, enabling installation directly with `pip`:

```bash
# Available after the PyPI release
python -m pip install "polymer-stca[chem]"
```

Until then, download or clone this repository, open a terminal in the directory containing `pyproject.toml`, and install from source:

```bash
python -m pip install ".[chem]"
python -m stca --version
```

The `chem` extra installs RDKit for SMILES input. For workflows using only precomputed binary descriptors, install with `python -m pip install .` instead.

## Quick start

### Screen a list of polymer structures

```python
from stca import load_pretrained

# Example repeat-unit SMILES; * marks a polymer attachment point.
smiles = ["*CC*", "*CCO*", "*c1ccc(cc1)*"]

model = load_pretrained("tg-high")
result = model.screen(smiles, tier=0.20)

print(result[["smiles", "selected", "rule_name"]])
print(model.rules(tier=0.20))
```

Pretrained screening needs only candidate structures, not measured properties or training data. These SMILES illustrate the input format rather than recommended material designs.

| Profile | Screening target | Available tiers |
|---|---|---|
| `tg-high` | High Tg | Top 30%, 20%, 10% |
| `ec-low` | Low EC | Bottom 20%, 15%, 10%, 5% |
| `ec-high` | High EC | Top 20%, 15%, 10%, 5% |

A tier chooses a target regime; it does **not** force that fraction of a new candidate pool to be selected. Some tiers share the same structural rule. `selected` reports a rule match, not a numerical property prediction or a guarantee of experimental performance.

For an explanation of an individual decision, inspect the required conditions and any violations:

```python
print(result[["smiles", "selected", "missing_required_present", "unexpected_present"]])
```

### Screen a CSV from the command line

Prepare `candidates.csv` with a `SMILES` column and, optionally, an identifier:

```csv
ID,SMILES
candidate_1,*CC*
candidate_2,*CCO*
candidate_3,*c1ccc(cc1)*
```

Run the command for your target property:

```bash
python -m stca screen --profile tg-high --tier 0.20 --input candidates.csv --output tg_screen.csv
python -m stca screen --profile ec-low --tier 0.10 --input candidates.csv --output ec_low_screen.csv
python -m stca screen --profile ec-high --tier 0.10 --input candidates.csv --output ec_high_screen.csv
```

The output retains your input identifiers and adds the screening decision and rule information. Invalid SMILES raise an error by default. Add `--errors report` to retain invalid rows with an explicit error and no selection decision.

## Train on your own data

Custom training requires **structures or binary descriptors together with measured property values**. STCA handles the threshold scan, substructure ranking, candidate-rule construction, and final rule selection.

### Train a Tg model

For a CSV named `tg_train.csv` with `SMILES` and `Tg` columns, where Tg is in degrees Celsius:

```python
import pandas as pd
from stca import STCA

train = pd.read_csv("tg_train.csv")

trainer = STCA.for_profile("tg-high", protocol="source_locked")
model = trainer.fit_smiles(train["SMILES"], train["Tg"])
model.save("my_tg_model.json")

candidates = pd.read_csv("candidates.csv")
result = model.screen(candidates["SMILES"], tier=0.20)
if "ID" in candidates:
    result.insert(0, "ID", candidates["ID"].to_numpy())
result.to_csv("custom_tg_screen.csv", index=False)
```

The profile supplies the Tg training settings. `source_locked` selects rules using only the supplied training data; reserve separate materials for evaluating screening performance. For a pretrained reference using the same selection protocol, use `load_pretrained("tg-high", protocol="source_locked")`.

### Train an EC model

The command-line preset also handles EC unit conversion. For an `ec_train.csv` containing `SMILES` and measured `EC` **in S/m**:

```bash
python -m stca train-profile --profile ec-low --protocol source_locked --input ec_train.csv --target EC --ec-input-unit "S/m" --output-dir my_ec_model
```

Use `--profile ec-high` for high-conductivity screening. Declare the unit actually stored in the file; for values already expressed as `log10(S/cm)`, use `--ec-input-unit "log10(S/cm)"` rather than applying a second logarithm.

### Reuse a saved model

```python
from stca import ScreeningModel

model = ScreeningModel.load("my_tg_model.json")
print(model.screen(["*CC*", "*CCO*"], tier=0.20))
```

Or screen with the model created by the EC command:

```bash
python -m stca screen --model my_ec_model/model.json --tier 0.10 --input candidates.csv --output custom_ec_screen.csv
```

For non-SMILES inputs, `STCA.fit()` accepts explicit 0/1 descriptor columns. See the [API reference](docs/API.md) and [training workflows](docs/WORKFLOWS.md) for examples, evaluation, and advanced configuration.

### Use the study's training protocol

The default pretrained profiles use `protocol="paper"`. To retrain with that configuration, use `load_pretrained("ec-low").new_trainer()` or `STCA.for_profile("ec-low", protocol="paper")` and supply the required labeled selection set. This set participates in choosing the final rule, so it is not an independent test set.

Comparing a pretrained model with a refit requires the same data, representation, split, and selection protocol. Different custom data can produce different rules. The [protocol guide](docs/PROTOCOL_USAGE.md) provides the full calls and explains the distinction between `paper` and `source_locked`.

## Documentation

[API reference](docs/API.md) · [Training workflows](docs/WORKFLOWS.md) · [Algorithm](docs/ALGORITHM.md) · [Profiles and protocols](docs/PROFILES.md) · [Result reproduction](docs/VERIFIED_RESULTS.md) · [Data and rule sources](docs/SOURCES.md)

For contributors, installation with `.[chem,dev]` adds the test and build tools. See [VALIDATION.md](VALIDATION.md) for test records and the [release guide](docs/RELEASING.md) for publication instructions.

## Citation

Please cite the related paper when using STCA in research:

> *Interpretable Substructure-Based Screening of Multi-Property Polymer Dielectrics with Prompt-Ready Rules for Rational Design*. npj Computational Materials.

For reproducibility, also identify **STCA 1.0**, the repository commit used, and the [Code Ocean release](https://doi.org/10.24433/CO.1601774.v1) when applicable. See [CITATION.md](CITATION.md).

## License

Copyright (c) 2025, The University of Tokyo, University College London

Permission is granted to use and modify this software for non-commercial academic research, education, and reproduction of scientific results.

Commercial use and redistribution, including distribution of modified versions, require prior written permission from the copyright holders.

This copyright notice and license text must be retained in copies of the software.

The software is provided "AS IS", without warranty of any kind. The copyright holders are not liable for claims or damages arising from its use.

## Contact

For questions or issues, please contact:

- [wang@hvg.t.u-tokyo.ac.jp](mailto:wang@hvg.t.u-tokyo.ac.jp)
- Laboratory: Kumada-Sato-Fujii-Umemoto Laboratory (URL UTokyo: https://www.hvg.t.u-tokyo.ac.jp/ UCL: https://mdi-group.github.io/)
- Institution: Department of Electrical Engineering & Information Systems, University of Tokyo
