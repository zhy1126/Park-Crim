# Research log

| Iteration | Change | Evaluation | Decision |
|---:|---|---|---|
| 0 | Initialized a fresh harmonized comparative build without modifying either city's source data. | Baseline | Continue |
| 1 | Froze a common 500 m grid, 1,500 m focal support, boundary-distance exposure, and exact-opening-date-centered six-month event clock. | Protocol checks passed | Continue |
| 2 | Built the balanced short panel for all 11 Shanghai and 9 NYC events and the long panel for 6 Shanghai and 9 NYC events with complete follow-up. | Panel identities and balance passed | Continue |
| 3 | Estimated city-specific and pooled continuous/binary PPML models, dynamic event studies, lead tests, placebos, overlap restrictions, leave-one-event-out estimates, and park jackknife diagnostics. | All requested models generated and converged | Continue |
| 4 | Compared all-event short estimates with same-event short and long estimates, showing that long-horizon attenuation is not explained solely by Shanghai event composition. | Horizon decomposition passed | Continue |
| 5 | Corrected the event-governance rule after researcher confirmation: all 11 Shanghai events are retained as `project_verified`; the abandoned machine-search exclusion file is explicitly obsolete. | Event ledger audit passed | Continue |
| 6 | Generated four publication-style figures and an English technical report; completed A4 section, heading, image, table-geometry, and accessibility audits. | Structural QA passed; pixel rendering unavailable because LibreOffice is absent | Continue with disclosed limitation |
| 7 | Regenerated the mechanical evaluation and SHA-256 artifact manifest. | 100/100, target met | Freeze comparative build |

The final interpretation is intentionally measurement-aware. The workflow is a reproducible comparison of recorded-case gradients in two different administrative systems, not a claim that the underlying causal effect on true crime is structurally different across cities.
