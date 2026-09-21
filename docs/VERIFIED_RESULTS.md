# Real-data rule, family and metric verification — 1.0

Executed on 2026-09-21. This report concerns the supplied archived Tg-core/EC-core calculation, not every statement or result in the final manuscript.

## Inputs and independent checks

The thermal complete archive supplies 7,291 PID/SMILES/Tg records, explicit submitted inter/extra labels (5,833/1,458), candidate metrics, family lists and original selected representatives. Units are degrees Celsius. Fingerprints were regenerated from those actual SMILES without recapping.

The electrical V15 archive supplies 863 PID/SMILES/log10(S/cm) records and a previous full MACCS verification table. It reports normal/extra counts of 691/172 but does not include an explicit original PID membership CSV. The refit uses the first 691 versus following 172 rows, **only after independently reproducing all 171 archived STCA family/scope metric records on that reconstruction**. This is strong output consistency evidence, not a claim that the missing original membership file was independently recovered.

The thermal complete archive has 120 STCA candidates per tier and three target-property scopes: 120 × 3 × 3 = 1,080 metric rows. The electrical primary family has 57 member/tier combinations and three scopes: 57 × 3 = 171 rows. All **1,251** matched, including discrete confusion counts where present and independently recomputed continuous metrics. Reference scores were used after fitting for assertions, never to inject a selected rule.

## Fresh fitted paper models

| Profile | Tier | Reference core score | Refit core score | Rule |
|---|---:|---:|---:|---|
| tg-high | 0.30 | 0.700057575903 | 0.700057575903 | MATCH |
| tg-high | 0.20 | 0.565267912769 | 0.565267912769 | MATCH |
| tg-high | 0.10 | 0.327636529343 | 0.327636529343 | MATCH |
| ec-low | 0.20 | 0.399329543790 | 0.399329543790 | MATCH |
| ec-low | 0.15 | 0.353636640108 | 0.353636640108 | MATCH |
| ec-low | 0.10 | 0.280353608766 | 0.280353608766 | MATCH |
| ec-low | 0.05 | 0.185058166151 | 0.185058166151 | MATCH |
| ec-high | 0.20 | 0.340605814256 | 0.340605814256 | MATCH |
| ec-high | 0.15 | 0.288988217671 | 0.288988217671 | MATCH |
| ec-high | 0.10 | 0.259907812638 | 0.259907812638 | MATCH |
| ec-high | 0.05 | 0.190408371261 | 0.190408371261 | MATCH |

The maximum difference between the tabulated reference and freshly recomputed selected score is 1.1102230246251565e-16. This is floating-point agreement, not a tolerance adjusted to make an adverse result disappear.

The score is the strict harmonic mean of inter/extra/all AS, with AS = (MCC + precision + F1)/3 and separately defined within-scope percentile labels. It is **not** the fixed-training-threshold extra-set F1 from the earlier user's terminal table. Comparing these two numbers directly would be incorrect.

Six models (paper and source_locked for each property direction) were fitted, saved, and fitted again through `new_trainer()` using only their stored recipe and the original labeled inputs. Each paired rule and regenerated-record screening mask matched. The paper masks also match the original SI snapshot rule conditions on all supplied structures. The source-only Tg choices agree with the explicitly locked archive; source-only EC choices agree with maximum valid source AS in the same declared EC family. This does not certify their held-out predictive usefulness.

## Why matching protocols matters

The generic estimator searches all prefixes and builds its own F1 family before selecting source AS. The recorded electrical primary analysis instead used a predeclared family: low EC 6,6,6,7 candidates and high EC 8 at each tier. Its archived core representative was selected by the core harmonic score. Changing either family or selection scope can change the winner. STCA 1.0 includes these templates as ranked prefix lengths and regenerates their MACCS identities from data.

The `paper` name is an explicit archival reconstruction label. It does not mean every supplementary analysis used external selection. The thermal-gap supplement records source-only locked analyses, and those remain a distinct protocol. No final-test labels are silently added to the default generic estimator.

## Boundaries and nonmatches

- **Thermal precomputed correlations:** the archive's saved precomputed correlation coefficients differ from a fresh value-grid scan (maximum absolute difference approximately 0.0018706407). The used top-10 positive and negative ordering, all candidate masks/metrics, retained families and selected rules agree. Full coefficient-level numerical reproduction is **not** claimed. `scan_reference_audit.csv` retains these differences instead of hiding them.
- **Raw fingerprint/order files:** original raw fingerprint CSVs and their original prediction-hash row order are not present in these result ZIPs. Current pretrain/custom per-record masks were compared directly; equality to every original archived SHA-1 prediction-mask string is not claimed. The historical V15 MACCS audit is supporting provenance, not a fresh original-bitwise verification.
- **Electrical membership:** row-order reconstruction is gated against all supplied family/scope results as described above, rather than labeled an explicit original split.
- **Scope-selected results:** the historical extra labels participate in paper core selection. These are retrospective parity results, not untouched-test accuracy estimates or new experiments.
- **Other SI results:** V14/V15 complete family tables match; V13 and thermal-gap supplement manifests were read to establish roles. Their 1,000-resample analyses, cross-property epsilon/Tm/Td/TC results and all alternative splits were not rerun.
- **Environment:** actual local refit used Linux CPython 3.13.5, NumPy 2.3.5, pandas 2.2.3, SciPy 1.17.0 and RDKit 2025.09.4. Python 3.10.6 compatibility tests are configured but the local runtime was not Python 3.10.6.

## Readable source locations

| Supplied archive | Relevant internal file / role |
|---|---|
| reviewer_ready_thermal_complete_outputs.zip | split_membership/submitted_tsne_split_membership_audit.csv; tables/all_candidate_dataset_metrics.csv; tables/selected_advantageous_patterns_by_harmonic_Tg_core.csv; tables/locked_inter_top1_frozen_external_summary.csv |
| reviewer_ready_thermal_gap_supplement_outputs.zip | supplement_manifest.json; source-only frozen alternative-split context |
| reviewer_ready_electrical_gap_supplement_outputs_v13.zip | supplement_manifest.json; PRIMARY_STCA_family_full_pipeline_permutation.csv; family-refit scope context |
| reviewer_ready_electrical_family_transfer_structure_outputs_v14.zip | family_level_EC_to_epsAC/BOTTOM_and_TOP_EC_picked_family_all_members.csv; equal to V15 |
| reviewer_ready_electrical_family_transfer_structure_outputs_v15.zip | smiles_ec_all_build/smiles_ec_all_validated_with_header.csv; corresponding build audit; family_level_EC_to_epsAC/BOTTOM_and_TOP_EC_picked_family_all_members.csv |

The aggregate model receipt in `src/stca/assets/verified_refit_summary.json` records input archive identities and the actual environment. No supplied data archives or per-material records are bundled in this public source tree or its wheel.
