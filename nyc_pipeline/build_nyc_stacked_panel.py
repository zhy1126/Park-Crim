from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"
GRID_M = 500
SUPPORT_M = 1_500
WINDOW = 3
LAMBDAS = (250, 500, 1000)


def half_index(timestamp: pd.Timestamp) -> int:
    return int(timestamp.year * 2 + (timestamp.month > 6))


def half_label(index: int) -> str:
    year, half0 = divmod(index, 2)
    return f"{year}H{half0 + 1}"


def main() -> None:
    payload = json.loads((DATA / "nyc_opening_parks.geojson").read_text(encoding="utf-8"))
    parks = gpd.GeoDataFrame.from_features(payload["features"], crs=4326)
    parks = parks.loc[parks["eligible_main"].astype(bool)].copy()
    parks["opening_date"] = pd.to_datetime(parks["opening_date"])
    parks_m = parks.to_crs(32618)

    rows: dict[tuple[str, str, int], dict] = {}
    grid_geometries: dict[str, object] = {}
    event_geometries: dict[str, object] = {}
    event_opening: dict[str, int] = {}

    for _, park in parks_m.iterrows():
        park_id = str(park["park_id"])
        geometry = park.geometry
        support = geometry.buffer(SUPPORT_M)
        minx, miny, maxx, maxy = support.bounds
        ix_min = math.floor(minx / GRID_M)
        ix_max = math.floor(maxx / GRID_M)
        iy_min = math.floor(miny / GRID_M)
        iy_max = math.floor(maxy / GRID_M)
        open_index = half_index(pd.Timestamp(park["opening_date"]))
        event_geometries[park_id] = geometry
        event_opening[park_id] = open_index

        for ix in range(ix_min, ix_max + 1):
            for iy in range(iy_min, iy_max + 1):
                cell = box(
                    ix * GRID_M,
                    iy * GRID_M,
                    (ix + 1) * GRID_M,
                    (iy + 1) * GRID_M,
                )
                if not cell.intersects(support):
                    continue
                distance = float(cell.distance(geometry))
                grid_id = f"nyc_g{ix}_{iy}"
                grid_geometries[grid_id] = cell
                for event_time in range(-WINDOW, WINDOW + 1):
                    period = open_index + event_time
                    post = int(event_time >= 0)
                    row = {
                        "city": "New York City",
                        "park_id": park_id,
                        "park_name": park["park_name"],
                        "grid_id": grid_id,
                        "grid_ix": ix,
                        "grid_iy": iy,
                        "half_index": period,
                        "half_year": half_label(period),
                        "event_time": event_time,
                        "post": post,
                        "opening_date": pd.Timestamp(park["opening_date"]).strftime("%Y-%m-%d"),
                        "opening_class": park["opening_class"],
                        "park_area_ha": float(park["boundary_area_ha"]),
                        "distance_m": distance,
                        "cell_area_km2": GRID_M * GRID_M / 1_000_000,
                        "stack_unit_id": f"{park_id}_{grid_id}",
                        "stack_half_id": f"{park_id}_{half_label(period)}",
                        "total_crime": 0,
                        "theft": 0,
                        "non_theft": 0,
                        "day_crime": 0,
                        "night_crime": 0,
                        "unknown_time": 0,
                    }
                    for decay in LAMBDAS:
                        exposure = math.exp(-distance / decay)
                        row[f"exposure_{decay}"] = exposure * post
                        row[f"baseline_exposure_{decay}"] = exposure
                        row[f"binary_{decay}"] = int(distance <= decay) * post
                    rows[(park_id, grid_id, period)] = row

    cases = pd.read_csv(
        DATA / "nyc_nypd_stack_cases.csv",
        dtype={"cmplnt_num": str, "park_id": str},
        low_memory=False,
    )
    points = gpd.GeoDataFrame(
        cases,
        geometry=gpd.points_from_xy(cases["longitude"], cases["latitude"]),
        crs=4326,
    ).to_crs(32618)
    xs = points.geometry.x.to_numpy()
    ys = points.geometry.y.to_numpy()
    ixs = np.floor(xs / GRID_M).astype(int)
    iys = np.floor(ys / GRID_M).astype(int)
    points["grid_id"] = [f"nyc_g{ix}_{iy}" for ix, iy in zip(ixs, iys)]
    points["incident_date"] = pd.to_datetime(points["incident_date"], errors="coerce")
    points["half_index"] = points["incident_date"].map(half_index)

    assigned = 0
    outside_grid = 0
    for record in points.itertuples(index=False):
        key = (str(record.park_id), str(record.grid_id), int(record.half_index))
        row = rows.get(key)
        if row is None:
            outside_grid += 1
            continue
        row["total_crime"] += 1
        if int(record.is_theft) == 1:
            row["theft"] += 1
        else:
            row["non_theft"] += 1
        if record.time_group == "day":
            row["day_crime"] += 1
        elif record.time_group == "night":
            row["night_crime"] += 1
        else:
            row["unknown_time"] += 1
        assigned += 1

    panel = pd.DataFrame(rows.values()).sort_values(
        ["park_id", "grid_id", "half_index"]
    )
    crime_identity = panel["total_crime"].eq(panel["theft"] + panel["non_theft"])
    time_identity = panel["total_crime"].eq(
        panel["day_crime"] + panel["night_crime"] + panel["unknown_time"]
    )
    if not crime_identity.all() or not time_identity.all():
        raise RuntimeError("Outcome identities failed")
    panel.to_csv(DATA / "nyc_stacked_grid_panel.csv", index=False, encoding="utf-8-sig")

    grids = gpd.GeoDataFrame(
        {"grid_id": list(grid_geometries), "geometry": list(grid_geometries.values())},
        crs=32618,
    ).to_crs(4326)
    (DATA / "nyc_analysis_grids.geojson").write_text(
        grids.to_json(drop_id=True), encoding="utf-8"
    )

    unit_counts = panel.groupby("park_id")["stack_unit_id"].nunique()
    overlap_rows = []
    for _, row in panel.loc[panel["event_time"].eq(0)].iterrows():
        cell = grid_geometries[row["grid_id"]]
        focal = row["park_id"]
        period = int(row["half_index"])
        competing = []
        for other_id, other_geometry in event_geometries.items():
            if other_id == focal or event_opening[other_id] > period:
                continue
            distance = float(cell.distance(other_geometry))
            if distance <= SUPPORT_M:
                competing.append({"park_id": other_id, "distance_m": distance})
        overlap_rows.append(
            {
                "park_id": focal,
                "grid_id": row["grid_id"],
                "open_period_competing_park_count": len(competing),
                "competing_parks": json.dumps(competing),
            }
        )
    overlap = pd.DataFrame(overlap_rows)
    overlap.to_csv(
        ARTIFACTS / "cross_park_exposure_audit.csv", index=False, encoding="utf-8-sig"
    )

    audit = {
        "rows": int(len(panel)),
        "parks": int(panel["park_id"].nunique()),
        "unique_grids": int(panel["grid_id"].nunique()),
        "stack_units": int(panel["stack_unit_id"].nunique()),
        "periods_per_complete_stack": 2 * WINDOW + 1,
        "min_units_per_stack": int(unit_counts.min()),
        "max_units_per_stack": int(unit_counts.max()),
        "assigned_case_stack_rows": int(assigned),
        "unassigned_case_stack_rows": int(outside_grid),
        "crime_identity_pass": bool(crime_identity.all()),
        "time_identity_pass": bool(time_identity.all()),
        "grid_size_m": GRID_M,
        "support_m": SUPPORT_M,
        "cross_park_contaminated_opening_cells_share": float(
            overlap["open_period_competing_park_count"].gt(0).mean()
        ),
    }
    for outcome in ["total_crime", "theft", "non_theft", "day_crime", "night_crime"]:
        audit[f"{outcome}_nonzero_share"] = float(panel[outcome].gt(0).mean())
        always_zero = panel.groupby("stack_unit_id")[outcome].sum().eq(0)
        audit[f"{outcome}_always_zero_unit_share"] = float(always_zero.mean())
    (ARTIFACTS / "panel_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
