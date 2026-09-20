# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from .chemistry import MACCS_NAMES, maccs_from_smiles, validate_maccs167
from .errors import STCAError, NoValidRuleError
from .metrics import target_cutoff, labels_at, screening_metrics
from .rules import Rule
from .validation import fraction, feature_names, checked_frame_matrix, target_vector, ensure_direction, positive_int

SCHEMA_VERSION = 1
PACKAGE_VERSION = "0.1.0rc2"


def tier_key(tier: float) -> str:
    return format(fraction(tier), ".12g")


def hash_group(value) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def dump_json(path, data, *, overwrite=False):
    path = Path(path)
    if path.exists() and not overwrite: raise FileExistsError(f"Output already exists: {path}")
    text = json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp = tempfile.mkstemp(dir=path.parent,prefix=path.name+".",suffix=".tmp")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f: f.write(text+"\n")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


class ScreeningModel:
    """Frozen signed rules. The selected flag is not a probability or a property value."""

    def __init__(self, artifact: dict):
        # A defensive JSON copy also disallows NaN and arbitrary Python objects.
        try: obj = json.loads(json.dumps(artifact,allow_nan=False))
        except (TypeError,ValueError) as exc: raise STCAError("Artifact must contain finite JSON values only.") from exc
        if not isinstance(obj,dict) or obj.get("schema_version")!=SCHEMA_VERSION:
            raise STCAError("Unsupported STCA artifact schema_version.")
        required = {"n_features","feature_names","feature_spec","direction","target_name","target_unit","tiers","provenance"}
        if required-set(obj): raise STCAError(f"Model fields missing: {sorted(required-set(obj))}")
        ensure_direction(obj["direction"])
        n = positive_int(obj["n_features"],"n_features")
        names = feature_names(obj["feature_names"],n)
        spec = obj["feature_spec"]
        if not isinstance(spec,dict) or spec.get("kind") not in ("binary","rdkit_maccs167"):
            raise STCAError("Unknown feature specification.")
        if spec["kind"]=="rdkit_maccs167" and (n!=167 or names!=MACCS_NAMES):
            raise STCAError("MACCS models must use 167 columns K0..K166, with dummy bit 0.")
        if not isinstance(obj["tiers"],dict) or not obj["tiers"]: raise STCAError("Model tiers are missing.")
        if not isinstance(obj["provenance"],dict): raise STCAError("Model provenance must be an object.")
        for key,entry in obj["tiers"].items():
            try: expected_key = tier_key(float(key))
            except (ValueError,TypeError) as exc: raise STCAError("Malformed tier key.") from exc
            if expected_key != key or not isinstance(entry,dict): raise STCAError("Noncanonical tier entry.")
            if "rules" not in entry or not isinstance(entry["rules"],list): raise STCAError("Missing tier rules.")
            names_seen = set()
            for record in entry["rules"]:
                if not isinstance(record,dict) or "rule" not in record: raise STCAError("Malformed rule record.")
                rule = Rule.from_dict(record["rule"])
                if max(rule.keys)>=n: raise STCAError("Serialized rule key exceeds schema.")
                if spec["kind"]=="rdkit_maccs167" and 0 in rule.keys: raise STCAError("Dummy MACCS key 0 cannot be a rule.")
                if rule.name in names_seen: raise STCAError("Rule names must be unique within each tier.")
                names_seen.add(rule.name)
            chosen = entry.get("selected_rule")
            if chosen is not None and chosen not in names_seen: raise STCAError("Selected rule not in saved family.")
            cutoff = entry.get("train_cutoff")
            if cutoff is not None and (isinstance(cutoff,bool) or not isinstance(cutoff,(float,int)) or not math.isfinite(cutoff)):
                raise STCAError("Invalid stored training cutoff.")
        self._artifact = obj

    @property
    def artifact(self) -> dict:
        return json.loads(json.dumps(self._artifact))

    @property
    def tiers(self) -> tuple[float, ...]:
        return tuple(float(t) for t in self._artifact["tiers"])

    @property
    def provenance(self) -> dict: return self.artifact["provenance"]

    def _entry(self,tier):
        key = tier_key(tier)
        if key not in self._artifact["tiers"]:
            raise STCAError(f"Tier {tier} unavailable. Available fractions: {self.tiers}. No interpolation is performed.")
        return self._artifact["tiers"][key]

    def rule_for(self,tier: float, *, rule_name: str | None = None) -> Rule:
        entry = self._entry(tier)
        chosen = rule_name or entry.get("selected_rule")
        if chosen is None: raise NoValidRuleError(f"No valid frozen rule at tier {tier}; the model abstains.")
        for record in entry["rules"]:
            if record["rule"]["name"]==chosen: return Rule.from_dict(record["rule"])
        raise STCAError(f"Unknown rule name {chosen!r} at tier {tier}.")

    def _matrix(self,X):
        names = tuple(self._artifact["feature_names"])
        a,_ = checked_frame_matrix(X,names)
        if self._artifact["feature_spec"]["kind"]=="rdkit_maccs167": a=validate_maccs167(a)
        return a

    def screen_fingerprints(self, X, *, tier: float=0.20) -> pd.DataFrame:
        a = self._matrix(X)
        rule = self.rule_for(tier)
        flags = a[:,rule.keys]==np.asarray(rule.values)
        names = self._artifact["feature_names"]
        missing, forbidden = [],[]
        for row in a:
            missing.append(";".join(names[k] for k,v in zip(rule.keys,rule.values) if v==1 and row[k]!=1))
            forbidden.append(";".join(names[k] for k,v in zip(rule.keys,rule.values) if v==0 and row[k]!=0))
        return pd.DataFrame({
            "row_position":np.arange(len(a)),"input_valid":True,
            "selected":np.all(flags,axis=1),"rule_name":rule.name,"tier":float(tier),
            "target_direction":self._artifact["direction"],"matched_literals":flags.sum(axis=1),
            "required_literals":len(rule.keys),"missing_required_present":missing,
            "unexpected_present":forbidden,"rule_signature":rule.signature,
            "profile_kind":self._artifact["provenance"].get("kind","unspecified"),
        })

    def screen(self, smiles, *, tier: float=0.20, errors: str="raise") -> pd.DataFrame:
        if self._artifact["feature_spec"]["kind"]!="rdkit_maccs167":
            raise STCAError("This model uses custom binary columns. Use screen_fingerprints, not SMILES.")
        # Resolve the rule even if every supplied row is invalid.
        self.rule_for(tier)
        X,audit = maccs_from_smiles(smiles,errors=errors)
        good = audit.input_valid.to_numpy(dtype=bool)
        base = audit.copy()
        base["selected"] = pd.Series(pd.NA,index=base.index,dtype="boolean")
        if good.any():
            result = self.screen_fingerprints(X[good],tier=tier)
            result.index = base.index[good]
            for c in result.columns:
                if c in ("row_position","input_valid"): continue
                if c=="selected": base.loc[good,c] = result[c].astype("boolean")
                else:
                    if c not in base: base[c] = pd.Series([None]*len(base),dtype="object")
                    base.loc[good,c] = result[c]
        base.attrs["rdkit_version"] = audit.attrs.get("rdkit_version")
        base.attrs["feature_policy"] = self._artifact["feature_spec"]
        return base

    def rules(self, *, tier: float=0.20) -> pd.DataFrame:
        entry=self._entry(tier); rows=[]
        for r in entry["rules"]:
            rule=Rule.from_dict(r["rule"])
            rows.append({"rule_name":rule.name,"selected":rule.name==entry.get("selected_rule"),
                         "family":rule.family,"literal_n":len(rule.keys),"signature":rule.signature,
                         "expression":rule.expression(self._artifact["feature_names"]),
                         **{f"source_{k}":v for k,v in r.get("source_metrics",{}).items()}})
        return pd.DataFrame(rows)

    def evaluate(self,X,y,*,tier:float=0.20,cutoff_mode="fixed_train",cutoff=None,
                 groups=None,allow_overlap=False) -> dict:
        a=self._matrix(X); y=target_vector(y,len(a))
        entry=self._entry(tier)
        if cutoff is not None:
            if cutoff_mode!="fixed_train": raise STCAError("An explicit cutoff cannot be combined with dataset_relative mode.")
            mode="explicit_cutoff"
        elif cutoff_mode=="fixed_train":
            cutoff=entry.get("train_cutoff"); mode=cutoff_mode
            if cutoff is None:
                raise STCAError("This archive has no verified numerical training cutoff. Supply an explicit cutoff or choose dataset_relative evaluation.")
        elif cutoff_mode=="dataset_relative":
            cutoff=target_cutoff(y,tier,self._artifact["direction"]); mode=cutoff_mode
        else: raise STCAError("cutoff_mode must be fixed_train or dataset_relative.")
        stored_groups=set(self._artifact.get("training_group_hashes",[]))
        group_audit="not_available"
        if stored_groups:
            if groups is None:
                raise STCAError("This model stores training groups. Supply evaluation groups for the overlap audit.")
            if len(groups)!=len(a) or pd.isna(np.asarray(groups)).any(): raise STCAError("Invalid evaluation groups.")
            overlap=stored_groups.intersection(hash_group(x) for x in groups)
            group_audit="overlap_allowed" if overlap else "disjoint"
            if overlap and not allow_overlap:
                raise STCAError(f"Training/evaluation overlap: {len(overlap)} groups. Use a disjoint test set.")
        selected=self.rule_for(tier).apply(a)
        result=screening_metrics(labels_at(y,cutoff,self._artifact["direction"]),selected,
                                 mcc_mode=self._artifact.get("mcc_mode","positive"),
                                 min_support=self._artifact.get("min_selected_support",1))
        result.update({"tier":float(tier),"cutoff":float(cutoff),"cutoff_mode":mode,
                       "target_name":self._artifact["target_name"],"target_unit":self._artifact["target_unit"],
                       "rule_name":self.rule_for(tier).name,"group_overlap_audit":group_audit,
                       "evaluation_role":"external_without_refitting",
                       "artifact_kind":self.provenance.get("kind")})
        return result

    def evaluate_smiles(self,smiles,y,**kwargs) -> dict:
        if self._artifact["feature_spec"]["kind"]!="rdkit_maccs167": raise STCAError("Not a SMILES model.")
        X,audit=maccs_from_smiles(smiles,errors="raise")
        if "groups" not in kwargs: kwargs["groups"]=audit.canonical_smiles.tolist()
        return self.evaluate(X,y,**kwargs)

    def save(self,path,*,overwrite=False): dump_json(path,self._artifact,overwrite=overwrite)

    @classmethod
    def load(cls,path):
        path=Path(path)
        if path.stat().st_size>50_000_000: raise STCAError("Model JSON exceeds 50 MB safety limit.")
        try:
            obj=json.loads(path.read_text(encoding="utf-8"),parse_constant=lambda x: (_ for _ in ()).throw(STCAError(f"Nonfinite JSON constant: {x}")))
        except json.JSONDecodeError as exc: raise STCAError("Malformed model JSON.") from exc
        return cls(obj)
