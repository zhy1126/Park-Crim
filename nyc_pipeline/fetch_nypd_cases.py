from __future__ import annotations

import json
import math
import time
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = ROOT / "raw" / "nypd_by_park"
ARTIFACTS = ROOT / "artifacts"
API = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
PAGE_SIZE = 50_000
SUPPORT_M = 1_500

SELECT = ",".join(
    [
        "cmplnt_num",
        "cmplnt_fr_dt",
        "cmplnt_fr_tm",
        "cmplnt_to_dt",
        "cmplnt_to_tm",
        "rpt_dt",
        "ky_cd",
        "ofns_desc",
        "pd_cd",
        "pd_desc",
        "crm_atpt_cptd_cd",
        "law_cat_cd",
        "boro_nm",
        "loc_of_occur_desc",
        "prem_typ_desc",
        "parks_nm",
        "latitude",
        "longitude",
    ]
)


def half_index(timestamp: pd.Timestamp) -> int:
    return int(timestamp.year * 2 + (timestamp.month > 6))


def half_bounds(opening: pd.Timestamp, lead: int = 3, lag: int = 3) -> tuple[date, date]:
    first = half_index(opening) - lead
    last = half_index(opening) + lag
    first_year, first_half0 = divmod(first, 2)
    last_year, last_half0 = divmod(last, 2)
    start = date(first_year, 1 if first_half0 == 0 else 7, 1)
    end = date(last_year, 6 if last_half0 == 0 else 12, 30 if last_half0 == 0 else 31)
    return start, end


def get_json(params: dict, attempts: int = 6) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(
                API,
                params=params,
                timeout=120,
                headers={"User-Agent": "Shanghai-NYC-comparative-research/1.0"},
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt + 1 == attempts:
                break
            time.sleep(2**attempt)
    raise RuntimeError(f"NYPD API request failed: {last_error}")


def download_bbox(
    park_id: str,
    bounds: tuple[float, float, float, float],
    start: date,
    end: date,
) -> tuple[pd.DataFrame, dict]:
    min_lon, min_lat, max_lon, max_lat = bounds
    where = (
        f"cmplnt_fr_dt between '{start.isoformat()}T00:00:00.000' "
        f"and '{end.isoformat()}T23:59:59.999' "
        f"and latitude between {min_lat:.8f} and {max_lat:.8f} "
        f"and longitude between {min_lon:.8f} and {max_lon:.8f} "
        "and law_cat_cd in ('FELONY','MISDEMEANOR')"
    )
    rows: list[dict] = []
    offset = 0
    while True:
        page = get_json(
            {
                "$select": SELECT,
                "$where": where,
                "$order": "cmplnt_num",
                "$limit": PAGE_SIZE,
                "$offset": offset,
            }
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    frame = pd.DataFrame(rows)
    audit = {
        "park_id": park_id,
        "query_start": start.isoformat(),
        "query_end": end.isoformat(),
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "bbox_records": int(len(frame)),
        "where": where,
    }
    return frame, audit


def time_group(value: object) -> str:
    try:
        hour = int(str(value).split(":", 1)[0])
    except (TypeError, ValueError):
        return "unknown"
    if not 0 <= hour <= 23:
        return "unknown"
    return "day" if 6 <= hour < 18 else "night"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(exist_ok=True)

    parks_payload = json.loads(
        (DATA / "nyc_opening_parks.geojson").read_text(encoding="utf-8")
    )
    parks = gpd.GeoDataFrame.from_features(parks_payload["features"], crs=4326)
    # Construct directly from GeoJSON to avoid a Fiona version mismatch.
    if len(parks) == 0:
        raise RuntimeError("Opening-park geometry file is empty")
    parks = parks.loc[parks["eligible_main"].astype(bool)].copy()
    parks["opening_date"] = pd.to_datetime(parks["opening_date"])
    parks = parks.set_crs(4326, allow_override=True)
    parks_m = parks.to_crs(32618)

    stack_frames: list[pd.DataFrame] = []
    query_audits: list[dict] = []
    for idx, park_m in parks_m.iterrows():
        park_id = str(park_m["park_id"])
        opening = pd.Timestamp(park_m["opening_date"])
        start, end = half_bounds(opening)
        support_wgs = gpd.GeoSeries(
            [park_m.geometry.buffer(SUPPORT_M)], crs=32618
        ).to_crs(4326).iloc[0]
        bounds = support_wgs.bounds
        cache_path = RAW / f"{park_id}_{start}_{end}.csv"
        audit_path = RAW / f"{park_id}_{start}_{end}_query.json"

        if cache_path.exists() and audit_path.exists():
            frame = pd.read_csv(cache_path, dtype={"cmplnt_num": str})
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        else:
            frame, audit = download_bbox(park_id, bounds, start, end)
            frame.to_csv(cache_path, index=False, encoding="utf-8-sig")
            audit_path.write_text(
                json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        for column in ["latitude", "longitude"]:
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        frame["incident_date"] = pd.to_datetime(
            frame.get("cmplnt_fr_dt"), errors="coerce"
        )
        coordinates_ok = frame[["latitude", "longitude"]].notna().all(axis=1)
        dated_ok = frame["incident_date"].notna()
        valid = frame.loc[coordinates_ok & dated_ok].copy()

        points = gpd.GeoDataFrame(
            valid,
            geometry=gpd.points_from_xy(valid["longitude"], valid["latitude"]),
            crs=4326,
        ).to_crs(32618)
        points["distance_to_park_m"] = points.geometry.distance(park_m.geometry)
        points = points.loc[points["distance_to_park_m"] <= SUPPORT_M].copy()
        points["park_id"] = park_id
        points["park_name"] = park_m["park_name"]
        points["opening_date"] = opening.strftime("%Y-%m-%d")
        points["opening_half_index"] = half_index(opening)
        points["incident_half_index"] = points["incident_date"].map(half_index)
        points["event_time"] = (
            points["incident_half_index"] - points["opening_half_index"]
        )
        points = points.loc[points["event_time"].between(-3, 3)].copy()

        offense = points["ofns_desc"].fillna("").str.upper()
        points["is_theft"] = offense.str.contains("LARCENY", regex=False).astype(int)
        points["time_group"] = points["cmplnt_fr_tm"].map(time_group)
        points["is_day"] = points["time_group"].eq("day").astype(int)
        points["is_night"] = points["time_group"].eq("night").astype(int)
        points["half_year"] = (
            points["incident_date"].dt.year.astype(str)
            + "H"
            + (points["incident_date"].dt.month.gt(6).astype(int) + 1).astype(str)
        )
        points = points.drop(columns="geometry")
        stack_frames.append(pd.DataFrame(points))

        audit.update(
            {
                "valid_date_records": int(dated_ok.sum()),
                "valid_coordinate_records": int(coordinates_ok.sum()),
                "within_1500m_records": int(len(points)),
            }
        )
        query_audits.append(audit)
        print(park_id, len(frame), "bbox ->", len(points), "support")

    cases = pd.concat(stack_frames, ignore_index=True)
    cases.to_csv(DATA / "nyc_nypd_stack_cases.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(query_audits).to_csv(
        ARTIFACTS / "nypd_query_manifest.csv", index=False, encoding="utf-8-sig"
    )

    source_records = int(sum(item["bbox_records"] for item in query_audits))
    audit = {
        "n_records": int(len(cases)),
        "bbox_source_records": source_records,
        "incident_date_share": float(cases["incident_date"].notna().mean()),
        "coordinate_share": float(
            cases[["latitude", "longitude"]].notna().all(axis=1).mean()
        ),
        "unique_complaints": int(cases["cmplnt_num"].nunique()),
        "stack_count": int(cases["park_id"].nunique()),
        "theft_share": float(cases["is_theft"].mean()),
        "day_share": float(cases["is_day"].mean()),
        "night_share": float(cases["is_night"].mean()),
        "unknown_time_share": float(cases["time_group"].eq("unknown").mean()),
        "support_m": SUPPORT_M,
        "law_categories": ["FELONY", "MISDEMEANOR"],
        "incident_date_field": "cmplnt_fr_dt",
    }
    (ARTIFACTS / "crime_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
