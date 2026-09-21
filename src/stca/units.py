# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

from __future__ import annotations
import numpy as np
from .validation import target_vector
from .errors import STCAError

EC_UNITS = ("S/cm","S/m","log10(S/cm)","log10(S/m)")

def ec_to_log10_s_cm(values, unit: str):
    """Explicit conversion only: no automatic log detection or double logarithm."""
    a = target_vector(values)
    if unit not in EC_UNITS: raise STCAError(f"EC unit must be one of {EC_UNITS}.")
    if unit.startswith("log10"):
        return a.copy() if unit=="log10(S/cm)" else a-2.0
    if (a<=0).any(): raise STCAError("Raw EC values must be positive before taking log10.")
    return np.log10(a) if unit=="S/cm" else np.log10(a)-2.0
