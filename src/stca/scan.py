# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import numpy as np
import pandas as pd
from scipy import stats

from .errors import STCAError
from .validation import binary_matrix, target_vector, positive_int, ensure_direction


@dataclass(frozen=True)
class ScanConfig:
    mode: str = "value"
    step: float = 1.0
    min_subset_size: int = 1
    max_points: int = 10000
    quantile_points: int = 81
    nominal_alpha: float = 0.05
    nominal_filter: str = "legacy_both_signs"

    def __post_init__(self):
        if self.mode not in ("value", "unique", "quantile"): raise STCAError("Invalid scan mode.")
        if not isinstance(self.step, (float,int)) or isinstance(self.step,bool) or not math.isfinite(self.step) or self.step <= 0:
            raise STCAError("scan step must be positive and finite.")
        positive_int(self.min_subset_size,"min_subset_size")
        positive_int(self.max_points,"max_points",4)
        positive_int(self.quantile_points,"quantile_points",4)
        if not 0 < self.nominal_alpha <= 1: raise STCAError("nominal_alpha must lie in (0,1].")
        if self.nominal_filter not in ("legacy_both_signs", "strict", "none"):
            raise STCAError("Invalid nominal_filter policy.")

    def to_dict(self): return asdict(self)


@dataclass
class ScanResult:
    table: pd.DataFrame
    thresholds: np.ndarray
    frequencies: np.ndarray
    counts: np.ndarray
    direction: str
    truncated: bool


def scan_frequencies(X, y, *, direction="high", config: ScanConfig | None = None) -> ScanResult:
    """Correlate threshold with each feature's frequency in {signed_y >= threshold}.

    The nominal p-values replicate a historical filter, not independent evidence:
    adjacent sliding subsets are nested. Use outer held-out evaluation for claims.
    """
    a = binary_matrix(X); y = target_vector(y,len(a),4)
    ensure_direction(direction)
    cfg = config or ScanConfig()
    score = y if direction == "high" else -y
    if np.ptp(score) == 0: raise STCAError("Cannot scan a constant target.")
    order = np.argsort(score, kind="stable")
    s = score[order]; ordered = a[order]
    cumulative = np.cumsum(ordered[::-1],axis=0,dtype=np.float64)[::-1]
    truncated = False
    if cfg.mode == "value":
        low = math.floor(float(s[0])/cfg.step)*cfg.step
        high = math.ceil(float(s[-1])/cfg.step)*cfg.step
        raw_n = int(math.floor((high + 0.5*cfg.step - low)/cfg.step)) + 1
        if raw_n > 2_000_000:
            raise STCAError("Value grid exceeds 2,000,000 points. Choose a larger explicit step or another mode.")
        thresholds = np.arange(low,high+0.5*cfg.step,cfg.step,dtype=float)
    elif cfg.mode == "unique": thresholds = np.unique(s)
    else: thresholds = np.unique(np.quantile(s,np.linspace(0,0.99,cfg.quantile_points)))
    if len(thresholds) > cfg.max_points:
        thresholds = thresholds[np.linspace(0,len(thresholds)-1,cfg.max_points).round().astype(int)]
        truncated = True
    first = np.searchsorted(s,thresholds,side="left")
    counts = len(s)-first
    ok = (first<len(s)) & (counts>=cfg.min_subset_size)
    thresholds, first, counts = thresholds[ok], first[ok], counts[ok]
    if len(thresholds) < 4: raise STCAError("Too few valid sliding-threshold points; at least four are required.")
    f = cumulative[first]/counts[:,None]
    tc = thresholds-thresholds.mean(); fc = f-f.mean(axis=0)
    numerator = np.sum(tc[:,None]*fc,axis=0)
    denominator = np.sqrt(np.sum(tc**2)*np.sum(fc**2,axis=0))
    r = np.divide(numerator,denominator,out=np.zeros_like(numerator),where=denominator>0)
    r = np.clip(r,-1,1)
    dfree = len(thresholds)-2
    t_stat = r*np.sqrt(dfree)/np.sqrt(np.maximum(1.0-r**2,1e-15))
    p = 2*stats.t.sf(np.abs(t_stat),dfree)
    prev = a.mean(axis=0)
    table = pd.DataFrame({"key":np.arange(a.shape[1]), "correlation":r,
                          "abs_correlation":np.abs(r),"nominal_p_value":p,
                          "feature_prevalence":prev,"scan_points":len(thresholds)})
    table = table[(prev>0)&(prev<1)].reset_index(drop=True)
    return ScanResult(table,thresholds,f,counts,direction,truncated)


def signed_rankings(result: ScanResult, config: ScanConfig | None = None):
    cfg = config or ScanConfig()
    table = result.table.copy()
    sig = table[table.nominal_p_value<=cfg.nominal_alpha]
    use_filter = cfg.nominal_filter == "strict" or (
        cfg.nominal_filter == "legacy_both_signs" and
        (sig.correlation>0).any() and (sig.correlation<0).any())
    if use_filter: table = sig
    pos = table[table.correlation>0].sort_values(["correlation","key"],ascending=[False,True])
    neg = table[table.correlation<0].sort_values(["abs_correlation","key"],ascending=[False,True])
    return pos.key.astype(int).tolist(),neg.key.astype(int).tolist(),{
        "nominal_filter_applied":bool(use_filter),
        "nominal_p_interpretation":"Historical nested-subset filter; not independent-sample significance.",
    }
