# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

from __future__ import annotations
from importlib.resources import files
import json
import warnings
import pandas as pd
from .errors import STCAError, ArchivedProfileWarning
from .model import ScreeningModel

PROFILES = {"tg-high":"tg_high_si20260822.json",
            "ec-low":"ec_low_si20260822.json", "ec-high":"ec_high_si20260822.json"}

def load_pretrained(property_name: str, *, direction: str | None=None,
                    protocol: str="paper", warn: bool=True) -> ScreeningModel:
    """Load a frozen fitted artifact. Does not read data or train anything.

    paper and source_locked are paired with STCA.for_profile(protocol=...).
    legacy_snapshot preserves the original SI transcription, including null cutoffs.
    """
    key=property_name.lower()
    if key in ("tg","ec"):
        d=direction if direction is not None else "high" if key=="tg" else "low"
        key=f"{key}-{d}"
    elif direction is not None and not key.endswith("-"+direction):
        raise STCAError("Conflicting profile and direction.")
    if key not in PROFILES:
        raise STCAError(f"Available profiles: {tuple(PROFILES)}")
    if protocol not in ("paper","source_locked","legacy_snapshot"):
        raise STCAError("protocol must be paper, source_locked or legacy_snapshot.")
    asset = PROFILES[key] if protocol=="legacy_snapshot" else key.replace("-","_")+"_"+protocol+"_refit.json"
    model=ScreeningModel(json.loads(files("stca").joinpath("assets",asset).read_text(encoding="utf-8")))
    if warn and protocol in ("paper","legacy_snapshot"):
        warnings.warn("Loaded a historical core-scope model. The paper protocol uses inter/extra/all labels for representative selection; its historical extra-set score is not an untouched-test estimate. See model.provenance.", ArchivedProfileWarning,stacklevel=2)
    return model

def list_profiles(*,protocol="paper") -> pd.DataFrame:
    rows=[]
    for name in PROFILES:
        model=load_pretrained(name,protocol=protocol,warn=False)
        for tier in model.tiers:
            rows.append({"profile":name,"tier":tier,"direction":model.artifact["direction"],
                "rule":model.rule_for(tier).signature,"protocol":protocol,
                "train_cutoff":model.artifact["tiers"][format(tier,".12g")].get("train_cutoff"),
                "kind":model.provenance.get("kind")})
    return pd.DataFrame(rows)
