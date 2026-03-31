"""
transit_equity.census
=====================
Constants and transformation helpers for ACS census data.

Public API
----------
BAY_AREA_COUNTIES : dict
    FIPS county code → county name for the nine Bay Area counties.

CENSUS_RENAME_MAP : dict
    ACS variable code → human-readable column name.

add_derived_columns(df) -> pd.DataFrame
    Engineer pct_no_vehicle, pct_nonwhite, poverty_rate, and all other
    derived rate columns used by the analysis.
"""

import numpy as np
import pandas as pd

# Constants

BAY_AREA_COUNTIES: dict[str, str] = {
    "001": "Alameda",
    "013": "Contra Costa",
    "041": "Marin",
    "055": "Napa",
    "075": "San Francisco",
    "081": "San Mateo",
    "085": "Santa Clara",
    "095": "Solano",
    "097": "Sonoma",
}

# Maps raw ACS variable codes to readable column names
CENSUS_RENAME_MAP: dict[str, str] = {
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

# ACS sentinel for missing / not applicable
_ACS_MISSING = -666_666_666


# Derived columns

def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived rate / percentage columns to a raw ACS DataFrame.

    Expects the DataFrame to already have columns renamed via
    ``CENSUS_RENAME_MAP``.  All numeric columns are coerced and ACS missing
    sentinels (``-666666666``) are replaced with ``NaN`` before any
    calculation.

    Parameters
    ----------
    df : pd.DataFrame
        Raw ACS data with renamed columns (output of ``get_census_data.py``
        before derived-column engineering).

    Returns
    -------
    pd.DataFrame
        Same DataFrame with additional derived columns appended in-place
        (a copy is returned).
    """
    df = df.copy()

    # Coerce and clean raw numeric columns
    numeric_cols = list(CENSUS_RENAME_MAP.values())
    existing_numeric = [c for c in numeric_cols if c in df.columns]
    df[existing_numeric] = df[existing_numeric].apply(
        pd.to_numeric, errors="coerce"
    )
    df[existing_numeric] = df[existing_numeric].replace(_ACS_MISSING, np.nan)

    # GEOID
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    df["county_name"] = df["county"].map(BAY_AREA_COUNTIES)

    # Vehicle availability
    df["households_no_vehicle"] = (
        df["owner_occ_no_vehicle"] + df["renter_occ_no_vehicle"]
    )
    df["pct_no_vehicle"] = (
        df["households_no_vehicle"] / df["total_households"] * 100
    ).round(2)

    # Race / ethnicity
    df["pop_nonwhite"]  = df["total_pop_race"] - df["white_alone"]
    df["pct_nonwhite"]  = (df["pop_nonwhite"]  / df["total_pop_race"] * 100).round(2)
    df["pct_white"]     = (df["white_alone"]   / df["total_pop_race"] * 100).round(2)
    df["pct_black"]     = (df["black_alone"]   / df["total_pop_race"] * 100).round(2)
    df["pct_asian"]     = (df["asian_alone"]   / df["total_pop_race"] * 100).round(2)

    # Poverty
    df["poverty_rate"] = (
        df["pop_below_poverty"] / df["total_pop_poverty_calc"] * 100
    ).round(2)

    # Housing tenure
    df["pct_renter"] = (df["renter_occupied"] / df["total_occupied_units"] * 100).round(2)
    df["pct_owner"]  = (df["owner_occupied"]  / df["total_occupied_units"] * 100).round(2)

    # Commute / transit
    df["pct_transit_commute"] = (
        df["public_transit_commuters"] / df["total_workers_16plus"] * 100
    ).round(2)
    df["pct_drove_alone"]  = (df["drove_alone"]          / df["total_workers_16plus"] * 100).round(2)
    df["pct_bike_commute"] = (df["bicycle_commuters"]    / df["total_workers_16plus"] * 100).round(2)
    df["pct_walk_commute"] = (df["walked_commuters"]     / df["total_workers_16plus"] * 100).round(2)
    df["pct_wfh"]          = (df["worked_from_home"]     / df["total_workers_16plus"] * 100).round(2)
    df["mean_travel_time_mins"] = (
        df["aggregate_travel_time_mins"] / df["total_workers_16plus"]
    ).round(2)

    # Employment
    df["unemployment_rate"] = (df["unemployed"] / df["labor_force"] * 100).round(2)

    # Education
    df["pop_bachelors_plus"] = (
        df["bachelors_degree"]
        + df["masters_degree"]
        + df["professional_degree"]
        + df["doctorate_degree"]
    )
    df["pct_bachelors_plus"] = (
        df["pop_bachelors_plus"] / df["pop_25plus"] * 100
    ).round(2)

    # Immigration
    df["pct_foreign_born"] = (
        df["foreign_born"] / df["total_pop_nativity"] * 100
    ).round(2)

    return df