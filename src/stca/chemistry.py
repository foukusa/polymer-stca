# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

from __future__ import annotations

import numpy as np
import pandas as pd
from .errors import STCAError

MACCS_NAMES = tuple(f"K{i}" for i in range(167))
MACCS_SPEC = {"kind":"rdkit_maccs167", "n_features":167, "dummy_bit":0,
              "real_keys":"1..166", "smiles_policy":"as_provided_no_capping_no_salt_or_tautomer_normalization"}


def _rdkit():
    try:
        from rdkit import Chem, DataStructs, rdBase
        from rdkit.Chem import MACCSkeys
    except ImportError as exc:
        raise ImportError("SMILES support requires RDKit. Install with: python -m pip install rdkit") from exc
    return Chem, DataStructs, rdBase, MACCSkeys


def maccs_from_smiles(smiles, *, errors="raise"):
    """Return (X, row audit). Invalid rows are -1, never all-zero absent-key hits."""
    if errors not in ("raise", "report"): raise STCAError("errors must be raise or report.")
    if isinstance(smiles,str): raise STCAError("Pass a list of SMILES, not a single string.")
    smiles = list(smiles)
    if not smiles: raise STCAError("No SMILES supplied.")
    Chem, DataStructs, rdBase, MACCSkeys = _rdkit()
    X = np.full((len(smiles),167),-1,dtype=np.int8)
    rows = []
    for i,s in enumerate(smiles):
        # No preprocessing: changing end-group chemistry can change MACCS bits.
        mol = Chem.MolFromSmiles(s) if isinstance(s,str) and s.strip() else None
        valid = mol is not None and mol.GetNumAtoms()>0 and any(a.GetAtomicNum()>0 for a in mol.GetAtoms())
        if not valid:
            if errors == "raise": raise STCAError(f"Invalid/nonmaterial SMILES at row position {i}: {s!r}")
            rows.append({"row_position":i,"smiles":s,"canonical_smiles":None,"input_valid":False,
                         "input_error":"invalid_or_empty_smiles"})
            continue
        arr = np.zeros(167,dtype=np.int8)
        DataStructs.ConvertToNumpyArray(MACCSkeys.GenMACCSKeys(mol),arr)
        if arr[0]!=0: raise STCAError("Unexpected RDKit MACCS dummy bit; representation check failed.")
        X[i] = arr
        rows.append({"row_position":i,"smiles":s,"canonical_smiles":Chem.MolToSmiles(mol),
                     "input_valid":True,"input_error":""})
    audit = pd.DataFrame(rows)
    audit.attrs["rdkit_version"] = rdBase.rdkitVersion
    return X,audit


def validate_maccs167(X):
    from .validation import binary_matrix
    a = binary_matrix(X,167)
    if (a[:,0]!=0).any(): raise STCAError("MACCS bit 0 is a dummy and must remain 0.")
    return a
