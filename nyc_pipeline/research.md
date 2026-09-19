# Shanghai-New York Park-Opening Comparative Autoresearch

## Goal

Construct and execute a reproducible New York City replication of the Shanghai park-opening design, then compare the two city-specific estimates without treating police complaints and adjudicated judgment records as identical outcomes.

## Success Metric

Target score: 90/100 from `python evaluate.py`.

The evaluator rewards an official-source opening-event ledger, verified NYC Parks boundary geometries, spatially and temporally valid NYPD complaint records, a complete focal stacked panel, converged continuous-exposure PPML and binary park-opening models, dynamic diagnostics, harmonized city comparison outputs, and a final technical report that states the recording-pipeline limitation correctly.

## Constraints

- Evaluator: `python evaluate.py`
- Keep policy: `score_improvement`
- `pause_every: never`
- `max_iterations: 8`
- `noise_runs: 1`
- `min_delta: 1`
- Runtime tier: Tier 1 (Python/R plus web access).
- Guard: never delete, overwrite, move, or modify any existing Shanghai source data, manuscript, or result.
- Guard: write all NYC downloads, intermediate files, models, and reports only under this directory.
- Guard: opening events must have month- or day-level public-opening evidence; acquisition dates and generic capital-project completion dates are not opening dates.
- Guard: ordinary partial renovations, toilets, lighting, field resurfacing, and similar component projects are excluded from the main opening-event sample.
- Guard: preserve non-converged and separation-like models as diagnostics rather than ordinary null findings.
- Guard: cross-city claims are limited to Shanghai and New York City and do not generalize to China versus the United States.

## Current Approach

The Shanghai study uses focal park-opening stacks, 500 m square grids, distance from the park boundary, exponential exposure decay, half-year event time, PPML with stack-unit and stack-period fixed effects, binary park-opening estimates, and event-study diagnostics. The New York replication will use the same analytical architecture with official NYC park boundaries and NYPD complaint records.

## Search Space

1. Build a candidate event ledger from NYC Parks press releases and the Capital Project Tracker.
2. Restrict the main sample to first public openings with precise dates; classify complete reopenings separately.
3. Download exact NYC Parks property polygons and match each event to a unique geometry.
4. Query NYPD Complaint Data Historic for the common 2010-2019 window and retain incident date, time, offense, and coordinates.
5. Construct 500 m grids within a 1,500 m focal support and calculate boundary distance and lambda 250/500/1000 exposure.
6. Build event windows of -3 to +3 half-years, with robustness windows where coverage permits.
7. Estimate continuous-exposure PPML, binary threshold models, dynamic event studies, sparsity diagnostics, and leave-one-park-out checks.
8. Harmonize total, theft, non-theft, day, and night outcomes and compare city-specific effect scales and timing.

## Context and Official Sources

- NYPD Complaint Data Historic: `https://data.cityofnewyork.us/resource/qgea-i56i.json`
- NYC Parks Properties: `https://data.cityofnewyork.us/resource/enfh-gkve.geojson` or the current official Parks Properties endpoint.
- NYC Parks Press Releases: `https://www.nycgovparks.org/news/press-releases/`
- NYC Parks Capital Project Tracker: `https://www.nycgovparks.org/planning-and-building/capital-project-tracker/completed`
- Existing Shanghai comparison outputs: set `SHANGHAI_RESULTS_CSV` to the local aggregate-results CSV.

## History

| Iteration | Hypothesis | Experiment | Score | Status | Notes |
|---:|---|---|---:|---|---|
| 0 | Baseline | Initialize immutable, versioned comparative research workspace | 0 | baseline | No NYC research artifacts yet |
