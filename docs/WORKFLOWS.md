# Training, evaluation, and reproduction

Practical examples for workflows beyond the [quick start](../README.md).

**Recommended online reproduction:** [Code Ocean research capsule](https://doi.org/10.24433/CO.1601774.v1). The examples below cover local use.

## Match a pretrained training protocol

### Refit the paper protocol

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

### Train with source-only selection

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

### Train with binary descriptors and reuse the model

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

