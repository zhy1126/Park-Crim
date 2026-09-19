# Data Sources

No source dataset is stored in this repository. The scripts download public New York City inputs to ignored local directories; the Shanghai files must be supplied locally by an authorized researcher.

## New York City

### NYC Parks press releases

- Purpose: discover and verify park-opening dates and opening scope.
- Source: NYC Department of Parks & Recreation.
- Archive: https://www.nycgovparks.org/news/press-releases/
- Access method: `nyc_pipeline/fetch_official_inputs.py` reads monthly archive pages for 2010-2019 and archives candidate release text locally.

The final event ledger uses official release-linked dates and excludes ordinary playground, court, field, comfort-station, and isolated amenity renovations. The curated decisions are recorded transparently in `nyc_pipeline/build_opening_ledger.py`.

### NYC Parks Properties

- Purpose: official park boundary polygons and property identifiers.
- Dataset page: https://data.cityofnewyork.us/Recreation/NYC-Parks-Properties/enfh-gkve
- GeoJSON API: https://data.cityofnewyork.us/resource/enfh-gkve.geojson
- Publisher: NYC Department of Parks & Recreation.

### NYPD Complaint Data Historic

- Purpose: incident-dated felony and misdemeanor complaints, offense descriptions, occurrence time, and coordinates.
- Dataset page: https://data.cityofnewyork.us/Public-Safety/NYPD-Complaint-Data-Historic/qgea-i56i
- Socrata API endpoint: https://data.cityofnewyork.us/resource/qgea-i56i.json
- Publisher: New York City Police Department.

The workflow uses `cmplnt_fr_dt` and `cmplnt_fr_tm` as the reported occurrence date and time. Records are queried within each focal event window and bounding box, then clipped locally to 1,500 m from the official park boundary. Only felony and misdemeanor complaints enter the reported outcomes.

## Shanghai

### CSNCSGD-derived Shanghai judgment records

- Purpose: geocoded adjudicated criminal judgment records with parsed incident date, offense label, time information, and coordinates.
- Reference: Zhang, Y., Kwan, M.-P., and Fang, L. (2025), "An LLM driven dataset on the spatiotemporal distributions of street and neighborhood crime in China," *Scientific Data*, 12, 467.
- Article: https://doi.org/10.1038/s41597-025-04757-8

The project uses an authorized local Shanghai extract. It is not redistributed here. Set `SHANGHAI_CASES_CSV` to the local CSV before running the harmonized comparison.

### Shanghai park boundaries and opening events

- Purpose: focal park polygons and researcher-verified opening dates.
- Boundary source: OpenStreetMap-derived park polygons that were matched and manually reviewed in the dissertation workflow.
- OpenStreetMap data: https://www.openstreetmap.org/
- OpenStreetMap copyright and licence: https://www.openstreetmap.org/copyright

The eleven Shanghai opening events are treated as researcher-verified project inputs. Set `SHANGHAI_PARK_BOUNDARIES` to the local GeoJSON before running the harmonized comparison. No Shanghai geometry or event-level source file is included in this repository.

## Important comparability note

NYPD complaints and Shanghai adjudicated judgments represent different stages of the criminal justice process. Reusing a common spatial-temporal estimator does not make the two outcomes institutionally identical. Cross-city contrasts should therefore be interpreted as transportability and measurement diagnostics rather than as a direct comparison of true-crime causal effects.
