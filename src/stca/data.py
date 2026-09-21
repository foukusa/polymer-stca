# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .errors import STCAError
from .validation import fraction, positive_int
from .chemistry import validate_maccs167


def grouped_holdout(groups,*,test_fraction=0.20,seed=42):
    """Label-free random group holdout. This is NOT a t-SNE/extrapolation split.

    Fraction applies to groups, not guaranteed record counts. No target sorting,
    stratification or duplicate-group leakage is introduced.
    """
    test_fraction=fraction(test_fraction,"test_fraction")
    positive_int(seed,"seed",0)
    groups=np.asarray(groups)
    if groups.ndim!=1 or len(groups)<2 or pd.isna(groups).any(): raise STCAError("Supply nonmissing 1D groups.")
    normalized=np.asarray([str(v) for v in groups])
    unique=np.unique(normalized)
    if len(unique)<2: raise STCAError("At least two groups are required for holdout.")
    shuffled=np.random.default_rng(seed).permutation(unique)
    n_test=min(len(unique)-1,max(1,int(np.ceil(len(unique)*test_fraction))))
    mask=np.isin(normalized,shuffled[:n_test])
    return np.flatnonzero(~mask),np.flatnonzero(mask)


def fingerprints_from_strings(strings,*,layout="maccs167"):
    strings=list(strings)
    if not strings or any(not isinstance(s,str) or not s or set(s)-{"0","1"} for s in strings):
        raise STCAError("Fingerprint strings must be nonempty strings of 0 and 1; read CSV with dtype=str.")
    expected=167 if layout=="maccs167" else 166 if layout=="maccs166_keys1to166" else None
    if expected is None: raise STCAError("Explicit fingerprint layout must be maccs167 or maccs166_keys1to166.")
    if any(len(s)!=expected for s in strings): raise STCAError(f"Expected exactly {expected} bits per record.")
    a=np.array([[int(c) for c in s] for s in strings],dtype=np.uint8)
    if expected==166: a=np.column_stack([np.zeros(len(a),dtype=np.uint8),a])
    return validate_maccs167(a)


def load_legacy_pair(fingerprint_csv,property_csv,*,has_header=False,layout="maccs167"):
    """Strict PID join for the historical two-column fingerprint/property files.

    Never use row position, auto-detect headers or silently drop unmatched IDs.
    """
    header=0 if has_header else None
    fp=pd.read_csv(Path(fingerprint_csv),header=header,dtype=str,keep_default_na=False)
    prop=pd.read_csv(Path(property_csv),header=header,dtype=str,keep_default_na=False)
    if fp.shape[1]!=2 or prop.shape[1]!=2: raise STCAError("Legacy input files must each have exactly two columns.")
    fp.columns=["id","fingerprint"]; prop.columns=["id","target"]
    for frame in (fp,prop):
        if frame.id.duplicated().any() or frame.id.eq("").any(): raise STCAError("Legacy PID values must be unique and nonempty.")
    if set(fp.id)!=set(prop.id): raise STCAError("Fingerprint/property PID sets differ; no silent inner join is permitted.")
    joined=fp.merge(prop,on="id",validate="one_to_one",sort=False)
    try: y=pd.to_numeric(joined.target,errors="raise").to_numpy(dtype=float)
    except ValueError as exc: raise STCAError("Legacy targets must be numeric.") from exc
    if not np.isfinite(y).all(): raise STCAError("Legacy targets contain nonfinite values.")
    return fingerprints_from_strings(joined.fingerprint,layout=layout),y,joined.id.to_numpy()
