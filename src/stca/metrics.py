# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

from __future__ import annotations

import math
import numpy as np

from .errors import STCAError
from .validation import target_vector, fraction, ensure_direction, positive_int


def target_cutoff(y, tier: float, direction: str) -> float:
    """Inclusive cutoff. Tied measurements can exceed the nominal tier fraction."""
    y = target_vector(y)
    tier = fraction(tier)
    ensure_direction(direction)
    return float(np.quantile(y, 1.0 - tier if direction == "high" else tier, method="linear"))


def labels_at(y, cutoff: float, direction: str) -> np.ndarray:
    y = target_vector(y)
    ensure_direction(direction)
    if not isinstance(cutoff, (int, float, np.number)) or not math.isfinite(cutoff):
        raise STCAError("cutoff must be a finite number in the target's stored units.")
    return y >= cutoff if direction == "high" else y <= cutoff


def screening_metrics(labels, selected, *, mcc_mode: str = "positive", min_support: int = 1) -> dict:
    labels = target_vector(labels)
    selected = target_vector(selected, len(labels))
    if not np.isin(labels, (0, 1)).all() or not np.isin(selected, (0, 1)).all():
        raise STCAError("Metric inputs must be binary, without invalid/missing records.")
    positive_int(min_support, "min_support")
    if mcc_mode not in ("positive", "nonnegative"):
        raise STCAError("mcc_mode must be positive or nonnegative.")
    y, p = labels.astype(bool), selected.astype(bool)
    tp = int(np.sum(y & p)); fp = int(np.sum(~y & p))
    tn = int(np.sum(~y & ~p)); fn = int(np.sum(y & ~p))
    n = len(y); s = tp + fp
    precision = tp / s if s else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    denom = math.sqrt(float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)))
    mcc = (tp * tn - fp * fn) / denom if denom else 0.0
    prevalence = float(y.mean())
    reasons = []
    if not 0 < tp + fn < n: reasons.append("target_has_one_class")
    if s < min_support: reasons.append("insufficient_selected_support")
    if not precision > prevalence: reasons.append("precision_not_above_prevalence")
    if (mcc_mode == "positive" and mcc <= 0) or (mcc_mode == "nonnegative" and mcc < -1e-12):
        reasons.append("MCC_validity_failed")
    return {
        "n": n, "positive_n": tp + fn, "negative_n": tn + fp,
        "selected_n": s, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "prevalence": prevalence, "mcc": mcc, "precision": precision,
        "recall": recall, "specificity": specificity, "f1": f1,
        "coverage": s / n, "enrichment_factor": precision / prevalence if prevalence else None,
        "average_score": (mcc + precision + f1) / 3,
        "valid_screen": not reasons, "invalid_reasons": reasons,
        "class_support_at_least_20": min(tp + fn, tn + fp) >= 20,
    }


def strict_harmonic(scores, valid=None) -> float | None:
    """Never discard an invalid/missing component to improve a comprehensive score."""
    values = list(scores)
    if not values: return None
    if valid is not None:
        flags = list(valid)
        if len(flags) != len(values): raise STCAError("valid must align with scores.")
        if not all(flags): return None
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values): return None
    return len(values) / sum(1.0 / v for v in values)
