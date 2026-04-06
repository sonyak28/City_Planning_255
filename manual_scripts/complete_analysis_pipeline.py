"""
COMPLETE PIPELINE: Fix Census + Run Full Analysis
This combines everything into one script
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from scipy import stats
from scipy.stats import permutation_test, rankdata
from pathlib import Path
from statsmodels.stats.multitest import multipletests
from scipy.stats import entropy
from scipy.stats import mannwhitneyu
from math import radians, cos, sin, asin, sqrt
import warnings
warnings.filterwarnings('ignore')

# Configs
# Paths assume script is run from the code/ directory
CENSUS_SHAPEFILE = "../data/raw/tl_2024_06_tract/tl_2024_06_tract.shp"
STATIONS_FILE = "../data/raw/transit_gdf.csv"
AMENITIES_FILE = "../data/raw/all_amenities.csv"
OUTPUT_DIR = Path("../data/processed")


# Create output directory
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("="*90)
print("COMPLETE ANALYSIS PIPELINE WITH CORRECTED CENSUS DATA")
print("="*90)

# PART 1: FIX CENSUS MATCHING
print("\nPART 1: FIXING CENSUS TRACT MATCHING")
print("-"*90)

# Load shapefile
if not Path(CENSUS_SHAPEFILE).exists():
    print(f"ERROR: Shapefile not found at {CENSUS_SHAPEFILE}")
    print("Required: Census TIGER/Line 2020 California tract boundaries")
    print("Download: https://www.census.gov/cgi-bin/geo/shapefiles/index.php")
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

print(f"Loaded {len(bay_tracts)} Bay Area census tracts")

# Load stations
stations = pd.read_csv(STATIONS_FILE)
stations_gdf = gpd.GeoDataFrame(
    stations,
    geometry=gpd.points_from_xy(stations['longitude'], stations['latitude']),
    crs='EPSG:4326'
)

print(f"Loaded {len(stations)} stations")

# Spatial join
stations_with_tracts = gpd.sjoin(
    stations_gdf,
    bay_tracts[['GEOID', 'NAME', 'geometry']],
    how='left',
    predicate='within'
)

matched = (~stations_with_tracts['GEOID'].isna()).sum()
print(f"Matched {matched}/{len(stations_with_tracts)} stations to tracts")


census_final = pd.read_csv('../data/processed/census_tract_data_2024_clean.csv')
census_final = census_final.rename(columns={'median_household_income': 'median_income'})
census_final['GEOID'] = census_final['GEOID'].astype(str).str.zfill(11)

stations_with_census = stations_with_tracts.merge(census_final, on='GEOID', how='left')

# PART 2: CALCULATE AMENITY ACCESS
print("\n\nPART 2: CALCULATING AMENITY ACCESS")
print("-"*90)

amenities = pd.read_csv(AMENITIES_FILE)
print(f"Loaded {len(amenities)} amenities")


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
        'kindergarten': counts.get('kindergarten', 0),
        'convenience': counts.get('convenience', 0),
        'median_income': station.get('median_income'),
        'pct_no_vehicle': station.get('pct_no_vehicle'),
        'pct_nonwhite': station.get('pct_nonwhite'),
        'total_pop': station.get('total_pop'),
        'geometry' : station['geometry']
    })

results_df = pd.DataFrame(results)
# print(results_df)

# RIDERSHIP-BASED CLASSIFICATION
# Replaces the old keyword/geographic classify_station approach
 
ridership_df = pd.read_csv('../data/processed/classification_results_fy2025.csv')
 
NAME_CROSSWALK = {
    # BART
    '12th Street / Oakland City Center':    '12th St. Oakland City Center',
    '16th Street Mission':                  '16th St. Mission',
    '19th Street Oakland':                  '19th St. Oakland',
    '24th Street Mission':                  '24th St. Mission',
    'Antioch':                   'Antioch',
    'Ashby':                                'Ashby',
    'Balboa Park':                          'Balboa Park',
    'Bayfair':                              'Bay Fair',
    'Berkeley':                             'Downtown Berkeley',
    'Berryessa / North San Jos\x8e':            'Berryessa/North San Jose',
    'Castro Valley':                        'Castro Valley',
    'Civic Center':                         'Civic Center/UN Plaza',
    'Coliseum':                             'Coliseum',
    'Colma':                                'Colma',
    'Concord':                              'Concord',
    'Daly City':                            'Daly City',
    'Dublin/Pleasanton':                    'Dublin/Pleasanton',
    'El Cerrito Del Norte':                 'El Cerrito del Norte',
    'El Cerrito Plaza':                     'El Cerrito Plaza',
    'Embarcadero':                          'Embarcadero',
    'Fremont':                              'Fremont',
    'Fruitvale':                            'Fruitvale',
    'Glen Park':                            'Glen Park',
    'Hayward':                              'Hayward',
    'Lafayette':                            'Lafayette',
    'Lake Merritt':                         'Lake Merritt',
    'MacArthur':                            'MacArthur',
    'Milpitas':                             'Milpitas',
    'Montgomery Street':                    'Montgomery St.',
    'North Berkeley':                       'North Berkeley',
    'North Concord':                        'North Concord/Martinez',
    'Oakland International Airport':        'Oakland International Airport',
    'Orinda':                               'Orinda',
    'Pittsburg Center':                     'Pittsburg Center',
    'Pittsburg/Bay Point':                  'Pittsburg/Bay Point',
    'Pleasant Hill':                        'Pleasant Hill/Contra Costa Centre',
    'Powell Street':                        'Powell St.',
    'Richmond':                             'Richmond',
    'Rockridge':                            'Rockridge',
    'San Francisco International Airport':  'San Francisco International Airport',
    'San Leandro':                          'San Leandro',
    'South Hayward':                        'South Hayward',
    'Union City':                           'Union City',
    'Walnut Creek':                         'Walnut Creek',
    'Warm Springs':                         'Warm Springs/South Fremont',
    'West Dublin/Pleasanton':               'West Dublin/Pleasanton',
    'West Oakland':                         'West Oakland',
    # Caltrain
    '22nd Street':                          '22nd Street',
    'Bayshore':                             'Bayshore',
    'Belmont':                              'Belmont',
    'Blossom Hill':                         'Blossom Hill Caltrain Station',
    'Broadway':                             'Broadway',
    'Burlingame':                           'Burlingame',
    'California Ave':                       'California Avenue',
    'Capitol':                              'Capitol Caltrain Station',
    'College Park':                         'College Park',
    'Gilroy':                               'Gilroy',
    'Hayward Park':                         'Hayward Park',
    'Hillsdale':                            'Hillsdale',
    'Lawrence':                             'Lawrence',
    'Menlo Park':                           'Menlo Park',
    'Morgan Hill':                          'Morgan Hill',
    'Mountain View':                        'Mountain View',
    'Palo Alto':                            'Palo Alto',
    'Redwood City':                         'Redwood City',
    'San Antonio':                          'San Antonio',
    'San Carlos':                           'San Carlos',
    'San Francisco':                        'San Francisco Caltrain Station',
    'San Jose Diridon':                     'San Jose Diridon',
    'San Martin':                           'San Martin',
    'San Mateo':                            'San Mateo',
    'Santa Clara':                          'Santa Clara Caltrain Station',
    'Sunnyvale':                            'Sunnyvale',
    'Tamien':                               'Tamien Caltrain Station',
}
 
ridership_df['station_name'] = ridership_df['station'].map(NAME_CROSSWALK)
 
# Handle duplicate station names across agencies
ridership_df.loc[
    (ridership_df['station'] == 'Millbrae') & (ridership_df['agency'] == 'BART'),
    'station_name'] = 'Millbrae'
ridership_df.loc[
    (ridership_df['station'] == 'Millbrae') & (ridership_df['agency'] == 'Caltrain'),
    'station_name'] = 'Millbrae'
ridership_df.loc[
    (ridership_df['station'] == 'South San Francisco') & (ridership_df['agency'] == 'BART'),
    'station_name'] = 'South San Francisco'
ridership_df.loc[
    (ridership_df['station'] == 'South San Francisco') & (ridership_df['agency'] == 'Caltrain'),
    'station_name'] = 'South San Francisco Caltrain Station'
ridership_df.loc[
    (ridership_df['station'] == 'San Bruno') & (ridership_df['agency'] == 'BART'),
    'station_name'] = 'San Bruno'
ridership_df.loc[
    (ridership_df['station'] == 'San Bruno') & (ridership_df['agency'] == 'Caltrain'),
    'station_name'] = 'San Bruno Caltrain Station'
 
unmapped = ridership_df[ridership_df['station_name'].isna()]
if len(unmapped) > 0:
    print(f"\nWARNING: {len(unmapped)} ridership stations could not be mapped:")
    print(unmapped[['station', 'agency']].to_string(index=False))
else:
    print("\nAll ridership stations mapped successfully")
 
ridership_merge = ridership_df[['station_name', 'consensus', 'avg_weekday_exits']].copy()
ridership_merge = ridership_merge.rename(columns={
    'consensus': 'station_type',
    'avg_weekday_exits': 'ridership'
})
 
results_df = results_df.merge(ridership_merge, on='station_name', how='left')

# Remove stations not in scope
EXCLUDE_STATIONS = ['Stanford', 'San Francisco International Airport']
results_df = results_df[~results_df['station_name'].isin(EXCLUDE_STATIONS)].reset_index(drop=True)
print(f"Removed {EXCLUDE_STATIONS} — {len(results_df)} stations remaining")

results_df = results_df.drop_duplicates(subset=['latitude', 'longitude'], keep='first')
 
unmatched = results_df[results_df['station_type'].isna()]
if len(unmatched) > 0:
    print(f"\nWARNING: {len(unmatched)} amenity stations did not match ridership data:")
    print(unmatched[['station_name', 'agency']].to_string(index=False))
else:
    print("All amenity stations matched to ridership classification")
 
core = results_df[results_df['station_type'] == 'core']
peri = results_df[results_df['station_type'] == 'peripheral']
 
print(f"\nClassification result: {len(core)} core, {len(peri)} peripheral")
print("\nPeripheral stations:")
print(peri[['station_name', 'agency', 'ridership']].sort_values(
    'ridership', ascending=False).to_string(index=False))
 
# GINI COEFFICIENT WITH BOOTSTRAP CONFIDENCE INTERVALS
print("\nCalculating Gini coefficient and unmet need index")
 
def calculate_gini(values):
    """Gini coefficient: 0 = perfect equality, 1 = perfect inequality."""
    sorted_values = np.sort(values)
    n = len(values)
    if n == 0:
        return np.nan
    cumsum = np.cumsum(sorted_values)
    return (2 * np.sum((np.arange(1, n+1)) * sorted_values)) / (n * cumsum[-1]) - (n + 1) / n
 
def bootstrap_gini(values, n_bootstrap=1000, ci=95):
    """Bootstrap confidence interval for Gini coefficient."""
    bootstrapped = [
        calculate_gini(np.random.choice(values, size=len(values), replace=True))
        for _ in range(n_bootstrap)
    ]
    lower = np.percentile(bootstrapped, (100 - ci) / 2)
    upper = np.percentile(bootstrapped, 100 - (100 - ci) / 2)
    return lower, upper
 
overall_gini = calculate_gini(results_df['total_amenities'].values)
core_gini    = calculate_gini(core['total_amenities'].values)
peri_gini    = calculate_gini(peri['total_amenities'].values)
 
overall_ci = bootstrap_gini(results_df['total_amenities'].values)
core_ci    = bootstrap_gini(core['total_amenities'].values)
peri_ci    = bootstrap_gini(peri['total_amenities'].values)
 
print(f"Gini (overall):    {overall_gini:.3f} (95% CI: {overall_ci[0]:.3f}–{overall_ci[1]:.3f})")
print(f"Gini (core):       {core_gini:.3f} (95% CI: {core_ci[0]:.3f}–{core_ci[1]:.3f})")
print(f"Gini (peripheral): {peri_gini:.3f} (95% CI: {peri_ci[0]:.3f}–{peri_ci[1]:.3f})")
 
# UNMET NEED INDEX — percentile rank multiplication
# High need AND low supply both required for high score 
results_df['need_pct']    = rankdata(results_df['pct_no_vehicle'].fillna(0)) / len(results_df)
results_df['supply_pct']  = rankdata(results_df['total_amenities']) / len(results_df)
results_df['supply_gap']  = 1 - results_df['supply_pct']
results_df['unmet_need_index'] = results_df['need_pct'] * results_df['supply_gap']

# Amenity Entropy (diversity score)
def amenity_entropy(row):
    """
    Shannon entropy measuring amenity diversity.
    Higher = more varied mix of amenity types
    """
    counts = [
        row["grocery"],
        row["park"],
        row["clinic"],
        row["pharmacy"],
        row["childcare"],
        row["convenience"],
        row['kindergarten'],
        row['hospital'],
        row['doctors']
    ]
    counts = [c for c in counts if c > 0]
    return entropy(counts) if counts else 0

results_df['amenity_entropy'] = results_df.apply(amenity_entropy, axis=1)
core = results_df[results_df['station_type'] == 'core']
peri = results_df[results_df['station_type'] == 'peripheral']

print(f"Calculated unmet need index for {len(results_df)} stations")
print(f"Calculated amenity entropy scores")

# PART 3: VALIDATION
print("\n\nPART 3: VALIDATION")
print("-"*90)


print(f"\nSample size: Core={len(core)}, Peripheral={len(peri)}")

print(f"\nDemographics validation:")
print(f"{'Metric':<25} {'Core':<15} {'Peripheral':<15} {'Status'}")
print("-"*70)

core_noveh = core['pct_no_vehicle'].mean()
peri_noveh = peri['pct_no_vehicle'].mean()
status = "valid" if core_noveh > peri_noveh + 3 else "error"

print(f"{'% No Vehicle':<25} {core_noveh:>14.1f}% {peri_noveh:>14.1f}%  {status}")
print(f"{'Median Income':<25} ${core['median_income'].mean():>13,.0f} "
      f"${peri['median_income'].mean():>13,.0f}")

if core_noveh > peri_noveh + 3:
    print("\nCensus matching appears correct!")
else:
    print("\nCensus matching may still have issues")

# PART 4: STATISTICAL ANALYSIS
print("\n\nPART 4: STATISTICAL ANALYSIS")
print("-"*90)

# Permutation tests
test_vars = {
    'total_amenities': 'Total Amenities',
    'grocery': 'Grocery Stores',
    'park': 'Parks',
    'clinic': 'Clinics',
    'pharmacy': 'Pharmacies',
    'hospital': "Hospital",
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
        n_resamples=10000,
        alternative='two-sided',
        random_state=42
    )
    
    # print(f'std for core:{core_vals.std()}, std for peri:{peri_vals.std()}')
    pooled_std = np.sqrt((core_vals.std()**2 + peri_vals.std()**2) / 2)
    cohens_d = (core_vals.mean() - peri_vals.mean()) / pooled_std
    glass_d = (core_vals.mean() - peri_vals.mean()) / peri_vals.std()
    
    p_values.append(res.pvalue)
    
    comparison_results.append({
        'variable': label,
        'core_mean': core_vals.mean(),
        'peri_mean': peri_vals.mean(),
        'difference': core_vals.mean() - peri_vals.mean(),
        'p_value': res.pvalue,
        'cohens_d': cohens_d,
        'glass_delta': glass_d
    })

comp_df = pd.DataFrame(comparison_results)

print(f"{'Variable':<20} {'Core':<8} {'Peri':<8} {'Diff':<8} {'p':<10} {'d':<6}")
print("-"*65)
for _, row in comp_df.iterrows():
    sig = "***" if row['p_value'] < 0.001 else "**" if row['p_value'] < 0.01 else "*" if row['p_value'] < 0.05 else ""
    print(f"{row['variable']:<20} {row['core_mean']:>7.1f} {row['peri_mean']:>7.1f} "
          f"{row['difference']:>7.1f} {row['p_value']:>9.4f} {sig:3} {row['glass_delta']:>5.2f}")

# FDR correction
reject, p_adj, _, _ = multipletests(p_values, method='fdr_bh')

print(f"\nAfter FDR correction:")
for var, p_raw, p_adjusted, sig in zip(test_vars.values(), p_values, p_adj, reject):
    print(f"{var:<20} p={p_raw:.4f} → q={p_adjusted:.4f}  {'Significant' if sig else ''}")

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
    print(f"\nAfter FDR: {sum(p_adj_corr < 0.05)}/{len(p_adj_corr)} significant")

# UNMET NEED & ENTROPY ANALYSIS
print(f"\n\nUNMET NEED ANALYSIS")
print("-"*90)

# Identify stations with highest unmet need
high_unmet_need = results_df.nlargest(10, 'unmet_need_index')[
    ['station_name', 'agency', 'station_type', 'total_amenities', 
     'pct_no_vehicle', 'unmet_need_index']
].copy()

print("\nTop 10 Stations with Highest Unmet Need:")
print("(High % no-vehicle + Low amenity count)")
print()
print(f"{'Station':<30} {'Agency':<10} {'Type':<12} {'Amenities':<12} {'% No Veh':<12} {'Unmet Need'}")
print("-"*90)
for _, row in high_unmet_need.iterrows():
    print(f"{row['station_name']:<30} {row['agency']:<10} {row['station_type']:<12} "
          f"{row['total_amenities']:<12.0f} {row['pct_no_vehicle']:<12.1f} {row['unmet_need_index']:>10.3f}")

# Entropy analysis
print(f"\n\nAMENITY DIVERSITY (ENTROPY) ANALYSIS")
print("-"*90)

core_entropy = core['amenity_entropy'].mean()
peri_entropy = peri['amenity_entropy'].mean()

print(f"\nMean amenity entropy:")
print(f"Core stations:       {core_entropy:.3f}")
print(f"Peripheral stations: {peri_entropy:.3f}")
print(f"Difference:          {core_entropy - peri_entropy:.3f}")

# Test if diversity differs
entropy_stat, entropy_p = mannwhitneyu(
    core['amenity_entropy'].dropna(), 
    peri['amenity_entropy'].dropna(),
    alternative='two-sided'
)
print(f"\nMann-Whitney U test: U={entropy_stat:.1f}, p={entropy_p:.4f}")

# Stations with most diverse amenity mix
diverse_stations = results_df.nlargest(10, 'amenity_entropy')[
    ['station_name', 'agency', 'total_amenities', 'amenity_entropy',
     'grocery', 'park', 'clinic', 'pharmacy', 'childcare', 'doctors', 
     'hospital', 'kindergarten', 'convenience']
]

print(f"\nTop 10 Most Diverse Amenity Mix (by entropy):")
print()
print(f"{'Station':<30} {'Total':<8} {'Entropy':<10} {'Groc':<6} {'Park':<6} {'Clin':<6} {'Phar':<6} {'Care':<6} {'Doc':<6} {'Hosp':<6} {'Kind':<6} {'Conv':<6}" )
print("-"*150)
for _, row in diverse_stations.iterrows():
    print(f"{row['station_name']:<30} {row['total_amenities']:<8.0f} {row['amenity_entropy']:<10.3f} "
          f"{row['grocery']:<6.0f} {row['park']:<6.0f} {row['clinic']:<6.0f} "
          f"{row['pharmacy']:<6.0f} {row['childcare']:<6.0f} {row['doctors']:<6.0f}"
          f"{row['hospital']:<6.0f} {row['kindergarten']:<6.0f} {row['convenience']:<6.0f}")

# PART 5: SAVE RESULTS
print("\n\nPART 5: SAVING RESULTS")
print("-"*90)

results_df.to_csv(OUTPUT_DIR / 'final_station_data.csv', index=False)
comp_df.to_csv(OUTPUT_DIR / 'peripheral_vs_core_results.csv', index=False)

print(f"Saved final station data")
print(f"Saved comparison results")

# SUMMARY
print("\n\n" + "="*90)
print("ANALYSIS COMPLETE")
print("="*90)

sig_count = sum(reject)

print(f"""
FINAL RESULTS:

1. PERIPHERAL vs CORE:
   {sig_count} of {len(p_values)} comparisons significant after FDR correction
   
2. STRONGEST FINDING:
   {comp_df.iloc[0]['variable']}: 
   Core = {comp_df.iloc[0]['core_mean']:.1f}, Peripheral = {comp_df.iloc[0]['peri_mean']:.1f}
   Difference = {comp_df.iloc[0]['difference']:.1f} (p={comp_df.iloc[0]['p_value']:.3f}, d={comp_df.iloc[0]['glass_delta']:.2f})

3. INEQUALITY METRICS:
   Gini coefficient: {overall_gini:.3f} (0=equality, 1=inequality)
   Highest unmet need: {high_unmet_need.iloc[0]['station_name']} ({high_unmet_need.iloc[0]['unmet_need_index']:.3f})
   
4. AMENITY DIVERSITY:
   Mean entropy: Core {core_entropy:.3f} vs Peripheral {peri_entropy:.3f}
   Diversity difference: {'Significant' if entropy_p < 0.05 else 'Not significant'} (p={entropy_p:.4f})

5. CENSUS MATCHING:
   {"Working correctly" if core_noveh > peri_noveh + 3 else "May need review"}
   Core: {core_noveh:.1f}% no vehicle, Peripheral: {peri_noveh:.1f}% no vehicle

OUTPUT FILES:
   - {OUTPUT_DIR / 'final_station_data.csv'}
   - {OUTPUT_DIR / 'peripheral_vs_core_results.csv'}

""")

print("="*90)
