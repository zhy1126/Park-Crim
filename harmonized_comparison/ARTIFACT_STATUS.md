# Artifact Status

The eleven Shanghai park-opening events are researcher-verified project inputs. All eleven are retained in the harmonized analysis with `verification_status = project_verified` and `core_eligible = True`.

An earlier automated web-search pass suggested excluding several Shanghai events. The researcher confirmed that the event ledger had already been manually verified, so those machine-generated exclusions were rejected and are not part of this repository's analytical rule.

The harmonized scripts generate their ledgers, panels, model outputs, figures, reports, audits, and hash manifests locally. These generated directories are excluded from Git because they depend on non-versioned case records and geometry files. Follow `REPRODUCE.md` to rebuild them.
