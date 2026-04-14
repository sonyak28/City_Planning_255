"""
scripts/complete_analysis_pipeline.py
======================================
Complete transit equity analysis pipeline.

Steps
-----
1. Census tract matching  — join stations to ACS tracts via spatial join
2. Amenity access         — count amenities within half a mile of each station
3. Ridership classification — merge core/peripheral labels from FY2025 data
4. Validation             — confirm census matching via demographic sanity check
5. Statistical analysis   — permutation tests, Spearman correlations, FDR
6. Unmet-need & entropy   — composite need index and amenity-diversity scores
7. Save results           — write CSVs to ../data/processed/

Usage
-----
Run from the scripts/ (or code/) directory:
    python complete_analysis_pipeline.py
"""

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import mannwhitneyu, permutation_test
from statsmodels.stats.multitest import multipletests

# Import all reusable logic from src/
from transit_equity.amenities import build_station_amenity_records
from transit_equity.census import BAY_AREA_COUNTIES
from transit_equity.classify import apply_name_crosswalk
from transit_equity.stats import (
    add_unmet_need_index,
    amenity_entropy,
    bootstrap_gini,
    calculate_gini,
)

warnings.filterwarnings("ignore")

# Config

CENSUS_SHAPEFILE = "../data/raw/tl_2024_06_tract/tl_2024_06_tract.shp"
STATIONS_FILE    = "../data/raw/transit_gdf.csv"
AMENITIES_FILE   = "../data/raw/all_amenities.csv"
OUTPUT_DIR       = Path("../data/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXCLUDE_STATIONS = ["Stanford", "San Francisco International Airport"]

# PART 1: Census tract matching

print("=" * 90)
print("COMPLETE ANALYSIS PIPELINE WITH CORRECTED CENSUS DATA")
print("=" * 90)

print("\nPART 1: FIXING CENSUS TRACT MATCHING")
print("-" * 90)

if not Path(CENSUS_SHAPEFILE).exists():
    print(f"ERROR: Shapefile not found at {CENSUS_SHAPEFILE}")
    print("Required: Census TIGER/Line 2024 California tract boundaries")
    print("Download: https://www.census.gov/cgi-bin/geo/shapefiles/index.php")
    raise SystemExit(1)

ca_tracts  = gpd.read_file(CENSUS_SHAPEFILE)
bay_tracts = ca_tracts[
    (ca_tracts["STATEFP"] == "06") &
    (ca_tracts["COUNTYFP"].isin(BAY_AREA_COUNTIES.keys()))  # ← from transit_equity.census
].to_crs("EPSG:4326")
print(f"Loaded {len(bay_tracts)} Bay Area census tracts")

stations = pd.read_csv(STATIONS_FILE)
stations_gdf = gpd.GeoDataFrame(
    stations,
    geometry=gpd.points_from_xy(stations["longitude"], stations["latitude"]),
    crs="EPSG:4326",
)
print(f"Loaded {len(stations)} stations")

stations_with_tracts = gpd.sjoin(
    stations_gdf,
    bay_tracts[["GEOID", "NAME", "geometry"]],
    how="left",
    predicate="within",
)
matched = (~stations_with_tracts["GEOID"].isna()).sum()
print(f"Matched {matched}/{len(stations_with_tracts)} stations to tracts")

census_final = pd.read_csv("../data/processed/census_tract_data_2024_clean.csv")
census_final = census_final.rename(columns={"median_household_income": "median_income"})
census_final["GEOID"] = census_final["GEOID"].astype(str).str.zfill(11)

stations_with_census = stations_with_tracts.merge(census_final, on="GEOID", how="left")

# PART 2: Amenity access

print("\n\nPART 2: CALCULATING AMENITY ACCESS")
print("-" * 90)

amenities = pd.read_csv(AMENITIES_FILE)
print(f"Loaded {len(amenities)} amenities")

# build_station_amenity_records lives in transit_equity.amenities
records    = build_station_amenity_records(stations_with_census, amenities)
results_df = pd.DataFrame(records)

# Ridership-based classification

ridership_df = pd.read_csv("../data/processed/classification_results_fy2025.csv")

# apply_name_crosswalk lives in transit_equity.classify
ridership_df  = apply_name_crosswalk(ridership_df)

ridership_merge = (
    ridership_df[["station_name", "consensus", "avg_weekday_exits"]]
    .copy()
    .rename(columns={"consensus": "station_type", "avg_weekday_exits": "ridership"})
)
results_df = results_df.merge(ridership_merge, on="station_name", how="left")

# Remove out-of-scope stations
results_df = (
    results_df[~results_df["station_name"].isin(EXCLUDE_STATIONS)]
    .reset_index(drop=True)
)
print(f"Removed {EXCLUDE_STATIONS} — {len(results_df)} stations remaining")
results_df = results_df.drop_duplicates(subset=["latitude", "longitude"], keep="first")

unmatched = results_df[results_df["station_type"].isna()]
if len(unmatched) > 0:
    print(f"\nWARNING: {len(unmatched)} amenity stations did not match ridership data:")
    print(unmatched[["station_name", "agency"]].to_string(index=False))
else:
    print("All amenity stations matched to ridership classification")

core = results_df[results_df["station_type"] == "core"]
peri = results_df[results_df["station_type"] == "peripheral"]

print(f"\nClassification result: {len(core)} core, {len(peri)} peripheral")
print("\nPeripheral stations:")
print(
    peri[["station_name", "agency", "ridership"]]
    .sort_values("ridership", ascending=False)
    .to_string(index=False)
)

# Gini coefficient (calculate_gini / bootstrap_gini from transit_equity.stats)

print("\nCalculating Gini coefficient and unmet need index")

overall_gini = calculate_gini(results_df["total_amenities"].values)
core_gini    = calculate_gini(core["total_amenities"].values)
peri_gini    = calculate_gini(peri["total_amenities"].values)

overall_ci = bootstrap_gini(results_df["total_amenities"].values)
core_ci    = bootstrap_gini(core["total_amenities"].values)
peri_ci    = bootstrap_gini(peri["total_amenities"].values)

print(f"Gini (overall):    {overall_gini:.3f} (95% CI: {overall_ci[0]:.3f}–{overall_ci[1]:.3f})")
print(f"Gini (core):       {core_gini:.3f} (95% CI: {core_ci[0]:.3f}–{core_ci[1]:.3f})")
print(f"Gini (peripheral): {peri_gini:.3f} (95% CI: {peri_ci[0]:.3f}–{peri_ci[1]:.3f})")

# Unmet-need index (add_unmet_need_index from transit_equity.stats)
results_df = add_unmet_need_index(results_df)

# Amenity entropy (amenity_entropy from transit_equity.stats)
results_df["amenity_entropy"] = results_df.apply(amenity_entropy, axis=1)

core = results_df[results_df["station_type"] == "core"]
peri = results_df[results_df["station_type"] == "peripheral"]
print(f"Calculated unmet need index for {len(results_df)} stations")
print("Calculated amenity entropy scores")

# PART 3: Validation

print("\n\nPART 3: VALIDATION")
print("-" * 90)

print(f"\nSample size: Core={len(core)}, Peripheral={len(peri)}")
print(f"\nDemographics validation:")
print(f"{'Metric':<25} {'Core':<15} {'Peripheral':<15} {'Status'}")
print("-" * 70)

core_noveh = core["pct_no_vehicle"].mean()
peri_noveh = peri["pct_no_vehicle"].mean()
status     = "valid" if core_noveh > peri_noveh + 3 else "error"

print(f"{'% No Vehicle':<25} {core_noveh:>14.1f}% {peri_noveh:>14.1f}%  {status}")
print(
    f"{'Median Income':<25} ${core['median_income'].mean():>13,.0f} "
    f"${peri['median_income'].mean():>13,.0f}"
)
if core_noveh > peri_noveh + 3:
    print("\nCensus matching appears correct!")
else:
    print("\nCensus matching may still have issues")

# PART 4: Statistical analysis

print("\n\nPART 4: STATISTICAL ANALYSIS")
print("-" * 90)

test_vars = {
    'total_amenities': 'Total Amenities',
    'grocery': 'Grocery Stores',
    'park': 'Parks',
    'clinic': 'Clinics',
    'pharmacy': 'Pharmacies',
    'hospital': "Hosiptal",
    'doctors': "Doctors",
    'childcare': "Childcare",
    'convenience': "Convenience",
    'kindergarten': 'Kindergarten'
}


print("\nPeripheral vs Core Comparison (Permutation Tests):\n")

comparison_results = []
p_values = []

for var, label in test_vars.items():
    core_vals = core[var].dropna().values
    peri_vals = peri[var].dropna().values

    if len(core_vals) < 3 or len(peri_vals) < 3:
        continue

    def statistic(x, y, axis):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    res = permutation_test(
        (core_vals, peri_vals),
        statistic,
        n_resamples=10_000,
        alternative="two-sided",
        random_state=42,
    )

    pooled_std = np.sqrt((core_vals.std() ** 2 + peri_vals.std() ** 2) / 2)
    cohens_d   = (core_vals.mean() - peri_vals.mean()) / pooled_std
    glass_d    = (core_vals.mean() - peri_vals.mean()) / peri_vals.std()

    p_values.append(res.pvalue)
    comparison_results.append({
        "variable":    label,
        "core_mean":   core_vals.mean(),
        "peri_mean":   peri_vals.mean(),
        "difference":  core_vals.mean() - peri_vals.mean(),
        "p_value":     res.pvalue,
        "cohens_d":    cohens_d,
        "glass delta": glass_d,
    })

comp_df = pd.DataFrame(comparison_results)

print(f"{'Variable':<20} {'Core':<8} {'Peri':<8} {'Diff':<8} {'p':<10} {'d':<6}")
print("-" * 65)
for _, row in comp_df.iterrows():
    sig = (
        "***" if row["p_value"] < 0.001 else
        "**"  if row["p_value"] < 0.01  else
        "*"   if row["p_value"] < 0.05  else ""
    )
    print(
        f"{row['variable']:<20} {row['core_mean']:>7.1f} {row['peri_mean']:>7.1f} "
        f"{row['difference']:>7.1f} {row['p_value']:>9.4f} {sig:3} {row["glass delta"]:>5.2f}"
    )

# FDR correction
reject, p_adj, _, _ = multipletests(p_values, method="fdr_bh")
print("\nAfter FDR correction:")
for var, p_raw, p_adjusted, sig in zip(test_vars.values(), p_values, p_adj, reject):
    print(
        f"{var:<20} p={p_raw:.4f} → q={p_adjusted:.4f}  "
        f"{'Significant' if sig else ''}"
    )

# Spearman correlations
print("\n\nSpearman Correlations (with demographics):\n")

corr_pairs = [
    ("total_amenities", "median_income"),
    ("total_amenities", "pct_no_vehicle"),
    ("total_amenities", "pct_nonwhite"),
]
corr_p_values = []
for var1, var2 in corr_pairs:
    clean = results_df[[var1, var2]].dropna()
    if len(clean) > 10:
        rho, p = stats.spearmanr(clean[var1], clean[var2])
        corr_p_values.append(p)
        print(f"  {var2:<20} ρ = {rho:>7.3f}, p = {p:.4f}")

if corr_p_values:
    _, p_adj_corr, _, _ = multipletests(corr_p_values, method="fdr_bh")
    print(f"\nAfter FDR: {sum(p_adj_corr < 0.05)}/{len(p_adj_corr)} significant")

# Unmet need analysis

print("\n\nUNMET NEED ANALYSIS")
print("-" * 90)

high_unmet_need = results_df.nlargest(10, "unmet_need_index")[
    ["station_name", "agency", "station_type", "total_amenities",
     "pct_no_vehicle", "unmet_need_index"]
].copy()

print("\nTop 10 Stations with Highest Unmet Need:")
print("(High % no-vehicle + Low amenity count)\n")
print(
    f"{'Station':<30} {'Agency':<10} {'Type':<12} "
    f"{'Amenities':<12} {'% No Veh':<12} {'Unmet Need'}"
)
print("-" * 90)
for _, row in high_unmet_need.iterrows():
    print(
        f"{row['station_name']:<30} {row['agency']:<10} {row['station_type']:<12} "
        f"{row['total_amenities']:<12.0f} {row['pct_no_vehicle']:<12.1f} "
        f"{row['unmet_need_index']:>10.3f}"
    )

# Amenity diversity analysis

print("\n\nAMENITY DIVERSITY (ENTROPY) ANALYSIS")
print("-" * 90)

core_entropy_mean = core["amenity_entropy"].mean()
peri_entropy_mean = peri["amenity_entropy"].mean()

print(f"\nMean amenity entropy:")
print(f"Core stations:       {core_entropy_mean:.3f}")
print(f"Peripheral stations: {peri_entropy_mean:.3f}")
print(f"Difference:          {core_entropy_mean - peri_entropy_mean:.3f}")

entropy_stat, entropy_p = mannwhitneyu(
    core["amenity_entropy"].dropna(),
    peri["amenity_entropy"].dropna(),
    alternative="two-sided",
)
print(f"\nMann-Whitney U test: U={entropy_stat:.1f}, p={entropy_p:.4f}")

diverse_stations = results_df.nlargest(10, "amenity_entropy")[
    ['station_name', 'agency', 'total_amenities', 'amenity_entropy',
     'grocery', 'park', 'clinic', 'pharmacy', 'childcare', 'doctors', 
     'hospital', 'kindergarten', 'convenience']
]
print("\nTop 10 Most Diverse Amenity Mix (by entropy):\n")
print(
    f"{'Station':<30} {'Total':<8} {'Entropy':<10} "
    f"{'Groc':<6} {'Park':<6} {'Clin':<6} {'Phar':<6} {'Care':<6}"
    f"{'Doc':<6} {'Hosp':<6} {'Kind':<6} {'Conv':<6}"
)
print("-" * 90)
for _, row in diverse_stations.iterrows():
    print(
        f"{row['station_name']:<30} {row['total_amenities']:<8.0f} "
        f"{row['amenity_entropy']:<10.3f} {row['grocery']:<6.0f} "
        f"{row['park']:<6.0f} {row['clinic']:<6.0f} "
        f"{row['pharmacy']:<6.0f} {row['childcare']:<6.0f}{row['doctors']:<6.0f}"
        f"{row['hospital']:<6.0f} {row['kindergarten']:<6.0f} {row['convenience']:<6.0f}"
    )

# PART 5: Save results

print("\n\nPART 5: SAVING RESULTS")
print("-" * 90)

results_df.to_csv(OUTPUT_DIR / "final_station_data.csv", index=False)
comp_df.to_csv(OUTPUT_DIR / "peripheral_vs_core_results.csv", index=False)
print("Saved final station data")
print("Saved comparison results")

# Summary

sig_count = sum(reject)

print("\n\n" + "=" * 90)
print("ANALYSIS COMPLETE")
print("=" * 90)
print(f"""
FINAL RESULTS:

1. PERIPHERAL vs CORE:
   {sig_count} of {len(p_values)} comparisons significant after FDR correction

2. STRONGEST FINDING:
   {comp_df.iloc[0]['variable']}:
   Core = {comp_df.iloc[0]['core_mean']:.1f}, Peripheral = {comp_df.iloc[0]['peri_mean']:.1f}
   Difference = {comp_df.iloc[0]['difference']:.1f} \
(p={comp_df.iloc[0]['p_value']:.3f}, d={comp_df.iloc[0]["glass delta"]:.2f})

3. INEQUALITY METRICS:
   Gini coefficient: {overall_gini:.3f} (0=equality, 1=inequality)
   Highest unmet need: {high_unmet_need.iloc[0]['station_name']} \
({high_unmet_need.iloc[0]['unmet_need_index']:.3f})

4. AMENITY DIVERSITY:
   Mean entropy: Core {core_entropy_mean:.3f} vs Peripheral {peri_entropy_mean:.3f}
   Diversity difference: \
{'Significant' if entropy_p < 0.05 else 'Not significant'} (p={entropy_p:.4f})

5. CENSUS MATCHING:
   {"Working correctly" if core_noveh > peri_noveh + 3 else "May need review"}
   Core: {core_noveh:.1f}% no vehicle, Peripheral: {peri_noveh:.1f}% no vehicle

OUTPUT FILES:
   - {OUTPUT_DIR / 'final_station_data.csv'}
   - {OUTPUT_DIR / 'peripheral_vs_core_results.csv'}
""")
print("=" * 90)
