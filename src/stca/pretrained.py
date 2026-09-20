# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

from __future__ import annotations

from importlib.resources import files
import json
import warnings
import pandas as pd

from .errors import STCAError, ArchivedProfileWarning
from .model import ScreeningModel

PROFILES = {"tg-high":"tg_high_si20260822.json",
            "ec-low":"ec_low_si20260822.json",
            "ec-high":"ec_high_si20260822.json"}


def load_pretrained(property_name: str, *, direction: str | None=None,
                    warn: bool=True) -> ScreeningModel:
    """Load an archived, explicitly sourced rule profile; does not download data.

    'pretrained' is a convenience API name. These are saved Boolean rules, not
    learned neural weights, calibrated probabilities or certified final-paper artifacts.
    """
    key=property_name.lower()
    if key in ("tg","ec"):
        d=direction if direction is not None else "high" if key=="tg" else "low"
        key=f"{key}-{d}"
    elif direction is not None and not key.endswith("-"+direction):
        raise STCAError("Conflicting profile and direction.")
    if key not in PROFILES: raise STCAError(f"Available profiles: {tuple(PROFILES)}")
    text=files("stca").joinpath("assets",PROFILES[key]).read_text(encoding="utf-8")
    model=ScreeningModel(json.loads(text))
    if warn:
        warnings.warn("Loaded archived SI-20260822 core-scope rule snapshot. "
                      "Scope-selected archive; not a newly reproduced source-only/final-paper model. "
                      "Numerical training cutoffs and prospective accuracy are not certified. "
                      "See model.provenance and docs/PROFILES.md.",ArchivedProfileWarning,stacklevel=2)
    return model


def list_profiles() -> pd.DataFrame:
    rows=[]
    for name in PROFILES:
        model=load_pretrained(name,warn=False)
        for tier in model.tiers:
            rows.append({"profile":name,"tier":tier,"direction":model.artifact["direction"],
                         "rule":model.rule_for(tier).signature,"snapshot":"SI-20260822",
                         "kind":"archived_scope_selected"})
    return pd.DataFrame(rows)
