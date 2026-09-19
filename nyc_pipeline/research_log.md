# Shanghai-New York Comparative Autoresearch Log

This append-only log records hypotheses, experiments, retained artifacts, and failures.

## Iteration 0 - Initialization

- The workspace is not a valid Git repository; versioned outputs and manifest hashes are used instead of Git rollback.
- Existing Shanghai files are immutable inputs.
- NYC data and outputs will remain within this research directory.
- Baseline score: 0/100.

## Iteration 1 - Official event discovery and boundary audit

- Parsed 821 NYC Parks press releases dated 2010-2019 and retained 213 broad opening-keyword candidates for audit.
- Constructed a strict, source-linked ledger of 10 opening events. Nine events enter the main design; Hunter's Point South is sensitivity-only because the current property polygon includes an earlier phase.
- Matched all nine main events to valid NYC Parks property polygons in the official Parks Properties dataset.
- Excluded ordinary playground, court, field, comfort-station, and amenity renovations from the focal-event sample.
- Mechanical evaluator: 32/100. Retained because event and boundary checks passed.

## Iteration 2 - NYPD cases and stacked grid panel

- Queried official NYPD Complaint Data Historic records by park-specific bounding box and exact event window, then clipped points to 1,500 m from each park polygon.
- Retained 385,181 park-stack case rows across nine events; incident-date and coordinate completeness are both 100% after query validation.
- Built a 500 m local stacked panel with 426 stack-grid units and 2,982 grid-half-year observations. All cases were assigned and all outcome identities passed.
- The NYC complaint outcome is substantially denser than the Shanghai judgment outcome: about 79.5% of NYC grid-half observations contain total crime.
- Mechanical evaluator: 60/100 after panel construction. Retained.

## Iteration 3 - Main models and cross-city comparison

- Estimated 15 continuous-exposure PPML models, 15 binary-threshold PPML models, and five dynamic event studies with stack-unit and stack-period fixed effects.
- At lambda 500, NYC total crime beta = 0.035 (p = 0.538); theft beta = 0.083 (p = 0.517); non-theft beta = 0.013 (p = 0.738); day beta = 0.075 (p = 0.265); night beta = -0.006 (p = 0.905).
- Binary 500 m estimates are also statistically indistinguishable from zero for all five outcomes.
- Joint lead tests reject parallel pretrends for total crime, non-theft, and daytime crime. NYC estimates are therefore treated as a non-replication with identification warnings, not as proof of no causal effect.
- Mechanical evaluator: 96/100 after adding the Shanghai-NYC coefficient comparison. Retained.

## Iteration 4 - Design diagnostics

- Leave-one-park-out estimates remain close to zero for total crime regardless of the omitted park.
- A strict six-event sample limited to first/new public openings remains null across all outcomes.
- Adding stack-unit-specific linear trends moves every estimate closer to zero or slightly negative; none is statistically significant.
- Removing grid units potentially exposed to another already-open focal park leaves the conclusions unchanged.
- Omitting Estella Diggs Park raises the total-crime joint pretrend p-value to 0.069, but no single park fully explains the aggregate pretrend pattern.

## Iteration 5 - Final synthesis and artifact QA

- Integrated the official-source audit, panel construction, central PPML estimates, binary-threshold checks, dynamic event studies, joint pretrend tests, and design diagnostics into an English technical report.
- Produced an A4 Word report with Times New Roman typography, 1.5-line body spacing, black academic three-line tables, embedded maps and coefficient figures, and native Word equation objects.
- Verified the DOCX package contains five tables, three Office Math equations, and four embedded figures; an independent A4 preview contained 11 pages with no visible clipping or overlap.
- Mechanical evaluator: 100/100. Target achieved.
