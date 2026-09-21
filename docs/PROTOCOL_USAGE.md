# Paired protocol API — STCA 1.0

The [README](../README.md#train-with-the-same-protocol) contains executable usage examples.

| Named protocol | Factory | Candidate family | Final selection | Extra selection data |
|---|---|---|---|---|
| paper (default in both profile interfaces) | STCA.for_profile(name) | Tg source-F1/sign-anchored family; EC bundled primary prefix templates | Strict inter/extra/all harmonic AS | Required, explicit acknowledgement |
| source_locked | STCA.for_profile(name, protocol="source_locked") | Same respective family recipe | Source AS | Not accepted |
| generic | STCA.for_profile(name, protocol="generic") or STCA(...) | Generic source F1/sign-anchored family | Source AS | Not accepted |

`load_pretrained(name, protocol="paper")` and `load_pretrained(name, protocol="source_locked")` return directly fitted artifacts for the matching recipe. `legacy_snapshot` explicitly accesses immutable SI-transcribed JSONs; they retain null numerical cutoffs and no complete training recipe.

## Presets

| Profile | Target representation | Scan | Step | Maximum positive/negative prefix | Family size |
|---|---|---|---:|---:|---|
| tg-high | degC | direct, increasing | 1.0 | 10 each | 8 at every tier |
| ec-low | log10(S/cm) | reversed -log10(EC) | 0.01 | 35 each | 6,6,6,7 at bottom20/15/10/5 |
| ec-high | log10(S/cm) | same reversed scan, swap ranking roles once | 0.01 | 35 each | 8 at every tier |

Minimum scanned subset is 1; nominal correlation p threshold is 0.05. The data determine eligible signed rankings. Family templates carry only prefix counts and order, never expected winner literals or target performance scores. Missing required depth is an explicit error, not a reason to inject reference keys.

## Saved recipe replay

`model.new_trainer()` reconstructs direction, tiers, ScanConfig, hierarchy, target units, maximum ranks, family/selection metrics, protocol ID, support validity and complete template definition. It does not copy `tiers`, `selected_rule`, `signed_rankings`, or scan coefficients into the fitter.

This method is the direct reproducibility contract: use identical data and the explicit selection scope, fit afresh, compare signatures and decisions. A new dataset is allowed to yield a new result. `source_locked` and `paper` cannot be expected to produce identical answers to one another.

Explicit low-level modes (`thermal_core`, `electrical_primary`, `template_source_locked`, `validation_as`) are available. `electrical_primary` still accepts a separately imported complete template family for another archived version. The automatically bundled family is the specific V15-resolved primary family, not an unqualified universal candidate family.

## Version migration

The generic constructor `STCA()` and generic `train` command keep their source-only behavior. The task-specific `for_profile`/`train-profile` default is `paper`, matching default `load_pretrained`; it therefore requires explicit selection data and acknowledgement. A source-only user must spell `protocol="source_locked"`, rather than the program silently treating a missing selection set as permission to change algorithms.
