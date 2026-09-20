# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import pandas as pd
import scipy

from .chemistry import MACCS_NAMES, MACCS_SPEC, maccs_from_smiles, validate_maccs167
from .errors import STCAError
from .metrics import target_cutoff, labels_at, screening_metrics
from .model import ScreeningModel, SCHEMA_VERSION, PACKAGE_VERSION, tier_key, hash_group
from .rules import signed_prefix_rules
from .scan import ScanConfig, scan_frequencies, signed_rankings
from .validation import target_vector, feature_names, checked_frame_matrix, fraction, ensure_direction, positive_int


@dataclass
class STCA:
    """Source-only discovery and family selection; no test labels enter fit().

    Generic custom training supports one-sided feature hierarchies. ec_reverse
    requires both signs, as in the retrieved V12 electrical core. The frozen
    deployment representative is selected by source AS inside a source-F1 family,
    not by a retrospective harmonic score involving external datasets.
    """
    direction: str = "high"
    tiers: Sequence[float] = (0.30,0.20,0.10)
    scan: ScanConfig = field(default_factory=ScanConfig)
    max_rank: int = 10
    family_size: int = 8
    hierarchy: str = "direct"
    target_name: str = "property"
    target_unit: str = "user_specified"
    mcc_mode: str = "positive"
    min_selected_support: int = 1

    def __post_init__(self):
        ensure_direction(self.direction)
        self.tiers=tuple(fraction(t) for t in self.tiers)
        if not self.tiers or len(set(tier_key(t) for t in self.tiers))!=len(self.tiers):
            raise STCAError("Provide distinct, nonempty target tier fractions.")
        positive_int(self.max_rank,"max_rank")
        positive_int(self.family_size,"family_size",3)
        positive_int(self.min_selected_support,"min_selected_support")
        if self.max_rank>100: raise STCAError("max_rank must be <=100 to bound candidate enumeration.")
        if self.hierarchy not in ("direct","ec_reverse"): raise STCAError("Invalid hierarchy.")
        if self.mcc_mode not in ("positive","nonnegative"): raise STCAError("Invalid mcc_mode.")
        if not isinstance(self.scan,ScanConfig): raise STCAError("scan must be a ScanConfig.")
        if not self.target_name or not self.target_unit: raise STCAError("Specify target_name and target_unit.")
        self.model_=None
        self.scan_result_=None
        self.candidate_table_=None

    def fit(self,X,y,*,feature_names_=None,feature_spec=None,groups=None,provenance=None) -> ScreeningModel:
        # Clear cached results: a failed second fit must not expose a stale model.
        self.model_=None; self.scan_result_=None; self.candidate_table_=None
        a,frame_names=checked_frame_matrix(X)
        names=feature_names(feature_names_ if feature_names_ is not None else frame_names,a.shape[1])
        if frame_names and feature_names_ is not None and names!=frame_names:
            raise STCAError("Explicit feature names do not match DataFrame column order.")
        y=target_vector(y,len(a),4)
        spec=dict(feature_spec or {"kind":"binary","n_features":a.shape[1]})
        if spec.get("kind")=="rdkit_maccs167":
            a=validate_maccs167(a)
            if names!=MACCS_NAMES: raise STCAError("Use names K0..K166 for MACCS167 training.")
        group_hashes=[]
        if groups is not None:
            groups=np.asarray(groups)
            if groups.ndim!=1 or len(groups)!=len(a) or pd.isna(groups).any(): raise STCAError("Invalid source groups.")
            group_hashes=sorted(set(hash_group(v) for v in groups))
        scan_direction="low" if self.hierarchy=="ec_reverse" else self.direction
        result=scan_frequencies(a,y,direction=scan_direction,config=self.scan)
        pos,neg,filter_info=signed_rankings(result,self.scan)
        if self.hierarchy=="ec_reverse" and (not pos or not neg):
            raise STCAError("Electrical reverse hierarchy requires both positive and negative key rankings.")
        swapped=self.hierarchy=="ec_reverse" and self.direction=="high"
        if swapped: pos,neg=neg,pos
        candidates=signed_prefix_rules(pos,neg,self.max_rank)
        if not candidates: raise STCAError("No eligible signed features. Inspect the scan or nominal filter.")
        rule_by_name={r.name:r for r in candidates}
        tier_entries={}; all_rows=[]
        for tier in self.tiers:
            cutoff=target_cutoff(y,tier,self.direction)
            labels=labels_at(y,cutoff,self.direction)
            rows=[]
            for rule in candidates:
                m=screening_metrics(labels,rule.apply(a),mcc_mode=self.mcc_mode,min_support=self.min_selected_support)
                rows.append({"rule_name":rule.name,"family":rule.family,"literal_n":len(rule.keys),
                             "signature":rule.signature,**m})
            # Legacy signed-family source ranking: descending F1, ascending name.
            ranked=sorted(rows,key=lambda r:(-r["f1"],r["rule_name"]))
            chosen=[]
            for fam in ("positive_only","negative_only","positive_plus_negative"):
                anchor=next((r for r in ranked if r["family"]==fam),None)
                if anchor is not None: chosen.append(anchor)
            seen={r["rule_name"] for r in chosen}
            for row in ranked:
                if len(chosen)>=self.family_size: break
                if row["rule_name"] not in seen:
                    chosen.append(row); seen.add(row["rule_name"])
            valid=[(i,r) for i,r in enumerate(chosen) if r["valid_screen"]]
            best=max(valid,key=lambda pair:(pair[1]["average_score"],-pair[0]))[1] if valid else None
            records=[]
            for rank,row in enumerate(chosen,1):
                m={k:v for k,v in row.items() if k not in ("rule_name","family","literal_n","signature")}
                records.append({"rule":rule_by_name[row["rule_name"]].to_dict(),"source_metrics":m,
                                "source_family_rank":rank})
            tier_entries[tier_key(tier)]={"train_cutoff":cutoff,
                "selected_rule":best["rule_name"] if best else None,"rules":records,
                "selection_status":"source_selected" if best else "abstain_no_valid_source_rule"}
            for row in rows:
                all_rows.append({"tier":float(tier),"train_cutoff":cutoff,"in_retained_family":row["rule_name"] in seen,
                                 "selected":bool(best and row["rule_name"]==best["rule_name"]),**row})
        content_hash=hashlib.sha256(a.tobytes()+y.astype("<f8").tobytes()+json.dumps(names).encode()).hexdigest()
        metadata={"kind":"custom_source_trained","selection_protocol":"F1-ranked source family with sign-family anchors; maximum source AS within retained valid family",
                  "external_labels_used_for_fit":False,"scan_direction":scan_direction,
                  "ec_roles_swapped_once":swapped,"hierarchy":self.hierarchy,
                  "nominal_filter":filter_info,"scan_truncated":result.truncated,
                  "source_content_sha256":content_hash,"n_source_records":len(a),
                  "numpy_version":np.__version__,"pandas_version":pd.__version__,"scipy_version":scipy.__version__,
                  "caller_metadata":dict(provenance or {}),
                  "compatibility":"Portable implementation; full archived-dataset numerical parity is not certified."}
        artifact={"schema_version":SCHEMA_VERSION,"package_version":PACKAGE_VERSION,
                  "n_features":a.shape[1],"feature_names":list(names),"feature_spec":spec,
                  "direction":self.direction,"target_name":self.target_name,"target_unit":self.target_unit,
                  "mcc_mode":self.mcc_mode,"min_selected_support":self.min_selected_support,
                  "tiers":tier_entries,"training_group_hashes":group_hashes,"provenance":metadata,
                  "training_config":{"scan":self.scan.to_dict(),"max_rank":self.max_rank,"family_size":self.family_size},
                  "signed_rankings":{"positive_keys":pos,"negative_keys":neg},
                  "scan_table":result.table.to_dict("records")}
        model=ScreeningModel(artifact)
        self.model_=model; self.scan_result_=result; self.candidate_table_=pd.DataFrame(all_rows)
        return model

    def fit_smiles(self,smiles,y,*,provenance=None) -> ScreeningModel:
        self.model_=None; self.scan_result_=None; self.candidate_table_=None
        X,audit=maccs_from_smiles(smiles,errors="raise")
        info={**dict(provenance or {}),"rdkit_version":audit.attrs["rdkit_version"]}
        return self.fit(X,y,feature_names_=MACCS_NAMES,feature_spec=MACCS_SPEC,
                        groups=audit.canonical_smiles.to_numpy(),provenance=info)

    def export_diagnostics(self,directory,*,overwrite=False):
        from pathlib import Path
        if self.model_ is None: raise STCAError("Fit has not completed successfully.")
        root=Path(directory)
        paths=[root/"scan_correlations.csv",root/"scan_thresholds.csv",root/"candidate_rules.csv"]
        if not overwrite and any(p.exists() for p in paths): raise FileExistsError("Diagnostics already exist.")
        root.mkdir(parents=True,exist_ok=True)
        self.scan_result_.table.to_csv(paths[0],index=False)
        pd.DataFrame({"signed_threshold":self.scan_result_.thresholds,"subset_n":self.scan_result_.counts}).to_csv(paths[1],index=False)
        self.candidate_table_.to_csv(paths[2],index=False)
