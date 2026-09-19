from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
SHANGHAI = Path(
    os.environ.get(
        "SHANGHAI_RESULTS_CSV",
        ROOT / "external_data" / "overall_main_ppml_fixest.csv",
    )
).expanduser()


OUTCOME_MAP = {
    "total_crime_count": "total_crime",
    "theft_count": "theft",
    "non_theft_count": "non_theft",
    "day_count": "day_crime",
    "night_count": "night_crime",
}


def main() -> None:
    if not SHANGHAI.is_file():
        raise FileNotFoundError(
            "Shanghai aggregate results were not found. Set SHANGHAI_RESULTS_CSV "
            "to the local overall_main_ppml_fixest.csv file."
        )
    shanghai = pd.read_csv(SHANGHAI)
    shanghai = shanghai.loc[shanghai["outcome"].isin(OUTCOME_MAP)].copy()
    shanghai["outcome"] = shanghai["outcome"].map(OUTCOME_MAP)
    shanghai_out = pd.DataFrame(
        {
            "city": "Shanghai",
            "outcome": shanghai["outcome"],
            "estimand": "continuous distance-decayed post-opening association",
            "estimate": shanghai["estimate"],
            "std_error": shanghai["std_error"],
            "p_value": shanghai["p_value"],
            "scale": "PPML log coefficient, lambda=500",
            "incidence_rate_ratio": shanghai["incidence_rate_ratio"],
            "n_obs": shanghai["n_obs"],
            "n_parks": 11,
            "data_source": "geocoded adjudicated judgment records",
            "support_definition": "existing Shanghai focal-grid analysis support",
        }
    )

    nyc = pd.read_csv(RESULTS / "nyc_main_ppml.csv")
    nyc = nyc.loc[nyc["scale_value"].eq(500)].copy()
    nyc_out = pd.DataFrame(
        {
            "city": "New York City",
            "outcome": nyc["outcome"],
            "estimand": "continuous distance-decayed post-opening association",
            "estimate": nyc["estimate"],
            "std_error": nyc["std_error"],
            "p_value": nyc["p_value"],
            "scale": "PPML log coefficient, lambda=500",
            "incidence_rate_ratio": nyc["incidence_rate_ratio"],
            "n_obs": nyc["n_obs"],
            "n_parks": nyc["n_parks"],
            "data_source": "NYPD complaint records (felony and misdemeanor)",
            "support_definition": "park-specific grids intersecting a 1,500 m support",
        }
    )
    comparison = pd.concat([shanghai_out, nyc_out], ignore_index=True)
    comparison.to_csv(
        RESULTS / "shanghai_nyc_comparison.csv", index=False, encoding="utf-8-sig"
    )

    wide = comparison.pivot(index="outcome", columns="city", values="estimate")
    wide["nyc_minus_shanghai"] = wide["New York City"] - wide["Shanghai"]
    wide["nyc_to_shanghai_ratio"] = wide["New York City"] / wide["Shanghai"]
    wide.reset_index().to_csv(
        RESULTS / "shanghai_nyc_coefficient_contrast.csv",
        index=False,
        encoding="utf-8-sig",
    )
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
