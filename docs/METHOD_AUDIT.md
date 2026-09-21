# STCA 1.0 method and provenance audit

Associated manuscript: **Interpretable Substructure-Based Screening of Multi-Property Polymer Dielectrics with Prompt-Ready Rules for Rational Design**, npj Computational Materials.

## Protocols are explicit

| Entry / protocol | Candidate family | Representative selection | Label-use boundary |
|---|---|---|---|
| Generic `STCA()` | Source-F1 family from signed cumulative prefixes | Source AS | Source labels only |
| `for_profile(..., protocol="paper")` | Thermal source-F1 family; bundled electrical primary prefix templates | Strict core-scope harmonic score | Declared inter/extra/all scope, retrospective reconstruction |
| `for_profile(..., protocol="source_locked")` | Matched task family | Source AS | No comparison labels choose the rule |
| `validation_as` | Explicit configured family | Validation AS | Validation set is selection data, not final test data |

Both `load_pretrained()` and task-specific training default to `paper`; generic
training remains source-only. `pretrained.new_trainer()` copies the stored recipe,
not the winner, fitted ranking or reference score. Exact pretrained/custom
agreement requires the same labeled inputs, representation, split and protocol.
Different datasets are not required to reproduce one historical answer.

## Verified scientific content

The author-provided five result archives were used for the documented real-data
refit: 7,291 Tg records and 863 EC records. The recorded checks recovered 11 paper
rules and matched 1,251 archived family/scope metric rows. Model artifacts include
training cutoffs and selection provenance. See `VERIFIED_RESULTS.md` for exact
scores, source locations and limitations, and the current `../VALIDATION.md` for
checks actually performed on this distribution.

In particular, the electrical split was reconstructed from row order and gated
against the archived family/scope metrics, rather than read from a missing
original PID split file. Thermal precomputed coefficients are not numerically
identical to a fresh scan, although the used ranking prefixes and final rule
results agree. Historical core selection uses extra labels and is not an
untouched-test evaluation. Resampling and every other SI task are not claimed to
have been rerun.

## Packaging and source identity

All package-version fields are 1.0. This metadata normalization changes no
substructure condition, numerical training cutoff, selection score, ranking or
training protocol. SI snapshot hash references identify the distributed 1.0
files; their scientific JSON contents differ from the supplied reference only in
the package-version field. Original research archive names (including v13, v14
and v15) remain intact because they identify data sources, not package releases.

No raw author measurement tables, PID/SMILES tables or per-record outputs are
included in the public source ZIP or wheel. Updating a local checkout neither
publishes the package nor asserts permission to redistribute it.
