# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Sequence

import numpy as np
import pandas as pd

from .errors import STCAError


def positive_int(value, name: str, minimum: int = 1) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < minimum:
        raise STCAError(f"{name} must be an integer >= {minimum}.")
    return int(value)


def fraction(value, name: str = "tier") -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise STCAError(f"{name} must be a fraction, e.g. 0.20, not 20.")
    value = float(value)
    if not math.isfinite(value) or not 0 < value < 1:
        raise STCAError(f"{name} must lie strictly between 0 and 1.")
    return value


def binary_matrix(X, n_features: int | None = None, allow_empty: bool = False) -> np.ndarray:
    try:
        a = np.asarray(X, dtype=float)
    except (ValueError, TypeError) as exc:
        raise STCAError("X must be a rectangular numeric binary matrix.") from exc
    if a.ndim != 2 or a.shape[1] < 1 or (a.shape[0] == 0 and not allow_empty):
        raise STCAError("X must have shape (n_samples, n_features) with nonempty axes.")
    if n_features is not None and a.shape[1] != n_features:
        raise STCAError(f"Expected {n_features} feature columns, received {a.shape[1]}.")
    if not np.isfinite(a).all() or not np.isin(a, (0, 1)).all():
        raise STCAError("X must contain only 0/1: missing or continuous values are not silently binarized.")
    return a.astype(np.uint8)


def target_vector(y, n: int | None = None, min_n: int = 1) -> np.ndarray:
    try:
        a = np.asarray(y, dtype=float)
    except (ValueError, TypeError) as exc:
        raise STCAError("The target must be numeric.") from exc
    if a.ndim != 1 or len(a) < min_n or (n is not None and len(a) != n):
        raise STCAError("The target must be a 1D array aligned one-to-one with X.")
    if not np.isfinite(a).all():
        raise STCAError("Targets must be finite; missing records must be resolved explicitly.")
    return a


def feature_names(names: Sequence[str] | None, n: int) -> tuple[str, ...]:
    if names is None:
        return tuple(f"x{i}" for i in range(n))
    if isinstance(names, str) or len(names) != n:
        raise STCAError("feature_names must provide exactly one distinct name per column.")
    names = tuple(str(x) for x in names)
    if len(set(names)) != n or any(not x.strip() for x in names):
        raise STCAError("Feature names must be unique and nonempty.")
    return names


def checked_frame_matrix(X, expected_names: tuple[str, ...] | None = None):
    if isinstance(X, pd.DataFrame):
        names = feature_names(X.columns, X.shape[1])
        if expected_names is not None:
            if set(names) != set(expected_names):
                raise STCAError("DataFrame columns do not match the fitted feature schema.")
            # Deliberate name-based alignment; arrays must already have the right order.
            X = X.copy()
            X.columns = names
            X = X.loc[:, list(expected_names)]
            names = expected_names
        return binary_matrix(X), names
    return binary_matrix(X, len(expected_names) if expected_names else None), None


def ensure_direction(direction: str) -> str:
    if direction not in ("high", "low"):
        raise STCAError("direction must be 'high' or 'low'.")
    return direction
