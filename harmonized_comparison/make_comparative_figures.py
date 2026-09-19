from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

CITY_LABELS = {"SH": "Shanghai", "NYC": "New York City"}
OUTCOME_LABELS = {
    "total_crime": "Total crime",
    "theft": "Theft / larceny",
    "non_theft": "Non-theft",
    "day_crime": "Daytime crime",
    "night_crime": "Nighttime crime",
}
OUTCOME_ORDER = list(OUTCOME_LABELS)
COLORS = {"SH": "#1F5A75", "NYC": "#B65A3A"}
MARKERS = {"SH": "o", "NYC": "s"}


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "grid.color": "#D7DCE1",
            "grid.linewidth": 0.65,
            "grid.alpha": 0.75,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def read_numeric(path: Path, columns: list[str]) -> pd.DataFrame:
    data = pd.read_csv(path)
    for column in columns:
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def save_figure(fig: plt.Figure, filename: str) -> None:
    fig.savefig(FIGURES / filename, dpi=360, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def static_city_comparison() -> None:
    data = read_numeric(
        RESULTS / "city_specific_static_ppml.csv",
        ["estimate", "std_error", "p_value"],
    )
    data = data[
        (data["sample"] == "core")
        & (data["vcov"] == "grid")
        & data["outcome"].isin(OUTCOME_ORDER)
    ].copy()
    designs = [
        ("continuous_park_opening_ppml", "Continuous distance-decayed exposure"),
        ("binary_park_opening_ppml", "Within 500 m after opening"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.45, 3.7), sharey=True)
    base_y = np.arange(len(OUTCOME_ORDER))[::-1]
    offsets = {"SH": 0.12, "NYC": -0.12}

    for axis, (design, panel_label) in zip(axes, designs):
        subset = data[data["design"] == design]
        axis.axvline(0, color="#404040", linewidth=0.85)
        for city in ["SH", "NYC"]:
            rows = subset[subset["city_code"] == city].set_index("outcome").loc[OUTCOME_ORDER]
            y = base_y + offsets[city]
            estimate = rows["estimate"].to_numpy()
            error = 1.96 * rows["std_error"].to_numpy()
            axis.errorbar(
                estimate,
                y,
                xerr=error,
                fmt=MARKERS[city],
                markersize=4.8,
                color=COLORS[city],
                ecolor=COLORS[city],
                elinewidth=1.1,
                capsize=2.2,
                label=CITY_LABELS[city],
                zorder=3,
            )
        axis.set_title(panel_label, pad=8, fontweight="bold")
        axis.set_xlabel("PPML coefficient")
        axis.grid(axis="x")
        axis.set_ylim(-0.55, len(OUTCOME_ORDER) - 0.45)
    axes[0].set_yticks(base_y)
    axes[0].set_yticklabels([OUTCOME_LABELS[item] for item in OUTCOME_ORDER])
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.025))
    fig.subplots_adjust(bottom=0.20, wspace=0.12)
    save_figure(fig, "figure_1_static_city_comparison.png")
    data.to_csv(FIGURES / "figure_1_static_city_comparison_data.csv", index=False)


def long_dynamic_comparison() -> None:
    data = read_numeric(
        RESULTS / "dynamic_event_study_long_m3_p3.csv",
        ["event_time", "estimate", "std_error", "p_value"],
    )
    data = data[
        (data["treatment_type"] == "continuous")
        & data["outcome"].isin(["total_crime", "night_crime"])
    ].copy()
    reference = pd.DataFrame(
        [
            {
                "city_code": city,
                "outcome": outcome,
                "treatment_type": "continuous",
                "event_time": -1,
                "estimate": 0.0,
                "std_error": np.nan,
                "p_value": np.nan,
            }
            for city in ["SH", "NYC"]
            for outcome in ["total_crime", "night_crime"]
        ]
    )
    plot_data = pd.concat([data, reference], ignore_index=True)
    fig, axes = plt.subplots(1, 2, figsize=(7.45, 3.6))
    offsets = {"SH": -0.045, "NYC": 0.045}

    for axis, outcome in zip(axes, ["total_crime", "night_crime"]):
        axis.axhline(0, color="#404040", linewidth=0.85)
        axis.axvline(-0.5, color="#7F7F7F", linestyle=(0, (4, 3)), linewidth=0.9)
        for city in ["SH", "NYC"]:
            rows = plot_data[
                (plot_data["city_code"] == city) & (plot_data["outcome"] == outcome)
            ].sort_values("event_time")
            x = rows["event_time"].to_numpy(dtype=float) + offsets[city]
            y = rows["estimate"].to_numpy(dtype=float)
            se = rows["std_error"].to_numpy(dtype=float)
            axis.plot(x, y, color=COLORS[city], linewidth=1.45, zorder=2)
            valid = np.isfinite(se)
            axis.errorbar(
                x[valid],
                y[valid],
                yerr=1.96 * se[valid],
                fmt=MARKERS[city],
                color=COLORS[city],
                ecolor=COLORS[city],
                markersize=4.6,
                elinewidth=1.0,
                capsize=2.2,
                label=CITY_LABELS[city],
                zorder=3,
            )
            ref = rows[rows["event_time"] == -1]
            axis.scatter(
                ref["event_time"] + offsets[city],
                ref["estimate"],
                s=28,
                facecolor="white",
                edgecolor=COLORS[city],
                linewidth=1.2,
                zorder=4,
            )
        axis.set_title(OUTCOME_LABELS[outcome], pad=8, fontweight="bold")
        axis.set_xlabel("Six-month event time")
        axis.set_xticks(range(-3, 4))
        axis.grid(axis="both")
    axes[0].set_ylabel("PPML coefficient")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.025))
    fig.subplots_adjust(bottom=0.20, wspace=0.18)
    save_figure(fig, "figure_2_long_dynamic_event_study.png")
    plot_data.to_csv(FIGURES / "figure_2_long_dynamic_event_study_data.csv", index=False)


def outcome_support_comparison() -> None:
    data = read_numeric(
        RESULTS / "outcome_support_diagnostics.csv",
        ["all_zero_stack_unit_share", "nonzero_observation_share"],
    )
    fig, axes = plt.subplots(1, 2, figsize=(7.45, 3.65), sharey=True)
    base_y = np.arange(len(OUTCOME_ORDER))[::-1]
    offsets = {"SH": 0.10, "NYC": -0.10}
    metrics = [
        ("all_zero_stack_unit_share", "Always-zero stack-units"),
        ("nonzero_observation_share", "Nonzero observations"),
    ]

    for axis, (metric, panel_label) in zip(axes, metrics):
        for city in ["SH", "NYC"]:
            rows = data[data["city_code"] == city].set_index("outcome").loc[OUTCOME_ORDER]
            values = 100 * rows[metric].to_numpy()
            axis.scatter(
                values,
                base_y + offsets[city],
                s=28,
                marker=MARKERS[city],
                color=COLORS[city],
                label=CITY_LABELS[city],
                zorder=3,
            )
        axis.set_title(panel_label, pad=8, fontweight="bold")
        axis.set_xlabel("Share (%)")
        axis.set_xlim(0, 100)
        axis.grid(axis="x")
        axis.set_ylim(-0.55, len(OUTCOME_ORDER) - 0.45)
    axes[0].set_yticks(base_y)
    axes[0].set_yticklabels([OUTCOME_LABELS[item] for item in OUTCOME_ORDER])
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.025))
    fig.subplots_adjust(bottom=0.20, wspace=0.12)
    save_figure(fig, "figure_3_outcome_support_comparison.png")
    data.to_csv(FIGURES / "figure_3_outcome_support_comparison_data.csv", index=False)


def leave_one_event_out_stability() -> None:
    frames = []
    for window, filename in [
        ("Short window", "leave_one_event_out.csv"),
        ("Long window", "leave_one_event_out_long_m3_p3.csv"),
    ]:
        data = read_numeric(RESULTS / filename, ["estimate", "std_error", "p_value"])
        data = data[
            (data["design"] == "continuous_park_opening_ppml")
            & (data["vcov"] == "grid")
            & data["outcome"].isin(["total_crime", "night_crime"])
        ].copy()
        data["window"] = window
        frames.append(data)
    plot_data = pd.concat(frames, ignore_index=True)
    fig, axes = plt.subplots(1, 2, figsize=(7.45, 3.55), sharey=False)
    rng = np.random.default_rng(20260808)
    x_positions = {
        ("Short window", "SH"): 0,
        ("Short window", "NYC"): 1,
        ("Long window", "SH"): 2.4,
        ("Long window", "NYC"): 3.4,
    }

    for axis, outcome in zip(axes, ["total_crime", "night_crime"]):
        axis.axhline(0, color="#404040", linewidth=0.85)
        subset = plot_data[plot_data["outcome"] == outcome]
        for (window, city), x in x_positions.items():
            values = subset[(subset["window"] == window) & (subset["city_code"] == city)][
                "estimate"
            ].dropna()
            jitter = rng.uniform(-0.08, 0.08, len(values))
            axis.scatter(
                np.full(len(values), x) + jitter,
                values,
                s=20,
                alpha=0.72,
                color=COLORS[city],
                marker=MARKERS[city],
                zorder=2,
            )
            if len(values):
                axis.plot([x - 0.15, x + 0.15], [values.mean(), values.mean()], color="#202020", linewidth=1.5)
        axis.axvline(1.7, color="#B0B0B0", linewidth=0.8)
        axis.set_title(OUTCOME_LABELS[outcome], pad=8, fontweight="bold")
        axis.set_xticks([0.5, 2.9])
        axis.set_xticklabels(["Short window", "Long window"])
        axis.set_xlabel("One focal park omitted per estimate")
        axis.grid(axis="y")
    axes[0].set_ylabel("PPML coefficient")
    legend_handles = [
        plt.Line2D([], [], marker=MARKERS[city], color=COLORS[city], linestyle="None", label=CITY_LABELS[city])
        for city in ["SH", "NYC"]
    ]
    fig.legend(legend_handles, [item.get_label() for item in legend_handles], loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.035))
    fig.subplots_adjust(bottom=0.22, wspace=0.22)
    save_figure(fig, "figure_4_leave_one_event_out_stability.png")
    plot_data.to_csv(FIGURES / "figure_4_leave_one_event_out_stability_data.csv", index=False)


def main() -> None:
    configure_style()
    static_city_comparison()
    long_dynamic_comparison()
    outcome_support_comparison()
    leave_one_event_out_stability()
    captions = {
        "figure_1_static_city_comparison.png": (
            "City-specific short-window PPML estimates using all 11 Shanghai and 9 NYC events. Points are coefficients "
            "and whiskers are 95% confidence intervals using grid-clustered standard errors."
        ),
        "figure_2_long_dynamic_event_study.png": (
            "Long-window continuous-exposure event-study estimates using 6 Shanghai and 9 NYC events with complete "
            "[-3,+3] support. The omitted six-month period immediately before opening is normalized to zero; whiskers "
            "are 95% confidence intervals using grid-clustered standard errors."
        ),
        "figure_3_outcome_support_comparison.png": (
            "Outcome support in the harmonized short-window panels. The contrast reflects both underlying case density "
            "and the different administrative stages represented by Shanghai judgments and NYC complaints."
        ),
        "figure_4_leave_one_event_out_stability.png": (
            "Leave-one-event-out continuous-exposure estimates. The short window contains 11 Shanghai and 9 NYC events; "
            "the long window contains 6 and 9. Each point omits one focal park; horizontal bars mark the mean across omissions."
        ),
    }
    (FIGURES / "captions.json").write_text(json.dumps(captions, indent=2), encoding="utf-8")
    print(json.dumps({"figures": list(captions), "output_dir": str(FIGURES)}, indent=2))


if __name__ == "__main__":
    main()
