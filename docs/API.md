# API reference

The [README](../README.md) and [protocol guide](PROTOCOL_USAGE.md) show complete calls.

- `load_pretrained(profile, protocol="paper", warn=True)`: load a directly fitted frozen profile without reading training data. Accepts `tg-high`, `ec-low`, `ec-high` (also tg/ec with direction).
- `STCA.for_profile(profile, protocol="paper", **overrides)`: build the matching task recipe, using a bundled primary family for electrical profiles. `paper` requires explicit selection data; `source_locked` does not use it.
- `model.new_trainer()`: reconstruct the full saved recipe, not a winner. Fit again with actual labeled data.
- `trainer.fit(X, y, feature_names_=..., feature_spec=..., groups=..., selection_data=SelectionData(...), acknowledge_selection_labels=True)`: train and freeze. Explicit extra labels are required only for a selection protocol that uses them.
- `trainer.fit_smiles(smiles, y, ...)`: same training interface plus canonical-SMILES grouping and MACCS generation.
- `model.screen(smiles, tier=.2, errors="raise")`: structure-only inference, no target required.
- `model.screen_fingerprints(X, tier=.2)`: inference on the stored binary descriptor schema.
- `model.evaluate(X, y, tier=.2, cutoff_mode="fixed_train", groups=..., allow_overlap=False)`: evaluate fixed rules; never refit. `dataset_relative` has a different label definition. Verified models use PID group hashes; supply the same identity convention.
- `model.evaluate_smiles(smiles, y, ...)`: generate MACCS before frozen evaluation; PID-based reference models require explicit `groups`.
- `trainer.export_diagnostics(directory)`: candidate table, selected family, scan and ranking diagnostics.
- `model.save(path)` / `ScreeningModel.load(path)`: finite JSON model persistence, no pickle execution.
- `stca.verified.run(reference_dir, output)`: actual private real-data replay from the supplied research result ZIPs, with assertions after fitting.

`STCA()` without a task preset remains a generic source-only estimator. `SelectionData`, `TemplateFamily`, `ScanConfig`, `ec_to_log10_s_cm`, `MACCS_NAMES` and `MACCS_SPEC` expose explicit configuration and representation choices. Invalid targets, incomplete template depths, missing selection acknowledgement and invalid structures are rejected instead of silently changing the method.
