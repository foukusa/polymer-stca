# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

"""Exceptions distinguish invalid inputs, unavailable rules and provenance warnings."""

class STCAError(ValueError):
    """Invalid STCA input, configuration, or serialized artifact."""

class NoValidRuleError(STCAError):
    """The predeclared candidate family contains no valid source-selected rule."""

class ArchivedProfileWarning(UserWarning):
    """An archived scope-selected rule is not a new prospective validation."""
