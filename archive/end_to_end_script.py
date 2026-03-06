"""
FULL ANALYSIS SCRIPT - Complete Bay Area Transit Amenity Study
Run this script for complete analysis with all statistics and reporting

This script:
1. Fixes census matching (spatial join)
2. Calculates amenity access
3. Cleans data (handles error codes)
4. Runs all statistical tests
5. Generates comprehensive descriptive statistics
6. Creates publication-ready tables
7. Saves all outputs
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from scipy import stats
from scipy.stats import permutation_test
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================

CENSUS_SHAPEFILE = "../data/census_shapefiles/tl_2020_06_tract.shp"
STATIONS_FILE = "../data/transit_gdf.csv"
AMENITIES_FILE = "../data/all_amenities.csv"
OUTPUT_DIR = Path("../data/final_results")
CENSUS_API_KEY = "7b4a89318687b3fe27be640b5333d3beb7d456e7"  # Add your key here

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("="*90)
print("FULL ANALYSIS: BAY AREA TRANSIT AMENITY ACCESS")
print("="*90)
print("\nThis script will:")
print("  1. Match stations to census tracts (spatial join)")
print("  2. Download census demographics")
print("  3. Calculate amenity access within 0.5 miles")
print("  4. Clean data and handle missing values")
print("  5. Generate descriptive statistics")
print("  6. Run statistical tests (permutation, correlations)")
print("  7. Apply multiple testing correction")
print("  8. Create publication-ready tables")
print("\n" + "="*90)

# ============================================================
# PART 1: DATA LOADING AND CENSUS MATCHING
# ============================================================

print("\n\nPART 1: SPATIAL DATA PREPARATION")
print("-"*90)

# Load census tracts
bay_area_counties = {
    '001': 'Alameda', '013': 'Contra Costa', '041': 'Marin', '055': 'Napa',
    '075': 'San Francisco', '081': 'San Mateo', '085': 'Santa Clara',
    '095': 'Solano', '097': 'Sonoma'
}

ca_tracts = gpd.read_file(CENSUS_SHAPEFILE)
bay_tracts = ca_tracts[
    (ca_tracts['STATEFP'] == '06') & 
    (ca_tracts['COUNTYFP'].isin(bay_area_counties.keys()))
].to_crs('EPSG:4326')

print(f"✓ Loaded {len(bay_tracts)} Bay Area census tracts")

# Load stations
stations = pd.read_csv(STATIONS_FILE)
stations_gdf = gpd.GeoDataFrame(
    stations,
    geometry=gpd.points_from_xy(stations['longitude'], stations['latitude']),
    crs='EPSG:4326'
)

print(f"✓ Loaded {len(stations)} transit stations")

# Spatial join
stations_with_tracts = gpd.sjoin(
    stations_gdf,
    bay_tracts[['GEOID', 'NAME', 'geometry']],
    how='left',
    predicate='within'
)

print(f"✓ Matched {(~stations_with_tracts['GEOID'].isna()).sum()}/{len(stations_with_tracts)} stations to tracts")

# Get census data
if CENSUS_API_KEY:
    print("\nDownloading census demographics from API...")
    import requests
    
    census_vars = {
        'B01003_001E': 'total_pop',
        'B19013_001E': 'median_income',
        'B25044_001E': 'total_households',
        'B25044_003E': 'hh_no_veh_own',
        'B25044_010E': 'hh_no_veh_rent',
        'B02001_001E': 'pop_total_race',
        'B02001_002E': 'pop_white',
    }
    
    census_list = []
    for cfips, cname in bay_area_counties.items():
        url = "https://api.census.gov/data/2022/acs/acs5"
        params = {
            'get': ','.join(census_vars.keys()),
            'for': 'tract:*',
            'in': f'state:06 county:{cfips}',
            'key': CENSUS_API_KEY
        }
        
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                data = r.json()
                df = pd.DataFrame(data[1:], columns=data[0])
                census_list.append(df)
                print(f"  ✓ {cname}")
        except:
            print(f"  ✗ {cname} failed")
    
    if census_list:
        census_data = pd.concat(census_list)
        census_data['GEOID'] = census_data['state'] + census_data['county'] + census_data['tract']
        
        for var in census_vars.keys():
            census_data[var] = pd.to_numeric(census_data[var], errors='coerce')
        
        census_data = census_data.rename(columns=census_vars)
        
        census_data['households_no_vehicle'] = (
            census_data['hh_no_veh_own'].fillna(0) + 
            census_data['hh_no_veh_rent'].fillna(0)
        )
        census_data['pct_no_vehicle'] = (
            census_data['households_no_vehicle'] / census_data['total_households'] * 100
        )
        census_data['pct_nonwhite'] = (
            (census_data['pop_total_race'] - census_data['pop_white']) / 
            census_data['pop_total_race'] * 100
        )
        
        census_final = census_data[[
            'GEOID', 'total_pop', 'median_income', 'total_households',
            'households_no_vehicle', 'pct_no_vehicle', 'pct_nonwhite'
        ]]
        
        stations_with_census = stations_with_tracts.merge(census_final, on='GEOID', how='left')
        print(f"✓ Downloaded demographics for {len(census_final)} tracts")
    else:
        stations_with_census = stations_with_tracts
        print("✗ Census download failed")
else:
    stations_with_census = stations_with_tracts
    print("⚠️  No Census API key provided")


# ============================================================
# PART 2: AMENITY ACCESS CALCULATION
# ============================================================

print("\n\nPART 2: CALCULATING AMENITY ACCESS")
print("-"*90)

amenities = pd.read_csv(AMENITIES_FILE)
print(f"✓ Loaded {len(amenities)} amenities")

from math import radians, cos, sin, asin, sqrt

def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * asin(sqrt(a)) * 6371000

HALF_MILE = 804.67

results = []
for idx, station in stations_with_census.iterrows():
    amenities['distance'] = amenities.apply(
        lambda r: haversine(station['longitude'], station['latitude'], 
                          r['longitude'], r['latitude']),
        axis=1
    )
    
    within = amenities[amenities['distance'] <= HALF_MILE]
    counts = within['category'].value_counts().to_dict()
    
    results.append({
        'station_name': station['name'],
        'agency': station['agency'],
        'latitude': station['latitude'],
        'longitude': station['longitude'],
        'GEOID': station.get('GEOID'),
        'total_amenities': len(within),
        'grocery': counts.get('grocery', 0),
        'park': counts.get('park', 0),
        'clinic': counts.get('clinic', 0),
        'pharmacy': counts.get('pharmacy', 0),
        'hospital': counts.get('hospital', 0),
        'doctors': counts.get('doctors', 0),
        'childcare': counts.get('childcare', 0),
        'median_income': station.get('median_income'),
        'pct_no_vehicle': station.get('pct_no_vehicle'),
        'pct_nonwhite': station.get('pct_nonwhite'),
        'total_pop': station.get('total_pop'),
        'total_households': station.get('total_households'),
    })

results_df = pd.DataFrame(results)
results_df = results_df.drop_duplicates(subset=['latitude', 'longitude'], keep='first')

print(f"✓ Calculated amenity access for {len(results_df)} unique stations")

# Classify stations
def classify_station(row):
    peripheral_indicators = [
        'antioch', 'pittsburg', 'concord', 'walnut creek', 
        'san jose', 'milpitas', 'fremont', 'dublin', 'pleasanton'
    ]
    station_name = str(row['station_name']).lower()
    if any(ind in station_name for ind in peripheral_indicators):
        return 'peripheral'
    return 'core'

results_df['station_type'] = results_df.apply(classify_station, axis=1)


# ============================================================
# PART 3: DATA CLEANING
# ============================================================

print("\n\nPART 3: DATA CLEANING")
print("-"*90)

# Fix Census error codes (-666666666 = missing data)
mask_bad_income = (results_df['median_income'] < 10000) | (results_df['median_income'] > 500000)
n_bad_income = mask_bad_income.sum()

if n_bad_income > 0:
    print(f"Found {n_bad_income} stations with invalid income data:")
    print(results_df[mask_bad_income][['station_name', 'median_income', 'GEOID']])
    results_df.loc[mask_bad_income, 'median_income'] = np.nan
    print("→ Set to NaN (excluded from income analysis)")

# Count valid data
n_valid_demographics = results_df[['median_income', 'pct_no_vehicle', 'pct_nonwhite']].dropna().shape[0]
print(f"\n✓ {n_valid_demographics}/{len(results_df)} stations have complete demographics")


# ============================================================
# PART 4: DESCRIPTIVE STATISTICS
# ============================================================

print("\n\n" + "="*90)
print("DESCRIPTIVE STATISTICS")
print("="*90)

core = results_df[results_df['station_type'] == 'core']
peri = results_df[results_df['station_type'] == 'peripheral']

print(f"\n{'SAMPLE COMPOSITION':-^90}")
print(f"\nTotal stations: {len(results_df)}")
print(f"  Core (urban):       {len(core)} ({100*len(core)/len(results_df):.1f}%)")
print(f"  Peripheral (suburban): {len(peri)} ({100*len(peri)/len(results_df):.1f}%)")

print(f"\nStations by agency:")
for agency in results_df['agency'].unique():
    n = len(results_df[results_df['agency'] == agency])
    print(f"  {agency}: {n} ({100*n/len(results_df):.1f}%)")

print(f"\n\n{'AMENITY ACCESS - DESCRIPTIVE STATISTICS':-^90}")
print(f"\n{'Overall (All Stations, N=' + str(len(results_df)) + ')':-^90}")

amenity_vars = ['total_amenities', 'grocery', 'park', 'clinic', 'pharmacy', 
                'hospital', 'doctors', 'childcare']

desc_all = results_df[amenity_vars].describe().T
desc_all['median'] = results_df[amenity_vars].median()

print(f"\n{'Variable':<20} {'Mean':>8} {'SD':>8} {'Median':>8} {'Min':>6} {'Max':>6}")
print("-"*62)
for var in amenity_vars:
    row = desc_all.loc[var]
    print(f"{var:<20} {row['mean']:>8.1f} {row['std']:>8.1f} {row['median']:>8.1f} "
          f"{row['min']:>6.0f} {row['max']:>6.0f}")

print(f"\n\n{'By Station Type':-^90}")
print(f"\n{'Variable':<20} {'Core Mean':>12} {'Core SD':>10} {'Peri Mean':>12} {'Peri SD':>10}")
print("-"*70)

for var in amenity_vars:
    core_mean = core[var].mean()
    core_sd = core[var].std()
    peri_mean = peri[var].mean()
    peri_sd = peri[var].std()
    print(f"{var:<20} {core_mean:>12.2f} {core_sd:>10.2f} {peri_mean:>12.2f} {peri_sd:>10.2f}")


print(f"\n\n{'DEMOGRAPHICS - DESCRIPTIVE STATISTICS':-^90}")
print(f"\n(Based on {n_valid_demographics} stations with valid census data)")

demo_vars = ['median_income', 'pct_no_vehicle', 'pct_nonwhite', 'total_pop']

print(f"\n{'Variable':<25} {'Core Mean':>15} {'Peri Mean':>15} {'Overall Mean':>15}")
print("-"*75)

for var in demo_vars:
    core_mean = core[var].mean()
    peri_mean = peri[var].mean()
    overall_mean = results_df[var].mean()
    
    if var == 'median_income':
        print(f"{var:<25} ${core_mean:>14,.0f} ${peri_mean:>14,.0f} ${overall_mean:>14,.0f}")
    elif 'pct' in var:
        print(f"{var:<25} {core_mean:>14.1f}% {peri_mean:>14.1f}% {overall_mean:>14.1f}%")
    else:
        print(f"{var:<25} {core_mean:>15,.0f} {peri_mean:>15,.0f} {overall_mean:>15,.0f}")


# ============================================================
# PART 5: STATISTICAL TESTS
# ============================================================

print("\n\n" + "="*90)
print("STATISTICAL ANALYSIS")
print("="*90)

print(f"\n{'A. PERIPHERAL vs CORE COMPARISON (Permutation Tests)':-^90}")

test_vars = {
    'total_amenities': 'Total Amenities',
    'grocery': 'Grocery Stores',
    'park': 'Parks',
    'clinic': 'Clinics',
    'pharmacy': 'Pharmacies',
}

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
        n_resamples=10000,
        alternative='two-sided',
        random_state=42
    )
    
    pooled_std = np.sqrt((core_vals.std()**2 + peri_vals.std()**2) / 2)
    cohens_d = (core_vals.mean() - peri_vals.mean()) / pooled_std
    
    # Bootstrap 95% CI
    rng = np.random.default_rng(42)
    boot_diffs = []
    for _ in range(1000):
        core_sample = rng.choice(core_vals, size=len(core_vals), replace=True)
        peri_sample = rng.choice(peri_vals, size=len(peri_vals), replace=True)
        boot_diffs.append(np.mean(core_sample) - np.mean(peri_sample))
    
    ci_low, ci_high = np.percentile(boot_diffs, [2.5, 97.5])
    
    p_values.append(res.pvalue)
    
    comparison_results.append({
        'variable': label,
        'core_mean': core_vals.mean(),
        'core_sd': core_vals.std(),
        'peri_mean': peri_vals.mean(),
        'peri_sd': peri_vals.std(),
        'difference': core_vals.mean() - peri_vals.mean(),
        'ci_low': ci_low,
        'ci_high': ci_high,
        'p_value': res.pvalue,
        'cohens_d': cohens_d
    })

comp_df = pd.DataFrame(comparison_results)

print(f"\n{'Variable':<20} {'Core':<15} {'Peripheral':<15} {'Diff [95% CI]':<25} {'p-value':<10} {'d':<6}")
print("-"*95)
for _, row in comp_df.iterrows():
    ci_str = f"[{row['ci_low']:.1f}, {row['ci_high']:.1f}]"
    core_str = f"{row['core_mean']:.1f} ± {row['core_sd']:.1f}"
    peri_str = f"{row['peri_mean']:.1f} ± {row['peri_sd']:.1f}"
    diff_str = f"{row['difference']:.1f} {ci_str}"
    sig = "***" if row['p_value'] < 0.001 else "**" if row['p_value'] < 0.01 else "*" if row['p_value'] < 0.05 else ""
    print(f"{row['variable']:<20} {core_str:<15} {peri_str:<15} {diff_str:<25} "
          f"{row['p_value']:<9.4f} {sig:1} {row['cohens_d']:>5.2f}")

# FDR correction
from statsmodels.stats.multitest import multipletests

reject, p_adj, _, _ = multipletests(p_values, method='fdr_bh')

print(f"\n{'After Benjamini-Hochberg FDR Correction (α=0.05):':-^90}")
print(f"\n{'Variable':<20} {'Raw p':<10} {'Adjusted q':<12} {'Significant?'}")
print("-"*50)
for var, p_raw, p_adjusted, sig in zip(test_vars.values(), p_values, p_adj, reject):
    status = "Yes ***" if sig else "No"
    print(f"{var:<20} {p_raw:<10.4f} {p_adjusted:<12.4f} {status}")

sig_count = sum(reject)
print(f"\nResult: {sig_count}/{len(p_values)} comparisons remain significant after FDR correction")


print(f"\n\n{'B. CORRELATIONS WITH DEMOGRAPHICS (Spearman)':-^90}")

corr_pairs = [
    ('total_amenities', 'median_income', 'Total Amenities vs Median Income'),
    ('total_amenities', 'pct_no_vehicle', 'Total Amenities vs % No Vehicle'),
    ('total_amenities', 'pct_nonwhite', 'Total Amenities vs % Nonwhite'),
    ('total_amenities', 'total_pop', 'Total Amenities vs Population'),
]

corr_results = []
corr_p_values = []

for var1, var2, label in corr_pairs:
    clean = results_df[[var1, var2]].dropna()
    if len(clean) > 10:
        rho, p = stats.spearmanr(clean[var1], clean[var2])
        corr_p_values.append(p)
        corr_results.append({
            'comparison': label,
            'rho': rho,
            'p_value': p,
            'n': len(clean)
        })

print(f"\n{'Comparison':<45} {'ρ':<10} {'p-value':<12} {'n':<6}")
print("-"*75)
for result in corr_results:
    sig = "***" if result['p_value'] < 0.001 else "**" if result['p_value'] < 0.01 else "*" if result['p_value'] < 0.05 else ""
    print(f"{result['comparison']:<45} {result['rho']:<9.3f} {sig:1} {result['p_value']:<11.4f} {result['n']:<6}")

# FDR for correlations
if corr_p_values:
    reject_corr, p_adj_corr, _, _ = multipletests(corr_p_values, method='fdr_bh')
    
    print(f"\n{'After FDR Correction:':-^75}")
    print(f"{'Comparison':<45} {'Raw p':<10} {'Adj q':<10} {'Sig?'}")
    print("-"*75)
    for result, p_adj, sig in zip(corr_results, p_adj_corr, reject_corr):
        status = "Yes" if sig else "No"
        print(f"{result['comparison']:<45} {result['p_value']:<10.4f} {p_adj:<10.4f} {status}")


# ============================================================
# PART 6: SAVE OUTPUTS
# ============================================================

print("\n\n" + "="*90)
print("SAVING RESULTS")
print("="*90)

# Save main dataset
results_df.to_csv(OUTPUT_DIR / 'final_station_data.csv', index=False)
print(f"✓ Station data: {OUTPUT_DIR / 'final_station_data.csv'}")

# Save comparison results
comp_df.to_csv(OUTPUT_DIR / 'peripheral_vs_core_comparison.csv', index=False)
print(f"✓ Comparison results: {OUTPUT_DIR / 'peripheral_vs_core_comparison.csv'}")

# Save correlation results
pd.DataFrame(corr_results).to_csv(OUTPUT_DIR / 'correlation_results.csv', index=False)
print(f"✓ Correlation results: {OUTPUT_DIR / 'correlation_results.csv'}")

# Create publication table
pub_table = comp_df[['variable', 'core_mean', 'peri_mean', 'difference', 
                      'ci_low', 'ci_high', 'p_value', 'cohens_d']].copy()
pub_table['p_adjusted'] = p_adj
pub_table['significant'] = reject
pub_table.to_csv(OUTPUT_DIR / 'publication_table.csv', index=False)
print(f"✓ Publication table: {OUTPUT_DIR / 'publication_table.csv'}")


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n\n" + "="*90)
print("ANALYSIS COMPLETE - SUMMARY")
print("="*90)

print(f"""
SAMPLE:
  • {len(results_df)} transit stations ({len(core)} core, {len(peri)} peripheral)
  • {n_valid_demographics} stations with complete demographics ({100*n_valid_demographics/len(results_df):.1f}%)
  • {len(amenities)} amenities mapped within study area

KEY FINDINGS:

1. PERIPHERAL vs CORE DIFFERENCES:
   • Total amenities: Core {comp_df.iloc[0]['core_mean']:.1f} vs Peripheral {comp_df.iloc[0]['peri_mean']:.1f}
   • Difference: {comp_df.iloc[0]['difference']:.1f} [{comp_df.iloc[0]['ci_low']:.1f}, {comp_df.iloc[0]['ci_high']:.1f}]
   • p = {comp_df.iloc[0]['p_value']:.4f}, Cohen's d = {comp_df.iloc[0]['cohens_d']:.2f}
   • {sig_count}/{len(p_values)} comparisons significant after FDR correction

2. DEMOGRAPHIC CORRELATIONS:
   • % No vehicle households: ρ = {corr_results[1]['rho']:.3f}, p = {corr_results[1]['p_value']:.4f}
   • Median income: ρ = {corr_results[0]['rho']:.3f}, p = {corr_results[0]['p_value']:.4f}
   • {sum(reject_corr)}/{len(corr_p_values)} correlations significant after FDR correction

STATISTICAL METHODS:
  ✓ Permutation tests (non-parametric, robust to violations)
  ✓ Effect sizes (Cohen's d) with bootstrapped 95% CIs
  ✓ Benjamini-Hochberg FDR correction (α = 0.05)
  ✓ Spearman correlations (robust to outliers)

OUTPUT FILES:
  • final_station_data.csv - Complete dataset
  • peripheral_vs_core_comparison.csv - Group comparison results
  • correlation_results.csv - Demographic correlations
  • publication_table.csv - Ready for manuscript tables

""")

print("="*90)
print("Ready for publication! 📊🎓")
print("="*90)