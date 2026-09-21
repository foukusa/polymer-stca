# Windows reproduction (Python 3.10.6)

After installing this corrected local source, no legacy core scripts or handwritten parameters are needed. Put the five supplied result archives in one private directory, not inside the Git repository. In PowerShell run:

```powershell
python -m stca verify-results --reference-dir "D:\hongo\STCA_reference_archives" --output "D:\hongo\STCA_verified_1.0"
```

Choose a new output directory for each run. `PASS_RULE_FAMILY_SCORE_PARITY` is the scoped final-rule/family/score result, not a claim that all supplementary coefficients or all independent accuracy tests passed. Exact scope is in `status.json` and the individual CSVs.

For ordinary candidate screening, only candidates.csv is needed:

```powershell
python -m stca screen --profile ec-low --tier 0.10 --input candidates.csv --output ec_screen.csv
```

The provided CI has an exact Windows Python 3.10.6 job. This is configuration, not evidence of a completed GitHub run. Current local execution environment is recorded separately in VALIDATION.md.
