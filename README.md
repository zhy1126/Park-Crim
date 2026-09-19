# Park Openings and Recorded Crime

This repository contains the reproducible code and documentation for the New York City park-opening study and the Shanghai-New York comparative workflow. It intentionally excludes all raw, case-level, geocoded, and analysis-ready datasets.

## Repository contents

- `nyc_pipeline/`: end-to-end New York City workflow using official NYC Parks and NYPD Open Data sources.
- `nyc_pipeline/results/`: aggregate model estimates and diagnostics from the completed run. These files contain no case-level records.
- `nyc_pipeline/figures/`: publication-style figures generated from the aggregate results.
- `nyc_pipeline/final_report.md`: technical report describing the design, results, and limitations.
- `harmonized_comparison/`: scripts for rebuilding the common Shanghai-New York design with identical 500 m grids, 1,500 m support, and event-centred six-month periods.
- `docs/`: the completed comparative Word report.
- `DATA_SOURCES.md`: official data descriptions, links, field definitions, and access notes.

## Main completed finding

The central continuous-exposure PPML estimate for total crime was `0.357` in Shanghai and `0.035` in New York City. The New York estimate was statistically indistinguishable from zero, while its event-study diagnostics rejected the no-pretrend null for total crime, non-theft crime, and daytime crime. The comparison is therefore treated as a measurement-aware non-replication, not as a definitive causal difference between cities.

## Quick start: New York City

Python 3.11 or later and R 4.3 or later are recommended.

```powershell
git clone https://github.com/zhy1126/Park-Crim.git
cd Park-Crim
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Rscript install_r_packages.R
cd nyc_pipeline
python fetch_official_inputs.py
python build_opening_ledger.py
python fetch_nypd_cases.py
python build_nyc_stacked_panel.py
Rscript run_nyc_models.R
Rscript run_nyc_diagnostics.R
python make_figures.py
```

The NYPD download is large and may take time. Every downloaded or constructed dataset is written to an ignored `raw/`, `data/`, or `artifacts/` directory.

## Shanghai-New York comparison

The completed exploratory comparison reuses the established Shanghai aggregate estimates. To rebuild `nyc_pipeline/results/shanghai_nyc_comparison.csv`, point `SHANGHAI_RESULTS_CSV` to the local Shanghai aggregate-results file:

```powershell
$env:SHANGHAI_RESULTS_CSV = "D:\path\to\overall_main_ppml_fixest.csv"
cd nyc_pipeline
python build_comparison.py
```

The fully harmonized workflow requires the non-public Shanghai judgment-record file and the Shanghai park-boundary file. Their expected environment variables and execution order are documented in [`harmonized_comparison/REPRODUCE.md`](harmonized_comparison/REPRODUCE.md).

## Data policy

No crime microdata, coordinates, locally cached API responses, park geometry files, or constructed analysis panels are committed. Only code, documentation, figures, and aggregate model outputs are versioned. See [`DATA_SOURCES.md`](DATA_SOURCES.md) for official download links.

