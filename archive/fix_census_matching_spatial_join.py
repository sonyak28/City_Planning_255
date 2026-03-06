"""
PROPER CENSUS TRACT MATCHING - SPATIAL JOIN METHOD
This script:
1. Downloads Bay Area census tract shapefiles
2. Performs spatial join (which tract contains each station)
3. Gets correct demographics for each station
4. Validates results
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
import requests
import zipfile
import io

print("="*90)
print("FIXING CENSUS TRACT MATCHING WITH SPATIAL JOIN")
print("="*90)

# ============================================================
# STEP 1: DOWNLOAD CENSUS TRACT SHAPEFILES
# ============================================================

print("\n1. DOWNLOADING CENSUS TRACT BOUNDARIES")
print("-"*90)

# Create directory for shapefiles
data_dir = Path("../data/census_shapefiles")
data_dir.mkdir(parents=True, exist_ok=True)

# Download California census tracts from Census Bureau
# Using 2020 TIGER/Line files
url = "https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_06_tract.zip"

print(f"Downloading from: {url}")
print("This may take a minute...")

try:
    response = requests.get(url, timeout=60)
    
    # Extract shapefile
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        z.extractall(data_dir)
    
    print(f"✓ Downloaded and extracted to {data_dir}")
    
    # Load shapefile
    shapefile_path = data_dir / "tl_2020_06_tract.shp"
    ca_tracts = gpd.read_file(shapefile_path)
    
    print(f"✓ Loaded {len(ca_tracts)} California census tracts")
    
except Exception as e:
    print(f"✗ Download failed: {e}")
    print("\nAlternative: Download manually from:")
    print("https://www.census.gov/cgi-bin/geo/shapefiles/index.php")
    print("Select: 2020, Census Tracts, California")
    exit(1)


# ============================================================
# STEP 2: FILTER TO BAY AREA COUNTIES
# ============================================================

print("\n2. FILTERING TO BAY AREA COUNTIES")
print("-"*90)

# Bay Area county FIPS codes
BAY_AREA_COUNTIES = {
    '001': 'Alameda',
    '013': 'Contra Costa', 
    '041': 'Marin',
    '055': 'Napa',
    '075': 'San Francisco',
    '081': 'San Mateo',
    '085': 'Santa Clara',
    '095': 'Solano',
    '097': 'Sonoma'
}

# Filter to Bay Area (STATEFP=06 for CA, COUNTYFP in our list)
bay_area_tracts = ca_tracts[
    (ca_tracts['STATEFP'] == '06') & 
    (ca_tracts['COUNTYFP'].isin(BAY_AREA_COUNTIES.keys()))
].copy()

print(f"Bay Area tracts: {len(bay_area_tracts)}")

# Add county name for readability
bay_area_tracts['county_name'] = bay_area_tracts['COUNTYFP'].map(BAY_AREA_COUNTIES)

# Display sample
print("\nSample tracts:")
print(bay_area_tracts[['GEOID', 'NAME', 'county_name']].head())


# ============================================================
# STEP 3: LOAD YOUR STATION DATA
# ============================================================

print("\n3. LOADING STATION DATA")
print("-"*90)

# Load your transit stations
stations = pd.read_csv("../data/transit_gdf.csv")
print(f"Loaded {len(stations)} stations")

# Convert to GeoDataFrame
stations_gdf = gpd.GeoDataFrame(
    stations,
    geometry=gpd.points_from_xy(stations['longitude'], stations['latitude']),
    crs='EPSG:4326'  # WGS84 (lat/lon)
)

print(f"Created GeoDataFrame with {len(stations_gdf)} stations")

# Make sure both use same CRS
bay_area_tracts = bay_area_tracts.to_crs('EPSG:4326')

print("\nSample stations:")
print(stations_gdf[['name', 'agency', 'latitude', 'longitude']].head())


# ============================================================
# STEP 4: SPATIAL JOIN - WHICH TRACT CONTAINS EACH STATION?
# ============================================================

print("\n4. PERFORMING SPATIAL JOIN")
print("-"*90)

# This finds which polygon (tract) each point (station) falls inside
stations_with_tracts = gpd.sjoin(
    stations_gdf,
    bay_area_tracts[['GEOID', 'NAME', 'county_name', 'geometry']],
    how='left',
    predicate='within'
)

# Check for stations that didn't match
unmatched = stations_with_tracts['GEOID'].isna().sum()

if unmatched > 0:
    print(f"⚠️  {unmatched} stations did not match to any tract")
    print("These stations may be:")
    print("  - On water (ferry terminals)")
    print("  - Outside Bay Area")
    print("  - Have incorrect coordinates")
    print("\nUnmatched stations:")
    print(stations_with_tracts[stations_with_tracts['GEOID'].isna()][
        ['name', 'agency', 'latitude', 'longitude']
    ])
else:
    print(f"✓ All {len(stations_with_tracts)} stations matched to census tracts")

# Display matches
print("\nSample matches:")
print(stations_with_tracts[['name', 'agency', 'GEOID', 'NAME', 'county_name']].head(10))


# ============================================================
# STEP 5: GET CENSUS DATA FOR THESE TRACTS
# ============================================================

print("\n5. DOWNLOADING CENSUS DATA FROM API")
print("-"*90)

# You can get a free Census API key at: https://api.census.gov/data/key_signup.html
# For now, we'll try without a key (limited to 500 requests/day)

# Get unique GEOIDs we need
tract_geoids = stations_with_tracts['GEOID'].dropna().unique()
print(f"Need census data for {len(tract_geoids)} unique tracts")

# ACS 5-year estimates (2022) - most recent complete dataset
# Variables we want:
census_vars = {
    'B01003_001E': 'total_pop',                    # Total population
    'B19013_001E': 'median_household_income',      # Median household income
    'B25044_001E': 'total_households',             # Total households
    'B25044_003E': 'households_no_vehicle_owner',  # Owner-occupied, no vehicle
    'B25044_010E': 'households_no_vehicle_renter', # Renter-occupied, no vehicle
    'B02001_001E': 'total_pop_race',               # Total pop (for race)
    'B02001_002E': 'pop_white_alone',              # White alone
}

var_list = ','.join(census_vars.keys())

# Download in chunks (to avoid API limits)
census_data_list = []

print("Downloading census data...")

# California FIPS = 06
for county_fips in BAY_AREA_COUNTIES.keys():
    url = f"https://api.census.gov/data/2022/acs/acs5"
    params = {
        'get': var_list,
        'for': 'tract:*',
        'in': f'state:06 county:{county_fips}'
    }
    
    # If you have an API key, add it here:
    # params['key'] = 'YOUR_API_KEY_HERE'
    
    try:
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # Convert to DataFrame
            df = pd.DataFrame(data[1:], columns=data[0])
            census_data_list.append(df)
            
            print(f"  ✓ {BAY_AREA_COUNTIES[county_fips]}: {len(df)} tracts")
        else:
            print(f"  ✗ {BAY_AREA_COUNTIES[county_fips]}: API error {response.status_code}")
            
    except Exception as e:
        print(f"  ✗ {BAY_AREA_COUNTIES[county_fips]}: {e}")

if census_data_list:
    census_data = pd.concat(census_data_list, ignore_index=True)
    print(f"\n✓ Downloaded census data for {len(census_data)} tracts")
else:
    print("\n✗ Failed to download census data")
    print("Get a free API key at: https://api.census.gov/data/key_signup.html")
    print("Then add it to the script where indicated")
    exit(1)


# ============================================================
# STEP 6: CLEAN AND CALCULATE DERIVED VARIABLES
# ============================================================

print("\n6. PROCESSING CENSUS DATA")
print("-"*90)

# Create GEOID (state + county + tract)
census_data['GEOID'] = (
    census_data['state'] + 
    census_data['county'] + 
    census_data['tract']
)

# Convert to numeric
for var in census_vars.keys():
    census_data[var] = pd.to_numeric(census_data[var], errors='coerce')

# Rename to friendly names
census_data = census_data.rename(columns=census_vars)

# Calculate derived variables
census_data['households_no_vehicle'] = (
    census_data['households_no_vehicle_owner'].fillna(0) + 
    census_data['households_no_vehicle_renter'].fillna(0)
)

census_data['pct_no_vehicle'] = (
    census_data['households_no_vehicle'] / census_data['total_households'] * 100
).replace([np.inf, -np.inf], np.nan)

census_data['pct_nonwhite'] = (
    (census_data['total_pop_race'] - census_data['pop_white_alone']) / 
    census_data['total_pop_race'] * 100
).replace([np.inf, -np.inf], np.nan)

# Keep only what we need
census_final = census_data[[
    'GEOID',
    'total_pop',
    'median_household_income',
    'total_households', 
    'households_no_vehicle',
    'pct_no_vehicle',
    'pct_nonwhite'
]].copy()

# Rename for consistency
census_final = census_final.rename(columns={
    'median_household_income': 'median_income'
})

print(f"✓ Processed {len(census_final)} tracts")
print("\nSample data:")
print(census_final.head())


# ============================================================
# STEP 7: JOIN CENSUS DATA TO STATIONS
# ============================================================

print("\n7. JOINING CENSUS DATA TO STATIONS")
print("-"*90)

# Merge census data with stations (by GEOID from spatial join)
stations_final = stations_with_tracts.merge(
    census_final,
    on='GEOID',
    how='left'
)

# Check for missing data
missing = stations_final[['median_income', 'pct_no_vehicle', 'pct_nonwhite']].isna().sum()
print(f"Missing values after join:")
print(missing)

# Convert to regular DataFrame (don't need geometry anymore)
stations_final = pd.DataFrame(stations_final.drop(columns='geometry'))

print(f"\n✓ Final dataset: {len(stations_final)} stations with census data")


# ============================================================
# STEP 8: VALIDATION - CHECK IF RESULTS MAKE SENSE
# ============================================================

print("\n8. VALIDATION CHECKS")
print("-"*90)

# Check specific stations we know should have high % no vehicle
test_stations = [
    '24th St. Mission',
    'Civic Center/UN Plaza',
    'Powell St.',
    'Montgomery St.',
    'Embarcadero'
]

print("\nDowntown SF stations (should have 25-45% no vehicle):")
print(f"{'Station':<30} {'% No Vehicle':<15} {'Median Income':<15} {'GEOID'}")
print("-"*75)

for station_name in test_stations:
    match = stations_final[stations_final['name'].str.contains(station_name, na=False)]
    if len(match) > 0:
        row = match.iloc[0]
        print(f"{row['name']:<30} {row['pct_no_vehicle']:>14.1f}% "
              f"${row['median_income']:>13,.0f}  {row['GEOID']}")

# Compare core vs peripheral
stations_final['station_type'] = stations_final.apply(
    lambda row: 'peripheral' if any(
        city in str(row.get('city', '')).lower() 
        for city in ['antioch', 'pittsburg', 'concord', 'walnut creek', 
                     'san jose', 'milpitas', 'fremont', 'dublin', 'pleasanton']
    ) else 'core',
    axis=1
)

core = stations_final[stations_final['station_type'] == 'core']
peri = stations_final[stations_final['station_type'] == 'peripheral']

print(f"\nCore vs Peripheral comparison:")
print(f"{'Metric':<30} {'Core Mean':<15} {'Peripheral Mean':<15} {'Expected?'}")
print("-"*75)

print(f"{'% No Vehicle':<30} {core['pct_no_vehicle'].mean():>14.1f}% "
      f"{peri['pct_no_vehicle'].mean():>14.1f}%  {'✓ Core should be higher' if core['pct_no_vehicle'].mean() > peri['pct_no_vehicle'].mean() + 3 else '⚠️ Problem!'}")

print(f"{'Median Income':<30} ${core['median_income'].mean():>13,.0f} "
      f"${peri['median_income'].mean():>13,.0f}  {'✓ Varies'}")

print(f"{'% Non-white':<30} {core['pct_nonwhite'].mean():>14.1f}% "
      f"{peri['pct_nonwhite'].mean():>14.1f}%  {'✓ Varies'}")


# ============================================================
# STEP 9: SAVE CORRECTED DATA
# ============================================================

print("\n9. SAVING CORRECTED DATA")
print("-"*90)

# Save station data with correct census demographics
output_path = Path("../data/stations_with_correct_census.csv")
stations_final.to_csv(output_path, index=False)

print(f"✓ Saved to: {output_path}")

# Save just the census data for reference
census_output = Path("../data/bay_area_census_correct.csv")
census_final.to_csv(census_output, index=False)

print(f"✓ Saved census data to: {census_output}")

# Save tract shapefile for mapping
tracts_output = Path("../data/bay_area_tracts.geojson")
bay_area_tracts.to_file(tracts_output, driver='GeoJSON')

print(f"✓ Saved tract boundaries to: {tracts_output}")


# ============================================================
# SUMMARY
# ============================================================

print("\n" + "="*90)
print("CENSUS MATCHING COMPLETE")
print("="*90)

if core['pct_no_vehicle'].mean() > peri['pct_no_vehicle'].mean() + 3:
    print("\n✓ SUCCESS! Demographics now make sense:")
    print(f"  - Core stations: {core['pct_no_vehicle'].mean():.1f}% no vehicle")
    print(f"  - Peripheral stations: {peri['pct_no_vehicle'].mean():.1f}% no vehicle")
    print("\n✓ Spatial join is working correctly")
    print("\n✓ Ready for statistical analysis with corrected demographics")
else:
    print("\n⚠️  WARNING: Results still look suspicious")
    print("  Check individual station matches manually")

print(f"\nNext steps:")
print("  1. Review validation output above")
print("  2. Check a few stations manually on censusreporter.org")
print("  3. Run statistical analysis with corrected data")
print("\n" + "="*90)
