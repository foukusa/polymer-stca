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
from .metrics import target_cutoff, labels_at, screening_metrics, strict_harmonic
from .model import ScreeningModel, SCHEMA_VERSION, PACKAGE_VERSION, tier_key, hash_group
from .rules import signed_prefix_rules
from .protocols import SelectionData, TemplateFamily, retain_source_family
from .scan import ScanConfig, scan_frequencies, signed_rankings
from .validation import target_vector, feature_names, checked_frame_matrix, fraction, ensure_direction, positive_int


@dataclass
class STCA:
    """STCA discovery with explicit family construction and representative selection.

    source_as (default) uses the source-only deployment protocol.
    core_harmonic explicitly uses a second selection dataset and the combined
    source+selection dataset. It is retrospective reporting, not held-out testing.
    Predeclared electrical families must be imported as complete prefix templates;
    they are never replaced with the source-F1 Top-8 exhaustive family.
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
    family_metric: str = "f1"
    template_family: TemplateFamily | None = None
    template_missing: str = "error"
    selection: str = "source_as"
    protocol_id: str = "custom_source_f1_as_v1"
    comparison_cutoff_mode: str = "dataset_relative"

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
        if self.family_metric not in ("f1", "average_score"):
            raise STCAError("family_metric must be f1 or average_score.")
        if self.selection not in ("source_as", "validation_as", "core_harmonic"):
            raise STCAError("selection must be source_as, validation_as or core_harmonic.")
        if self.comparison_cutoff_mode not in ("dataset_relative", "fixed_train"):
            raise STCAError("Invalid comparison cutoff mode.")
        if self.template_missing not in ("error", "truncate"):
            raise STCAError("template_missing must be error or truncate.")
        if self.template_family is not None:
            if not isinstance(self.template_family, TemplateFamily):
                raise STCAError("template_family must be a validated TemplateFamily.")
            expected_direction = "low" if self.template_family.profile == "ec-low" else "high"
            if self.direction != expected_direction:
                raise STCAError("Template profile direction disagrees with trainer direction.")
            if any(tier_key(t) not in self.template_family.document["tiers"] for t in self.tiers):
                raise STCAError("The complete template family must cover every requested tier.")
        if self.protocol_id == "archival_ec_primary_v12_v13" and self.template_family is None:
            raise STCAError("Paper EC primary reproduction requires the complete archived primary family.")
        self.model_=None
        self.scan_result_=None
        self.candidate_table_=None
        self.selection_table_=None
        self.template_audit_=None

    def fit(self,X,y,*,feature_names_=None,feature_spec=None,groups=None,provenance=None,
            selection_data: SelectionData | None = None, combined_data: SelectionData | None = None,
            acknowledge_selection_labels=False) -> ScreeningModel:
        # Clear cached results: a failed second fit must not expose a stale model.
        self.model_=None; self.scan_result_=None; self.candidate_table_=None
        self.selection_table_=None; self.template_audit_=None
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
        comparison = None
        explicit_combined = None
        if combined_data is not None and self.selection != "core_harmonic":
            raise STCAError("combined_data is only used by explicit core_harmonic selection.")
        comparison_hashes = []
        if self.selection == "source_as":
            if selection_data is not None:
                raise STCAError("source_as refuses selection_data; use it only after fit for independent evaluation.")
        else:
            if not acknowledge_selection_labels:
                raise STCAError("Explicit acknowledge_selection_labels=True is required: these labels affect representative selection.")
            if not isinstance(selection_data, SelectionData):
                raise STCAError("This selection protocol requires SelectionData(X, y, groups).")
            ca, _ = checked_frame_matrix(selection_data.X, names)
            cy = target_vector(selection_data.y, len(ca), 2)
            if spec.get("kind") == "rdkit_maccs167":
                ca = validate_maccs167(ca)
            if selection_data.groups is not None:
                cg = np.asarray(selection_data.groups)
                if cg.ndim != 1 or len(cg) != len(ca) or pd.isna(cg).any():
                    raise STCAError("Invalid selection groups.")
                comparison_hashes = sorted(set(hash_group(v) for v in cg))
                if set(comparison_hashes).intersection(group_hashes):
                    raise STCAError("Source/selection group overlap. A historical overlap must be resolved explicitly, not silently accepted.")
            comparison = (ca, cy)
        if combined_data is not None:
            if not isinstance(combined_data, SelectionData):
                raise STCAError("combined_data must be SelectionData.")
            ax, _ = checked_frame_matrix(combined_data.X, names)
            ay = target_vector(combined_data.y, len(ax), 4)
            if spec.get("kind") == "rdkit_maccs167": ax = validate_maccs167(ax)
            if len(ax) != len(a) + len(comparison[0]):
                raise STCAError("Explicit core-all must contain the source and comparison observations.")
            if groups is None or selection_data.groups is None or combined_data.groups is None:
                raise STCAError("Explicit core-all requires source/comparison/all IDs for membership auditing.")
            from collections import Counter
            ag = np.asarray(combined_data.groups)
            if ag.ndim != 1 or len(ag) != len(ax) or pd.isna(ag).any():
                raise STCAError("Invalid explicit core-all group IDs.")
            original = list(map(str, groups)) + list(map(str, selection_data.groups))
            if Counter(map(str, ag)) != Counter(original):
                raise STCAError("Explicit core-all membership differs from source+comparison.")
            # Original workflows can supply a separately represented all-data table.
            # It is used explicitly, never replaced by a convenient union silently.
            explicit_combined = (ax, ay)
        scan_direction="low" if self.hierarchy=="ec_reverse" else self.direction
        result=scan_frequencies(a,y,direction=scan_direction,config=self.scan)
        pos,neg,filter_info=signed_rankings(result,self.scan)
        if self.hierarchy=="ec_reverse" and (not pos or not neg):
            raise STCAError("Electrical reverse hierarchy requires both positive and negative key rankings.")
        swapped=self.hierarchy=="ec_reverse" and self.direction=="high"
        if swapped: pos,neg=neg,pos
        all_candidates=signed_prefix_rules(pos,neg,self.max_rank)
        if not all_candidates: raise STCAError("No eligible signed features. Inspect the scan or nominal filter.")
        tier_entries={}; all_rows=[]; selection_rows=[]; template_audit=[]
        for tier in self.tiers:
            if self.template_family is None:
                candidates = all_candidates
            else:
                candidates, ta = self.template_family.instantiate(tier, pos, neg, missing=self.template_missing)
                template_audit.extend(ta)
            rule_by_name = {r.name: r for r in candidates}
            cutoff=target_cutoff(y,tier,self.direction)
            labels=labels_at(y,cutoff,self.direction)
            rows=[]
            for rule in candidates:
                m=screening_metrics(labels,rule.apply(a),mcc_mode=self.mcc_mode,min_support=self.min_selected_support)
                rows.append({"rule_name":rule.name,"family":rule.family,"literal_n":len(rule.keys),
                             "signature":rule.signature,**m})
            if self.template_family is None:
                chosen = retain_source_family(rows, size=self.family_size, metric=self.family_metric)
            else:
                # The electrical primary protocol retains its predeclared family,
                # NOT the exhaustive-pool Top-8 F1 family.
                chosen = list(rows)
            seen = {r["rule_name"] for r in chosen}
            scored = []
            for rank, row in enumerate(chosen, 1):
                metrics = {"source": {k: v for k, v in row.items()
                           if k not in ("rule_name", "family", "literal_n", "signature")}}
                if comparison is not None:
                    ca, cy = comparison
                    scopes = [("comparison", ca, cy)]
                    if self.selection == "core_harmonic":
                        scopes.append(("combined", *(explicit_combined if explicit_combined is not None else (np.vstack([a, ca]), np.concatenate([y, cy])))))
                    rule = rule_by_name[row["rule_name"]]
                    for scope, sx, sy in scopes:
                        sc = (target_cutoff(sy, tier, self.direction)
                              if self.comparison_cutoff_mode == "dataset_relative" else cutoff)
                        metrics[scope] = screening_metrics(labels_at(sy, sc, self.direction), rule.apply(sx),
                                                mcc_mode=self.mcc_mode, min_support=self.min_selected_support)
                        metrics[scope]["cutoff"] = sc
                if self.selection == "core_harmonic":
                    score = strict_harmonic([v["average_score"] for v in metrics.values()],
                                            [v["valid_screen"] for v in metrics.values()])
                elif self.selection == "validation_as":
                    m = metrics["comparison"]
                    score = m["average_score"] if m["valid_screen"] else None
                else:
                    score = row["average_score"] if row["valid_screen"] else None
                item = {"row": row, "rank": rank, "selection_score": score, "metrics": metrics}
                scored.append(item)
                for scope, m in metrics.items():
                    selection_rows.append({"tier": float(tier), "rule_name": row["rule_name"],
                        "signature": row["signature"], "source_family_rank": rank,
                        "scope": scope, "selection_score": score, "selection_protocol": self.selection,
                        "cutoff_mode": "fixed_train" if scope == "source" else self.comparison_cutoff_mode,
                        "cutoff": cutoff if scope == "source" else m.get("cutoff"), **m})
            eligible = [z for z in scored if z["selection_score"] is not None]
            selected = max(eligible, key=lambda z: (z["selection_score"], -z["rank"])) if eligible else None
            best = selected["row"] if selected else None
            scored_by_name = {z["row"]["rule_name"]: z for z in scored}
            records=[]
            for rank,row in enumerate(chosen,1):
                m={k:v for k,v in row.items() if k not in ("rule_name","family","literal_n","signature")}
                records.append({"rule":rule_by_name[row["rule_name"]].to_dict(),"source_metrics":m,
                                "source_family_rank":rank,
                                "selection_score":scored_by_name[row["rule_name"]]["selection_score"],
                                "selection_scope_metrics":scored_by_name[row["rule_name"]]["metrics"]})
            tier_entries[tier_key(tier)]={"train_cutoff":cutoff,
                "selected_rule":best["rule_name"] if best else None,"rules":records,
                "selection_status":(self.selection + "_selected") if best else "abstain_no_valid_selection_rule",
                "selection_score":selected["selection_score"] if selected else None}
            for row in rows:
                all_rows.append({"tier":float(tier),"train_cutoff":cutoff,"in_retained_family":row["rule_name"] in seen,
                                 "selected":bool(best and row["rule_name"]==best["rule_name"]),
                                 "selection_score":scored_by_name.get(row["rule_name"],{}).get("selection_score"),**row})
        content_hash=hashlib.sha256(a.tobytes()+y.astype("<f8").tobytes()+json.dumps(names).encode()).hexdigest()
        metadata={"kind":"custom_source_trained" if self.selection == "source_as" else "explicit_selection_trained",
                  "selection_protocol":self.selection, "protocol_id":self.protocol_id,
                  "candidate_family_protocol":"predeclared_prefix_templates" if self.template_family else "source_ranked_with_sign_anchors",
                  "family_source_metric":self.family_metric if self.template_family is None else None,
                  "comparison_cutoff_mode":self.comparison_cutoff_mode if comparison is not None else None,
                  "external_labels_used_for_fit":comparison is not None,
                  "core_all_source":"explicit_membership_audited_table" if explicit_combined is not None else "source_comparison_union" if comparison is not None else None,
                  "comparison_is_untouched_test":False if comparison is not None else None,
                  "selection_group_audit":"available" if comparison_hashes else "not_available",
                  "template_provenance":self.template_family.document["provenance"] if self.template_family else None,"scan_direction":scan_direction,
                  "ec_roles_swapped_once":swapped,"hierarchy":self.hierarchy,
                  "nominal_filter":filter_info,"scan_truncated":result.truncated,
                  "source_content_sha256":content_hash,"n_source_records":len(a),
                  "numpy_version":np.__version__,"pandas_version":pd.__version__,"scipy_version":scipy.__version__,
                  "caller_metadata":dict(provenance or {}),
                  "compatibility":"Per-fit numerical parity is not assumed. Compare against a matching reference dataset and protocol."}
        artifact={"schema_version":SCHEMA_VERSION,"package_version":PACKAGE_VERSION,
                  "n_features":a.shape[1],"feature_names":list(names),"feature_spec":spec,
                  "direction":self.direction,"target_name":self.target_name,"target_unit":self.target_unit,
                  "mcc_mode":self.mcc_mode,"min_selected_support":self.min_selected_support,
                  "tiers":tier_entries,"training_group_hashes":group_hashes,"selection_group_hashes":comparison_hashes,"provenance":metadata,
                  "training_config":{"direction":self.direction,"tiers":list(self.tiers),
                      "hierarchy":self.hierarchy,"target_name":self.target_name,"target_unit":self.target_unit,
                      "mcc_mode":self.mcc_mode,"min_selected_support":self.min_selected_support,
                      "comparison_cutoff_mode":self.comparison_cutoff_mode,"scan":self.scan.to_dict(),"max_rank":self.max_rank,"family_size":self.family_size,
                      "family_metric":self.family_metric,"selection":self.selection,"protocol_id":self.protocol_id,
                      "template_missing":self.template_missing,
                      "template_family":self.template_family.document if self.template_family else None},
                  "signed_rankings":{"positive_keys":pos,"negative_keys":neg},
                  "scan_table":result.table.to_dict("records")}
        model=ScreeningModel(artifact)
        self.model_=model; self.scan_result_=result; self.candidate_table_=pd.DataFrame(all_rows)
        self.selection_table_=pd.DataFrame(selection_rows); self.template_audit_=pd.DataFrame(template_audit)
        return model

    def fit_smiles(self,smiles,y,*,provenance=None,selection_smiles=None,selection_y=None,
                   acknowledge_selection_labels=False) -> ScreeningModel:
        self.model_=None; self.scan_result_=None; self.candidate_table_=None
        self.selection_table_=None; self.template_audit_=None
        X,audit=maccs_from_smiles(smiles,errors="raise")
        info={**dict(provenance or {}),"rdkit_version":audit.attrs["rdkit_version"]}
        selection_data = None
        if selection_smiles is not None or selection_y is not None:
            if selection_smiles is None or selection_y is None:
                raise STCAError("selection_smiles and selection_y must be supplied together.")
            sx, sa = maccs_from_smiles(selection_smiles, errors="raise")
            selection_data = SelectionData(sx, selection_y, sa.canonical_smiles.to_numpy())
        return self.fit(X,y,feature_names_=MACCS_NAMES,feature_spec=MACCS_SPEC,
                        groups=audit.canonical_smiles.to_numpy(),provenance=info,
                        selection_data=selection_data, acknowledge_selection_labels=acknowledge_selection_labels)

    def export_diagnostics(self,directory,*,overwrite=False):
        from pathlib import Path
        if self.model_ is None: raise STCAError("Fit has not completed successfully.")
        root=Path(directory)
        paths=[root/"scan_correlations.csv",root/"scan_thresholds.csv",root/"candidate_rules.csv",
               root/"selection_scope_metrics.csv",root/"template_reference_audit.csv"]
        if not overwrite and any(p.exists() for p in paths): raise FileExistsError("Diagnostics already exist.")
        root.mkdir(parents=True,exist_ok=True)
        self.scan_result_.table.to_csv(paths[0],index=False)
        pd.DataFrame({"signed_threshold":self.scan_result_.thresholds,"subset_n":self.scan_result_.counts}).to_csv(paths[1],index=False)
        self.candidate_table_.to_csv(paths[2],index=False)
        self.selection_table_.to_csv(paths[3],index=False)
        self.template_audit_.to_csv(paths[4],index=False)


    @classmethod
    def for_profile(cls, profile, *, protocol="paper", template_family=None, **overrides):
        """Create a trainer, never load a trained rule.

        paper: the reproduced core-selection protocol of the bundled paper model.
        source_locked: same candidate-family definition, source-AS selection only.
        generic: exhaustive source-F1 family, for exploratory custom deployment.

        paper requires explicit selection_data and acknowledgement in fit().
        Different data or protocols need not produce identical rules.
        """
        from .protocols import bundled_primary_family
        if profile not in ("tg-high", "ec-low", "ec-high"):
            raise STCAError("Unknown training profile.")
        ec = profile.startswith("ec-")
        config = dict(direction="low" if profile == "ec-low" else "high",
            tiers=(.20,.15,.10,.05) if ec else (.30,.20,.10),
            scan=ScanConfig(step=.01 if ec else 1.0), max_rank=35 if ec else 10,
            mcc_mode="nonnegative" if ec else "positive", hierarchy="ec_reverse" if ec else "direct",
            target_name="EC" if ec else "Tg", target_unit="log10(S/cm)" if ec else "degC")
        if protocol in ("paper", "source_locked"):
            if template_family is not None:
                raise STCAError("Named paired protocols load their audited family automatically; use electrical_primary or template_source_locked for another family.")
            if ec:
                config["template_family"] = bundled_primary_family(profile)
            config.update(selection="core_harmonic" if protocol == "paper" else "source_as",
                protocol_id=("paper_ec_family_v15_core_v1" if ec else "paper_tg_core_v1")
                    if protocol == "paper" else ("ec_v15_family_source_as_v1" if ec else "tg_source_f1_as_v1"))
        elif protocol == "generic":
            if template_family is not None:
                raise STCAError("Generic exhaustive discovery does not accept a template family.")
            config.update(protocol_id="custom_source_f1_as_v1", selection="source_as")
        elif protocol == "thermal_core":
            if ec or template_family is not None:
                raise STCAError("thermal_core applies to Tg only.")
            config.update(protocol_id="archival_thermal_core_f1_harmonic_v1", selection="core_harmonic")
        elif protocol in ("electrical_primary", "template_source_locked"):
            if not ec or template_family is None:
                raise STCAError("A complete electrical TemplateFamily is required.")
            if not isinstance(template_family, TemplateFamily) or template_family.profile != profile:
                raise STCAError("Template profile mismatch.")
            config.update(template_family=template_family,
                selection="core_harmonic" if protocol == "electrical_primary" else "source_as",
                protocol_id="archival_ec_primary_v12_v13" if protocol == "electrical_primary" else "custom_template_source_as_v1")
        else:
            raise STCAError("Unknown training protocol.")
        protected = {"direction", "hierarchy", "template_family", "selection", "protocol_id"}
        if protected.intersection(overrides):
            raise STCAError("Protocol identity fields cannot be silently overridden in for_profile.")
        config.update(overrides)
        return cls(**config)
