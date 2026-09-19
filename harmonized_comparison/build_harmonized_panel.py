from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"

EVENT_GEOJSON = DATA / "harmonized_event_geometries.geojson"
NYC_PIPELINE_DIR = Path(
    os.environ.get("NYC_PIPELINE_DIR", ROOT.parent / "nyc_pipeline")
).expanduser()
SHANGHAI_CASES = Path(
    os.environ.get(
        "SHANGHAI_CASES_CSV",
        ROOT / "external_data" / "ChinaCrime_shanghai.csv",
    )
).expanduser()
NYC_RAW_SHORT = Path(
    os.environ.get(
        "NYC_RAW_SHORT_DIR",
        NYC_PIPELINE_DIR / "raw" / "nypd_by_park",
    )
).expanduser()

GRID_M = 500
SUPPORT_M = 1500
PRE_PERIODS = 3
WINDOW_MODE = os.environ.get("HARMONIZED_WINDOW", "short").strip().lower()
if WINDOW_MODE not in {"short", "long"}:
    raise ValueError("HARMONIZED_WINDOW must be 'short' or 'long'")
POST_PERIODS = 0 if WINDOW_MODE == "short" else 3
EVENT_TIMES = tuple(range(-PRE_PERIODS, POST_PERIODS + 1))
WINDOW_SUFFIX = "" if WINDOW_MODE == "short" else "_long_m3_p3"
NYC_RAW = NYC_RAW_SHORT if WINDOW_MODE == "short" else ROOT / "raw" / "nypd_by_park_long"
LAMBDAS = (250, 500, 1000)
CRS_BY_CITY = {"SH": 32651, "NYC": 32618}
SHANGHAI_COVERAGE_START = pd.Timestamp("2010-01-01")
SHANGHAI_COVERAGE_END_EXCLUSIVE = pd.Timestamp("2019-08-11")
SHANGHAI_STABLE_START = pd.Timestamp("2013-10-01")
SHANGHAI_STABLE_END_EXCLUSIVE = pd.Timestamp("2019-04-01")


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def month_offset(timestamp: pd.Timestamp, months: int) -> pd.Timestamp:
    return timestamp + pd.DateOffset(months=months)


def event_period_bounds(opening: pd.Timestamp, event_time: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    return month_offset(opening, 6 * event_time), month_offset(opening, 6 * (event_time + 1))


def period_label(start: pd.Timestamp, end: pd.Timestamp) -> str:
    return f"{start.date().isoformat()}_{(end - pd.Timedelta(days=1)).date().isoformat()}"


def parse_chinese_hour(text: object) -> int | None:
    value = "" if pd.isna(text) else str(text)
    match = re.search(r"(\d{1,2})\s*(?:时|點|点)", value)
    if not match:
        return None
    hour = int(match.group(1))
    if any(token in value for token in ("下午", "晚上", "晚间", "夜间")) and 1 <= hour <= 11:
        hour += 12
    if "凌晨" in value and hour == 12:
        hour = 0
    if hour == 24:
        hour = 0
    return hour if 0 <= hour <= 23 else None


def classify_shanghai_time(frame: pd.DataFrame) -> pd.Series:
    parsed = pd.to_datetime(frame["formatted_datetime"], errors="coerce")
    groups = pd.Series("unknown", index=frame.index, dtype="object")
    known = parsed.notna()
    groups.loc[known & parsed.dt.hour.between(6, 17)] = "day"
    groups.loc[known & ~parsed.dt.hour.between(6, 17)] = "night"
    missing = groups.eq("unknown")
    if missing.any():
        fallback = frame.loc[missing, "incident_time"].map(parse_chinese_hour)
        fallback_known = fallback.notna()
        groups.loc[fallback.index[fallback_known & fallback.between(6, 17)]] = "day"
        groups.loc[fallback.index[fallback_known & ~fallback.between(6, 17)]] = "night"
    return groups


def classify_nyc_time(values: pd.Series) -> pd.Series:
    hours = pd.to_numeric(values.fillna("").astype(str).str.extract(r"^(\d{1,2})")[0], errors="coerce")
    groups = pd.Series("unknown", index=values.index, dtype="object")
    groups.loc[hours.between(6, 17)] = "day"
    groups.loc[hours.notna() & ~hours.between(6, 17)] = "night"
    return groups


def load_events() -> list[dict]:
    payload = json.loads(EVENT_GEOJSON.read_text(encoding="utf-8"))
    events: list[dict] = []
    for feature in payload["features"]:
        props = dict(feature["properties"])
        props["geometry_wgs84"] = shape(feature["geometry"])
        props["opening_date"] = pd.Timestamp(props["opening_date"])
        props["core_eligible"] = bool_value(props["core_eligible"])
        props["broad_eligible"] = bool_value(props["broad_eligible"])
        props["rebuild_comparable"] = bool_value(props["rebuild_comparable"])
        events.append(props)
    return events


def load_shanghai_cases(transformer: Transformer) -> pd.DataFrame:
    usecols = [
        "case_number",
        "case_type",
        "latitude",
        "longitude",
        "incident_time",
        "formatted_datetime",
        "judgment_date",
    ]
    frame = pd.read_csv(
        SHANGHAI_CASES,
        usecols=usecols,
        dtype=str,
        encoding="utf-8-sig",
        low_memory=False,
    )
    frame["incident_datetime"] = pd.to_datetime(frame["formatted_datetime"], errors="coerce")
    frame["incident_date"] = frame["incident_datetime"].dt.normalize()
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame = frame.loc[
        frame["incident_date"].notna()
        & frame["longitude"].between(120.8, 122.2)
        & frame["latitude"].between(30.6, 31.9)
    ].copy()
    frame = frame.loc[
        frame["incident_date"].ge(SHANGHAI_COVERAGE_START)
        & frame["incident_date"].lt(SHANGHAI_COVERAGE_END_EXCLUSIVE)
    ].copy()
    x, y = transformer.transform(frame["longitude"].to_numpy(), frame["latitude"].to_numpy())
    frame["metric_x"] = x
    frame["metric_y"] = y
    frame["grid_ix"] = np.floor(frame["metric_x"] / GRID_M).astype(int)
    frame["grid_iy"] = np.floor(frame["metric_y"] / GRID_M).astype(int)
    frame["grid_id"] = [f"SH_g{ix}_{iy}" for ix, iy in zip(frame["grid_ix"], frame["grid_iy"])]
    offense = frame["case_type"].fillna("").astype(str)
    frame["is_theft"] = offense.str.contains("盗窃|扒窃", regex=True).astype(int)
    frame["time_group"] = classify_shanghai_time(frame)
    frame["case_id"] = frame["case_number"].fillna("").astype(str) + "_row" + frame.index.astype(str)
    return frame


def nyc_query_file(park_id: str) -> Path:
    matches = sorted(NYC_RAW.glob(f"{park_id}_*.csv"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one NYC cached query for {park_id}, found {len(matches)}")
    return matches[0]


def nyc_query_coverage(path: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    match = re.match(r"^[^_]+_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$", path.stem)
    if not match:
        raise ValueError(f"Cannot parse query coverage from {path.name}")
    return pd.Timestamp(match.group(1)), pd.Timestamp(match.group(2)) + pd.Timedelta(days=1)


def load_nyc_cases(path: Path, transformer: Transformer) -> pd.DataFrame:
    usecols = [
        "cmplnt_num",
        "cmplnt_fr_dt",
        "cmplnt_fr_tm",
        "ofns_desc",
        "law_cat_cd",
        "latitude",
        "longitude",
    ]
    frame = pd.read_csv(path, usecols=usecols, dtype={"cmplnt_num": str}, low_memory=False)
    frame = frame.loc[frame["law_cat_cd"].isin(["FELONY", "MISDEMEANOR"])].copy()
    frame["incident_date"] = pd.to_datetime(frame["cmplnt_fr_dt"], errors="coerce").dt.normalize()
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame = frame.loc[
        frame["incident_date"].notna()
        & frame["longitude"].between(-74.3, -73.6)
        & frame["latitude"].between(40.4, 41.0)
    ].copy()
    frame = frame.sort_values("cmplnt_num").drop_duplicates("cmplnt_num", keep="first")
    x, y = transformer.transform(frame["longitude"].to_numpy(), frame["latitude"].to_numpy())
    frame["metric_x"] = x
    frame["metric_y"] = y
    frame["grid_ix"] = np.floor(frame["metric_x"] / GRID_M).astype(int)
    frame["grid_iy"] = np.floor(frame["metric_y"] / GRID_M).astype(int)
    frame["grid_id"] = [f"NYC_g{ix}_{iy}" for ix, iy in zip(frame["grid_ix"], frame["grid_iy"])]
    frame["is_theft"] = frame["ofns_desc"].fillna("").str.upper().str.contains("LARCENY", regex=False).astype(int)
    frame["time_group"] = classify_nyc_time(frame["cmplnt_fr_tm"])
    frame["case_id"] = frame["cmplnt_num"].astype(str)
    return frame


def build_cells(event: dict, metric_geometry) -> dict[str, object]:
    support = metric_geometry.buffer(SUPPORT_M)
    minx, miny, maxx, maxy = support.bounds
    cells: dict[str, object] = {}
    city_code = event["city_code"]
    for ix in range(math.floor(minx / GRID_M), math.floor(maxx / GRID_M) + 1):
        for iy in range(math.floor(miny / GRID_M), math.floor(maxy / GRID_M) + 1):
            cell = box(ix * GRID_M, iy * GRID_M, (ix + 1) * GRID_M, (iy + 1) * GRID_M)
            if cell.intersects(support):
                cells[f"{city_code}_g{ix}_{iy}"] = cell
    return cells


def event_coverage(event: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    if event["city_code"] == "SH":
        return SHANGHAI_COVERAGE_START, SHANGHAI_COVERAGE_END_EXCLUSIVE
    return nyc_query_coverage(nyc_query_file(str(event["source_park_id"])))


def make_rows_for_event(
    event: dict,
    metric_geometry,
    cells: dict[str, object],
    cases: pd.DataFrame,
    coverage_start: pd.Timestamp,
    coverage_end: pd.Timestamp,
) -> tuple[list[dict], dict]:
    opening = event["opening_date"]
    complete_flags = []
    rows: dict[tuple[str, int], dict] = {}
    for grid_id, cell in cells.items():
        distance = float(cell.distance(metric_geometry))
        base = {decay: math.exp(-distance / decay) for decay in LAMBDAS}
        ix, iy = [int(value) for value in re.findall(r"-?\d+", grid_id.split("_g", 1)[1])]
        for event_time in EVENT_TIMES:
            start, end = event_period_bounds(opening, event_time)
            complete = start >= coverage_start and end <= coverage_end
            complete_flags.append(complete)
            post = int(event_time >= 0)
            row = {
                "city": event["city"],
                "city_code": event["city_code"],
                "event_id": event["event_id"],
                "park_name": event["park_name"],
                "park_name_local": event["park_name_local"],
                "opening_date": opening.date().isoformat(),
                "event_family": event["event_family"],
                "source_grade": event["source_grade"],
                "core_eligible": int(event["core_eligible"]),
                "broad_eligible": int(event["broad_eligible"]),
                "rebuild_comparable": int(event["rebuild_comparable"]),
                "grid_id": grid_id,
                "grid_ix": ix,
                "grid_iy": iy,
                "event_time": event_time,
                "period_start": start.date().isoformat(),
                "period_end_exclusive": end.date().isoformat(),
                "period_label": period_label(start, end),
                "period_complete": int(complete),
                "post": post,
                "distance_to_park_m": distance,
                "cell_area_km2": GRID_M * GRID_M / 1_000_000,
                "park_area_ha": float(event["boundary_area_ha"]),
                "stack_unit_id": f"{event['event_id']}__{grid_id}",
                "stack_period_id": f"{event['event_id']}__e{event_time}",
                "grid_cluster_id": grid_id,
                "park_cluster_id": event["event_id"],
                "total_crime": 0,
                "theft": 0,
                "non_theft": 0,
                "day_crime": 0,
                "night_crime": 0,
                "unknown_time": 0,
            }
            for decay in LAMBDAS:
                row[f"base_exposure_{decay}"] = base[decay]
                row[f"continuous_post_{decay}"] = base[decay] * post
                row[f"binary_post_{decay}"] = int(distance <= decay) * post
            rows[(grid_id, event_time)] = row

    event_cases = cases.loc[
        cases["incident_date"].ge(event_period_bounds(opening, EVENT_TIMES[0])[0])
        & cases["incident_date"].lt(event_period_bounds(opening, EVENT_TIMES[-1])[1])
        & cases["grid_id"].isin(cells)
    ].copy()
    event_cases["event_time"] = pd.NA
    for event_time in EVENT_TIMES:
        start, end = event_period_bounds(opening, event_time)
        event_cases.loc[
            event_cases["incident_date"].ge(start) & event_cases["incident_date"].lt(end),
            "event_time",
        ] = event_time
    event_cases = event_cases.dropna(subset=["event_time"]).copy()
    event_cases["event_time"] = event_cases["event_time"].astype(int)

    grouped = event_cases.groupby(["grid_id", "event_time"], observed=True)
    for (grid_id, event_time), group in grouped:
        row = rows.get((str(grid_id), int(event_time)))
        if row is None:
            continue
        row["total_crime"] = int(len(group))
        row["theft"] = int(group["is_theft"].sum())
        row["non_theft"] = int(len(group) - group["is_theft"].sum())
        row["day_crime"] = int(group["time_group"].eq("day").sum())
        row["night_crime"] = int(group["time_group"].eq("night").sum())
        row["unknown_time"] = int(group["time_group"].eq("unknown").sum())

    event_complete = bool(all(complete_flags))
    for row in rows.values():
        row["balanced_window_eligible"] = int(event_complete)
        row["analysis_core"] = int(event_complete and event["core_eligible"])
        row["analysis_broad"] = int(event_complete and event["broad_eligible"])
        row["analysis_source_ab"] = int(
            event_complete and event["core_eligible"] and event["source_grade"] in {"A", "B", "V"}
        )
        row["analysis_rebuild_comparable"] = int(event_complete and event["rebuild_comparable"])
        stable = True
        if event["city_code"] == "SH":
            stable = (
                event_period_bounds(opening, EVENT_TIMES[0])[0] >= SHANGHAI_STABLE_START
                and event_period_bounds(opening, EVENT_TIMES[-1])[1] <= SHANGHAI_STABLE_END_EXCLUSIVE
            )
        row["analysis_stable_window"] = int(event_complete and event["core_eligible"] and stable)

    event_audit = {
        "event_id": event["event_id"],
        "city_code": event["city_code"],
        "park_name": event["park_name"],
        "opening_date": opening.date().isoformat(),
        "cells": len(cells),
        "case_rows": len(event_cases),
        "unique_cases": int(event_cases["case_id"].nunique()),
        "total_count": int(event_cases.shape[0]),
        "theft_count": int(event_cases["is_theft"].sum()),
        "day_count": int(event_cases["time_group"].eq("day").sum()),
        "night_count": int(event_cases["time_group"].eq("night").sum()),
        "unknown_time_count": int(event_cases["time_group"].eq("unknown").sum()),
        "coverage_start": coverage_start.date().isoformat(),
        "coverage_end_exclusive": coverage_end.date().isoformat(),
        "balanced_window_eligible": event_complete,
    }
    return list(rows.values()), event_audit


def add_cross_park_exposure(panel: pd.DataFrame, event_runtime: dict[str, dict], cells: dict[str, object]) -> pd.DataFrame:
    competing = []
    for row in panel.itertuples(index=False):
        cell = cells[row.grid_id]
        midpoint = pd.Timestamp(row.period_start) + (
            pd.Timestamp(row.period_end_exclusive) - pd.Timestamp(row.period_start)
        ) / 2
        count = 0
        nearest = math.inf
        for other_id, other in event_runtime.items():
            if other_id == row.event_id or other["city_code"] != row.city_code:
                continue
            if other["opening_date"] > midpoint:
                continue
            distance = float(cell.distance(other["metric_geometry"]))
            if distance <= SUPPORT_M:
                count += 1
                nearest = min(nearest, distance)
        competing.append((count, nearest if math.isfinite(nearest) else np.nan))
    panel = panel.copy()
    panel["competing_open_event_count"] = [item[0] for item in competing]
    panel["nearest_competing_open_event_m"] = [item[1] for item in competing]
    unit_contaminated = panel.groupby("stack_unit_id")["competing_open_event_count"].transform("max").gt(0)
    panel["ever_competing_open_event"] = unit_contaminated.astype(int)
    panel["analysis_core_uncontaminated"] = (
        panel["analysis_core"].eq(1) & panel["ever_competing_open_event"].eq(0)
    ).astype(int)
    return panel


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    events = load_events()
    transformers = {
        city: Transformer.from_crs(4326, epsg, always_xy=True)
        for city, epsg in CRS_BY_CITY.items()
    }
    geometry_transformers = {
        city: Transformer.from_crs(4326, epsg, always_xy=True).transform
        for city, epsg in CRS_BY_CITY.items()
    }
    sh_cases = load_shanghai_cases(transformers["SH"])

    all_rows: list[dict] = []
    event_audits: list[dict] = []
    event_runtime: dict[str, dict] = {}
    unique_cells: dict[str, object] = {}

    for event in events:
        city_code = event["city_code"]
        metric_geometry = transform(geometry_transformers[city_code], event["geometry_wgs84"])
        cells = build_cells(event, metric_geometry)
        unique_cells.update(cells)
        if city_code == "SH":
            cases = sh_cases
        else:
            query = nyc_query_file(str(event["source_park_id"]))
            cases = load_nyc_cases(query, transformers["NYC"])
        coverage_start, coverage_end = event_coverage(event)
        rows, audit = make_rows_for_event(
            event, metric_geometry, cells, cases, coverage_start, coverage_end
        )
        all_rows.extend(rows)
        event_audits.append(audit)
        event_runtime[event["event_id"]] = {
            "city_code": city_code,
            "opening_date": event["opening_date"],
            "metric_geometry": metric_geometry,
        }
        print(event["event_id"], len(cells), "cells", audit["case_rows"], "case rows")

    panel = pd.DataFrame(all_rows).sort_values(["city_code", "event_id", "grid_id", "event_time"])
    panel = add_cross_park_exposure(panel, event_runtime, unique_cells)

    crime_identity = panel["total_crime"].eq(panel["theft"] + panel["non_theft"])
    time_identity = panel["total_crime"].eq(
        panel["day_crime"] + panel["night_crime"] + panel["unknown_time"]
    )
    balance = panel.groupby("stack_unit_id")["event_time"].nunique().eq(len(EVENT_TIMES))
    if not crime_identity.all() or not time_identity.all() or not balance.all():
        raise RuntimeError("Panel identity or balance check failed")

    panel.to_csv(
        DATA / f"harmonized_stacked_grid_panel_500m{WINDOW_SUFFIX}.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(event_audits).to_csv(
        ARTIFACTS / f"event_case_assignment_audit{WINDOW_SUFFIX}.csv",
        index=False,
        encoding="utf-8-sig",
    )
    panel[
        [
            "city_code",
            "event_id",
            "grid_id",
            "ever_competing_open_event",
            "competing_open_event_count",
            "nearest_competing_open_event_m",
        ]
    ].to_csv(
        ARTIFACTS / f"cross_park_exposure_audit{WINDOW_SUFFIX}.csv",
        index=False,
        encoding="utf-8-sig",
    )

    grid_features = []
    for grid_id, cell in sorted(unique_cells.items()):
        city_code = grid_id.split("_", 1)[0]
        inverse = Transformer.from_crs(CRS_BY_CITY[city_code], 4326, always_xy=True).transform
        grid_features.append(
            {
                "type": "Feature",
                "properties": {"grid_id": grid_id, "city_code": city_code, "grid_size_m": GRID_M},
                "geometry": mapping(transform(inverse, cell)),
            }
        )
    (DATA / f"harmonized_analysis_grids{WINDOW_SUFFIX}.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": grid_features}), encoding="utf-8"
    )

    outcomes = ["total_crime", "theft", "non_theft", "day_crime", "night_crime"]
    audit = {
        "rows": int(len(panel)),
        "events": int(panel["event_id"].nunique()),
        "core_events": int(panel.loc[panel["analysis_core"].eq(1), "event_id"].nunique()),
        "core_events_shanghai": int(panel.loc[panel["analysis_core"].eq(1) & panel["city_code"].eq("SH"), "event_id"].nunique()),
        "core_events_nyc": int(panel.loc[panel["analysis_core"].eq(1) & panel["city_code"].eq("NYC"), "event_id"].nunique()),
        "unique_grids": int(panel["grid_id"].nunique()),
        "stack_units": int(panel["stack_unit_id"].nunique()),
        "event_times": list(EVENT_TIMES),
        "window_mode": WINDOW_MODE,
        "grid_size_m": GRID_M,
        "support_m": SUPPORT_M,
        "crime_identity_pass": bool(crime_identity.all()),
        "time_identity_pass": bool(time_identity.all()),
        "balanced_panel_pass": bool(balance.all()),
        "incomplete_events": sorted(panel.loc[panel["balanced_window_eligible"].eq(0), "event_id"].unique().tolist()),
        "contaminated_stack_unit_share": float(panel.groupby("stack_unit_id")["ever_competing_open_event"].max().mean()),
        "shanghai_source_valid_case_rows": int(len(sh_cases)),
        "shanghai_source_min_date": sh_cases["incident_date"].min().date().isoformat(),
        "shanghai_source_max_date": sh_cases["incident_date"].max().date().isoformat(),
    }
    for city in ("SH", "NYC"):
        subset = panel.loc[panel["analysis_core"].eq(1) & panel["city_code"].eq(city)]
        audit[f"{city}_core_rows"] = int(len(subset))
        audit[f"{city}_core_stack_units"] = int(subset["stack_unit_id"].nunique())
        for outcome in outcomes:
            audit[f"{city}_{outcome}_nonzero_share"] = float(subset[outcome].gt(0).mean())
            always_zero = subset.groupby("stack_unit_id")[outcome].sum().eq(0)
            audit[f"{city}_{outcome}_always_zero_unit_share"] = float(always_zero.mean())
    (ARTIFACTS / f"panel_audit{WINDOW_SUFFIX}.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dictionary = [
        ("event_id", "Unique city-event identifier"),
        ("grid_id", "City-specific 500 m grid identifier"),
        ("event_time", "Opening-date-centered six-month period; -1 is the reference period"),
        ("distance_to_park_m", "Shortest distance from the grid polygon to the focal park polygon"),
        ("continuous_post_500", "exp(-distance/500) multiplied by the post-opening indicator"),
        ("binary_post_500", "Within-500 m indicator multiplied by the post-opening indicator"),
        ("total_crime", "All eligible recorded cases in the grid-period"),
        ("theft", "Shanghai theft-labelled judgments or NYC larceny complaints"),
        ("non_theft", "Total recorded cases minus theft/larceny"),
        ("day_crime", "Recorded cases with incident time from 06:00 through 17:59"),
        ("night_crime", "Recorded cases with incident time from 18:00 through 05:59"),
        ("unknown_time", "Recorded cases without a parseable incident time"),
        ("analysis_core", "Balanced, validated core event sample"),
        ("analysis_rebuild_comparable", "Events classified as reconstruction or reopening in both cities"),
        ("analysis_source_ab", "Core events with source grade A or B"),
        ("analysis_core_uncontaminated", "Core stack-units not exposed to another studied opening"),
    ]
    pd.DataFrame(dictionary, columns=["variable", "definition"]).to_csv(
        DATA / f"harmonized_data_dictionary{WINDOW_SUFFIX}.csv",
        index=False,
        encoding="utf-8-sig",
    )
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
