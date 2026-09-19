from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent
NYC_PIPELINE_DIR = Path(
    os.environ.get("NYC_PIPELINE_DIR", ROOT.parent / "nyc_pipeline")
).expanduser()
LEDGER = ROOT / "data" / "harmonized_event_ledger.csv"
OLD_RAW = Path(
    os.environ.get(
        "NYC_RAW_SHORT_DIR",
        NYC_PIPELINE_DIR / "raw" / "nypd_by_park",
    )
).expanduser()
OUTPUT = ROOT / "raw" / "nypd_by_park_long"
ARTIFACTS = ROOT / "artifacts"

API = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
PAGE_SIZE = 50_000
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


def request_page(params: dict, attempts: int = 7) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(
                API,
                params=params,
                timeout=180,
                headers={"User-Agent": "Shanghai-NYC-harmonized-comparison/2.0"},
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(min(60, 2**attempt))
    raise RuntimeError(f"NYC Open Data request failed: {last_error}")


def bbox_for_park(park_id: str) -> list[float]:
    matches = sorted(OLD_RAW.glob(f"{park_id}_*_query.json"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one prior bbox manifest for {park_id}, found {len(matches)}")
    payload = json.loads(matches[0].read_text(encoding="utf-8"))
    return [float(value) for value in payload["bbox"]]


def download(park_id: str, opening: pd.Timestamp) -> dict:
    start = opening + pd.DateOffset(months=-18)
    end_exclusive = opening + pd.DateOffset(months=24)
    end_inclusive = end_exclusive - pd.Timedelta(days=1)
    min_lon, min_lat, max_lon, max_lat = bbox_for_park(park_id)
    where = (
        f"cmplnt_fr_dt between '{start.date().isoformat()}T00:00:00.000' "
        f"and '{end_inclusive.date().isoformat()}T23:59:59.999' "
        f"and latitude between {min_lat:.8f} and {max_lat:.8f} "
        f"and longitude between {min_lon:.8f} and {max_lon:.8f} "
        "and law_cat_cd in ('FELONY','MISDEMEANOR')"
    )
    csv_path = OUTPUT / (
        f"{park_id}_{start.date().isoformat()}_{end_inclusive.date().isoformat()}.csv"
    )
    json_path = csv_path.with_name(csv_path.stem + "_query.json")
    if csv_path.exists() and json_path.exists():
        audit = json.loads(json_path.read_text(encoding="utf-8"))
        audit["cache_reused"] = True
        return audit

    rows: list[dict] = []
    offset = 0
    while True:
        page = request_page(
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
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    audit = {
        "park_id": park_id,
        "opening_date": opening.date().isoformat(),
        "query_start": start.date().isoformat(),
        "query_end": end_inclusive.date().isoformat(),
        "coverage_end_exclusive": end_exclusive.date().isoformat(),
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "bbox_records": int(len(frame)),
        "where": where,
        "api": API,
        "cache_reused": False,
    }
    json_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    ledger = pd.read_csv(LEDGER)
    nyc = ledger.loc[ledger["city_code"].eq("NYC")].copy()
    nyc["opening_date"] = pd.to_datetime(nyc["opening_date"], errors="raise")

    audits: list[dict] = []
    for row in nyc.itertuples(index=False):
        audit = download(str(row.source_park_id), pd.Timestamp(row.opening_date))
        audits.append(audit)
        print(row.source_park_id, audit["bbox_records"], "bbox records")

    manifest = pd.DataFrame(audits).sort_values("park_id")
    manifest.to_csv(
        ARTIFACTS / "nyc_exact_long_window_query_manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )
    summary = {
        "events": int(len(manifest)),
        "bbox_records_total": int(manifest["bbox_records"].sum()),
        "all_exact_windows_cached": bool(len(manifest) == len(nyc)),
        "api": API,
    }
    (ARTIFACTS / "nyc_exact_long_window_download_audit.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
