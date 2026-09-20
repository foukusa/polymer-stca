# Public API

## ScreeningModel

`load_pretrained("tg", direction="high")`, `load_pretrained("ec", direction="low")` and `load_pretrained("ec-high")` load the corresponding archived rule profile. `list_profiles()` lists each available tier, snapshot and exact signature.

`model.screen(smiles, tier=0.20, errors="raise")` applies a MACCS model to a sequence of SMILES and returns an auditable DataFrame. `errors="report"` preserves invalid inputs with missing decisions. Wildcards are retained. Generic binary models reject this method rather than inventing chemical features.

`model.screen_fingerprints(X, tier=0.20)` applies a model to a binary matrix or named DataFrame. DataFrames are aligned by feature name; arrays must already follow the stored column order. A MACCS model requires 167 columns, with key 0 fixed to zero.

`model.rule_for(tier)` returns the frozen `Rule`. `model.rules(tier=...)` returns the saved family and source metrics where available. `model.provenance` and `model.artifact` return defensive copies.

`model.evaluate(X, y, tier=..., cutoff_mode="fixed_train", groups=...)` uses the saved numerical cutoff and never refits. `cutoff_mode="dataset_relative"` is explicitly distinct. Supplying `cutoff=...` under fixed mode requests an explicit numerical cutoff. Archived models without numeric cutoffs cannot use the default without such an explicit value.

`model.evaluate_smiles(smiles,y,...)` uses canonical SMILES for the overlap audit. If source groups were stored, overlapping groups raise unless the user explicitly sets `allow_overlap=True`, which is appropriate for clearly labeled resubstitution diagnostics, not independent validation. Generic matrix models trained without groups report the overlap audit as unavailable.

`model.save(path)` writes finite JSON atomically and does not overwrite by default. `ScreeningModel.load(path)` validates schema, rule indices, tier keys and feature mapping. No pickle or expression execution is used.

## Training

```python
trainer = STCA(
    direction="high", tiers=(0.30,0.20,0.10),
    scan=ScanConfig(mode="value",step=1.0,min_subset_size=1),
    max_rank=10, family_size=8, hierarchy="direct",
    target_name="Tg", target_unit="degC",
    mcc_mode="positive", min_selected_support=1,
)
model = trainer.fit_smiles(smiles, y)
```

`fit`/`fit_smiles` return a `ScreeningModel` rather than the trainer. The fitted object is also available as `trainer.model_`. `scan_result_` contains the complete scan trajectory; `candidate_table_` contains all per-tier candidate metrics. `export_diagnostics(directory)` exports the source-only tables.

For a binary matrix use `fit(X,y,feature_names_=[...],groups=[...])`. A DataFrame's columns supply the feature names. For historical MACCS data supply `feature_names_=MACCS_NAMES` and `feature_spec=MACCS_SPEC` from `stca.chemistry`, or use the SMILES helper. The generic API does not silently declare arbitrary 167-column data to be MACCS.

The source-F1 family has anchors for the available positive-only, negative-only and mixed classes. Family size must be at least three. Generic training permits a one-sided feature hierarchy; `ec_reverse` requires both signs to match the retrieved electrical-core requirement. No eligible features raises a descriptive error; no valid rule at a tier is saved as abstention.

## Data helpers

`grouped_holdout(groups,test_fraction=0.20,seed=42)` returns source/test row indices. It randomizes groups, not labels. It is **not** chemical extrapolation or t-SNE.

`load_legacy_pair(fingerprint_csv, property_csv, has_header=False, layout="maccs167")` reads strict two-column files and requires unique, identical PID sets. It aligns measurements by PID and retains fingerprint order. No silent inner join is performed.

`fingerprints_from_strings(strings,layout="maccs166_keys1to166")` explicitly prepends the dummy zero bit. The default requires 167 bits and never guesses a missing dummy position.

`ec_to_log10_s_cm(values,unit)` accepts `S/cm`, `S/m`, `log10(S/cm)` or `log10(S/m)` and returns the internal log10(S/cm) representation. Raw zero/negative conductivity values are rejected.

## Legacy import

```python
from stca import import_legacy_rule
model = import_legacy_rule(
    "locked_inter_top1_frozen_external_summary.csv",
    row_index=0, tier=0.20, direction="high", target_name="Tg", target_unit="degC",
    selection_provenance="User-confirmed source-only representative; exact source filename/version",
    train_cutoff=None,
)
```

The example requires a row containing a complete `pattern_signature` or both `keys` and `values`; not every legacy summary file has those columns. Select the matching complete output file explicitly. `row_index` is a zero-based positional CSV row after the header. No external metric is copied as a new score, and no speculative rule is reconstructed from a pattern name alone.
