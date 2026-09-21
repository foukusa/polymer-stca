# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

"""Executable SYNTHETIC demo. Values are simulated, not material measurements."""
from pathlib import Path

import numpy as np
import pandas as pd

from stca import STCA, ScanConfig, grouped_holdout


def main():
    rng = np.random.default_rng(20260920)
    frame = pd.DataFrame(rng.integers(0, 2, (600, 8)), columns=[f"feature_{i}" for i in range(8)])
    y = 9.0 * frame.feature_0 - 7.0 * frame.feature_1 + 2.0 * frame.feature_2 + rng.normal(0, 1.0, len(frame))
    groups = np.arange(len(frame))
    source, test = grouped_holdout(groups, test_fraction=0.20, seed=42)
    trainer = STCA(direction="high", tiers=(0.30, 0.20, 0.10), scan=ScanConfig(step=0.25),
                   target_name="SYNTHETIC_demo_target", target_unit="arbitrary")
    model = trainer.fit(frame.iloc[source], y.iloc[source], groups=groups[source],
                        provenance={"dataset_kind": "synthetic_demonstration_not_research_data"})
    output = Path("runs/synthetic_demo")
    model.save(output / "model.json", overwrite=True)
    trainer.export_diagnostics(output, overwrite=True)
    for tier in model.tiers:
        print(tier, model.evaluate(frame.iloc[test], y.iloc[test], tier=tier, groups=groups[test]))
    print(f"Synthetic demonstration model: {output / 'model.json'}")


if __name__ == "__main__":
    main()
