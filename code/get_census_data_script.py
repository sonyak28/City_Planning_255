"""
Bay Area Census Pipeline
Data from 2024 ACS
============================================================================

  American Community Survey 2024
  ─────────────────────────────────────
  Source: API call: https://api.census.gov/data/2024/acs/acs5?get=NAME,group(B01001)&for=us:1&key=YOUR_KEY_GOES_HERE


Usage:
  python get_census_data_script.py

Outputs:
  census_tract_data_2024_clean.py
"""

import requests
import pandas as pd
import numpy as np

API_KEY = "7b4a89318687b3fe27be640b5333d3beb7d456e7"
BASE_URL = "https://api.census.gov/data/2024/acs/acs5"


# Bay Area counties (FIPS)
bay_area_counties = "001,013,041,055,075,081,085,095,097"

# Bay Area FIPS Map
county_names = {
    "001": "Alameda", "013": "Contra Costa", "041": "Marin",
    "055": "Napa", "075": "San Francisco", "081": "San Mateo",
    "085": "Santa Clara", "095": "Solano", "097": "Sonoma"
}

# Variables to pull
variables = [
    "NAME",
    # --- Population & Race ---
    "B01003_001E",   # total_pop
    "B01002_001E",   # median_age
    "B02001_001E",   # total_pop_race (denominator)
    "B02001_002E",   # white_alone
    "B02001_003E",   # black_alone
    "B02001_004E",   # aian_alone (American Indian/Alaska Native)
    "B02001_005E",   # asian_alone
    "B02001_006E",   # nhpi_alone (Native Hawaiian/Pacific Islander)
    "B02001_007E",   # other_race_alone
    "B02001_008E",   # two_or_more_races
    # --- Income & Poverty ---
    "B19013_001E",   # median_household_income
    "B19301_001E",   # per_capita_income
    "B17001_001E",   # total_pop_poverty_calc (denominator)
    "B17001_002E",   # pop_below_poverty
    # --- Housing ---
    "B25001_001E",   # total_housing_units
    "B25003_001E",   # total_occupied_units
    "B25003_002E",   # owner_occupied
    "B25003_003E",   # renter_occupied
    "B25044_001E",   # total_households (vehicle availability)
    "B25044_003E",   # owner_occ_no_vehicle
    "B25044_010E",   # renter_occ_no_vehicle
    "B25064_001E",   # median_gross_rent
    "B25077_001E",   # median_home_value
    # --- Commute & Transportation ---
    "B08301_001E",   # total_workers_16plus
    "B08301_003E",   # drove_alone
    "B08301_010E",   # public_transit_commuters
    "B08301_018E",   # bicycle_commuters
    "B08301_019E",   # walked_commuters
    "B08301_021E",   # worked_from_home
    "B08135_001E",   # aggregate_travel_time (use with B08301_001E for mean)
    # --- Employment ---
    "B23025_002E",   # labor_force
    "B23025_004E",   # employed
    "B23025_005E",   # unemployed
    # --- Education ---
    "B15003_001E",   # pop_25plus (denominator)
    "B15003_022E",   # bachelors_degree
    "B15003_023E",   # masters_degree
    "B15003_024E",   # professional_degree
    "B15003_025E",   # doctorate_degree
    # --- Immigration & Language ---
    "B05002_013E",   # foreign_born
    "B05002_001E",   # total_pop_nativity (denominator)
]

params = {
    "get": ",".join(variables),
    "for": "tract:*",
    "in": f"state:06 county:{bay_area_counties}",
    "key": API_KEY
}

# Get data
response = requests.get(BASE_URL, params=params)
data = response.json()

# Convert data to pandas dataframe
df = pd.DataFrame(data[1:], columns=data[0])

# Rename columns
rename_map = {
    "B01003_001E": "total_pop",
    "B01002_001E": "median_age",
    "B02001_001E": "total_pop_race",
    "B02001_002E": "white_alone",
    "B02001_003E": "black_alone",
    "B02001_004E": "aian_alone",
    "B02001_005E": "asian_alone",
    "B02001_006E": "nhpi_alone",
    "B02001_007E": "other_race_alone",
    "B02001_008E": "two_or_more_races",
    "B19013_001E": "median_household_income",
    "B19301_001E": "per_capita_income",
    "B17001_001E": "total_pop_poverty_calc",
    "B17001_002E": "pop_below_poverty",
    "B25001_001E": "total_housing_units",
    "B25003_001E": "total_occupied_units",
    "B25003_002E": "owner_occupied",
    "B25003_003E": "renter_occupied",
    "B25044_001E": "total_households",
    "B25044_003E": "owner_occ_no_vehicle",
    "B25044_010E": "renter_occ_no_vehicle",
    "B25064_001E": "median_gross_rent",
    "B25077_001E": "median_home_value",
    "B08301_001E": "total_workers_16plus",
    "B08301_003E": "drove_alone",
    "B08301_010E": "public_transit_commuters",
    "B08301_018E": "bicycle_commuters",
    "B08301_019E": "walked_commuters",
    "B08301_021E": "worked_from_home",
    "B08135_001E": "aggregate_travel_time_mins",
    "B23025_002E": "labor_force",
    "B23025_004E": "employed",
    "B23025_005E": "unemployed",
    "B15003_001E": "pop_25plus",
    "B15003_022E": "bachelors_degree",
    "B15003_023E": "masters_degree",
    "B15003_024E": "professional_degree",
    "B15003_025E": "doctorate_degree",
    "B05002_013E": "foreign_born",
    "B05002_001E": "total_pop_nativity",
}

df = df.rename(columns=rename_map)

# Make sure numerical columns remain numerical
# Replace census data null values with nan
numeric_cols = list(rename_map.values())
df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
df[numeric_cols] = df[numeric_cols].replace(-666666666, np.nan)


# Engineer new columns for analysis
df["GEOID"] = df["state"] + df["county"] + df["tract"]
df["county_name"] = df["county"].map(county_names)

# ── Vehicles ──
df["households_no_vehicle"] = df["owner_occ_no_vehicle"] + df["renter_occ_no_vehicle"]
df["pct_no_vehicle"] = (df["households_no_vehicle"] / df["total_households"] * 100).round(2)

# ── Race/Ethnicity ──
df["pop_nonwhite"] = df["total_pop_race"] - df["white_alone"]
df["pct_nonwhite"] = (df["pop_nonwhite"] / df["total_pop_race"] * 100).round(2)
df["pct_white"] = (df["white_alone"] / df["total_pop_race"] * 100).round(2)
df["pct_black"] = (df["black_alone"] / df["total_pop_race"] * 100).round(2)
df["pct_asian"] = (df["asian_alone"] / df["total_pop_race"] * 100).round(2)

# ── Poverty ──
df["poverty_rate"] = (df["pop_below_poverty"] / df["total_pop_poverty_calc"] * 100).round(2)

# ── Housing ──
df["pct_renter"] = (df["renter_occupied"] / df["total_occupied_units"] * 100).round(2)
df["pct_owner"] = (df["owner_occupied"] / df["total_occupied_units"] * 100).round(2)

# ── Commute / Transit ──
df["pct_transit_commute"] = (df["public_transit_commuters"] / df["total_workers_16plus"] * 100).round(2)
df["pct_drove_alone"] = (df["drove_alone"] / df["total_workers_16plus"] * 100).round(2)
df["pct_bike_commute"] = (df["bicycle_commuters"] / df["total_workers_16plus"] * 100).round(2)
df["pct_walk_commute"] = (df["walked_commuters"] / df["total_workers_16plus"] * 100).round(2)
df["pct_wfh"] = (df["worked_from_home"] / df["total_workers_16plus"] * 100).round(2)
df["mean_travel_time_mins"] = (df["aggregate_travel_time_mins"] / df["total_workers_16plus"]).round(2)

# ── Employment ──
df["unemployment_rate"] = (df["unemployed"] / df["labor_force"] * 100).round(2)

# -- Education --
df["pop_bachelors_plus"] = (df["bachelors_degree"] + df["masters_degree"] +
                                df["professional_degree"] + df["doctorate_degree"])
df["pct_bachelors_plus"] = (df["pop_bachelors_plus"] / df["pop_25plus"] * 100).round(2)

# -- Immigration/Language --
df["pct_foreign_born"] = (df["foreign_born"] / df["total_pop_nativity"] * 100).round(2)


# Save census data into data folder
df.to_csv('../data/census_tract_data_2024_clean.csv', index=False)
