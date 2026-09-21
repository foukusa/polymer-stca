# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

"""Portable STCA training and frozen-rule screening."""
from .model import ScreeningModel, PACKAGE_VERSION as __version__
from .training import STCA
from .scan import ScanConfig, scan_frequencies, signed_rankings
from .rules import Rule, signed_prefix_rules
from .pretrained import load_pretrained, list_profiles
from .metrics import screening_metrics, strict_harmonic
from .data import grouped_holdout, load_legacy_pair, fingerprints_from_strings
from .units import ec_to_log10_s_cm
from .legacy import import_legacy_rule, rule_from_signature
from .errors import STCAError, NoValidRuleError, ArchivedProfileWarning

__all__ = ["STCA","ScanConfig","ScreeningModel","Rule","load_pretrained","list_profiles",
           "scan_frequencies","signed_rankings","signed_prefix_rules","screening_metrics",
           "strict_harmonic","grouped_holdout","load_legacy_pair","fingerprints_from_strings",
           "ec_to_log10_s_cm","import_legacy_rule","rule_from_signature",
           "STCAError","NoValidRuleError","ArchivedProfileWarning"]

from .protocols import SelectionData, TemplateFamily
__all__ += ["SelectionData", "TemplateFamily"]

from .protocols import bundled_primary_family
__all__ += ["bundled_primary_family"]
