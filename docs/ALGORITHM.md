# Computational protocol

## Threshold-frequency analysis

For source binary matrix X and measured target y, define s = y for a high-direction direct scan and s = -y for a low-direction scan. At each threshold t, the retained subset is s >= t. Each key's trajectory is its fraction of ones in that subset. STCA computes the Pearson correlation between t and the frequency trajectory, not the correlation between a feature and one fixed binary target label.

The portable implementation uses sorted source scores and reverse cumulative feature counts. The value grid is based on floor(min/step) through ceil(max/step), inclusive where source support exists. Quantile and unique-value grids are explicit alternatives. Minimum subset size and any grid truncation are recorded.

Nominal p-values use a t transformation with n_thresholds-2 degrees of freedom, as in the retrieved core. These nested subsets are not independent observations. The value is a historical feature-screening filter, not an independent test of causal mechanism or chemical significance.

`legacy_both_signs` preserves the retrieved fallback: apply the nominal filter only when both correlation signs remain represented; otherwise retain the unfiltered nonconstant-feature table. `strict` and `none` are explicit alternatives. The applied policy is recorded. Keys are ordered by absolute directional correlation, with key index as the tie break.

## Signed prefixes and family

Positive keys require presence (1); negative keys require absence (0). Each rule is an AND, never an OR and never a majority vote. With p positive and q negative prefixes there are p + q + p*q candidates, so rank caps of ten on both signs produce 120 candidates. No synthetic chemical interpretation is assigned to generic binary columns.

For each requested tier, the package constructs source labels using the source's inclusive percentile cutoff. It sorts candidate rules by source F1 descending and name ascending, anchors the best positive-only, negative-only and mixed family member, and fills the remaining retained family to a configurable size (default eight) by source F1. It does not discard members simply because an external result is invalid.

The deployment representative is the valid retained family member with maximum source AS, with retained-family order as tie break. AS = (MCC + precision + F1)/3. Every threshold, ranking, candidate score and choice uses source records only. A family without a valid source member has a null representative and abstains. It is not silently relaxed.

This representative rule is **not** the historical retrospective maximum of an external-inclusive harmonic score. Treating the latter as a prospective deployment choice would change the evaluation's meaning. The built-in archive is kept separate for exactly this reason.

## EC reversal

`hierarchy="ec_reverse"` always scans -y, where the EC convention is an explicitly stored log10(S/cm) target. For low EC, the reverse scan's positive/negative rankings are used directly. For high EC they swap roles once. The evaluator still applies positive=1 and negative=0. Swapping lists and also flipping their literals would be an erroneous double inversion.

Conversion from log10(S/cm) to log10(S/m) is an addition of 2. Raw EC must be positive before a logarithm is taken. The package never guesses units or whether a logarithm has already been applied.

## Metric validity and cutoffs

A valid rule must select at least the configured source support and have precision greater than the target prevalence. The default generic/Tg mode requires MCC > 0. The explicit EC `nonnegative` mode permits numerical MCC >= -1e-12, following the retrieved V12 convention. Both target classes must exist. Class counts below 20 are flagged; the flag is not silently promoted into a new undocumented scientific rejection rule.

Evaluation returns TP, FP, TN, FN, MCC, precision, recall, specificity, F1, coverage, enrichment factor and AS. `strict_harmonic` returns missing when any required component is invalid, missing or nonpositive. It never removes failed datasets to increase a score.

`fixed_train` evaluates y against the numeric cutoff saved during source fitting. `dataset_relative` recalculates an evaluation-only cutoff from that dataset and labels the result accordingly. It never affects the rule. Percentile ties are inclusive, so the actual positive fraction can differ from the requested nominal tier. A structural rule also need not select the nominal fraction of candidates.

## Split and representation contracts

The training API receives source records only. An outer holdout is supplied separately. `grouped_holdout` is a label-free random group split; it is not advertised as chemical extrapolation, t-SNE, scaffold, or a reconstruction of the historical paper partition. Use frozen externally supplied memberships for the paper's split.

`fit_smiles` retains wildcard connection atoms and does not salt-strip, tautomer-normalize, H-cap or oligomerize. It generates RDKit's 167-position MACCS vector; key 0 is the unused dummy and keys 1..166 retain their numbered positions. The broad RDKit dependency range enables installation, but **does not certify fingerprint parity across versions**. Pin and audit the historical representation for reproduction.

Canonical SMILES are identity checks, not an applicability-domain metric and not complete polymer equivalence. Alternative repeat-unit encodings may still require domain-specific grouping. A failed input is never encoded as all zeros. A malformed or contradictory rule, nonbinary descriptor, undefined tier, unknown target unit conversion or missing training cutoff is rejected rather than guessed.

## Scope limits

No neural regressor, probability calibration, all-range continuous ranking model, C-STCA-specific composite pipeline, benchmark reproduction suite or causal claim is introduced. Training diagnostics describe in-sample discovery; rigorous scientific assessment still requires fixed, genuinely independent or chemically held-out datasets, appropriate resampling and controlled physical validation.
