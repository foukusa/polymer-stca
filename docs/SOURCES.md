# Sources and provenance

## Recommended online reproduction

[Code Ocean research capsule](https://doi.org/10.24433/CO.1601774.v1), as supplied by the project maintainer. The DOI refers to that capsule, not the journal article. Use the capsule's own metadata and terms when citing or reusing its contents.

Associated manuscript: **Interpretable Substructure-Based Screening of Multi-Property Polymer Dielectrics with Prompt-Ready Rules for Rational Design**, npj Computational Materials.

The numerical inputs are the **five author-provided research result archives**, not an online substitute database, generated targets, or earlier smoke-test fixtures. Actual relevant internal paths, row counts, reconstructed electrical membership, matched quantities and limitations are documented in [VERIFIED_RESULTS.md](VERIFIED_RESULTS.md).

The three `*_si20260822.json` snapshots retain the same scientific contents; only their package-version field is labeled 1.0. Their literal definitions came from the archived SI Table S17. They are accessible as `protocol="legacy_snapshot"` and serve as independent frozen rule references. Their distributed-file SHA-256 values are checked by `paper-audit`, a static—not numerical—test. The SI rules and historical reference scores are unchanged; the hash scope is explicitly the files distributed in STCA 1.0.

The six `*_paper_refit.json` and `*_source_locked_refit.json` artifacts were produced by actual `STCA.fit()` calls from the supplied structure/target records. They include numeric training cutoffs, complete retained families, group hashes, selection-role provenance and the training recipe. Their `verified_refit_summary.json` receipt is evidence from the executed fit, not an input used to choose a winner.

The two `*_primary_family_v15.json` configurations contain only resolved prefix lengths, ordering and textual provenance. They do not contain the reference MACCS winner, source metrics or core scores. A new fit learns its own substructure rankings.

Author measurement tables and PIDs/SMILES were used locally for validation but are deliberately not redistributed inside this software package. Distribution permission and original data access terms must be checked separately. Identifying the source as author-provided PoLyInfo-derived research outputs is not a fresh audit of every source-paper measurement or extraction step.

The current method/protocol distinctions are summarized in [METHOD_AUDIT.md](METHOD_AUDIT.md). Executed packaging and installation checks are recorded in [../VALIDATION.md](../VALIDATION.md).
