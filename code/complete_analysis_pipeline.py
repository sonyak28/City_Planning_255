"""
COMPLETE PIPELINE: Fix Census + Run Full Analysis
This combines everything into one script
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

# Set these paths
CENSUS_SHAPEFILE = "../data/census_shapefiles/tl_2020_06_tract.shp"
STATIONS_FILE = "../data/transit_gdf.csv"
AMENITIES_FILE = "../data/all_amenities.csv"
OUTPUT_DIR = Path("../data/final_results")

# Optional: Add your Census API key here
CENSUS_API_KEY = "7b4a89318687b3fe27be640b5333d3beb7d456e7"  # Get free key at: https://api.census.gov/data/key_signup.html

# Create output directory
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("="*90)
print("COMPLETE ANALYSIS PIPELINE WITH CORRECTED CENSUS DATA")
print("="*90)

# ============================================================
# PART 1: FIX CENSUS MATCHING
# ============================================================

print("\nPART 1: FIXING CENSUS TRACT MATCHING")
print("-"*90)

# Load shapefile
if not Path(CENSUS_SHAPEFILE).exists():
    print(f"✗ Shapefile not found: {CENSUS_SHAPEFILE}")
    print("\nDOWNLOAD INSTRUCTIONS:")
    print("1. Go to: https://www.census.gov/cgi-bin/geo/shapefiles/index.php")
    print("2. Select: 2020, Census Tracts, California")
    print("3. Extract to: ../data/census_shapefiles/")
    exit(1)

bay_area_counties = {
    '001': 'Alameda', '013': 'Contra Costa', '041': 'Marin', '055': 'Napa',
    '075': 'San Francisco', '081': 'San Mateo', '085': 'Santa Clara',
    '095': 'Solano', '097': 'Sonoma'
}

# Load and filter tracts
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

print(f"✓ Loaded {len(stations)} stations")

# Spatial join
stations_with_tracts = gpd.sjoin(
    stations_gdf,
    bay_tracts[['GEOID', 'NAME', 'geometry']],
    how='left',
    predicate='within'
)

matched = (~stations_with_tracts['GEOID'].isna()).sum()
print(f"✓ Matched {matched}/{len(stations_with_tracts)} stations to tracts")

# Get census data from API
if CENSUS_API_KEY:
    print("\n Downloading census demographics...")
    
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
    for cfips in bay_area_counties.keys():
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
        except:
            pass
    
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
        print("✗ Census API download failed - will use existing data if available")
        stations_with_census = stations_with_tracts
else:
    print("⚠️  No Census API key - skipping demographics download")
    print("   Get free key at: https://api.census.gov/data/key_signup.html")
    stations_with_census = stations_with_tracts

# ============================================================
# PART 2: CALCULATE AMENITY ACCESS
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
    return 2 * asin(sqrt(a)) * 6371000  # meters

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
    })

results_df = pd.DataFrame(results)

# Remove duplicates
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
# PART 3: VALIDATION
# ============================================================

print("\n\nPART 3: VALIDATION")
print("-"*90)

core = results_df[results_df['station_type'] == 'core']
peri = results_df[results_df['station_type'] == 'peripheral']

print(f"\nSample size: Core={len(core)}, Peripheral={len(peri)}")

print(f"\nDemographics validation:")
print(f"{'Metric':<25} {'Core':<15} {'Peripheral':<15} {'Status'}")
print("-"*70)

core_noveh = core['pct_no_vehicle'].mean()
peri_noveh = peri['pct_no_vehicle'].mean()
status = "✓" if core_noveh > peri_noveh + 3 else "⚠️"

print(f"{'% No Vehicle':<25} {core_noveh:>14.1f}% {peri_noveh:>14.1f}%  {status}")
print(f"{'Median Income':<25} ${core['median_income'].mean():>13,.0f} "
      f"${peri['median_income'].mean():>13,.0f}  ✓")

if core_noveh > peri_noveh + 3:
    print("\n✓ Census matching appears correct!")
else:
    print("\n⚠️  Census matching may still have issues")

# ============================================================
# PART 4: STATISTICAL ANALYSIS
# ============================================================

print("\n\nPART 4: STATISTICAL ANALYSIS")
print("-"*90)

# Permutation tests
test_vars = {
    'total_amenities': 'Total Amenities',
    'grocery': 'Grocery Stores',
    'park': 'Parks',
    'clinic': 'Clinics',
    'pharmacy': 'Pharmacies',
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
        n_resamples=10000,
        alternative='two-sided',
        random_state=42
    )
    
    pooled_std = np.sqrt((core_vals.std()**2 + peri_vals.std()**2) / 2)
    cohens_d = (core_vals.mean() - peri_vals.mean()) / pooled_std
    
    p_values.append(res.pvalue)
    
    comparison_results.append({
        'variable': label,
        'core_mean': core_vals.mean(),
        'peri_mean': peri_vals.mean(),
        'difference': core_vals.mean() - peri_vals.mean(),
        'p_value': res.pvalue,
        'cohens_d': cohens_d
    })

comp_df = pd.DataFrame(comparison_results)

print(f"{'Variable':<20} {'Core':<8} {'Peri':<8} {'Diff':<8} {'p':<10} {'d':<6}")
print("-"*65)
for _, row in comp_df.iterrows():
    sig = "***" if row['p_value'] < 0.001 else "**" if row['p_value'] < 0.01 else "*" if row['p_value'] < 0.05 else ""
    print(f"{row['variable']:<20} {row['core_mean']:>7.1f} {row['peri_mean']:>7.1f} "
          f"{row['difference']:>7.1f} {row['p_value']:>9.4f} {sig:3} {row['cohens_d']:>5.2f}")

# FDR correction
from statsmodels.stats.multitest import multipletests

reject, p_adj, _, _ = multipletests(p_values, method='fdr_bh')

print(f"\nAfter FDR correction:")
for var, p_raw, p_adjusted, sig in zip(test_vars.values(), p_values, p_adj, reject):
    print(f"  {var:<20} p={p_raw:.4f} → q={p_adjusted:.4f}  {'✓ Significant' if sig else ''}")

# Non-parametric correlations
print(f"\n\nSpearman Correlations (with demographics):\n")

corr_pairs = [
    ('total_amenities', 'median_income'),
    ('total_amenities', 'pct_no_vehicle'),
    ('total_amenities', 'pct_nonwhite'),
]

corr_p_values = []
for var1, var2 in corr_pairs:
    clean = results_df[[var1, var2]].dropna()
    if len(clean) > 10:
        rho, p = stats.spearmanr(clean[var1], clean[var2])
        corr_p_values.append(p)
        print(f"  {var2:<20} ρ = {rho:>7.3f}, p = {p:.4f}")

if corr_p_values:
    _, p_adj_corr, _, _ = multipletests(corr_p_values, method='fdr_bh')
    print(f"\n  After FDR: {sum(p_adj_corr < 0.05)}/{len(p_adj_corr)} significant")

# ============================================================
# PART 5: SAVE RESULTS
# ============================================================

print("\n\nPART 5: SAVING RESULTS")
print("-"*90)

results_df.to_csv(OUTPUT_DIR / 'final_station_data.csv', index=False)
comp_df.to_csv(OUTPUT_DIR / 'peripheral_vs_core_results.csv', index=False)

print(f"✓ Saved final station data")
print(f"✓ Saved comparison results")

# ============================================================
# SUMMARY
# ============================================================

print("\n\n" + "="*90)
print("ANALYSIS COMPLETE")
print("="*90)

sig_count = sum(reject)

print(f"""
✓ FINAL RESULTS:

1. PERIPHERAL vs CORE:
   {sig_count} of {len(p_values)} comparisons significant after FDR correction
   
2. STRONGEST FINDING:
   {comp_df.iloc[0]['variable']}: 
   Core = {comp_df.iloc[0]['core_mean']:.1f}, Peripheral = {comp_df.iloc[0]['peri_mean']:.1f}
   Difference = {comp_df.iloc[0]['difference']:.1f} (p={comp_df.iloc[0]['p_value']:.3f}, d={comp_df.iloc[0]['cohens_d']:.2f})

3. CENSUS MATCHING:
   {"✓ Working correctly" if core_noveh > peri_noveh + 3 else "⚠️ May need review"}
   Core: {core_noveh:.1f}% no vehicle, Peripheral: {peri_noveh:.1f}% no vehicle

📁 OUTPUT FILES:
   - {OUTPUT_DIR / 'final_station_data.csv'}
   - {OUTPUT_DIR / 'peripheral_vs_core_results.csv'}

""")

print("="*90)
