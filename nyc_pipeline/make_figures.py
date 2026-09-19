from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = ROOT / "raw"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

BLUE = "#1F5A7A"
ORANGE = "#C45D2C"
GREEN = "#2F6B4F"
PALE_GREEN = "#D8E7DC"
GRID = "#D7DEE5"

plt.rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#333333",
        "axes.linewidth": 0.8,
        "xtick.color": "#333333",
        "ytick.color": "#333333",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


LABELS = {
    "total_crime": "Total crime",
    "theft": "Theft",
    "non_theft": "Non-theft",
    "day_crime": "Day crime",
    "night_crime": "Night crime",
}


def comparison_figure() -> None:
    frame = pd.read_csv(RESULTS / "shanghai_nyc_comparison.csv")
    order = ["total_crime", "theft", "non_theft", "day_crime", "night_crime"]
    ybase = np.arange(len(order))[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for city, offset, color, marker in [
        ("Shanghai", 0.11, ORANGE, "s"),
        ("New York City", -0.11, BLUE, "o"),
    ]:
        city_frame = frame.loc[frame["city"].eq(city)].set_index("outcome").loc[order]
        estimates = city_frame["estimate"].to_numpy()
        errors = 1.96 * city_frame["std_error"].to_numpy()
        ax.errorbar(
            estimates,
            ybase + offset,
            xerr=errors,
            fmt=marker,
            color=color,
            ecolor=color,
            markersize=5.5,
            elinewidth=1.2,
            capsize=3,
            label=city,
        )
    ax.axvline(0, color="#555555", linewidth=0.9)
    ax.set_yticks(ybase)
    ax.set_yticklabels([LABELS[item] for item in order])
    ax.set_xlabel("PPML coefficient (lambda = 500)")
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIGURES / "shanghai_nyc_ppml_comparison.png", dpi=350, bbox_inches="tight")
    plt.close(fig)


def event_study_figure() -> None:
    frame = pd.read_csv(RESULTS / "nyc_event_study.csv")
    order = ["total_crime", "theft", "non_theft", "day_crime", "night_crime"]
    fig, axes = plt.subplots(2, 3, figsize=(10.2, 6.1))
    axes = axes.flatten()
    for ax, outcome in zip(axes, order):
        subset = frame.loc[frame["outcome"].eq(outcome)].copy()
        reference = pd.DataFrame(
            {"event_time": [-1], "estimate": [0.0], "std_error": [0.0]}
        )
        subset = pd.concat([subset, reference], ignore_index=True).sort_values("event_time")
        x = subset["event_time"].to_numpy()
        y = subset["estimate"].to_numpy()
        error = 1.96 * subset["std_error"].fillna(0).to_numpy()
        ax.plot(x, y, color=BLUE, marker="o", linewidth=1.6, markersize=4.8)
        ax.errorbar(x, y, yerr=error, fmt="none", ecolor="#79A6C5", capsize=3, linewidth=1.0)
        ax.scatter([-1], [0], s=36, facecolor="white", edgecolor=BLUE, linewidth=1.4, zorder=4)
        ax.axhline(0, color="#555555", linewidth=0.8)
        ax.axvline(-0.5, color="#888888", linestyle=(0, (4, 3)), linewidth=0.9)
        ax.grid(color=GRID, linewidth=0.65)
        ax.set_xticks(range(-3, 4))
        ax.set_title(LABELS[outcome], fontsize=11, fontweight="bold", pad=5)
    axes[-1].axis("off")
    fig.supxlabel("Half-year event time relative to park opening", y=0.02)
    fig.supylabel("PPML coefficient", x=0.02)
    fig.tight_layout(rect=(0.035, 0.04, 1, 1))
    fig.savefig(FIGURES / "nyc_dynamic_event_study.png", dpi=350, bbox_inches="tight")
    plt.close(fig)


def map_figure() -> None:
    borough_path = RAW / "nyc_borough_boundaries.geojson"
    if not borough_path.exists():
        response = requests.get(
            "https://data.cityofnewyork.us/resource/gthc-hcne.geojson?$limit=10",
            timeout=120,
            headers={"User-Agent": "Shanghai-NYC-comparative-research/1.0"},
        )
        response.raise_for_status()
        borough_path.write_bytes(response.content)

    boroughs = gpd.GeoDataFrame.from_features(
        json.loads(borough_path.read_text(encoding="utf-8"))["features"], crs=4326
    )
    all_parks = gpd.GeoDataFrame.from_features(
        json.loads((RAW / "nyc_parks_properties.geojson").read_text(encoding="utf-8"))["features"],
        crs=4326,
    )
    focal = gpd.GeoDataFrame.from_features(
        json.loads((DATA / "nyc_opening_parks.geojson").read_text(encoding="utf-8"))["features"],
        crs=4326,
    )
    focal = focal.loc[focal["eligible_main"].astype(bool)].copy()
    grids = gpd.GeoDataFrame.from_features(
        json.loads((DATA / "nyc_analysis_grids.geojson").read_text(encoding="utf-8"))["features"],
        crs=4326,
    )

    fig, ax = plt.subplots(figsize=(7.4, 7.4))
    boroughs.plot(ax=ax, facecolor="#F7F7F5", edgecolor="#666666", linewidth=0.65)
    all_parks.plot(ax=ax, facecolor=PALE_GREEN, edgecolor="none", alpha=0.9)
    grids.boundary.plot(ax=ax, color="#6F8FA8", linewidth=0.28, alpha=0.7)
    focal.plot(ax=ax, facecolor=GREEN, edgecolor="#1E4934", linewidth=0.8, zorder=4)
    for index, row in focal.reset_index(drop=True).iterrows():
        point = row.geometry.representative_point()
        ax.text(
            point.x,
            point.y,
            str(index + 1),
            ha="center",
            va="center",
            fontsize=7.5,
            color="white",
            fontweight="bold",
            zorder=5,
        )
    ax.set_xlim(-74.28, -73.68)
    ax.set_ylim(40.48, 40.94)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.tight_layout(pad=0.1)
    fig.savefig(FIGURES / "nyc_focal_parks_and_analysis_grids.png", dpi=400, bbox_inches="tight")
    plt.close(fig)


def opening_timeline() -> None:
    frame = pd.read_csv(DATA / "nyc_park_opening_ledger.csv")
    frame = frame.loc[frame["eligible_main"].astype(bool)].copy()
    frame["opening_date"] = pd.to_datetime(frame["opening_date"])
    frame = frame.sort_values("opening_date")
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    y = np.arange(len(frame))[::-1]
    ax.hlines(y, pd.Timestamp("2010-01-01"), frame["opening_date"], color=GRID, linewidth=1.0)
    ax.scatter(frame["opening_date"], y, color=GREEN, s=32, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(frame["park_name"])
    ax.set_xlim(pd.Timestamp("2009-09-01"), pd.Timestamp("2020-03-01"))
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_xlabel("Official opening date")
    fig.tight_layout()
    fig.savefig(FIGURES / "nyc_focal_park_opening_timeline.png", dpi=350, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    comparison_figure()
    event_study_figure()
    map_figure()
    opening_timeline()
    print("created", len(list(FIGURES.glob("*.png"))), "figures")
