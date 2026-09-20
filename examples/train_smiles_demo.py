# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

"""Run a SMILES-to-STCA workflow with explicitly SYNTHETIC target values.

No value in this demo is an experimental Tg, EC, or other material property.
Outputs are written to runs/synthetic_smiles relative to the working directory.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from stca import STCA, ScanConfig, ScreeningModel
from stca.chemistry import maccs_from_smiles
from stca.model import dump_json


def main() -> None:
    smiles = [
        "C", "CC", "CCC", "CCCC", "CCCCC", "CCCCCC", "CO", "CCO", "CCCO", "CCCCO",
        "COC", "CCOC", "CN", "CCN", "CCCN", "CCCCN", "CNC", "CCNC",
        "c1ccccc1", "Cc1ccccc1", "CCc1ccccc1", "Oc1ccccc1", "Nc1ccccc1", "COc1ccccc1",
        "Clc1ccccc1", "Fc1ccccc1", "c1ccncc1", "c1ccoc1", "c1ccsc1", "c1ccc2ccccc2c1",
    ]
    X, _ = maccs_from_smiles(smiles)
    synthetic = 20.0 * X[:, 162] - 9.0 * X[:, 151] + np.arange(len(smiles)) * 0.1
    test_rows = {2, 7, 12, 19, 24, 27}
    data = pd.DataFrame({
        "ID": [f"synthetic_{i:02d}" for i in range(len(smiles))],
        "SMILES": smiles,
        "synthetic_target": synthetic,
        "split": ["test" if i in test_rows else "train" for i in range(len(smiles))],
    })
    train = data.loc[data["split"] == "train"].reset_index(drop=True)
    test = data.loc[data["split"] == "test"].reset_index(drop=True)
    output = Path("runs/synthetic_smiles")
    output.mkdir(parents=True, exist_ok=True)
    data.to_csv(output / "data.csv", index=False)
    train.to_csv(output / "train.csv", index=False)
    test.to_csv(output / "test.csv", index=False)

    trainer = STCA(
        direction="high", tiers=(0.20,), scan=ScanConfig(step=0.25),
        target_name="SYNTHETIC_demo_target", target_unit="arbitrary",
    )
    model = trainer.fit_smiles(
        train["SMILES"], train["synthetic_target"],
        provenance={"dataset_kind": "synthetic_demonstration_not_research_data"},
    )
    model.save(output / "model.json", overwrite=True)
    trainer.export_diagnostics(output, overwrite=True)
    loaded = ScreeningModel.load(output / "model.json")
    result = loaded.screen(test["SMILES"], tier=0.20)
    result.insert(0, "ID", test["ID"].to_numpy())
    result.to_csv(output / "screen.csv", index=False)
    model.rules(tier=0.20).to_csv(output / "rules.csv", index=False)
    metrics = loaded.evaluate_smiles(test["SMILES"], test["synthetic_target"], tier=0.20)
    dump_json(output / "metrics.json", metrics, overwrite=True)
    print("SYNTHETIC SOFTWARE DEMO ONLY: targets are not material measurements.")
    print(result[["ID", "input_valid", "selected", "rule_name"]].to_string(index=False))
    print(pd.Series(metrics).to_string())
    print(f"Saved demonstration outputs to {output}")


if __name__ == "__main__":
    main()
