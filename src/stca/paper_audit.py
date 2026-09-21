# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
"""Independent archived-table checks; reference values never enter STCA.fit()."""
from __future__ import annotations
import hashlib
from importlib.resources import files
import json
import pandas as pd
from .pretrained import load_pretrained, PROFILES


def paper_reference():
    return json.loads(files('stca').joinpath('assets', 'paper_reference_si20260822.json').read_text(encoding='utf-8'))


def audit_bundled_rules():
    rows=[]
    for ref in paper_reference()['rows']:
        model=load_pretrained(ref['profile'],protocol='legacy_snapshot',warn=False)
        actual=model.rule_for(ref['tier']).signature
        digest=hashlib.sha256(files('stca').joinpath('assets', PROFILES[ref['profile']]).read_bytes()).hexdigest()
        rows.append({**ref, 'actual_signature':actual,
                     'literal_status':'MATCH' if actual==ref['reference_signature'] else 'MISMATCH',
                     'snapshot_bytes_status':'UNCHANGED' if digest==ref['source_asset_sha256'] else 'CHANGED',
                     'numerical_refit_status':'NOT_EVALUATED_NO_RAW_DATA',
                     'selection_provenance_status':'VERSION_PROTOCOL_RECONCILIATION_REQUIRED'})
    return pd.DataFrame(rows)
