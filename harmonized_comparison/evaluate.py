from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
ARTIFACTS = ROOT / "artifacts"
FIGURES = ROOT / "figures"
REPORTS = ROOT / "reports"
LOG = ROOT / "autoresearch-results.tsv"


def tagged(filename: str, suffix: str) -> str:
    path = Path(filename)
    return f"{path.stem}{suffix}{path.suffix}"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def park_jackknife(suffix: str) -> pd.DataFrame:
    static = pd.read_csv(RESULTS / tagged("city_specific_static_ppml.csv", suffix))
    loo = pd.read_csv(RESULTS / tagged("leave_one_event_out.csv", suffix))
    full = static.loc[
        static["sample"].eq("core") & static["vcov"].eq("grid")
    ].copy()
    rows: list[dict] = []
    for _, model in full.iterrows():
        subset = loo.loc[
            loo["city_code"].eq(model["city_code"])
            & loo["design"].eq(model["design"])
            & loo["outcome"].eq(model["outcome"])
        ].copy()
        estimates = pd.to_numeric(subset["estimate"], errors="coerce").dropna().to_numpy()
        clusters = len(estimates)
        if clusters >= 3:
            mean_loo = float(estimates.mean())
            variance = float((clusters - 1) / clusters * np.square(estimates - mean_loo).sum())
            se = float(np.sqrt(max(variance, 0)))
            estimate = float(model["estimate"])
            statistic = estimate / se if se > 0 else np.nan
            p_value = (
                float(2 * student_t.sf(abs(statistic), df=clusters - 1))
                if np.isfinite(statistic)
                else np.nan
            )
            critical = float(student_t.ppf(0.975, df=clusters - 1))
            lower = estimate - critical * se
            upper = estimate + critical * se
            bias_corrected = clusters * estimate - (clusters - 1) * mean_loo
        else:
            mean_loo = se = statistic = p_value = lower = upper = bias_corrected = np.nan
        rows.append(
            {
                "window": "long_m3_p3" if suffix else "short_m3_p0",
                "city_code": model["city_code"],
                "design": model["design"],
                "outcome": model["outcome"],
                "full_estimate": float(model["estimate"]),
                "grid_cluster_se": float(model["std_error"]),
                "grid_cluster_p": float(model["p_value"]),
                "park_clusters": clusters,
                "leave_one_out_mean": mean_loo,
                "leave_one_out_min": float(estimates.min()) if clusters else np.nan,
                "leave_one_out_max": float(estimates.max()) if clusters else np.nan,
                "same_sign_share": (
                    float(np.mean(np.sign(estimates) == np.sign(float(model["estimate"]))))
                    if clusters
                    else np.nan
                ),
                "jackknife_bias_corrected_estimate": bias_corrected,
                "park_jackknife_se": se,
                "park_jackknife_t": statistic,
                "park_jackknife_p": p_value,
                "park_jackknife_ci_lower": lower,
                "park_jackknife_ci_upper": upper,
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(
        RESULTS / tagged("park_jackknife_inference.csv", suffix),
        index=False,
        encoding="utf-8-sig",
    )
    return result


def key_results() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for suffix, window in [("", "short_m3_p0"), ("_long_m3_p3", "long_m3_p3")]:
        static = pd.read_csv(RESULTS / tagged("city_specific_static_ppml.csv", suffix))
        static = static.loc[
            static["sample"].eq("core") & static["vcov"].eq("grid")
        ].copy()
        static["window"] = window
        static["result_type"] = "static_average_post"
        static["event_time"] = np.nan
        rows.append(
            static[
                [
                    "window",
                    "result_type",
                    "city_code",
                    "design",
                    "outcome",
                    "event_time",
                    "estimate",
                    "std_error",
                    "p_value",
                    "n_obs",
                    "n_events",
                ]
            ]
        )
        dynamic = pd.read_csv(RESULTS / tagged("dynamic_event_study.csv", suffix))
        dynamic = dynamic.loc[dynamic["treatment_type"].eq("continuous")].copy()
        dynamic["window"] = window
        dynamic["result_type"] = "dynamic_relative_to_m1"
        dynamic["design"] = "continuous_park_opening_ppml"
        dynamic["n_events"] = dynamic["city_code"].map(
            static.groupby("city_code")["n_events"].first()
        )
        rows.append(
            dynamic[
                [
                    "window",
                    "result_type",
                    "city_code",
                    "design",
                    "outcome",
                    "event_time",
                    "estimate",
                    "std_error",
                    "p_value",
                    "n_obs",
                    "n_events",
                ]
            ]
        )
    result = pd.concat(rows, ignore_index=True)
    result["incidence_rate_ratio"] = np.exp(result["estimate"])
    result["percent_change_full_scale"] = 100 * (result["incidence_rate_ratio"] - 1)
    result.to_csv(RESULTS / "key_result_matrix.csv", index=False, encoding="utf-8-sig")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_manifest() -> pd.DataFrame:
    include_roots = [DATA, RESULTS, ARTIFACTS, FIGURES, REPORTS]
    files: list[Path] = []
    for folder in include_roots:
        if folder.exists():
            files.extend(path for path in folder.rglob("*") if path.is_file())
    files.extend(
        path
        for path in ROOT.glob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".r", ".md", ".tsv"}
    )
    rows = []
    for path in sorted(set(files)):
        if path.name == "artifact_manifest.csv":
            continue
        rows.append(
            {
                "relative_path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    manifest = pd.DataFrame(rows)
    manifest.to_csv(ARTIFACTS / "artifact_manifest.csv", index=False, encoding="utf-8-sig")
    return manifest


def score_run() -> dict:
    event_audit = read_json(ARTIFACTS / "event_ledger_audit.json")
    short_panel = read_json(ARTIFACTS / "panel_audit.json")
    long_panel = read_json(ARTIFACTS / "panel_audit_long_m3_p3.json")
    short_models = read_json(ARTIFACTS / "model_run_audit.json")
    long_models = read_json(ARTIFACTS / "model_run_audit_long_m3_p3.json")
    ledger = pd.read_csv(DATA / "harmonized_event_ledger.csv")
    short_pre = pd.read_csv(RESULTS / "joint_pretrend_tests.csv")
    long_pre = pd.read_csv(RESULTS / "joint_pretrend_tests_long_m3_p3.csv")
    short_placebo = pd.read_csv(RESULTS / "preperiod_placebo_tests.csv")
    short_jackknife = park_jackknife("")
    long_jackknife = park_jackknife("_long_m3_p3")
    key_results()

    criteria = {
        "events_20_with_11_shanghai_9_nyc": event_audit.get("events_total") == 20
        and event_audit.get("core_events_shanghai") == 11
        and event_audit.get("core_events_nyc") == 9,
        "all_events_verified_and_geometrically_valid": bool(
            event_audit.get("all_events_have_explicit_verification_status")
            and event_audit.get("all_geometries_valid")
            and ledger["verification_status"].fillna("").ne("").all()
        ),
        "all_dates_at_least_month_precision": bool(
            event_audit.get("all_dates_month_or_day_precision")
        ),
        "short_panel_uses_all_20_events": short_panel.get("core_events") == 20,
        "long_panel_has_both_cities": long_panel.get("core_events_shanghai", 0) > 0
        and long_panel.get("core_events_nyc", 0) > 0,
        "panel_identities_and_balance_pass": all(
            bool(item.get(key))
            for item in (short_panel, long_panel)
            for key in ("crime_identity_pass", "time_identity_pass", "balanced_panel_pass")
        ),
        "spatial_protocol_is_500m_1500m": all(
            item.get("grid_size_m") == 500 and item.get("support_m") == 1500
            for item in (short_panel, long_panel)
        ),
        "all_static_models_converged": short_models.get("static_successes")
        == short_models.get("static_models")
        and long_models.get("static_successes") == long_models.get("static_models"),
        "all_dynamic_models_generated": short_models.get("dynamic_models") == 20
        and long_models.get("dynamic_models") == 20
        and short_pre["converged"].astype(str).str.lower().eq("true").all()
        and long_pre["converged"].astype(str).str.lower().eq("true").all(),
        "placebo_models_generated_and_converged": len(short_placebo) == 20
        and short_placebo["converged"].astype(str).str.lower().eq("true").all(),
        "leave_one_event_out_and_jackknife_generated": len(short_jackknife) == 20
        and len(long_jackknife) == 20
        and short_jackknife["park_clusters"].min() >= 9
        and long_jackknife["park_clusters"].min() >= 6,
        "exact_nyc_long_window_cache_complete": (
            ARTIFACTS / "nyc_exact_long_window_download_audit.json"
        ).exists()
        and read_json(ARTIFACTS / "nyc_exact_long_window_download_audit.json").get(
            "all_exact_windows_cached"
        ),
        "source_stage_limitation_frozen_in_protocol": "source-stage limitation"
        in (ROOT / "research.md").read_text(encoding="utf-8").lower(),
        "technical_report_exists": any(REPORTS.glob("*.docx")),
        "figures_exist": len(list(FIGURES.glob("*.png"))) >= 3,
    }
    criteria = {name: bool(value) for name, value in criteria.items()}

    weights = {
        "events_20_with_11_shanghai_9_nyc": 8,
        "all_events_verified_and_geometrically_valid": 7,
        "all_dates_at_least_month_precision": 5,
        "short_panel_uses_all_20_events": 7,
        "long_panel_has_both_cities": 5,
        "panel_identities_and_balance_pass": 8,
        "spatial_protocol_is_500m_1500m": 5,
        "all_static_models_converged": 8,
        "all_dynamic_models_generated": 8,
        "placebo_models_generated_and_converged": 6,
        "leave_one_event_out_and_jackknife_generated": 9,
        "exact_nyc_long_window_cache_complete": 5,
        "source_stage_limitation_frozen_in_protocol": 4,
        "technical_report_exists": 10,
        "figures_exist": 5,
    }
    score = int(sum(weights[name] for name, passed in criteria.items() if passed))
    min_placebo_p = float(pd.to_numeric(short_placebo["p_value"], errors="coerce").min())
    min_pretrend_p = float(
        min(
            pd.to_numeric(short_pre["p_value"], errors="coerce").min(),
            pd.to_numeric(long_pre["p_value"], errors="coerce").min(),
        )
    )
    evaluation = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "score": score,
        "target": 90,
        "target_met": score >= 90,
        "criteria": criteria,
        "diagnostic_facts": {
            "short_core_events": short_panel.get("core_events"),
            "long_core_events": long_panel.get("core_events"),
            "long_shanghai_events": long_panel.get("core_events_shanghai"),
            "long_nyc_events": long_panel.get("core_events_nyc"),
            "short_min_placebo_p": min_placebo_p,
            "minimum_joint_pretrend_p": min_pretrend_p,
            "short_contaminated_stack_unit_share": short_panel.get(
                "contaminated_stack_unit_share"
            ),
            "source_stage_comparable": False,
        },
        "causal_readiness": {
            "status": "comparative replication with qualified causal interpretation",
            "binding_limitations": [
                "Shanghai judgments and NYC complaints are different recording stages.",
                "Only 11 Shanghai and 9 NYC focal events are available.",
                "The 20-event common sample identifies only the first six post-opening months.",
                "Shanghai static total-crime significance is not replicated by the binary design or long-window average.",
                "About one sixth of short-window stack-units overlap another studied opening; an uncontaminated sensitivity is required.",
            ],
        },
    }
    (ARTIFACTS / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return evaluation


def append_log(evaluation: dict) -> None:
    rows: list[list[str]] = []
    if LOG.exists():
        with LOG.open("r", encoding="utf-8") as stream:
            rows = list(csv.reader(stream, delimiter="\t"))
    if not rows:
        rows = [["iteration", "timestamp", "score", "status", "change"]]
    iterations = [int(row[0]) for row in rows[1:] if row and row[0].isdigit()]
    iteration = max(iterations, default=-1) + 1
    rows.append(
        [
            str(iteration),
            evaluation["timestamp"],
            str(evaluation["score"]),
            "target_met" if evaluation["target_met"] else "in_progress",
            "harmonized short and long panels, PPML diagnostics, and park jackknife",
        ]
    )
    with LOG.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerows(rows)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    evaluation = score_run()
    append_log(evaluation)
    manifest = artifact_manifest()
    print(
        json.dumps(
            {
                "score": evaluation["score"],
                "target_met": evaluation["target_met"],
                "manifest_files": int(len(manifest)),
            }
        )
    )


if __name__ == "__main__":
    main()
