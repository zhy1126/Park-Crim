from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent


def csv_check(path: Path, required: set[str], min_rows: int = 1):
    if not path.exists():
        return False, None
    try:
        frame = pd.read_csv(path)
    except Exception:
        return False, None
    return len(frame) >= min_rows and required.issubset(frame.columns), frame


def json_load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    score = 0
    checks: dict[str, object] = {}

    ok, ledger = csv_check(
        ROOT / "data/nyc_park_opening_ledger.csv",
        {"park_id", "park_name", "opening_date", "opening_precision", "event_class", "source_url", "eligible_main"},
        5,
    )
    checks["opening_ledger"] = bool(ok)
    checks["eligible_events"] = int(ledger["eligible_main"].fillna(False).astype(bool).sum()) if ok else 0
    if ok:
        score += 12
    if checks["eligible_events"] >= 8:
        score += 8

    boundary = json_load(ROOT / "artifacts/boundary_audit.json")
    checks["boundary_match"] = bool(boundary.get("eligible_events") and boundary.get("matched_events") == boundary.get("eligible_events"))
    if checks["boundary_match"]:
        score += 12

    crime = json_load(ROOT / "artifacts/crime_audit.json")
    checks["crime_data"] = bool(crime.get("n_records", 0) > 0 and crime.get("incident_date_share", 0) > 0.95 and crime.get("coordinate_share", 0) > 0.95)
    if checks["crime_data"]:
        score += 12

    ok, panel = csv_check(
        ROOT / "data/nyc_stacked_grid_panel.csv",
        {"park_id", "grid_id", "half_year", "event_time", "post", "distance_m", "exposure_500", "total_crime", "theft", "non_theft", "day_crime", "night_crime"},
        100,
    )
    checks["stacked_panel"] = bool(ok and panel is not None and panel["park_id"].nunique() >= 5)
    if checks["stacked_panel"]:
        score += 16

    ok, main = csv_check(
        ROOT / "results/nyc_main_ppml.csv",
        {"outcome", "estimate", "std_error", "p_value", "converged", "n_obs"},
        5,
    )
    checks["main_ppml"] = bool(ok and main is not None and main["converged"].astype(bool).all())
    if checks["main_ppml"]:
        score += 12

    ok, binary = csv_check(
        ROOT / "results/nyc_binary_models.csv",
        {"outcome", "threshold_m", "estimate", "std_error", "p_value", "converged"},
        5,
    )
    checks["binary_models"] = bool(ok)
    if checks["binary_models"]:
        score += 8

    ok, dynamic = csv_check(
        ROOT / "results/nyc_event_study.csv",
        {"outcome", "event_time", "estimate", "std_error", "converged"},
        10,
    )
    checks["event_study"] = bool(ok)
    if checks["event_study"]:
        score += 8

    ok, comparison = csv_check(
        ROOT / "results/shanghai_nyc_comparison.csv",
        {"city", "outcome", "estimand", "estimate", "std_error", "scale"},
        10,
    )
    checks["comparison"] = bool(ok and comparison is not None and set(comparison["city"]) == {"Shanghai", "New York City"})
    if checks["comparison"]:
        score += 8

    report = ROOT / "final_report.md"
    checks["final_report"] = report.exists() and report.stat().st_size > 3000
    if checks["final_report"]:
        score += 4

    score = min(score, 100)
    print(json.dumps({"pass": score >= 90, "score": score, "target": 90, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
