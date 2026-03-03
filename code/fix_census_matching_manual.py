"""
ALTERNATIVE: MANUAL CENSUS TRACT MATCHING
Use this if the automatic download doesn't work
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path

print("="*90)
print("MANUAL CENSUS TRACT MATCHING GUIDE")
print("="*90)

print("""
STEP-BY-STEP INSTRUCTIONS:

1. DOWNLOAD CENSUS TRACT SHAPEFILE
   ----------------------------------
   Go to: https://www.census.gov/cgi-bin/geo/shapefiles/index.php
   
   Select:
   - Year: 2020
   - Layer Type: Census Tracts
   - State: California
   
   Click "Download" and extract the ZIP file to: ../data/census_shapefiles/
   
   You should have these files:
   - tl_2020_06_tract.shp
   - tl_2020_06_tract.shx
   - tl_2020_06_tract.dbf
   - tl_2020_06_tract.prj


2. GET CENSUS API KEY (FREE)
   ---------------------------
   Go to: https://api.census.gov/data/key_signup.html
   
   Enter your email and organization: "UC Berkeley Student Research"
   
   You'll receive a key like: abc123def456ghi789jkl012mno345pqr678stu901
   
   Copy it and paste below where it says YOUR_API_KEY_HERE


3. RUN THIS SCRIPT
   ----------------
   python fix_census_matching_manual.py
   
""")

# Ask user to confirm they have the files
response = input("\nDo you have the shapefile downloaded? (yes/no): ").lower()

if response != 'yes':
    print("\nPlease download the shapefile first, then run this script again.")
    exit()

api_key = input("\nEnter your Census API key (or press Enter to skip): ").strip()

if not api_key:
    print("\n⚠️  No API key provided. You can still do spatial join,")
    print("   but you'll need to get census data separately.")
    use_api = False
else:
    use_api = True
    print(f"\n✓ Using API key: {api_key[:10]}...")


# ============================================================
# LOAD SHAPEFILE
# ============================================================

print("\n" + "="*90)
print("LOADING CENSUS TRACT SHAPEFILE")
print("="*90)

shapefile_path = Path("../data/census_shapefiles/tl_2020_06_tract.shp")

if not shapefile_path.exists():
    print(f"\n✗ Shapefile not found at: {shapefile_path}")
    print("\nPlease make sure you extracted the ZIP file to the correct location:")
    print("  ../data/census_shapefiles/")
    exit(1)

try:
    ca_tracts = gpd.read_file(shapefile_path)
    print(f"✓ Loaded {len(ca_tracts)} California census tracts")
except Exception as e:
    print(f"✗ Error loading shapefile: {e}")
    exit(1)

# Filter to Bay Area
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

bay_area_tracts = ca_tracts[
    (ca_tracts['STATEFP'] == '06') & 
    (ca_tracts['COUNTYFP'].isin(BAY_AREA_COUNTIES.keys()))
].copy()

print(f"✓ Filtered to {len(bay_area_tracts)} Bay Area tracts")


# ============================================================
# LOAD STATIONS
# ============================================================

print("\n" + "="*90)
print("LOADING STATION DATA")
print("="*90)

stations = pd.read_csv("../data/transit_gdf.csv")
print(f"✓ Loaded {len(stations)} stations")

stations_gdf = gpd.GeoDataFrame(
    stations,
    geometry=gpd.points_from_xy(stations['longitude'], stations['latitude']),
    crs='EPSG:4326'
)

bay_area_tracts = bay_area_tracts.to_crs('EPSG:4326')


# ============================================================
# SPATIAL JOIN
# ============================================================

print("\n" + "="*90)
print("PERFORMING SPATIAL JOIN")
print("="*90)

stations_with_tracts = gpd.sjoin(
    stations_gdf,
    bay_area_tracts[['GEOID', 'NAME', 'COUNTYFP', 'geometry']],
    how='left',
    predicate='within'
)

unmatched = stations_with_tracts['GEOID'].isna().sum()

if unmatched > 0:
    print(f"⚠️  {unmatched} stations didn't match:")
    print(stations_with_tracts[stations_with_tracts['GEOID'].isna()][
        ['name', 'agency', 'latitude', 'longitude']
    ])
else:
    print(f"✓ All {len(stations_with_tracts)} stations matched")

print("\nSample matches:")
print(stations_with_tracts[['name', 'GEOID', 'NAME']].head(10))


# ============================================================
# GET CENSUS DATA
# ============================================================

if use_api:
    print("\n" + "="*90)
    print("DOWNLOADING CENSUS DATA FROM API")
    print("="*90)
    
    import requests
    
    census_vars = {
        'B01003_001E': 'total_pop',
        'B19013_001E': 'median_household_income',
        'B25044_001E': 'total_households',
        'B25044_003E': 'households_no_vehicle_owner',
        'B25044_010E': 'households_no_vehicle_renter',
        'B02001_001E': 'total_pop_race',
        'B02001_002E': 'pop_white_alone',
    }
    
    var_list = ','.join(census_vars.keys())
    census_data_list = []
    
    for county_fips, county_name in BAY_AREA_COUNTIES.items():
        url = "https://api.census.gov/data/2022/acs/acs5"
        params = {
            'get': var_list,
            'for': 'tract:*',
            'in': f'state:06 county:{county_fips}',
            'key': api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                df = pd.DataFrame(data[1:], columns=data[0])
                census_data_list.append(df)
                print(f"  ✓ {county_name}: {len(df)} tracts")
            else:
                print(f"  ✗ {county_name}: Error {response.status_code}")
                
        except Exception as e:
            print(f"  ✗ {county_name}: {e}")
    
    if census_data_list:
        census_data = pd.concat(census_data_list, ignore_index=True)
        
        # Process
        census_data['GEOID'] = (
            census_data['state'] + 
            census_data['county'] + 
            census_data['tract']
        )
        
        for var in census_vars.keys():
            census_data[var] = pd.to_numeric(census_data[var], errors='coerce')
        
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
        
        census_final = census_data[[
            'GEOID',
            'total_pop',
            'median_household_income',
            'total_households',
            'households_no_vehicle',
            'pct_no_vehicle',
            'pct_nonwhite'
        ]].copy()
        
        census_final = census_final.rename(columns={
            'median_household_income': 'median_income'
        })
        
        # Join to stations
        stations_final = stations_with_tracts.merge(
            census_final,
            on='GEOID',
            how='left'
        )
        
        # Save
        stations_final_df = pd.DataFrame(stations_final.drop(columns='geometry'))
        stations_final_df.to_csv("../data/stations_with_correct_census.csv", index=False)
        
        print(f"\n✓ Saved: ../data/stations_with_correct_census.csv")
        
        # Validation
        print("\n" + "="*90)
        print("VALIDATION")
        print("="*90)
        
        test_stations = ['24th St. Mission', 'Civic Center', 'Powell']
        
        print(f"\n{'Station':<30} {'% No Vehicle':<15} {'Income':<15}")
        print("-"*60)
        for name in test_stations:
            match = stations_final_df[stations_final_df['name'].str.contains(name, na=False)]
            if len(match) > 0:
                row = match.iloc[0]
                print(f"{row['name']:<30} {row['pct_no_vehicle']:>14.1f}% "
                      f"${row['median_income']:>13,.0f}")
        
        print("\n✓ COMPLETE! Census data successfully matched to stations")
        
    else:
        print("\n✗ Failed to download census data")
        
else:
    # Save just the tract assignments
    stations_with_tracts_df = pd.DataFrame(
        stations_with_tracts.drop(columns='geometry')
    )
    stations_with_tracts_df.to_csv("../data/stations_with_geoid.csv", index=False)
    
    print(f"\n✓ Saved tract assignments to: ../data/stations_with_geoid.csv")
    print("\nTo get census data:")
    print("1. Get API key from: https://api.census.gov/data/key_signup.html")
    print("2. Run this script again with your API key")
    print("\nOR download data manually from:")
    print("https://data.census.gov/")

print("\n" + "="*90)
