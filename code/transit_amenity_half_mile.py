import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
from scipy import stats

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def haversine(lon1, lat1, lon2, lat2):
    """Distance in meters between two lat/lon points."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * asin(sqrt(a)) * 6371000


def classify_station(row):
    """
    Classify each station as peripheral or core.
    Peripheral = outer Bay Area (eastern Contra Costa, southern Santa Clara).
    """
    peripheral_cities = [
        "antioch", "pittsburg", "bay point", "north concord", "concord",
        "pleasant hill", "walnut creek", "san jose", "milpitas",
        "warm springs", "fremont", "union city", "dublin",
        "pleasanton", "livermore", "gilroy", "morgan hill", "berryessa"
    ]
    city   = str(row.get("city", "")).lower()
    county = str(row.get("county", "")).lower().replace(" ", "")
    if county in ["contracosta", "santaclara"] or any(c in city for c in peripheral_cities):
        return "peripheral"
    return "core"


def nearest_census_tract(station_lat, station_lon, census_df):
    """Return the index of the census tract centroid closest to the station."""
    dists = census_df.apply(
        lambda r: haversine(station_lon, station_lat, r["tract_lon"], r["tract_lat"]),
        axis=1
    )
    return dists.idxmin()


# ============================================================
# STEP 1 — LOAD DATA
# ============================================================

print("Loading data...")
transit   = pd.read_csv("transit_gdf.csv")
amenities = pd.read_csv("all_amenities.csv")
census    = pd.read_csv("bay_area_census_tracts.csv")

print(f"  {len(transit)} transit stations")
print(f"  {len(amenities)} amenities")
print(f"  {len(census)} census tracts\n")

# Fix county name inconsistency in transit data
transit["county"] = transit["county"].str.lower().str.replace(" ", "")

# Classify stations as peripheral or core
transit["station_type"] = transit.apply(classify_station, axis=1)
print("Station type breakdown:")
print(transit["station_type"].value_counts(), "\n")


# ============================================================
# STEP 2 — BUILD APPROXIMATE CENSUS TRACT CENTROIDS
# The Census API doesn't return lat/lon centroids directly,
# so we anchor each tract to its county center and add a small
# per-tract offset so each row has a unique location.
# Replace tract_lat / tract_lon with real centroids if you have them.
# ============================================================

COUNTY_CENTROIDS = {
    1:  (37.6879, -121.9101),   # Alameda
    13: (37.9227, -121.9022),   # Contra Costa
    75: (37.7749, -122.4194),   # San Francisco
    81: (37.5630, -122.3255),   # San Mateo
    85: (37.3382, -121.8863),   # Santa Clara
}

census["tract_lat"] = census["county"].map({k: v[0] for k, v in COUNTY_CENTROIDS.items()})
census["tract_lon"] = census["county"].map({k: v[1] for k, v in COUNTY_CENTROIDS.items()})

# Small deterministic jitter so each tract centroid is unique
np.random.seed(42)
census["tract_lat"] += np.random.uniform(-0.15, 0.15, len(census))
census["tract_lon"] += np.random.uniform(-0.15, 0.15, len(census))


# ============================================================
# STEP 3 — BUFFER ANALYSIS: COUNT AMENITIES WITHIN 0.5 MILES
# Expands original code to capture all amenity categories
# and adds diversity score + nearest-amenity distance.
# ============================================================

HALF_MILE  = 804.67   # meters
ESSENTIAL  = ["grocery", "park", "clinic", "pharmacy"]

results = []
print("Calculating amenity buffers for each station...")

for idx, station in transit.iterrows():
    if (idx + 1) % 10 == 0:
        print(f"  Processed {idx + 1}/{len(transit)} stations...")

    slat, slon = station["latitude"], station["longitude"]

    amenities["distance"] = amenities.apply(
        lambda row: haversine(slon, slat, row["longitude"], row["latitude"]),
        axis=1
    )

    within = amenities[amenities["distance"] <= HALF_MILE].copy()
    counts = within["category"].value_counts().to_dict()

    # Diversity score: how many of the 4 essential categories are present (0-4)
    diversity_score  = sum(1 for cat in ESSENTIAL if counts.get(cat, 0) > 0)
    nearest_dist     = within["distance"].min() if len(within) > 0 else np.nan

    result = {
        "station_name":      station["name"],
        "station_id":        station.get("station_id", idx),
        "agency":            station["agency"],
        "city":              station.get("city", "Unknown"),
        "county":            station["county"],
        "latitude":          slat,
        "longitude":         slon,
        "station_type":      station["station_type"],
        "total_amenities":   len(within),
        "diversity_score":   diversity_score,
        "nearest_amenity_m": nearest_dist,
        # All categories
        "grocery":           counts.get("grocery", 0),
        "park":              counts.get("park", 0),
        "clinic":            counts.get("clinic", 0),
        "pharmacy":          counts.get("pharmacy", 0),
        "hospital":          counts.get("hospital", 0),
        "doctors":           counts.get("doctors", 0),
        "childcare":         counts.get("childcare", 0),
        "kindergartens":     counts.get("kindergartens", 0),
        "convenience":       counts.get("convenience", 0),
    }
    results.append(result)

results_df = pd.DataFrame(results)


# ============================================================
# STEP 4 — JOIN CENSUS DEMOGRAPHICS TO EACH STATION
# Snap each station to its nearest census tract centroid.
# ============================================================

print("\nJoining census demographics to stations...")
census_matches = []

for _, station in results_df.iterrows():
    nearest_idx = nearest_census_tract(station["latitude"], station["longitude"], census)
    tract = census.loc[nearest_idx]
    census_matches.append({
        "station_name":          station["station_name"],
        "median_income":         tract["median_income"],
        "total_pop":             tract["total_pop"],
        "total_households":      tract["total_households"],
        "households_no_vehicle": tract["households_no_vehicle"],
        "pct_no_vehicle":        tract["pct_no_vehicle"],
        "pct_nonwhite":          tract["pct_nonwhite"],
        "GEOID":                 tract["GEOID"],
    })

results_df = results_df.merge(pd.DataFrame(census_matches), on="station_name", how="left")

# Normalised access metric: amenities per 1,000 residents
results_df["amenities_per_1000"] = (
    results_df["total_amenities"] / results_df["total_pop"] * 1000
).replace([np.inf, -np.inf], np.nan)

results_df = results_df.sort_values("total_amenities", ascending=False)


# ============================================================
# STEP 5 — ORIGINAL OUTPUT (preserved from your script)
# ============================================================

SEP = "=" * 90

print(f"\n{SEP}")
print("AMENITIES WITHIN HALF MILE (0.5 mi = 804.67 m) OF EACH TRANSIT STATION")
print(SEP)
print(f"\nTotal stations analyzed: {len(results_df)}")

print(f"\n{SEP}\nTOP 15 STATIONS BY TOTAL AMENITIES\n{SEP}")
print(results_df[["station_name","agency","total_amenities",
                   "hospital","clinic","doctors","pharmacy"]].head(15).to_string(index=False))

print(f"\n{SEP}\nBOTTOM 10 STATIONS BY AMENITIES\n{SEP}")
print(results_df[["station_name","agency","total_amenities",
                   "hospital","clinic","doctors","pharmacy"]].tail(10).to_string(index=False))

print(f"\n{SEP}\nSUMMARY STATISTICS\n{SEP}")
print(f"Average amenities per station : {results_df['total_amenities'].mean():.1f}")
print(f"Median amenities per station  : {results_df['total_amenities'].median():.1f}")
print(f"Standard deviation            : {results_df['total_amenities'].std():.1f}")
print(f"Max amenities at one station  : {results_df['total_amenities'].max()}")
print(f"Station with most amenities   : {results_df.iloc[0]['station_name']} ({results_df.iloc[0]['agency']})")
print(f"Stations with NO amenities    : {(results_df['total_amenities'] == 0).sum()}")
print(f"Stations with 10+ amenities   : {(results_df['total_amenities'] >= 10).sum()}")
print(f"Stations with 50+ amenities   : {(results_df['total_amenities'] >= 50).sum()}")

print(f"\n{SEP}\nAVERAGE AMENITIES BY TRANSIT AGENCY\n{SEP}")
print(results_df.groupby("agency").agg(
    total_amenities_mean   =("total_amenities","mean"),
    total_amenities_median =("total_amenities","median"),
    total_amenities_min    =("total_amenities","min"),
    total_amenities_max    =("total_amenities","max"),
    hospital_mean          =("hospital","mean"),
    clinic_mean            =("clinic","mean"),
    doctors_mean           =("doctors","mean"),
    pharmacy_mean          =("pharmacy","mean"),
).round(1).to_string())

results_df["healthcare_total"] = results_df["hospital"] + results_df["clinic"]
print(f"\n{SEP}\nSTATIONS WITH BEST HEALTHCARE ACCESS (hospitals + clinics)\n{SEP}")
print(results_df.nlargest(10, "healthcare_total")[
    ["station_name","agency","hospital","clinic","healthcare_total"]
].to_string(index=False))


# ============================================================
# STEP 6 — NEW: PERIPHERAL vs CORE COMPARISON
# ============================================================

print(f"\n{SEP}\nPERIPHERAL vs CORE STATION COMPARISON\n{SEP}")
print(results_df.groupby("station_type").agg(
    n_stations            =("station_name","count"),
    avg_total_amenities   =("total_amenities","mean"),
    avg_grocery           =("grocery","mean"),
    avg_park              =("park","mean"),
    avg_clinic            =("clinic","mean"),
    avg_pharmacy          =("pharmacy","mean"),
    avg_diversity_score   =("diversity_score","mean"),
    avg_amenities_per_1000=("amenities_per_1000","mean"),
    avg_median_income     =("median_income","mean"),
    avg_pct_no_vehicle    =("pct_no_vehicle","mean"),
    avg_pct_nonwhite      =("pct_nonwhite","mean"),
).round(2).to_string())


# ============================================================
# STEP 7 — NEW: CORRELATION ANALYSIS
# Does income / car-free rate / race correlate with amenity access?
# ============================================================

print(f"\n{SEP}\nCORRELATION ANALYSIS\n{SEP}")

corr_targets = {
    "total_amenities": "Total Amenities",
    "diversity_score": "Diversity Score (0-4)",
}
corr_predictors = {
    "median_income":  "Median Income",
    "pct_no_vehicle": "% Households No Vehicle",
    "pct_nonwhite":   "% Non-White Population",
    "total_pop":      "Total Population",
}

for target_col, target_label in corr_targets.items():
    print(f"\n  Correlations with {target_label}:")
    for pred_col, pred_label in corr_predictors.items():
        clean = results_df[[target_col, pred_col]].dropna()
        if len(clean) < 5:
            continue
        r, p = stats.pearsonr(clean[target_col], clean[pred_col])
        sig  = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "(ns)"
        print(f"    vs {pred_label:<30}  r = {r:+.3f},  p = {p:.4f}  {sig}")


# ============================================================
# STEP 8 — NEW: T-TESTS / MANN-WHITNEY (PERIPHERAL vs CORE)
# ============================================================

print(f"\n{SEP}\nT-TEST: PERIPHERAL vs CORE STATIONS\n{SEP}")
print("Null hypothesis: no difference in means between peripheral and core stations\n")

core_df = results_df[results_df["station_type"] == "core"]
peri_df = results_df[results_df["station_type"] == "peripheral"]

ttest_vars = {
    "total_amenities":    "Total Amenities",
    "diversity_score":    "Diversity Score",
    "grocery":            "Grocery Stores",
    "park":               "Parks",
    "clinic":             "Clinics",
    "pharmacy":           "Pharmacies",
    "amenities_per_1000": "Amenities per 1,000 Residents",
    "median_income":      "Median Income",
    "pct_no_vehicle":     "% No Vehicle",
    "pct_nonwhite":       "% Non-White",
}

for col, label in ttest_vars.items():
    c_vals = core_df[col].dropna()
    p_vals_raw = peri_df[col].dropna()
    if len(c_vals) < 3 or len(p_vals_raw) < 3:
        continue

    # Use Mann-Whitney (non-parametric) — safer for small, skewed samples
    stat, p_val = stats.mannwhitneyu(c_vals, p_vals_raw, alternative="two-sided")
    sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "(ns)"

    # Cohen's d for effect size
    pooled_std = np.sqrt((c_vals.std()**2 + p_vals_raw.std()**2) / 2)
    d = (c_vals.mean() - p_vals_raw.mean()) / pooled_std if pooled_std > 0 else np.nan
    effect = "large" if abs(d) > 0.8 else "medium" if abs(d) > 0.5 else "small"

    print(f"  {label}")
    print(f"    Core mean={c_vals.mean():.2f}  |  Peripheral mean={p_vals_raw.mean():.2f}")
    print(f"    Mann-Whitney U={stat:.1f}, p={p_val:.4f}  {sig}  |  Cohen's d={d:.3f} ({effect})")
    print()


# ============================================================
# STEP 9 — NEW: MULTIPLE REGRESSION
# What predicts total amenity count at a station?
# ============================================================

print(f"\n{SEP}\nMULTIPLE REGRESSION: PREDICTORS OF TOTAL AMENITIES\n{SEP}")
print("Dependent  : total_amenities")
print("Predictors : median_income, pct_no_vehicle, pct_nonwhite, total_pop, is_peripheral\n")

reg_df = results_df[[
    "total_amenities","median_income","pct_no_vehicle",
    "pct_nonwhite","total_pop","station_type"
]].dropna().copy()

reg_df["is_peripheral"] = (reg_df["station_type"] == "peripheral").astype(int)

# Standardise predictors so coefficients are directly comparable
predictors = ["median_income","pct_no_vehicle","pct_nonwhite","total_pop","is_peripheral"]
for col in predictors:
    mu, sd = reg_df[col].mean(), reg_df[col].std()
    reg_df[f"{col}_z"] = (reg_df[col] - mu) / sd if sd > 0 else 0.0

pred_z = [f"{p}_z" for p in predictors]
X = np.column_stack([np.ones(len(reg_df))] + [reg_df[p].values for p in pred_z])
y = reg_df["total_amenities"].values

# OLS solution
coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)

# R-squared
y_hat  = X @ coeffs
ss_res = np.sum((y - y_hat) ** 2)
ss_tot = np.sum((y - y.mean()) ** 2)
r2     = 1 - ss_res / ss_tot
n, k   = X.shape
adj_r2 = 1 - (1 - r2) * (n - 1) / (n - k)

# Standard errors and t-statistics
mse    = ss_res / (n - k)
cov    = mse * np.linalg.inv(X.T @ X)
se     = np.sqrt(np.diag(cov))
t_vals = coeffs / se
p_vals_reg = [2 * (1 - stats.t.cdf(abs(t), df=n - k)) for t in t_vals]

print(f"  R-squared      : {r2:.4f}")
print(f"  Adj. R-squared : {adj_r2:.4f}")
print(f"  n observations : {n}\n")

var_labels = ["(Intercept)", "Median Income (z)", "% No Vehicle (z)",
              "% Non-White (z)", "Total Pop (z)", "Is Peripheral (z)"]

print(f"  {'Variable':<22} {'Coeff':>8} {'SE':>8} {'t':>8} {'p':>9}  Sig")
print(f"  {'-'*65}")
for label, coef, se_val, t_val, p_val in zip(var_labels, coeffs, se, t_vals, p_vals_reg):
    sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
    print(f"  {label:<22} {coef:>8.3f} {se_val:>8.3f} {t_val:>8.3f} {p_val:>9.4f}  {sig}")

print("\n  *** p<0.001  ** p<0.01  * p<0.05")


# ============================================================
# STEP 10 — NEW: EQUITY FLAGS
# Stations that are amenity-poor AND serve disadvantaged communities
# ============================================================

print(f"\n{SEP}\nEQUITY FLAGS: LOW AMENITIES + DISADVANTAGED DEMOGRAPHICS\n{SEP}")
print("Flagged = below-median amenities AND (above-median % non-white OR above-median % no vehicle)\n")

med_amenities  = results_df["total_amenities"].median()
med_nonwhite   = results_df["pct_nonwhite"].median()
med_no_vehicle = results_df["pct_no_vehicle"].median()

results_df["equity_flag"] = (
    (results_df["total_amenities"] < med_amenities) &
    (
        (results_df["pct_nonwhite"]   > med_nonwhite) |
        (results_df["pct_no_vehicle"] > med_no_vehicle)
    )
)

flagged = results_df[results_df["equity_flag"]].sort_values("total_amenities")
print(f"  {len(flagged)} of {len(results_df)} stations flagged\n")
print(flagged[[
    "station_name","agency","station_type",
    "total_amenities","diversity_score",
    "pct_nonwhite","pct_no_vehicle","median_income"
]].to_string(index=False))


# ============================================================
# STEP 11 — SAVE OUTPUTS
# ============================================================

results_df.to_csv("transit_amenity_full_results.csv", index=False)
flagged.to_csv("transit_amenity_equity_flags.csv", index=False)

print(f"\n{SEP}\nFILES SAVED\n{SEP}")
print("  Full results  : transit_amenity_full_results.csv")
print("  Equity flags  : transit_amenity_equity_flags.csv")
