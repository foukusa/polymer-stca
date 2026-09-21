# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
import numpy as np

from .errors import STCAError
from .validation import binary_matrix, positive_int


@dataclass(frozen=True)
class Rule:
    """A nonempty AND of signed binary literals, using explicit column indices."""
    keys: tuple[int, ...]
    values: tuple[int, ...]
    name: str = "custom_rule"
    family: str = "custom"

    def __post_init__(self):
        object.__setattr__(self, "keys", tuple(self.keys))
        object.__setattr__(self, "values", tuple(self.values))
        if not self.keys or len(self.keys) != len(self.values):
            raise STCAError("A rule requires equal, nonempty keys/values.")
        if any(isinstance(k, (bool, np.bool_)) or not isinstance(k, Integral) or k < 0 for k in self.keys):
            raise STCAError("Rule keys must be nonnegative integer column indices.")
        if len(set(self.keys)) != len(self.keys): raise STCAError("Duplicate/contradictory rule keys.")
        if any(not isinstance(v, Integral) or v not in (0, 1) for v in self.values):
            raise STCAError("Rule values must be integer 0 or 1.")
        if not isinstance(self.name, str) or not self.name: raise STCAError("Rule name must be nonempty.")
        object.__setattr__(self, "keys", tuple(int(k) for k in self.keys))
        object.__setattr__(self, "values", tuple(int(v) for v in self.values))

    @property
    def signature(self) -> str:
        return "STCA|AND|" + "&".join(f"K{k}={v}" for k, v in sorted(zip(self.keys, self.values)))

    def apply(self, X) -> np.ndarray:
        a = binary_matrix(X, allow_empty=True)
        if max(self.keys) >= a.shape[1]: raise STCAError("A rule key is outside the input feature schema.")
        return np.all(a[:, self.keys] == np.asarray(self.values), axis=1)

    def expression(self, names=None) -> str:
        return " AND ".join(f"{names[k] if names is not None else 'K'+str(k)}={v}" for k,v in zip(self.keys,self.values))

    def to_dict(self) -> dict:
        return {"keys": list(self.keys), "values": list(self.values), "name": self.name, "family": self.family}

    @classmethod
    def from_dict(cls, obj: dict) -> Rule:
        if not isinstance(obj, dict): raise STCAError("Rule must be an object.")
        try: return cls(**obj)
        except TypeError as exc: raise STCAError("Malformed rule schema.") from exc


def signed_prefix_rules(positive, negative, max_rank: int = 10) -> list[Rule]:
    positive_int(max_rank, "max_rank")
    pos, neg = list(positive)[:max_rank], list(negative)[:max_rank]
    if len(set(pos+neg)) != len(pos+neg): raise STCAError("Signed rankings must be distinct and nonoverlapping.")
    rules = []
    for i in range(1,len(pos)+1):
        rules.append(Rule(tuple(pos[:i]),(1,)*i,f"Top{i}_positive_only","positive_only"))
    for j in range(1,len(neg)+1):
        rules.append(Rule(tuple(neg[:j]),(0,)*j,f"Top{j}_negative_only","negative_only"))
    for i in range(1,len(pos)+1):
        for j in range(1,len(neg)+1):
            rules.append(Rule(tuple(pos[:i]+neg[:j]),(1,)*i+(0,)*j,
                              f"Top{i}_positive_plus_Top{j}_negative","positive_plus_negative"))
    return rules
