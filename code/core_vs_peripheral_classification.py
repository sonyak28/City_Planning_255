"""
Bay Area Transit Station Ridership Pipeline & Core/Peripheral Classification
Data from FY2025 Edition (July 2024 - June 2025)
============================================================================

  BART (FY2025 = Jul 2024 - Jun 2025)
  ─────────────────────────────────────
  Source: Monthly Ridership Snapshot PDFs, bart.gov/about/reports/ridership
  Metric: Average Weekday Exits (station-level, reported in each monthly PDF)
  URL pattern: https://www.bart.gov/sites/default/files/{YYYY-MM}/{YYYYMM}%20Monthly%20Ridership%20Snapshot.pdf

  Caltrain (FY2025 = Jul 2024 - Jun 2025)
  ─────────────────────────────────────────
  Source: FY2025 Annual Ridership Report, Table 3 (Average Mid-Week Ridership
          by Origin Station), caltrain.com/media/35885
  Metric: Average Mid-Week Ridership (AMWR) — average of Tue/Wed/Thu boardings,
          which avoids Monday/Friday commute anomalies.


Usage:
  python bay_area_transit_classification_fy2025.py

Outputs (written to ./output/):
  ridership_raw_fy2025.csv            — cleaned merged table with source metadata
  classification_results_fy2025.csv  — all four labels + consensus per station
  # classification_disagreements_fy2025.csv — borderline stations
  ridership_distribution_fy2025.png  — histogram with boundary overlays
  # classification_comparison_fy2025.png — heatmap comparing all methods
  ridership_bar_fy2025.png           — ranked bar chart coloured by consensus
"""

import io
import os
import zipfile
import warnings
import requests
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from scipy import stats
from sklearn.cluster import KMeans

warnings.filterwarnings("ignore")
OUTPUT_DIR = "./output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1 — BART DATA  (FY2025: Jul 2024 – Jun 2025)
# ──────────────────────────────────────────────────────────────────────────────
#
# BART ridership csv was manually created from "Average Weekday Exits by Station" XLS on 
# https://www.bart.gov/about/reports/ridership as we were unable to parse the pdf document
# shared on the same site.
# We used XLS from July 2024 to Jun 2025


bart_csv_path = "../City_Planning_255/data/bart_stations_ridership.csv"

def fetch_bart_fy2025():
    """
    Load BART FY2025 average weekday exits from manually compiled CSV.
    
    Returns:
        - result (DataFrame)
    
    """
    print("Loading BART FY2025 ridership data from CSV")
    df = pd.read_csv(bart_csv_path, encoding="latin1")

    df = df.rename(columns = {
        "Station Name" : "station",
        "Average Weekday Exit" : "avg_weekday_exits"
    })

    result = df[['station', 'avg_weekday_exits']].dropna(subset=['avg_weekday_exits'])
    result['agency'] = "BART"
    result['metric'] = 'avg_weekday_exits'
    result["avg_weekday_exits"] = pd.to_numeric(result["avg_weekday_exits"], errors="coerce")

    print(f"Loaded {len(result)} BART stations from {bart_csv_path}")
    return result

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2 — CALTRAIN DATA  (FY2025: Jul 2024 – Jun 2025)
# ──────────────────────────────────────────────────────────────────────────────
# Table 3 from the FY2025 Annual Ridership Report (caltrain.com/media/35885)
# "Average Mid-Week Ridership by Origin Station"
# AMWR = average of Tuesday, Wednesday, Thursday boardings across FY2025.
# All 31 Caltrain stations included:
#   29 daily + Broadway (weekend-only) + Stanford (special events only).

CALTRAIN_FY2025_AMWR = {
    "San Francisco":       6874,
    "22nd Street":         1261,
    "Bayshore":             168,
    "South San Francisco":  692,
    "San Bruno":            377,
    "Millbrae":            1489,
    "Broadway":              91, # weekend only
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
    "Stanford":          np.nan, # No data (open only for special events)
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


def fetch_caltrain_fy2025() -> pd.DataFrame:
    """
    Parse Caltrain FY2025 AMWR by station from the official PDF.
    Fall back to the hardcoded Table 3 values if PDF parsing fails.

    Source: caltrain.com/media/35885 (FY2025 Annual Ridership Report, Table 3)

    Returns:
        - df (DataFrame)
    """
    print("Fetching Caltrain FY2025 Annual Ridership Report (PDF)")
    url = "https://www.caltrain.com/media/35885"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = _parse_caltrain_fy2025_pdf(resp.content)
        if df is not None and len(df) >= 30:
            print(f"Parsed {len(df)} Caltrain stations from FY2025 PDF")
            return df
        else:
            print("PDF parsed but insufficient stations found — using hardcoded values.")
    except Exception as e:
        print(f"PDF download failed ({e}) — using hardcoded FY2025 values.")

    return _caltrain_fy2025_fallback()


def _parse_caltrain_fy2025_pdf(pdf_bytes: bytes) -> pd.DataFrame | None:
    """
    Parse Table 3 "Average Mid-Week Ridership by Origin Station" from the
    Caltrain FY2025 Annual Ridership Report PDF.
    """
    rows = []
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            in_table3 = False
            for page in pdf.pages:
                text = page.extract_text() or ""
                if "Average Mid-Week Ridership by Origin Station" in text:
                    in_table3 = True
                if not in_table3:
                    continue

                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or not row[0]:
                            continue
                        station = str(row[0]).strip()
                        if not station or station.lower() in ("station", "origin station"):
                            continue
                        # Find the FY2025 AMWR column (usually first numeric col)
                        for cell in row[1:]:
                            cell_str = str(cell or "").strip().replace(",", "")
                            if re.match(r"^\d+$", cell_str) and int(cell_str) > 20:
                                rows.append({
                                    "station": station,
                                    "avg_weekday_exits": int(cell_str),
                                })
                                break

                # Also try line-by-line if table parsing missed rows
                if len(rows) < 10:
                    for line in text.split("\n"):
                        m = re.match(r"^([A-Za-z\s/\.]+?)\s{2,}([\d,]+)", line.strip())
                        if m:
                            station = m.group(1).strip()
                            val = int(m.group(2).replace(",", ""))
                            if val > 20:
                                rows.append({"station": station, "avg_weekday_exits": val})

                if len(rows) >= 20:
                    break  # Got enough rows

    except Exception as e:
        print(f"    PDF parse error: {e}")
        return None

    if not rows:
        return None

    df = pd.DataFrame(rows).drop_duplicates("station")
    df["agency"] = "Caltrain"
    df["metric"] = "avg_mid_week_ridership_AMWR"
    return df


def _caltrain_fy2025_fallback() -> pd.DataFrame:
    """
    Hardcoded Caltrain FY2025 AMWR values from Table 3 of the official
    FY2025 Annual Ridership Report (caltrain.com/media/35885, Sep 2025).
    All 31 stations included (28 daily + Broadway + College Park + Stanford).
    Atherton station closed December 2020 and is excluded.
    """
    print("Using hardcoded Caltrain FY2025 AMWR values (Table 3, all 31 stations).")
    rows = [
        {"station": stn, "avg_weekday_exits": amwr}
        for stn, amwr in CALTRAIN_FY2025_AMWR.items()
    ]
    df = pd.DataFrame(rows)
    assert len(df) == 31, f"Expected 31 Caltrain stations, got {len(df)}"
    df["agency"] = "Caltrain"
    df["metric"] = "avg_mid_week_ridership_AMWR"
    print(f"Loaded {len(df)} Caltrain stations.")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3 — MERGE & CLEAN
# ──────────────────────────────────────────────────────────────────────────────

def build_ridership_table():
    """
    Create DataFrame with BART and Caltrain Stations and their respective ridership data.

    Returns:
        - combined (DataFrame)
    """
    bart_df = fetch_bart_fy2025()
    caltrain_df = fetch_caltrain_fy2025()

    combined = pd.concat([bart_df, caltrain_df], ignore_index=True)
    combined = combined[combined["avg_weekday_exits"] > 0].dropna(subset=["avg_weekday_exits"])
    combined["avg_weekday_exits"] = combined["avg_weekday_exits"].astype(int)

    # New columns
    combined["avg_weekly_ridership"]  = combined["avg_weekday_exits"] * 5
    combined["avg_annual_ridership"]  = combined["avg_weekday_exits"] * 260

    combined = combined.sort_values("avg_weekday_exits", ascending=False).reset_index(drop=True)
    combined["rank"] = combined.index + 1

    n_bart = (combined.agency == "BART").sum()
    n_ct   = (combined.agency == "Caltrain").sum()
    print(f"\nCombined FY2025 table: {len(combined)} stations "
          f"({n_bart} BART, {n_ct} Caltrain)")
    return combined


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4 — CLASSIFICATION METHODS
# ──────────────────────────────────────────────────────────────────────────────

def classify_percentile(df, threshold = 0.50):
    """
    Classify stations above `threshold` percentile as core, otherwise peripheral. Default: top 50%.
    
    Arguments:
        - df (DataFrame)
        - threshold (float)
    
    Returns:
        - pd.Series
    """
    cutoff = df["avg_weekday_exits"].quantile(threshold)
    return (df["avg_weekday_exits"] >= cutoff).map({True: "core", False: "peripheral"})


# def classify_zscore(df, z_threshold) -> pd.Series:
#     """Classify stations with z-score >= z_threshold as core.

    
#     """
#     z = pd.Series(stats.zscore(df["avg_weekday_exits"]), index=df.index)
#     return (z >= z_threshold).map({True: "core", False: "peripheral"})


def classify_kmeans(df, n_clusters = 2, random_state = 255):
    """
    K-means on log-transformed ridership. Higher centroid cluster = core.
    
    Arguments:
        - df (DataFrame)
        - n_clusters (int)
        - random_state (int)
    Returns:
        - pd.Series
    """
    X = np.log1p(df["avg_weekday_exits"].values).reshape(-1, 1)
    km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = km.fit_predict(X)
    core_label = int(np.argmax(km.cluster_centers_.flatten()))
    return pd.Series(labels).map({core_label: "core"}).fillna("peripheral")


def classify_jenks(df):
    """
    Natural breaks: split at the single largest gap in the distribution.
    
    Arguments:
        - df (DataFrame)
    Returns:
        - pd.Series
    """
    try:
        import jenkspy
        breaks = jenkspy.jenks_breaks(df["avg_weekday_exits"].values.tolist(), n_classes=2)
        cutoff = breaks[1]
    except ImportError:
        sorted_vals = np.sort(df["avg_weekday_exits"].values)
        gaps = np.diff(sorted_vals)
        cutoff = sorted_vals[np.argmax(gaps) + 1]
    return (df["avg_weekday_exits"] >= cutoff).map({True: "core", False: "peripheral"})


def run_all_classifications(df):
    """
    Run all classification methods and pick the label with highest consensus.

    Arguments:
        - df (DataFrame)
    Returns:
        - df (DataFram)
    """
    df = df.copy()
    df["method_percentile"] = classify_percentile(df).values
    # df["method_zscore"]     = classify_zscore(df).values
    df["method_kmeans"]     = classify_kmeans(df).values
    df["method_jenks"]      = classify_jenks(df).values

    method_cols = ["method_percentile", "method_kmeans", "method_jenks"]
    df["core_votes"] = df[method_cols].apply(lambda r: sum(v == "core" for v in r), axis=1)
    df["consensus"]  = df["core_votes"].apply(lambda v: "core" if v >= 2 else "peripheral")

    print(f"\n{'Method':<26} {'Core':>6} {'Peripheral':>11} {'% Core':>8}")
    print("─" * 55)
    for col, label in zip(
        method_cols + ["consensus"],
        ["Percentile (≥50th %ile)", "K-means (2 clusters)",
         "Jenks (natural break)", "Consensus (≥2/3 methods)"]
    ):
        n_core = (df[col] == "core").sum()
        n_peri = (df[col] == "peripheral").sum()
        print(f"  {label:<24} {n_core:>6} {n_peri:>11} {100*n_core/len(df):>7.1f}%")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5 — VISUALISATIONS
# ──────────────────────────────────────────────────────────────────────────────

COLORS = {
    "core":       "#2563EB",
    "peripheral": "#D1D5DB",
    "BART":       "#F59E0B",
    "Caltrain":   "#10B981",
}


def _get_boundary(df, col):
    core = df[df[col] == "core"]["avg_weekday_exits"]
    peri = df[df[col] == "peripheral"]["avg_weekday_exits"]
    if col == "method_percentile":
        return df["avg_weekday_exits"].quantile(0.50)
    # elif col == "method_zscore":
    #     return df["avg_weekday_exits"].mean()
    elif col == "method_kmeans":
        return (core.mean() + peri.mean()) / 2
    else:  # jenks
        try:
            import jenkspy
            return jenkspy.jenks_breaks(df["avg_weekday_exits"].values.tolist(), n_classes=2)[1]
        except Exception:
            sorted_vals = np.sort(df["avg_weekday_exits"].values)
            return sorted_vals[np.argmax(np.diff(sorted_vals)) + 1]


def plot_distribution(df):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("FY2025 Station Ridership Distribution — Core/Peripheral Boundaries",
                 fontsize=13, fontweight="bold", y=1.01)

    methods = [
        ("method_percentile", "1. Percentile (top 50%)"),
       #("method_zscore",     "2. Z-score (≥ mean)"),
        ("method_kmeans",     "3. K-means (2 clusters)"),
        ("method_jenks",      "4. Natural Breaks (Jenks)"),
    ]
    for ax, (col, title) in zip(axes.flatten(), methods):
        ax.hist(df[df[col]=="peripheral"]["avg_weekday_exits"],
                bins=20, color=COLORS["peripheral"], edgecolor="white", label="Peripheral")
        ax.hist(df[df[col]=="core"]["avg_weekday_exits"],
                bins=20, color=COLORS["core"], edgecolor="white", alpha=0.85, label="Core")
        boundary = _get_boundary(df, col)
        ax.axvline(boundary, color="crimson", linestyle="--", linewidth=1.8,
                   label=f"Boundary: {boundary:,.0f}")
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("Avg Weekday Ridership")
        ax.set_ylabel("# Stations")
        ax.legend(fontsize=8)
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "ridership_distribution_fy2025.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# def plot_comparison_heatmap(df):
#     method_cols = ["method_percentile",
#                    "method_jenks", "consensus"]
#     col_labels  = ["Percentile", "Jenks", "Consensus"]

#     heat = (df.set_index("station")[method_cols]
#               .applymap(lambda v: 1 if v == "core" else 0))
#     heat = heat.loc[df.sort_values("avg_weekday_exits", ascending=False)["station"]]

#     fig_h = max(8, len(heat) * 0.27)
#     fig, ax = plt.subplots(figsize=(9, fig_h))
#     cmap = plt.matplotlib.colors.ListedColormap([COLORS["peripheral"], COLORS["core"]])
#     sns.heatmap(heat, ax=ax, cmap=cmap, linewidths=0.4, linecolor="white",
#                 cbar=False, xticklabels=col_labels, yticklabels=True)
#     ax.set_title("FY2025 Core/Peripheral Classification Comparison\n(blue = core, grey = peripheral)",
#                  fontweight="bold", pad=12)
#     ax.tick_params(axis="y", labelsize=7)
#     ax.tick_params(axis="x", labelsize=9)

#     agency_order = df.set_index("station").loc[heat.index, "agency"]
#     for i, (_, agency) in enumerate(agency_order.items()):
#         ax.add_patch(mpatches.Rectangle(
#             (len(method_cols) + 0.05, i), 0.35, 1,
#             color=COLORS[agency], clip_on=False, transform=ax.transData
#         ))

#     legend_patches = [
#         mpatches.Patch(color=COLORS["core"],       label="Core"),
#         mpatches.Patch(color=COLORS["peripheral"], label="Peripheral"),
#         mpatches.Patch(color=COLORS["BART"],       label="BART"),
#         mpatches.Patch(color=COLORS["Caltrain"],   label="Caltrain"),
#     ]
#     ax.legend(handles=legend_patches, loc="upper left",
#               bbox_to_anchor=(1.12, 1.0), fontsize=8)
#     plt.tight_layout()
#     path = os.path.join(OUTPUT_DIR, "classification_comparison_fy2025.png")
#     plt.savefig(path, dpi=150, bbox_inches="tight")
#     plt.close()
#     print(f"  Saved: {path}")


def plot_ridership_bar(df):
    df_s = df.sort_values("avg_weekday_exits", ascending=True)
    fig_h = max(10, len(df_s) * 0.27)
    fig, ax = plt.subplots(figsize=(11, fig_h))

    bars = ax.barh(df_s["station"], df_s["avg_weekday_exits"],
                   color=df_s["consensus"].map(COLORS), edgecolor="white", height=0.75)
    for bar, (_, row) in zip(bars, df_s.iterrows()):
        marker = "●" if row["agency"] == "BART" else "▲"
        ax.text(bar.get_width() + 80, bar.get_y() + bar.get_height() / 2,
                marker, va="center", fontsize=7, color=COLORS[row["agency"]])

    ax.set_xlabel("Avg Weekday Ridership (FY2025)", fontsize=10)
    ax.set_title("Bay Area Transit — FY2025 Station Ridership\n(Consensus: Core vs Peripheral)",
                 fontweight="bold")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    legend_patches = [
        mpatches.Patch(color=COLORS["core"],       label="Core"),
        mpatches.Patch(color=COLORS["peripheral"], label="Peripheral"),
        mpatches.Patch(color=COLORS["BART"],       label="● BART (avg weekday exits)"),
        mpatches.Patch(color=COLORS["Caltrain"],   label="▲ Caltrain (AMWR Tue-Thu)"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8)
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "ridership_bar_fy2025.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6 — SAVE OUTPUTS
# ──────────────────────────────────────────────────────────────────────────────

def save_outputs(df: pd.DataFrame):
    raw_cols = ["station", "agency", "metric", "avg_weekday_exits",
                "avg_weekly_ridership", "avg_annual_ridership", "rank"]
    raw_cols = [c for c in raw_cols if c in df.columns]
    df[raw_cols].to_csv(os.path.join(OUTPUT_DIR, "ridership_raw_fy2025.csv"), index=False)
    print(f"  Saved: ridership_raw_fy2025.csv")

    class_cols = ["station", "agency", "metric", "avg_weekday_exits", "rank",
                  "method_percentile", "method_kmeans",
                  "method_jenks", "core_votes", "consensus"]
    class_cols = [c for c in class_cols if c in df.columns]
    df[class_cols].to_csv(os.path.join(OUTPUT_DIR, "classification_results_fy2025.csv"), index=False)
    print(f"  Saved: classification_results_fy2025.csv")

    # mixed = df[(df["core_votes"] > 0) & (df["core_votes"] < 3)]
    # if not mixed.empty:
    #     mixed[class_cols].to_csv(
    #         os.path.join(OUTPUT_DIR, "classification_disagreements_fy2025.csv"), index=False)
    #     print(f"  Saved: classification_disagreements_fy2025.csv ({len(mixed)} borderline stations)")


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7 — SUMMARY TABLE
# ──────────────────────────────────────────────────────────────────────────────

def print_summary(df):
    method_cols = ["method_percentile",
                   "method_kmeans", "method_jenks", "consensus"]
    print("\n" + "=" * 95)
    print("FY2025 STATION CLASSIFICATION RESULTS")
    print("=" * 95)
    print(f"{'#':>3}  {'Station':<36} {'Agency':<9} {'Metric':<7} {'Value':>7}"
          f"  {'Pct':^5}{'KMn':^5}{'Jnk':^5} │ {'Vote':>4} {'Consensus':^12}")
    print("─" * 95)
    for _, row in df.sort_values("avg_weekday_exits", ascending=False).iterrows():
        metric_abbr = "AMWR" if row.get("metric", "").startswith("avg_mid") else "AWE"
        vals = [("C" if row[m] == "core" else "p") for m in method_cols[:-1]]
        print(f"{int(row['rank']):>3}  {row['station']:<36} {row['agency']:<9} {metric_abbr:<7} "
              f"{int(row['avg_weekday_exits']):>7,}"
              f"  {'  '.join(vals)}    │ {int(row['core_votes']):>4}  {row['consensus']:^12}")
    print("─" * 95)
    print("Key: C=core  p=peripheral │ AWE=BART Avg Weekday Exits │ AMWR=Caltrain Avg Mid-Week Ridership")
    print("Consensus: ≥2 of 3 methods → CORE")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("Bay Area Transit FY2025 Station Classification Pipeline")
    print("Fiscal Year 2025: July 2024 – June 2025")
    print("=" * 65)

    df = build_ridership_table()
    df = run_all_classifications(df)
    print_summary(df)

    print("\nGenerating visualisations...")
    plot_distribution(df)
    plot_comparison_heatmap(df)
    plot_ridership_bar(df)

    print("\nSaving CSVs...")
    save_outputs(df)

    print("\n Done — all outputs in ./output/")


if __name__ == "__main__":
    main()