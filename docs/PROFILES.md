# Frozen profiles

Both `load_pretrained(profile)` and `STCA.for_profile(profile)` default to `paper`. The default models now contain actual fitted families, cutoffs and complete recipes; they are not the old cutoff-less snapshots. To inspect all exact current conditions:

```bash
python -m stca profiles
python -m stca profiles --protocol source_locked
python -m stca inspect --profile ec-low --protocol paper
```

The paper final rules remain identical to the original SI literals: Tg30/20 requires K142 present and K90/91/93/118/123/128/129/147 absent; Tg10 requires K90/91/93/118/123/128/129/147/155 absent. Low EC requires K163 present and K26/36/39/40/48/49/73/88/102/124/130 absent. High EC requires K36 present. All conditions are AND. Refer to `docs/VERIFIED_RESULTS.md` for the actual refit evidence and its precise scope.

The paired `source_locked` models are separately fitted using source-only selection; they are not promised to equal the paper winner or to be high-accuracy deployment models. The `legacy_snapshot` models preserve the old transcribed artifacts and their null numeric cutoffs. A warning when loading `paper` describes historical selection scope, not a failure to load or an assertion that the rule is invalid.
