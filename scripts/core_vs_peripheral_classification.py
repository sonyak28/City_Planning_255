"""
scripts/core_vs_peripheral_classification.py
============================================
Build the FY2025 BART + Caltrain ridership table, classify stations as
core or peripheral, generate visualisations, and write output CSVs.

Data sources
------------
BART     : ../data/raw/bart_stations_ridership.csv
           (manually compiled from BART monthly XLS, Jul 2024 – Jun 2025)
Caltrain : hardcoded AMWR values from Table 3 of the FY2025 Annual Ridership
           Report (caltrain.com/media/35885, Sep 2025)

Outputs (../data/processed/)
-----------------------------
ridership_raw_fy2025.csv
classification_results_fy2025.csv

Outputs (../visualizations/)
-----------------------------
ridership_distribution_fy2025.png
ridership_bar_fy2025.png

Usage
-----
Run from the scripts/ (or code/) directory:
    python core_vs_peripheral_classification.py
"""

import os
import warnings

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Import classification logic from src/
from transit_equity.classify import run_all_classifications

warnings.filterwarnings("ignore")

OUTPUT_DIR     = "../data/processed"
OUTPUT_VIZ_DIR = "../visualizations"
os.makedirs(OUTPUT_DIR,     exist_ok=True)
os.makedirs(OUTPUT_VIZ_DIR, exist_ok=True)

BART_CSV_PATH = "../data/raw/bart_stations_ridership.csv"

COLORS = {
    "core":       "#2563EB",
    "peripheral": "#D1D5DB",
    "BART":       "#F59E0B",
    "Caltrain":   "#10B981",
}

# Caltrain FY2025 AMWR — hardcoded fallback values (Table 3)

CALTRAIN_FY2025_AMWR: dict[str, float] = {
    "San Francisco":       6874,
    "22nd Street":         1261,
    "Bayshore":             168,
    "South San Francisco":  692,
    "San Bruno":            377,
    "Millbrae":            1489,
    "Broadway":              91,
    "Burlingame":           620,
    "San Mateo":           1270,
    "Hayward Park":         366,
    "Hillsdale":           1596,
    "Belmont":              654,
    "San Carlos":           644,
    "Redwood City":        2111,
    "Menlo Park":           863,
    "Palo Alto":           3603,
    "California Ave":       817,
    "Stanford":           np.nan,
    "San Antonio":          655,
    "Mountain View":       2288,
    "Sunnyvale":           1770,
    "Lawrence":             686,
    "Santa Clara":          839,
    "College Park":          41,
    "San Jose Diridon":    2136,
    "Tamien":               243,
    "Capitol":               49,
    "Blossom Hill":          71,
    "Morgan Hill":          130,
    "San Martin":            25,
    "Gilroy":               110,
}


# SECTION 1 — BART data

def fetch_bart_fy2025() -> pd.DataFrame:
    """Load BART FY2025 average weekday exits from manually compiled CSV."""
    print("Loading BART FY2025 ridership data from CSV")
    df = pd.read_csv(BART_CSV_PATH, encoding="latin1")
    df = df.rename(columns={
        "Station Name":        "station",
        "Average Weekday Exit": "avg_weekday_exits",
    })
    df = df[["station", "avg_weekday_exits"]].dropna(subset=["avg_weekday_exits"])
    df["agency"]            = "BART"
    df["metric"]            = "avg_weekday_exits"
    df["avg_weekday_exits"] = pd.to_numeric(df["avg_weekday_exits"], errors="coerce")
    print(f"Loaded {len(df)} BART stations from {BART_CSV_PATH}")
    return df


# SECTION 2 — Caltrain data

def load_caltrain_fy2025() -> pd.DataFrame:
    """
    Return Caltrain FY2025 AMWR values from Table 3 of the official
    FY2025 Annual Ridership Report (caltrain.com/media/35885, Sep 2025).
    All 31 stations included; Stanford excluded (special events only, no data).
    """
    df = pd.DataFrame([
        {"station": stn, "avg_weekday_exits": amwr}
        for stn, amwr in CALTRAIN_FY2025_AMWR.items()
    ])
    assert len(df) == 31, f"Expected 31 Caltrain stations, got {len(df)}"
    df["agency"] = "Caltrain"
    df["metric"] = "avg_mid_week_ridership_AMWR"
    print(f"Loaded {len(df)} Caltrain stations (hardcoded FY2025 AMWR values).")
    return df


# SECTION 3 — Merge & clean

def build_ridership_table() -> pd.DataFrame:
    """Combine BART and Caltrain ridership into one sorted DataFrame."""
    bart_df     = fetch_bart_fy2025()
    caltrain_df = load_caltrain_fy2025()

    combined = pd.concat([bart_df, caltrain_df], ignore_index=True)
    combined = combined[combined["avg_weekday_exits"] > 0].dropna(
        subset=["avg_weekday_exits"]
    )
    combined["avg_weekday_exits"]  = combined["avg_weekday_exits"].astype(int)
    combined["avg_weekly_ridership"] = combined["avg_weekday_exits"] * 5
    combined["avg_annual_ridership"] = combined["avg_weekday_exits"] * 260
    combined = combined.sort_values(
        "avg_weekday_exits", ascending=False
    ).reset_index(drop=True)
    combined["rank"] = combined.index + 1

    n_bart = (combined.agency == "BART").sum()
    n_ct   = (combined.agency == "Caltrain").sum()
    print(f"\nCombined FY2025 table: {len(combined)} stations "
          f"({n_bart} BART, {n_ct} Caltrain)")
    return combined


# SECTION 4 — Visualisations

def _get_boundary(df: pd.DataFrame, col: str) -> float:
    core = df[df[col] == "core"]["avg_weekday_exits"]
    peri = df[df[col] == "peripheral"]["avg_weekday_exits"]
    if col == "method_percentile":
        return df["avg_weekday_exits"].quantile(0.50)
    if col == "method_kmeans":
        return (core.mean() + peri.mean()) / 2
    # jenks
    try:
        import jenkspy
        return jenkspy.jenks_breaks(
            df["avg_weekday_exits"].values.tolist(), n_classes=2
        )[1]
    except Exception:
        sorted_vals = np.sort(df["avg_weekday_exits"].values)
        return sorted_vals[np.argmax(np.diff(sorted_vals)) + 1]


def plot_distribution(df: pd.DataFrame) -> None:
    """Four-panel histogram showing each classification boundary."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "FY2025 Station Ridership Distribution — Core/Peripheral Boundaries",
        fontsize=13, fontweight="bold", y=1.01,
    )
    methods = [
        ("method_percentile", "1. Percentile (top 50%)"),
        ("method_kmeans",     "3. K-means (2 clusters)"),
        ("method_jenks",      "4. Natural Breaks (Jenks)"),
    ]
    for ax, (col, title) in zip(axes.flatten(), methods):
        ax.hist(
            df[df[col] == "peripheral"]["avg_weekday_exits"],
            bins=20, color=COLORS["peripheral"], edgecolor="white", label="Peripheral",
        )
        ax.hist(
            df[df[col] == "core"]["avg_weekday_exits"],
            bins=20, color=COLORS["core"], edgecolor="white", alpha=0.85, label="Core",
        )
        boundary = _get_boundary(df, col)
        ax.axvline(
            boundary, color="crimson", linestyle="--",
            linewidth=1.8, label=f"Boundary: {boundary:,.0f}",
        )
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("Avg Weekday Ridership")
        ax.set_ylabel("# Stations")
        ax.legend(fontsize=8)
    plt.tight_layout()
    path = os.path.join(OUTPUT_VIZ_DIR, "ridership_distribution_fy2025.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_ridership_bar(df: pd.DataFrame) -> None:
    """Horizontal bar chart ranked by ridership, coloured by consensus label."""
    df_s = df.sort_values("avg_weekday_exits", ascending=True)
    fig_h = max(10, len(df_s) * 0.27)
    fig, ax = plt.subplots(figsize=(11, fig_h))

    bars = ax.barh(
        df_s["station"], df_s["avg_weekday_exits"],
        color=df_s["consensus"].map(COLORS),
        edgecolor="white", height=0.75,
    )
    for bar, (_, row) in zip(bars, df_s.iterrows()):
        marker = "●" if row["agency"] == "BART" else "▲"
        ax.text(
            bar.get_width() + 80,
            bar.get_y() + bar.get_height() / 2,
            marker, va="center", fontsize=7, color=COLORS[row["agency"]],
        )

    ax.set_xlabel("Avg Weekday Ridership (FY2025)", fontsize=10)
    ax.set_title(
        "Bay Area Transit — FY2025 Station Ridership\n"
        "(Consensus: Core vs Peripheral)",
        fontweight="bold",
    )
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    legend_patches = [
        mpatches.Patch(color=COLORS["core"],       label="Core"),
        mpatches.Patch(color=COLORS["peripheral"], label="Peripheral"),
        mpatches.Patch(color=COLORS["BART"],       label="● BART (avg weekday exits)"),
        mpatches.Patch(color=COLORS["Caltrain"],   label="▲ Caltrain (AMWR Tue-Thu)"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8)
    plt.tight_layout()
    path = os.path.join(OUTPUT_VIZ_DIR, "ridership_bar_fy2025.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# SECTION 5 — Save outputs

def save_outputs(df: pd.DataFrame) -> None:
    raw_cols = [
        c for c in
        ["station", "agency", "metric", "avg_weekday_exits",
         "avg_weekly_ridership", "avg_annual_ridership", "rank"]
        if c in df.columns
    ]
    df[raw_cols].to_csv(
        os.path.join(OUTPUT_DIR, "ridership_raw_fy2025.csv"), index=False
    )
    print("  Saved: ridership_raw_fy2025.csv")

    class_cols = [
        c for c in
        ["station", "agency", "metric", "avg_weekday_exits", "rank",
         "method_percentile", "method_kmeans", "method_jenks",
         "core_votes", "consensus"]
        if c in df.columns
    ]
    df[class_cols].to_csv(
        os.path.join(OUTPUT_DIR, "classification_results_fy2025.csv"), index=False
    )
    print("  Saved: classification_results_fy2025.csv")


# SECTION 6 — Summary table

def print_summary(df: pd.DataFrame) -> None:
    method_cols = ["method_percentile", "method_kmeans", "method_jenks", "consensus"]
    print("\n" + "=" * 95)
    print("FY2025 STATION CLASSIFICATION RESULTS")
    print("=" * 95)
    print(
        f"{'#':>3}  {'Station':<36} {'Agency':<9} {'Metric':<7} {'Value':>7}"
        f"  {'Pct':^5}{'KMn':^5}{'Jnk':^5} │ {'Vote':>4} {'Consensus':^12}"
    )
    print("─" * 95)
    for _, row in df.sort_values("avg_weekday_exits", ascending=False).iterrows():
        metric_abbr = "AMWR" if str(row.get("metric", "")).startswith("avg_mid") else "AWE"
        vals = [("C" if row[m] == "core" else "p") for m in method_cols[:-1]]
        print(
            f"{int(row['rank']):>3}  {row['station']:<36} {row['agency']:<9} "
            f"{metric_abbr:<7} {int(row['avg_weekday_exits']):>7,}"
            f"  {'  '.join(vals)}    │ {int(row['core_votes']):>4}  {row['consensus']:^12}"
        )
    print("─" * 95)
    print(
        "Key: C=core  p=peripheral │ "
        "AWE=BART Avg Weekday Exits │ AMWR=Caltrain Avg Mid-Week Ridership\n"
        "Consensus: ≥2 of 3 methods → CORE"
    )


# Main

def main() -> None:
    print("=" * 65)
    print("Bay Area Transit FY2025 Station Classification Pipeline")
    print("Fiscal Year 2025: July 2024 – June 2025")
    print("=" * 65)

    df = build_ridership_table()
    df = run_all_classifications(df)   # ← from transit_equity.classify
    print_summary(df)

    print("\nGenerating visualisations…")
    plot_distribution(df)
    plot_ridership_bar(df)

    print("\nSaving CSVs…")
    save_outputs(df)

    print("\nDone!")


if __name__ == "__main__":
    main()
