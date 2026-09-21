# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.
"""Explicit candidate-family and representative-selection protocols.

An imported paper family supplies PREFIX COUNTS, never a replacement prediction.
Frozen signatures are retained only as audit references. Metrics from the imported
CSV are not used for training or copied into new evaluations.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import STCAError
from .legacy import rule_from_signature, _sequence
from .model import dump_json, tier_key
from .rules import Rule


@dataclass
class SelectionData:
    """Data explicitly used to select a representative, NOT an untouched test set."""
    X: Any
    y: Any
    groups: Any = None
    name: str = "selection_comparison"


class TemplateFamily:
    """An ordered, per-tier family of (positive-prefix, negative-prefix) counts."""
    def __init__(self, document: dict):
        try:
            doc = json.loads(json.dumps(document, allow_nan=False))
        except (ValueError, TypeError) as exc:
            raise STCAError("Template family must contain finite JSON values.") from exc
        if doc.get("schema") != "stca-prefix-family-v1":
            raise STCAError("Unsupported prefix-family schema.")
        if doc.get("profile") not in ("tg-high", "ec-low", "ec-high"):
            raise STCAError("Template family requires an explicit Tg/EC profile.")
        if not isinstance(doc.get("provenance"), dict) or not doc["provenance"]:
            raise STCAError("A template family requires provenance.")
        if not isinstance(doc.get("tiers"), dict) or not doc["tiers"]:
            raise STCAError("Empty template family.")
        for key, records in doc["tiers"].items():
            if tier_key(float(key)) != key or not isinstance(records, list) or not records:
                raise STCAError("Invalid template tier.")
            names = set()
            for rec in records:
                if not isinstance(rec, dict) or not isinstance(rec.get("name"), str) or not rec["name"]:
                    raise STCAError("Every template needs a nonempty name.")
                if rec["name"] in names:
                    raise STCAError("Template names must be unique within a tier.")
                names.add(rec["name"])
                for field in ("positive_n", "negative_n"):
                    v = rec.get(field)
                    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 166:
                        raise STCAError("Template prefix counts must be integers in 0..166.")
                if rec["positive_n"] + rec["negative_n"] == 0:
                    raise STCAError("An empty, match-everything template is forbidden.")
                sig = rec.get("reference_signature")
                if sig is not None:
                    rule = rule_from_signature(sig)
                    if any(k == 0 or k > 166 for k in rule.keys):
                        raise STCAError("Paper MACCS references must use keys 1..166.")
                    if sum(rule.values) != rec["positive_n"] or len(rule.values)-sum(rule.values) != rec["negative_n"]:
                        raise STCAError("Prefix counts disagree with the reference literals.")
        self._document = doc

    @property
    def document(self):
        return json.loads(json.dumps(self._document))

    @property
    def profile(self):
        return self._document["profile"]

    def instantiate(self, tier, positive, negative, *, missing="error"):
        """Generate new rules from newly learned rankings, not stored literals.

        missing='truncate' reproduces the .head(n) behavior of the retrieved V13
        template constructor. Such truncation is always logged. Default 'error'
        prevents a scientific protocol change from being silently accepted.
        """
        if missing not in ("error", "truncate"):
            raise STCAError("missing must be error or truncate.")
        key = tier_key(tier)
        if key not in self._document["tiers"]:
            raise STCAError(f"Template family has no tier {tier}.")
        pos, neg = list(positive), list(negative)
        if len(set(pos+neg)) != len(pos+neg):
            raise STCAError("Template rankings overlap or contain duplicate keys.")
        rules, audit = [], []
        for rec in self._document["tiers"][key]:
            pn, nn = rec["positive_n"], rec["negative_n"]
            truncated = pn > len(pos) or nn > len(neg)
            if truncated and missing == "error":
                raise STCAError(f"Insufficient ranked keys for template {rec['name']} ({pn}, {nn}).")
            pk, nk = pos[:pn], neg[:nn]
            if not pk and not nk:
                raise STCAError("Template collapsed to an empty rule; no fallback is allowed.")
            rule = Rule(tuple(pk+nk), (1,)*len(pk)+(0,)*len(nk), rec["name"], "primary_template")
            rules.append(rule)
            expected = rec.get("reference_signature")
            audit.append({"tier": float(tier), "rule_name": rule.name,
                          "requested_positive_n": pn, "requested_negative_n": nn,
                          "template_truncated": truncated,
                          "generated_signature": rule.signature,
                          "reference_signature": expected,
                          "reference_match": rule.signature == expected if expected else None})
        return rules, audit

    def save(self, path, *, overwrite=False):
        dump_json(path, self.document, overwrite=overwrite)

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > 10_000_000:
            raise STCAError("Template JSON exceeds 10 MB.")
        return cls(json.loads(path.read_text(encoding="utf-8-sig")))

    @classmethod
    def from_primary_csv(cls, path, *, profile):
        """Read a complete historical primary-family CSV, without selecting rows by score.

        Required: method, regime, percentile and an explicit signed rule in
        pattern_signature, or keys/values. All STCA rows for the selected regime
        are retained in file order. Range labels alone are insufficient.
        """
        path = Path(path)
        if profile not in ("ec-low", "ec-high"):
            raise STCAError("The electrical primary-table importer requires ec-low or ec-high.")
        frame = pd.read_csv(path)
        if not {"method", "regime", "percentile"}.issubset(frame):
            raise STCAError("Not a primary-family table: method/regime/percentile are required.")
        regime = "insulation" if profile == "ec-low" else "conduction"
        rows = frame[(frame.method.astype(str) == "STCA") & (frame.regime.astype(str) == regime)]
        if rows.empty:
            raise STCAError(f"No STCA {regime} family rows found.")
        tiers = {}
        for source_index, row in rows.iterrows():
            p = float(row.percentile)
            if not math.isfinite(p) or not 0 < p < 100:
                raise STCAError("Invalid historical percentile.")
            key = tier_key((100.0-p)/100.0)
            name = str(row.get("pattern_name", f"primary_row_{source_index}"))
            sig = row.get("pattern_signature")
            if isinstance(sig, str) and sig.startswith("STCA|AND|"):
                rule = rule_from_signature(sig, name=name)
            elif "keys" in row and "values" in row:
                rule = Rule(_sequence(row["keys"]), _sequence(row["values"]), name)
            else:
                raise STCAError("Missing complete signed literals; ambiguous paper labels are not expanded by matching scores.")
            if "keys" in row and "values" in row and isinstance(row["keys"], str):
                other = Rule(_sequence(row["keys"]), _sequence(row["values"]), name)
                if other.signature != rule.signature:
                    raise STCAError("CSV signature disagrees with keys/values.")
            # Physical required-present/absent counts avoid historical source-role
            # label ambiguity in conduction names. Literal membership is audit-only.
            pn = sum(rule.values); nn = len(rule.values)-pn
            records = tiers.setdefault(key, [])
            unique_name = name
            if any(r["name"] == name for r in records):
                unique_name = f"{name}__source_row_{source_index}"
            records.append({"name": unique_name, "positive_n": pn, "negative_n": nn,
                            "reference_signature": rule.signature,
                            "source_row": int(source_index),
                            "paper_pattern_label": str(row.get("paper_pattern_label", name))})
        return cls({"schema": "stca-prefix-family-v1", "profile": profile,
                    "tiers": tiers, "provenance": {
                        "kind": "complete_primary_table_import",
                        "source_file": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "source_rule_count": len(rows),
                        "rule_order": "input_csv_order",
                        "counts": "required_present_and_absent_literals",
                        "external_scores_used_by_importer": False,
                        "table_origin_requires_author_verification": True}})


def retain_source_family(rows, *, size=8, metric="f1"):
    """Retrieved thermal/core family: stable source score/name, three anchors."""
    if metric not in ("f1", "average_score"):
        raise STCAError("family_metric must be f1 or average_score.")
    ranked = sorted(rows, key=lambda r: (-r[metric], r["rule_name"]))
    chosen = []
    for family in ("positive_only", "negative_only", "positive_plus_negative"):
        anchor = next((r for r in ranked if r["family"] == family), None)
        if anchor is not None:
            chosen.append(anchor)
    seen = {r["signature"] for r in chosen}
    for row in ranked:
        if len(chosen) >= size:
            break
        if row["signature"] not in seen:
            chosen.append(row); seen.add(row["signature"])
    return chosen


def bundled_primary_family(profile):
    """Return complete, ordered V15 prefix lengths; no historical winning bits."""
    from importlib.resources import files
    if profile not in ("ec-low", "ec-high"):
        raise STCAError("Bundled primary families apply to EC profiles only.")
    path = files("stca").joinpath("assets", profile.replace("-", "_") + "_primary_family_v15.json")
    return TemplateFamily(json.loads(path.read_text(encoding="utf-8")))
