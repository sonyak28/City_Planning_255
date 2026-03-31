"""
transit_equity.amenities
========================
Functions for computing amenity access around transit stations.

Public API
----------
haversine(lon1, lat1, lon2, lat2) -> float
    Great-circle distance in metres between two lat/lon points.

count_amenities_for_station(station, amenities_df, radius_m) -> dict
    Count amenities within `radius_m` metres of a station point.

build_station_amenity_records(stations_df, amenities_df, radius_m) -> list[dict]
    Iterate over every station and return a list of amenity-count dicts
    ready to be turned into a DataFrame.
"""

from math import asin, cos, radians, sin, sqrt

import pandas as pd

# Default search radius: half a mile in metres
HALF_MILE_M: float = 804.67


# Distance helper

def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    Return the great-circle distance in **metres** between two points
    given as (longitude, latitude) pairs in decimal degrees.

    Uses the haversine formula with Earth radius = 6 371 000 m.

    Parameters
    ----------
    lon1, lat1 : float
        Longitude and latitude of the first point (decimal degrees).
    lon2, lat2 : float
        Longitude and latitude of the second point (decimal degrees).

    Returns
    -------
    float
        Distance in metres.
    """
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * 6_371_000


# Per-station amenity counting

def count_amenities_for_station(
    station_lon: float,
    station_lat: float,
    amenities_df: pd.DataFrame,
    radius_m: float = HALF_MILE_M,
) -> dict:
    """
    Count amenities within *radius_m* metres of a single station point.

    Parameters
    ----------
    station_lon, station_lat : float
        Longitude / latitude of the station.
    amenities_df : pd.DataFrame
        Must contain columns ``longitude``, ``latitude``, and ``category``.
    radius_m : float, optional
        Search radius in metres.  Defaults to ``HALF_MILE_M`` (804.67 m).

    Returns
    -------
    dict
        Keys: ``total``, ``grocery``, ``park``, ``clinic``, ``pharmacy``,
        ``hospital``, ``doctors``, ``childcare``.
    """
    amenities_df = amenities_df.copy()
    amenities_df["distance"] = amenities_df.apply(
        lambda r: haversine(station_lon, station_lat, r["longitude"], r["latitude"]),
        axis=1,
    )
    within = amenities_df[amenities_df["distance"] <= radius_m]
    counts = within["category"].value_counts().to_dict()

    return {
        "total_amenities": len(within),
        "grocery":   counts.get("grocery",   0),
        "park":      counts.get("park",      0),
        "clinic":    counts.get("clinic",    0),
        "pharmacy":  counts.get("pharmacy",  0),
        "hospital":  counts.get("hospital",  0),
        "doctors":   counts.get("doctors",   0),
        "childcare": counts.get("childcare", 0),
    }


# Full station loop

def build_station_amenity_records(
    stations_df: pd.DataFrame,
    amenities_df: pd.DataFrame,
    radius_m: float = HALF_MILE_M,
) -> list[dict]:
    """
    Build a list of amenity-count records — one per station — ready to be
    passed to ``pd.DataFrame()``.

    Parameters
    ----------
    stations_df : pd.DataFrame
        Must contain at minimum: ``name``, ``agency``, ``latitude``,
        ``longitude``, ``geometry``, and any census columns you want
        forwarded (``GEOID``, ``median_income``, ``pct_no_vehicle``,
        ``pct_nonwhite``, ``total_pop``).
    amenities_df : pd.DataFrame
        Must contain ``longitude``, ``latitude``, and ``category``.
    radius_m : float, optional
        Search radius in metres.  Defaults to ``HALF_MILE_M``.

    Returns
    -------
    list[dict]
        Each dict contains station metadata + amenity counts.
    """
    records = []
    for _, station in stations_df.iterrows():
        amenity_counts = count_amenities_for_station(
            station["longitude"], station["latitude"], amenities_df, radius_m
        )
        records.append(
            {
                "station_name":   station["name"],
                "agency":         station["agency"],
                "latitude":       station["latitude"],
                "longitude":      station["longitude"],
                "GEOID":          station.get("GEOID"),
                "median_income":  station.get("median_income"),
                "pct_no_vehicle": station.get("pct_no_vehicle"),
                "pct_nonwhite":   station.get("pct_nonwhite"),
                "total_pop":      station.get("total_pop"),
                "geometry":       station["geometry"],
                **amenity_counts,
            }
        )
    return records