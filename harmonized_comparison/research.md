# Shanghai-New York Harmonized Park-Opening Comparative Study

## Goal

Build a genuinely harmonized, reproducible comparative dataset and empirical
workflow for Shanghai and New York City. The same spatial support, event-time
definition, exposure functions, outcomes, and estimators must be applied in
both cities. Existing city outputs are read-only inputs; all new artifacts are
written below this directory.

## Research questions

1. Do recorded crime counts change more in grid cells that are more exposed to
   a focal park after it opens or reopens?
2. Is the exposure-response relationship different between Shanghai and New
   York City?
3. Are any differences robust to a binary 500 m treatment, event-study leads
   and lags, source-quality restrictions, removal of overlapping park events,
   and restriction to reconstruction/reopening projects in both cities?

## Frozen harmonization protocol

- Spatial unit: square 500 m grid cells, generated independently in each
  city's metric CRS but using the same cell size and algorithm.
- Focal support: cells intersecting a 1,500 m buffer around the focal park
  polygon.
- Distance: shortest distance from the grid-cell polygon to the focal park
  polygon boundary; cells touching or intersecting the park have distance 0.
- Main exposure: `exp(-distance / 500) * Post`.
- Binary robustness exposure: `1(distance <= 500) * Post`.
- Event time: exact opening-date-centered six-month intervals. Event time 0 is
  `[opening date, opening date + 6 months)`, event time -1 is the immediately
  preceding six months, and so on.
- Common balanced window: event times -3, -2, -1, and 0. The main estimand is
  the short-run effect during the first six months after opening. This window
  retains all project-verified Shanghai events, including late-2018 and
  early-2019 openings, without coding unobserved future periods as zero.
- Estimated outcomes: total recorded cases, theft/larceny, non-theft, day,
  and night counts. Day is 06:00-17:59; night is 18:00-05:59. Unknown-time
  counts are retained only as an accounting field used to verify that total
  equals day plus night plus unknown; they are not modeled as a separate
  outcome.
- Main estimator: PPML with stack-by-grid and stack-by-event-period fixed
  effects. Shanghai and NYC exposure coefficients enter separately in a pooled
  model, permitting a direct test of their difference.
- Inference: grid-clustered and two-way grid-plus-park clustered covariance
  estimates are both reported. Park-level leave-one-event-out estimates and
  pre-period placebo specifications supplement asymptotic inference because
  the number of focal park events is small.

## Event definitions

The broad treatment is public opening after a substantial capital project,
including first openings, replacement parks, complete rebuilds, and major
renovation reopenings. Ordinary amenity additions are excluded. A narrower
rebuild/reopening comparison is estimated because the current Shanghai event
ledger is dominated by reopened existing parks, whereas the NYC ledger also
contains first openings.

The eleven Shanghai opening dates are treated as project-verified inputs, as
confirmed by the researcher. The comparative workflow does not independently
re-adjudicate their substantive validity. It preserves date precision and
event class metadata so that month-date and reopening sensitivities can still
be reported transparently.

## Source-stage limitation

Shanghai outcomes are geocoded adjudicated judgment records, while NYC
outcomes are NYPD complaint records. The harmonized coefficients therefore
compare proportional changes in each city's recorded-case system, not equal
levels of underlying crime or equal criminal-justice stages. A pooled city
interaction is reported as a comparative replication diagnostic and is not
described as a structural difference in true crime incidence.

## Autoresearch settings

- Mode: unattended
- Pause cadence: never
- Maximum iterations: 8
- Target evaluator score: 90/100
- Guard condition: no pre-existing Shanghai or NYC input may be modified.
- Mechanical evaluator: `evaluate.py`

## Iteration search space

1. Correct event eligibility and source grading.
2. Exact-date versus calendar-half-year timing.
3. Broad versus reconstruction/reopening event samples.
4. Source-grade and stable-coverage restrictions.
5. Overlapping-event contamination restrictions.
6. Continuous versus binary exposure.
7. Dynamic leads/lags, placebo timing, and leave-one-event-out stability.
8. Alternative 250 m grid support if the common 500 m pipeline is stable.

## Publication-readiness success criteria

- Every included event has at least month-level opening timing, a matched
  polygon, an explicit verification status, and a traceable project record.
- Both cities use identical grid, support, timing, outcome, and exposure code.
- All panel identities and balance checks pass.
- Static, dynamic, city-difference, pretrend, placebo, and sensitivity outputs
  are generated without silent non-convergence.
- The report distinguishes engineering reproducibility from causal validity
  and states any remaining comparability limitations explicitly.
