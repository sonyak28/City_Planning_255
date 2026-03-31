"""
scripts/get_census_data.py
==========================
Fetch Bay Area ACS 2024 census tract data and write a clean CSV.

Data source
-----------
American Community Survey 5-Year Estimates (2024)
API: https://api.census.gov/data/2024/acs/acs5

Output
------
../data/processed/census_tract_data_2024_clean.csv

Usage
-----
Run from the scripts/ (or code/) directory:
    python get_census_data.py
"""

import requests
import pandas as pd

# Import reusable constants and transformation logic from src/
from transit_equity.census import (
    BAY_AREA_COUNTIES,
    CENSUS_RENAME_MAP,
    add_derived_columns,
)

# Config

API_KEY  = input("Please enter your API key: ")
BASE_URL = "https://api.census.gov/data/2024/acs/acs5"
OUTPUT_PATH = "../data/processed/census_tract_data_2024_clean.csv"

# Comma-separated FIPS codes for the nine Bay Area counties
BAY_FIPS_STR = ",".join(BAY_AREA_COUNTIES.keys())

# All ACS variable codes we want to pull
VARIABLES = ["NAME"] + list(CENSUS_RENAME_MAP.keys())

# Fetch

params = {
    "get": ",".join(VARIABLES),
    "for": "tract:*",
    "in":  f"state:06 county:{BAY_FIPS_STR}",
    "key": API_KEY,
}

print("Fetching ACS 2024 data from Census API…")
response = requests.get(BASE_URL, params=params)
response.raise_for_status()
data = response.json()

# Parse → rename → derive

df = pd.DataFrame(data[1:], columns=data[0])
df = df.rename(columns=CENSUS_RENAME_MAP)
df = add_derived_columns(df)

# Save

df.to_csv(OUTPUT_PATH, index=False)
print(f"Saved {len(df)} tracts → {OUTPUT_PATH}")
