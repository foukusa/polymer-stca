# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

from __future__ import annotations

import ast
import re
import numpy as np
import pandas as pd

from .errors import STCAError
from .rules import Rule
from .chemistry import MACCS_NAMES, MACCS_SPEC
from .model import ScreeningModel, SCHEMA_VERSION, PACKAGE_VERSION, tier_key
from .validation import fraction, ensure_direction


def rule_from_signature(signature: str,*,name="imported_rule") -> Rule:
    """Parse the historical STCA|AND|Kx=1&Ky=0 format without executing code."""
    if not isinstance(signature,str) or not signature.startswith("STCA|AND|"):
        raise STCAError("Expected a signed STCA AND signature.")
    tokens=signature[len("STCA|AND|"):].split("&")
    keys=[]; values=[]
    for token in tokens:
        m=re.fullmatch(r"K(\d+)=(0|1)",token)
        if m is None: raise STCAError("Invalid rule signature token.")
        keys.append(int(m[1])); values.append(int(m[2]))
    return Rule(tuple(keys),tuple(values),name,"legacy_import")


def _sequence(s):
    try:
        value=ast.literal_eval(s) if isinstance(s,str) else s
    except (ValueError,SyntaxError) as exc: raise STCAError("Invalid keys/values sequence.") from exc
    if not isinstance(value,(list,tuple)): raise STCAError("keys and values must be lists or tuples.")
    return tuple(value)


def import_legacy_rule(csv_path,*,row_index:int,tier:float,direction:str,target_name:str,
                       target_unit:str,selection_provenance:str,train_cutoff=None) -> ScreeningModel:
    """Import one EXPLICITLY chosen row; never rank historical rows using test scores.

    Repeating this for multiple tiers preserves the user's choice instead of
    guessing which of several retrospective reporting scopes is deployable.
    """
    ensure_direction(direction); fraction(tier)
    if not selection_provenance.strip(): raise STCAError("Explicit selection_provenance is required.")
    frame=pd.read_csv(csv_path)
    if not isinstance(row_index,int) or row_index<0 or row_index>=len(frame): raise STCAError("Invalid positional row_index.")
    row=frame.iloc[row_index]
    if "method" in row and str(row["method"])!="STCA": raise STCAError("Chosen row is not the STCA method.")
    if "percentile" in row and not np.isclose(float(row["percentile"]),100*(1-tier),atol=1e-8,rtol=0):
        raise STCAError("Chosen row's historical directional percentile does not match tier.")
    name=str(row.get("pattern_name",f"legacy_row_{row_index}"))
    signature=row.get("pattern_signature",None)
    if isinstance(signature,str): rule=rule_from_signature(signature,name=name)
    elif "keys" in row and "values" in row:
        rule=Rule(_sequence(row["keys"]),_sequence(row["values"]),name,"legacy_import")
    else: raise STCAError("No complete signed rule in this row.")
    if isinstance(signature,str) and "keys" in row and "values" in row and not pd.isna(row["keys"]):
        other=Rule(_sequence(row["keys"]),_sequence(row["values"]),name)
        if other.signature!=rule.signature: raise STCAError("signature disagrees with keys/values.")
    artifact={"schema_version":SCHEMA_VERSION,"package_version":PACKAGE_VERSION,
              "n_features":167,"feature_names":list(MACCS_NAMES),"feature_spec":MACCS_SPEC,
              "direction":direction,"target_name":target_name,"target_unit":target_unit,
              "tiers":{tier_key(tier):{"train_cutoff":train_cutoff,"selected_rule":name,
                        "rules":[{"rule":rule.to_dict()}]}},
              "provenance":{"kind":"explicit_legacy_row_import","selection_provenance":selection_provenance,
                            "source_filename":str(csv_path).replace('\\','/').split('/')[-1],"source_row_position":row_index,
                            "source_metrics_reproduced":False,
                            "note":"No stored external metric is copied into a new evaluation."}}
    return ScreeningModel(artifact)
