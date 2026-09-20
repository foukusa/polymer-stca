# Archived profiles: exact scope and limitations

Snapshot: `SI-20260822`. Source: uploaded `STCA_SI_fixed_record_tSNE_canonical_grouped_robustness_blue.docx`, Table S17, **Tg-core / EC-core** rows. Rule signs were also checked against available adjacent-version SI text and thermal result-table snippets. This is not a claim of complete file-byte or per-record computational reproduction.

| Profile | Tiers | Required present | Required absent |
|---|---|---|---|
| tg-high | 0.30, 0.20 | 142 | 90, 91, 93, 118, 123, 128, 129, 147 |
| tg-high | 0.10 | none | 90, 91, 93, 118, 123, 128, 129, 147, 155 |
| ec-low | 0.20, 0.15, 0.10, 0.05 | 163 | 26, 36, 39, 40, 48, 49, 73, 88, 102, 124, 130 |
| ec-high | 0.20, 0.15, 0.10, 0.05 | 36 | none |

Every row is an AND of its literals. The table is a signed-literal specification, not the discovery rank order. For example, sorting absent-key numbers for storage leaves the rule's mask unchanged. The absent keys are not reinterpreted as an ordered feature ranking.

The three profiles cover eleven property-tier combinations, but only four distinct Boolean rule signatures. Identical tier rules deliberately remain identical. There is no invented interpolation to tiers such as 12% or 25%.

## Why this is an archive, not a newly validated model

The SI gives scope-specific representatives. In particular, a representative selected by a score involving inter/extra/all is not automatically the top source-only representative. Some electrical-all rows use different keys from EC-core, and the EC-to-epsilon supplement explicitly allows different family members for different tasks. None of those stronger or different claims is substituted for these core-scope masks.

The package includes no archived numerical cutoff, calibrated success probability or regression coefficient. The asset sets `train_cutoff: null`, `is_final_paper_artifact: false`, and `original_full_pipeline_reproduced_in_this_package: false`. It emits an archive warning on load. Missing cutoffs are not guessed from an unrelated dataset.

Local tests verify schema consistency, signed-literal application, matching against independent Boolean reference masks, and nonmatching witnesses formed by flipping required literals. They do **not** establish that the package reproduces each paper's original TP/FP/MCC/F1 or held-out membership.

## Promoting a final model

For a final paper release, verify the exact original input matrices and PID memberships, Python/RDKit preprocessing policy, positive/negative rankings, per-tier candidate family, rule selection scope and numerical cutoffs. Preserve old snapshots when adding a new one; do not silently change their meaning. Prefer a source-locked deployment artifact with independently evaluated metrics.

An explicit legacy-row importer is available for a **user-selected** row with complete signed keys or `STCA|AND|Kx=1&Ky=0` signature. It never automatically chooses the row with the best external score. `scripts/verify_against_legacy.py` provides an optional scan/ranking/prefix-mask parity adapter for trusted original Python files and original two-column CSVs. It must be run locally with those files; no report from that adapter is claimed in this delivery.
