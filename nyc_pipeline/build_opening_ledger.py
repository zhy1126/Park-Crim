from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = ROOT / "raw"
ARTIFACTS = ROOT / "artifacts"


# Each row is tied to an official NYC Parks release already archived by
# fetch_official_inputs.py. Ordinary amenity upgrades and partial facility
# openings are deliberately omitted.
CURATED_EVENTS = [
    {
        "park_name": "Macombs Dam Park",
        "gispropnum": "X030",
        "opening_date": "2010-04-09",
        "release_id": 20906,
        "opening_class": "replacement_park_opening",
        "eligible_main": True,
        "scope_note": "Official release describes the new Macombs Dam Park and seven-acre track-and-field opening.",
    },
    {
        "park_name": "Robert E. Venable Park",
        "gispropnum": "B380",
        "opening_date": "2010-07-02",
        "release_id": 20929,
        "opening_class": "new_park_from_scratch",
        "eligible_main": True,
        "scope_note": "Official release states that the reconstruction created a new park from scratch.",
    },
    {
        "park_name": "River Avenue Parks",
        "gispropnum": "X348",
        "opening_date": "2010-08-31",
        "release_id": 20943,
        "opening_class": "new_pocket_parks",
        "eligible_main": True,
        "scope_note": "Official release describes newly constructed pocket parks on a former parking lot.",
    },
    {
        "park_name": "Estella Diggs Park",
        "gispropnum": "X243",
        "opening_date": "2011-11-07",
        "release_id": 21023,
        "opening_class": "new_park_opening",
        "eligible_main": True,
        "scope_note": "Official release records the community opening of the newly constructed park.",
    },
    {
        "park_name": "Schmul Park",
        "gispropnum": "R045",
        "opening_date": "2012-10-05",
        "release_id": 21097,
        "opening_class": "complete_rebuild_reopening",
        "eligible_main": True,
        "scope_note": "Official ribbon cutting marks public reopening after a complete park reconstruction.",
    },
    {
        "park_name": "Starlight Park",
        "gispropnum": "X147A",
        "opening_date": "2013-05-10",
        "release_id": 21128,
        "opening_class": "new_rebuilt_park_opening",
        "eligible_main": True,
        "scope_note": "Official release announces the opening of the rebuilt and expanded park.",
    },
    {
        "park_name": "Hunter's Point South Park",
        "gispropnum": "Q471",
        "opening_date": "2018-06-27",
        "release_id": 21586,
        "opening_class": "new_phase_opening",
        "eligible_main": False,
        "scope_note": "The release concerns a new 5.5-acre phase, while the current property polygon also contains an earlier phase.",
    },
    {
        "park_name": "Chelsea Green",
        "gispropnum": "M402",
        "opening_date": "2019-07-26",
        "release_id": 21682,
        "opening_class": "first_public_opening",
        "eligible_main": True,
        "scope_note": "Official release identifies the first new community park built in Chelsea in forty years.",
    },
    {
        "park_name": "Betty Carter Park",
        "gispropnum": "B592",
        "opening_date": "2019-09-20",
        "release_id": 21698,
        "opening_class": "first_public_opening",
        "eligible_main": True,
        "scope_note": "Official release states that NYC Parks officially opened and dedicated the park.",
    },
    {
        "park_name": "Richmond Terrace Park",
        "gispropnum": "R167",
        "opening_date": "2019-11-26",
        "release_id": 21728,
        "opening_class": "first_public_opening",
        "eligible_main": True,
        "scope_note": "Official release records the ribbon cutting for a brand-new park.",
    },
]


def release_id(url: str) -> int | None:
    match = re.search(r"(?:id=|pressrelease/)(\d+)", str(url))
    return int(match.group(1)) if match else None


def main() -> None:
    DATA.mkdir(exist_ok=True)
    ARTIFACTS.mkdir(exist_ok=True)

    releases = pd.read_csv(DATA / "nyc_press_release_index_2010_2019.csv")
    releases["release_id"] = releases["url"].map(release_id)
    releases = releases.dropna(subset=["release_id"]).copy()
    releases["release_id"] = releases["release_id"].astype(int)

    parks_payload = json.loads(
        (RAW / "nyc_parks_properties.geojson").read_text(encoding="utf-8")
    )
    parks = gpd.GeoDataFrame.from_features(parks_payload["features"], crs=4326)
    if parks.crs is None:
        parks = parks.set_crs(4326)
    parks = parks.to_crs(4326)

    curated = pd.DataFrame(CURATED_EVENTS)
    curated["opening_date"] = pd.to_datetime(curated["opening_date"])
    curated = curated.merge(
        releases[["release_id", "release_date", "title", "url"]],
        on="release_id",
        how="left",
        validate="one_to_one",
    )
    if curated[["title", "url"]].isna().any().any():
        missing = curated.loc[curated["title"].isna(), "release_id"].tolist()
        raise RuntimeError(f"Missing archived official releases: {missing}")

    selected_parks = parks.loc[parks["gispropnum"].isin(curated["gispropnum"])].copy()
    matched = selected_parks.merge(
        curated, on="gispropnum", how="inner", validate="one_to_one"
    )
    if len(matched) != len(curated):
        found = set(matched["gispropnum"])
        missing = curated.loc[~curated["gispropnum"].isin(found), "gispropnum"].tolist()
        raise RuntimeError(f"Missing official park polygons: {missing}")

    projected = matched.to_crs(32618)
    matched["boundary_area_ha"] = projected.geometry.area / 10_000
    matched["geometry_valid"] = matched.geometry.is_valid
    matched["boundary_match"] = True
    matched["source_type"] = "NYC Parks official press release"
    matched["date_precision"] = "day"
    matched["opening_precision"] = matched["date_precision"]
    matched["event_class"] = matched["opening_class"]
    matched["source_url"] = matched["url"]
    matched["opening_half"] = (
        matched["opening_date"].dt.year.astype(str)
        + "H"
        + (matched["opening_date"].dt.month.gt(6).astype(int) + 1).astype(str)
    )
    matched["park_id"] = matched["gispropnum"]

    ledger_cols = [
        "park_id",
        "park_name",
        "gispropnum",
        "opening_date",
        "opening_half",
        "date_precision",
        "opening_class",
        "eligible_main",
        "boundary_match",
        "geometry_valid",
        "boundary_area_ha",
        "acres",
        "borough",
        "typecategory",
        "title",
        "url",
        "source_type",
        "scope_note",
    ]
    matched[ledger_cols].drop(columns="geometry_valid").to_csv(
        DATA / "nyc_opening_ledger.csv", index=False, encoding="utf-8-sig"
    )
    evaluator_cols = [
        "park_id",
        "park_name",
        "opening_date",
        "opening_precision",
        "event_class",
        "source_url",
        "eligible_main",
        "boundary_match",
        "boundary_area_ha",
        "scope_note",
    ]
    matched[evaluator_cols].to_csv(
        DATA / "nyc_park_opening_ledger.csv", index=False, encoding="utf-8-sig"
    )
    geo_out = matched[ledger_cols + ["geometry"]].copy()
    geo_out["opening_date"] = geo_out["opening_date"].dt.strftime("%Y-%m-%d")
    (DATA / "nyc_opening_parks.geojson").write_text(
        geo_out.to_json(drop_id=True), encoding="utf-8"
    )

    summary = {
        "candidate_release_count": int(len(releases)),
        "audited_event_count": int(len(matched)),
        "main_eligible_count": int(matched["eligible_main"].sum()),
        "sensitivity_only_count": int((~matched["eligible_main"]).sum()),
        "all_boundaries_matched": bool(matched["boundary_match"].all()),
        "all_geometries_valid": bool(matched["geometry_valid"].all()),
        "opening_date_min": matched["opening_date"].min().date().isoformat(),
        "opening_date_max": matched["opening_date"].max().date().isoformat(),
    }
    (ARTIFACTS / "opening_ledger_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    boundary_audit = {
        "eligible_events": int(matched["eligible_main"].sum()),
        "matched_events": int(
            matched.loc[matched["eligible_main"], "boundary_match"].sum()
        ),
        "all_geometries_valid": bool(
            matched.loc[matched["eligible_main"], "geometry_valid"].all()
        ),
        "crs": "EPSG:4326",
        "metric_crs_for_distance": "EPSG:32618",
    }
    (ARTIFACTS / "boundary_audit.json").write_text(
        json.dumps(boundary_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
