from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.validation import make_valid


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"

NYC_PIPELINE_DIR = Path(
    os.environ.get("NYC_PIPELINE_DIR", ROOT.parent / "nyc_pipeline")
).expanduser()
SHANGHAI_BOUNDARIES = Path(
    os.environ.get(
        "SHANGHAI_PARK_BOUNDARIES",
        ROOT / "external_data" / "osm_park_boundaries_shanghai.geojson",
    )
).expanduser()
NYC_OPENING_PARKS = (
    NYC_PIPELINE_DIR / "data" / "nyc_opening_parks.geojson"
)


# DEPRECATED MACHINE-REVIEW MATERIAL. These constants record an abandoned
# automated web-search pass. They are never read by the harmonized builder and
# must not be used to validate, exclude, or reinterpret Shanghai events. The
# researcher-verified ledger below is the sole authoritative Shanghai input.
_DEPRECATED_MACHINE_REVIEW_SHANGHAI_EVENTS_DO_NOT_USE = [
    {
        "source_osm_type": "way",
        "source_osm_id": 544050175,
        "park_name": "Jiachuan Road Pocket Park",
        "park_name_local": "嘉川路小游园",
        "opening_date": "2013-05-01",
        "event_family": "major_renovation_reopening",
        "source_grade": "C",
        "source_type": "secondary historical entry",
        "source_url": "https://baike.baidu.com/item/%E5%98%89%E5%B7%9D%E8%B7%AF%E5%B0%8F%E6%B8%B8%E5%9B%AD",
        "source_note": "Existing garden renovated from late 2012 and formally reopened on 1 May 2013.",
        "core_eligible": True,
        "broad_eligible": True,
        "rebuild_comparable": True,
    },
    {
        "source_osm_type": "way",
        "source_osm_id": 1069118321,
        "park_name": "Aisi Children's Park",
        "park_name_local": "爱思儿童公园",
        "opening_date": "2015-06-01",
        "event_family": "long_closure_reopening",
        "source_grade": "B",
        "source_type": "contemporaneous newspaper archive",
        "source_url": "https://xmwb.xinmin.cn/resfile/2015-06-01/B07/B07.pdf",
        "source_note": "Contemporaneous report documents reopening after a thirteen-year closure.",
        "core_eligible": True,
        "broad_eligible": True,
        "rebuild_comparable": True,
    },
    {
        "source_osm_type": "way",
        "source_osm_id": 72233364,
        "park_name": "Xiangyang Park",
        "park_name_local": "襄阳公园",
        "opening_date": "2016-09-30",
        "event_family": "major_renovation_reopening",
        "source_grade": "B",
        "source_type": "contemporaneous municipal newspaper",
        "source_url": "https://www.jfdaily.com/wx/detail.do?id=24875",
        "source_note": "Contemporaneous report announces reopening after approximately ten months of reconstruction.",
        "core_eligible": True,
        "broad_eligible": True,
        "rebuild_comparable": True,
    },
    {
        "source_osm_type": "way",
        "source_osm_id": 1153422469,
        "park_name": "Xikang Park",
        "park_name_local": "西康公园",
        "opening_date": "2018-02-01",
        "event_family": "major_renovation_reopening",
        "source_grade": "B",
        "source_type": "district-government syndicated account",
        "source_url": "https://www.thepaper.cn/newsDetail_forward_20468113",
        "source_note": "Shanghai Jing'an account documents completion of the 2017 renovation and reopening in February 2018.",
        "core_eligible": True,
        "broad_eligible": True,
        "rebuild_comparable": True,
    },
    {
        "source_osm_type": "way",
        "source_osm_id": 489341227,
        "park_name": "Lanxi Youth Park",
        "park_name_local": "兰溪青年公园",
        "opening_date": "2018-06-01",
        "event_family": "major_renovation_reopening",
        "source_grade": "B",
        "source_type": "district government plus historical opening entry",
        "source_url": "https://www.shpt.gov.cn/zhengwu/jyta-lrjzhzw/2024/299/192807.html",
        "source_note": "Putuo government confirms the 2018 whole-park renovation; the day is retained from the historical park entry.",
        "core_eligible": True,
        "broad_eligible": True,
        "rebuild_comparable": True,
    },
    {
        "source_osm_type": "way",
        "source_osm_id": 51051529,
        "park_name": "Zhabei Park",
        "park_name_local": "闸北公园",
        "opening_date": "2018-08-16",
        "event_family": "partial_section_reopening",
        "source_grade": "C",
        "source_type": "secondary contemporaneous report",
        "source_url": "https://m.sh.bendibao.com/tour/196617.html",
        "source_note": "West section reopened while the east section closed for reconstruction; excluded from the core event sample.",
        "core_eligible": False,
        "broad_eligible": True,
        "rebuild_comparable": False,
    },
]


_DEPRECATED_MACHINE_REVIEW_EXCLUSIONS_REJECTED_DO_NOT_USE = [
    {
        "park_name": "Jing'an Sculpture Park",
        "park_name_local": "静安雕塑公园",
        "previous_date": "2012-07-01",
        "reason": "The cited date refers to the opening of a museum site, not the park. Official Shanghai material dates park phases to 2008 and 2010.",
        "verification_url": "https://lhsr.sh.gov.cn/ywdt/20220922/0390e192-11b6-478a-90c8-854d5e9c62c2.html",
    },
    {
        "park_name": "Zhongshan Park",
        "park_name_local": "中山公园",
        "previous_date": "2014-08-21",
        "reason": "The cited date concerns a science room inside Beijing Zhongshan Park, not Shanghai Zhongshan Park.",
        "verification_url": "https://lhsr.sh.gov.cn/ywdt/20220913/3ba665a4-abf2-4abc-937d-0601dac65b44.html",
    },
    {
        "park_name": "Tinglin Park",
        "park_name_local": "亭林公园",
        "previous_date": "2015-03-01",
        "reason": "The cited source concerns the reopening of a memorial hall in Kunshan rather than a Shanghai park opening.",
        "verification_url": "https://baike.baidu.com/item/%E4%BA%AD%E6%9E%97%E5%85%AC%E5%9B%AD",
    },
    {
        "park_name": "Liuzhou Park",
        "park_name_local": "柳洲公园",
        "previous_date": "2018-12-05",
        "reason": "The polygon and source are in Jiashan County, Zhejiang, outside Shanghai.",
        "verification_url": "https://baike.baidu.com/item/%E6%9F%B3%E6%B4%B2%E5%85%AC%E5%9B%AD",
    },
    {
        "park_name": "Xiao Park",
        "park_name_local": "小公园",
        "previous_date": "2019-01-01",
        "reason": "The cited evidence refers to Shantou Small Park; it does not verify the matched Shanghai polygon.",
        "verification_url": "https://baike.baidu.com/item/%E5%B0%8F%E5%85%AC%E5%9B%AD",
    },
]


# The researcher confirmed that the eleven-event Shanghai ledger has already
# been manually verified. This list is therefore the sole authoritative
# Shanghai input for the harmonized build. No automated source search may
# override, exclude, or relabel these events.
USER_VERIFIED_SHANGHAI_EVENTS = [
    ("way", 404696024, "Jing'an Sculpture Park", "静安雕塑公园", "2012-07-01", "day", "project_verified_opening", False),
    ("way", 544050175, "Jiachuan Road Pocket Park", "嘉川路小游园", "2013-05-01", "day", "major_renovation_reopening", True),
    ("way", 45220427, "Zhongshan Park", "中山公园", "2014-08-21", "day", "project_verified_opening", False),
    ("way", 709148322, "Tinglin Park", "亭林公园", "2015-03-01", "month", "project_verified_opening", False),
    ("way", 1069118321, "Aisi Children's Park", "爱思儿童公园", "2015-06-01", "day", "long_closure_reopening", True),
    ("way", 72233364, "Xiangyang Park", "襄阳公园", "2016-09-30", "day", "major_renovation_reopening", True),
    ("way", 1153422469, "Xikang Park", "西康公园", "2018-02-01", "day", "major_renovation_reopening", True),
    ("way", 489341227, "Lanxi Youth Park", "兰溪青年公园", "2018-06-01", "day", "major_renovation_reopening", True),
    ("way", 51051529, "Zhabei Park", "闸北公园", "2018-08-16", "day", "major_renovation_reopening", True),
    ("way", 439866471, "Liuzhou Park", "柳洲公园", "2018-12-05", "day", "project_verified_opening", False),
    ("way", 570675897, "Xiao Park", "小公园", "2019-01-01", "month", "project_verified_opening", False),
]


def project_verified_shanghai_events() -> list[dict]:
    events = []
    for osm_type, osm_id, name, local_name, date, precision, family, rebuild in USER_VERIFIED_SHANGHAI_EVENTS:
        events.append(
            {
                "source_osm_type": osm_type,
                "source_osm_id": osm_id,
                "park_name": name,
                "park_name_local": local_name,
                "opening_date": date,
                "date_precision": precision,
                "event_family": family,
                "source_grade": "V",
                "source_type": "researcher-verified project ledger",
                "source_url": "",
                "source_note": "Opening timing confirmed by the researcher; source archive retained in the Shanghai project materials.",
                "verification_status": "project_verified",
                "core_eligible": True,
                "broad_eligible": True,
                "rebuild_comparable": rebuild,
            }
        )
    return events


def read_geojson(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    fieldnames = columns or list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    sh_payload = read_geojson(SHANGHAI_BOUNDARIES)
    sh_lookup = {
        (str(feature["properties"].get("osm_type")), int(feature["properties"].get("osm_id"))): feature
        for feature in sh_payload["features"]
    }

    features: list[dict] = []
    ledger: list[dict] = []
    for event in project_verified_shanghai_events():
        key = (event["source_osm_type"], int(event["source_osm_id"]))
        source_feature = sh_lookup.get(key)
        if source_feature is None:
            raise RuntimeError(f"Missing Shanghai polygon: {key}")
        geom = make_valid(shape(source_feature["geometry"]))
        event_id = f"SH_{key[0]}_{key[1]}"
        props = {
            **event,
            "event_id": event_id,
            "city": "Shanghai",
            "city_code": "SH",
            "date_precision": event["date_precision"],
            "boundary_area_ha": float(source_feature["properties"].get("area_m2", 0)) / 10000,
            "geometry_valid": bool(geom.is_valid),
            "boundary_source": str(SHANGHAI_BOUNDARIES),
        }
        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
        ledger.append(props)

    ny_payload = read_geojson(NYC_OPENING_PARKS)
    for source_feature in ny_payload["features"]:
        source_props = source_feature["properties"]
        if not bool(source_props.get("eligible_main")):
            continue
        geom = make_valid(shape(source_feature["geometry"]))
        park_id = str(source_props["park_id"])
        event_class = str(source_props["opening_class"])
        rebuild = event_class in {
            "replacement_park_opening",
            "complete_rebuild_reopening",
            "new_rebuilt_park_opening",
        }
        props = {
            "event_id": f"NYC_{park_id}",
            "city": "New York City",
            "city_code": "NYC",
            "park_name": str(source_props["park_name"]),
            "park_name_local": str(source_props["park_name"]),
            "opening_date": str(source_props["opening_date"]),
            "date_precision": "day",
            "event_family": "replacement_or_rebuild" if rebuild else "first_or_new_opening",
            "source_grade": "A",
            "source_type": "NYC Parks official press release",
            "source_url": str(source_props.get("url", "")),
            "source_note": str(source_props.get("scope_note", "")),
            "verification_status": "official_source_verified",
            "core_eligible": True,
            "broad_eligible": True,
            "rebuild_comparable": rebuild,
            "source_park_id": park_id,
            "boundary_area_ha": float(source_props["boundary_area_ha"]),
            "geometry_valid": bool(geom.is_valid),
            "boundary_source": str(NYC_OPENING_PARKS),
        }
        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
        ledger.append(props)

    ledger.sort(key=lambda row: (row["city_code"], row["opening_date"], row["event_id"]))
    write_csv(DATA / "harmonized_event_ledger.csv", ledger)
    write_csv(
        ARTIFACTS / "shanghai_project_verified_event_audit.csv",
        [
            {
                "event_id": row["event_id"],
                "park_name": row["park_name"],
                "park_name_local": row["park_name_local"],
                "opening_date": row["opening_date"],
                "date_precision": row["date_precision"],
                "verification_status": row.get("verification_status", "official_nyc_record"),
            }
            for row in ledger
            if row["city_code"] == "SH"
        ],
    )
    (DATA / "harmonized_event_geometries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = {
        "events_total": len(ledger),
        "core_events_total": sum(bool(row["core_eligible"]) for row in ledger),
        "core_events_shanghai": sum(row["city_code"] == "SH" and bool(row["core_eligible"]) for row in ledger),
        "core_events_nyc": sum(row["city_code"] == "NYC" and bool(row["core_eligible"]) for row in ledger),
        "rebuild_comparable_events": sum(bool(row["rebuild_comparable"]) for row in ledger),
        "excluded_shanghai_events": 0,
        "all_dates_month_or_day_precision": all(row["date_precision"] in {"day", "month"} for row in ledger),
        "all_geometries_valid": all(bool(row["geometry_valid"]) for row in ledger),
        "all_events_have_explicit_verification_status": all(
            bool(row.get("verification_status")) for row in ledger
        ),
    }
    (ARTIFACTS / "event_ledger_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
