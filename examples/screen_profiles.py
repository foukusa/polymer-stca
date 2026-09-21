# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

"""Screen syntax examples; outputs are rule matches, not verified properties."""
from pathlib import Path
import pandas as pd
from stca import load_pretrained


def main():
    candidates = pd.read_csv(Path(__file__).with_name("candidates.csv"))
    out = Path("runs/archive_demo")
    out.mkdir(parents=True, exist_ok=True)
    for profile, tier in [("tg-high", .2), ("ec-low", .1), ("ec-high", .05)]:
        model = load_pretrained(profile)
        result = model.screen(candidates.SMILES, tier=tier)
        result.insert(0, "ID", candidates.ID)
        result.to_csv(out / f"{profile}.csv", index=False)
        print(profile, result[["ID", "input_valid", "selected", "rule_name"]])


if __name__ == "__main__":
    main()
