# Reproducing the Harmonized Shanghai-New York Build

The harmonized workflow uses a common 500 m grid, a 1,500 m focal support, boundary-distance exposure, and six-month periods centred on each park's exact opening date. No input dataset is stored in Git.

## 1. Prepare the New York inputs

Run the public New York pipeline first:

```powershell
cd ..\nyc_pipeline
python fetch_official_inputs.py
python build_opening_ledger.py
python fetch_nypd_cases.py
python build_nyc_stacked_panel.py
```

This creates the ignored park geometry, complaint cache, and panel files needed by the comparison.

## 2. Configure the Shanghai inputs

Supply the authorized local files through environment variables:

```powershell
$env:SHANGHAI_CASES_CSV = "D:\path\to\ChinaCrime_shanghai.csv"
$env:SHANGHAI_PARK_BOUNDARIES = "D:\path\to\osm_park_boundaries_shanghai.geojson"
```

Optional overrides are available when the New York pipeline is not the sibling directory:

```powershell
$env:NYC_PIPELINE_DIR = "D:\path\to\Park-Crim\nyc_pipeline"
$env:NYC_RAW_SHORT_DIR = "D:\path\to\Park-Crim\nyc_pipeline\raw\nypd_by_park"
$env:PARK_CRIME_R_LIB = "D:\path\to\R-library"
```

The eleven Shanghai park-opening dates are researcher-verified project inputs. The deprecated automated-search audit described in `ARTIFACT_STATUS.md` must not be used to exclude or reinterpret these events.

## 3. Build and estimate the short window

The short design covers event times -3, -2, -1, and 0, using exact-date-centred six-month periods.

```powershell
cd ..\harmonized_comparison
$env:HARMONIZED_WINDOW = "short"
python build_harmonized_events.py
python build_harmonized_panel.py
$env:HARMONIZED_MODEL_WINDOW = "short"
Rscript run_harmonized_models.R
```

## 4. Build and estimate the long window

The long design covers event times -3 through +3. Only events with complete follow-up enter this version.

```powershell
python fetch_nyc_exact_long_window.py
$env:HARMONIZED_WINDOW = "long"
python build_harmonized_panel.py
$env:HARMONIZED_MODEL_WINDOW = "long"
Rscript run_harmonized_models.R
```

## 5. Figures, report, and evaluation

```powershell
python make_comparative_figures.py
python make_comparative_technical_report.py
python evaluate.py
```

Locally generated `data/`, `raw/`, `artifacts/`, `results/`, `figures/`, and `reports/` directories are excluded from Git. Their expected contents are:

- `data/harmonized_event_ledger.csv`
- `data/harmonized_stacked_grid_panel_500m.csv`
- `data/harmonized_stacked_grid_panel_500m_long_m3_p3.csv`
- `results/`: model estimates and diagnostics
- `figures/`: comparative figures
- `reports/`: generated technical report
- `artifacts/`: audit JSON files and SHA-256 manifest

## Verification gates

After reproduction, confirm that:

- the event ledger contains 20 events: 11 Shanghai and 9 New York City;
- the short panel is balanced across all 20 events;
- the long panel contains the events with complete post-opening support;
- all requested model rows have a successful convergence status;
- outcome identities hold within every stack-grid-period row;
- no case-level file has been added to Git.
