"""
Bay Area Transit & Amenities Data Collection
=============================================
Run this script from the `code/` directory.
Outputs are saved to `../data/`.

Usage:
    python get_bay_area_data.py

Requirements:
    pip install pandas geopandas requests overpy
"""

import os
import time
import zipfile
from io import BytesIO

import pandas as pd
import geopandas as gpd
import requests
from overpy import Overpass, exception as overpy_exc

# CONFIG
DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data/raw")
CACHE_DIR = DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)

BBOX = {"south": 36.9, "west": -123.0, "north": 38.9, "east": -121.2}


# SECTION 1: TRANSIT DATA
def get_bart_stations():
    url = "https://api.bart.gov/api/stn.aspx"
    params = {"cmd": "stns", "key": "MW9S-E7SL-26DU-VV8V", "json": "y"}
    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    stations = []
    for s in data["root"]["stations"]["station"]:
        stations.append({
            "station_id": s["abbr"],
            "name":       s["name"],
            "latitude":   float(s["gtfs_latitude"]),
            "longitude":  float(s["gtfs_longitude"]),
            "address":    s.get("address", ""),
            "city":       s.get("city", ""),
            "county":     s.get("county", ""),
            "zipcode":    s.get("zipcode", ""),
            "agency":     "BART",
            "mode":       "Heavy Rail",
        })
    return pd.DataFrame(stations)


def get_caltrain_stations():
    api_key  = "de7a7fb5-476e-4b52-91d1-241b1165d3dd"
    gtfs_url = f"https://api.511.org/transit/datafeeds?api_key={api_key}&operator_id=CT"
    try:
        r = requests.get(gtfs_url)
        r.raise_for_status()
        with zipfile.ZipFile(BytesIO(r.content)) as z:
            with z.open("stops.txt") as f:
                stops_df = pd.read_csv(f)
        stations = stops_df[stops_df["location_type"] == 1].copy()
        stations = stations.rename(columns={
            "stop_id":   "station_id",
            "stop_name": "name",
            "stop_lat":  "latitude",
            "stop_lon":  "longitude",
        })
        stations["agency"] = "Caltrain"
        stations["mode"]   = "Commuter Rail"
        return stations[["station_id", "name", "latitude", "longitude", "agency", "mode"]]
    except Exception as e:
        print(f"could not download Caltrain: {e}")
        return pd.DataFrame()


# SECTION 2: OSM AMENITIES (with caching + retry)
def run_overpass_query(query, max_retries=5, base_wait=60):
    api = Overpass()
    for attempt in range(max_retries):
        try:
            return api.query(query)
        except (overpy_exc.OverpassTooManyRequests,
                overpy_exc.OverpassGatewayTimeout) as e:
            wait = base_wait * (attempt + 1)
            print(f"    {type(e).__name__}: retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Overpass query failed after all retries.")


def cache_or_query(path, query_fn, *args):
    if os.path.exists(path):
        print(f"  Loading cached: {os.path.basename(path)}")
        return pd.read_csv(path)
    df = query_fn(*args)
    df.to_csv(path, index=False)
    print(f"  Saved: {os.path.basename(path)}")
    return df


def query_osm_amenities(amenity_type, bbox):
    query = f"""
    [out:json][timeout:180];
    (
      node["amenity"="{amenity_type}"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      way["amenity"="{amenity_type}"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
    );
    out center;
    """
    result   = run_overpass_query(query)
    features = []
    for node in result.nodes:
        features.append({
            "osm_id": f"node/{node.id}",
            "name":   node.tags.get("name", "Unnamed"),
            "type": "amenity", "subtype": amenity_type,
            "latitude": node.lat, "longitude": node.lon,
            "street":        node.tags.get("addr:street", ""),
            "city":          node.tags.get("addr:city", ""),
            "operator":      node.tags.get("operator", ""),
            "opening_hours": node.tags.get("opening_hours", ""),
        })
    for way in result.ways:
        features.append({
            "osm_id": f"way/{way.id}",
            "name":   way.tags.get("name", "Unnamed"),
            "type": "amenity", "subtype": amenity_type,
            "latitude": way.center_lat, "longitude": way.center_lon,
            "street":        way.tags.get("addr:street", ""),
            "city":          way.tags.get("addr:city", ""),
            "operator":      way.tags.get("operator", ""),
            "opening_hours": way.tags.get("opening_hours", ""),
        })
    return pd.DataFrame(features)


def query_osm_shops(shop_type, bbox):
    query = f"""
    [out:json][timeout:180];
    (
      node["shop"="{shop_type}"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      way["shop"="{shop_type}"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
    );
    out center;
    """
    result   = run_overpass_query(query)
    features = []
    for node in result.nodes:
        features.append({
            "osm_id": f"node/{node.id}",
            "name":   node.tags.get("name", "Unnamed"),
            "type": "shop", "subtype": shop_type,
            "latitude": node.lat, "longitude": node.lon,
            "street":        node.tags.get("addr:street", ""),
            "city":          node.tags.get("addr:city", ""),
            "operator":      node.tags.get("operator", ""),
            "opening_hours": node.tags.get("opening_hours", ""),
        })
    for way in result.ways:
        features.append({
            "osm_id": f"way/{way.id}",
            "name":   way.tags.get("name", "Unnamed"),
            "type": "shop", "subtype": shop_type,
            "latitude": way.center_lat, "longitude": way.center_lon,
            "street":        way.tags.get("addr:street", ""),
            "city":          way.tags.get("addr:city", ""),
            "operator":      way.tags.get("operator", ""),
            "opening_hours": way.tags.get("opening_hours", ""),
        })
    return pd.DataFrame(features)


def query_parks(bbox):
    query = f"""
    [out:json][timeout:180];
    (
      way["leisure"="park"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
      relation["leisure"="park"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
    );
    out center;
    """
    result   = run_overpass_query(query)
    features = []
    for way in result.ways:
        features.append({
            "osm_id": f"way/{way.id}",
            "name": way.tags.get("name", "Unnamed"),
            "type": "leisure", "subtype": "park",
            "latitude": way.center_lat, "longitude": way.center_lon,
            "opening_hours": way.tags.get("opening_hours", ""),
        })
    for rel in result.relations:
        features.append({
            "osm_id": f"relation/{rel.id}",
            "name": rel.tags.get("name", "Unnamed"),
            "type": "leisure", "subtype": "park",
            "latitude": rel.center_lat, "longitude": rel.center_lon,
            "opening_hours": rel.tags.get("opening_hours", ""),
        })
    return pd.DataFrame(features)


# MAIN

def main():
    print("=" * 60)
    print("Bay Area Data Collection")
    print("=" * 60)

    # Transit 
    print("\n[1/2] Transit stations...")
    bart_df     = get_bart_stations()
    caltrain_df = get_caltrain_stations()
    all_transit = pd.concat([bart_df, caltrain_df], ignore_index=True)
    transit_gdf = gpd.GeoDataFrame(
        all_transit,
        geometry=gpd.points_from_xy(all_transit["longitude"], all_transit["latitude"]),
        crs="EPSG:4326",
    )
    print(f"  BART: {len(bart_df)}  Caltrain: {len(caltrain_df)}  Total: {len(transit_gdf)}")

    # Amenities
    print("\n[2/2] OSM amenities...")
    jobs = [
        ("hospitals.csv",     query_osm_amenities, "hospital",     "hospital"),
        ("clinics.csv",       query_osm_amenities, "clinic",       "clinic"),
        ("doctors.csv",       query_osm_amenities, "doctors",      "doctors"),
        ("pharmacies.csv",    query_osm_amenities, "pharmacy",     "pharmacy"),
        ("kindergartens.csv", query_osm_amenities, "kindergarten", "childcare"),
        ("childcare.csv",     query_osm_amenities, "childcare",    "childcare"),
        ("supermarkets.csv",  query_osm_shops,     "supermarket",  "grocery"),
        ("convenience.csv",   query_osm_shops,     "convenience",  "convenience"),
        ("parks.csv",         query_parks,         None,           "park"),
    ]

    frames = []
    for filename, fn, osm_type, category in jobs:
        path = os.path.join(CACHE_DIR, filename)
        args = (osm_type, BBOX) if osm_type else (BBOX,)
        already_cached = os.path.exists(path)
        df = cache_or_query(path, fn, *args)
        if not df.empty:
            df = df.copy()
            df["category"] = category
            frames.append(df)
        if not already_cached:
            time.sleep(45)  # only pause after a live query, not a cache hit
        if not already_cached:
            time.sleep(45)

    all_amenities = pd.concat(frames, ignore_index=True)
    amenities_gdf = gpd.GeoDataFrame(
        all_amenities,
        geometry=gpd.points_from_xy(all_amenities["longitude"], all_amenities["latitude"]),
        crs="EPSG:4326",
    )
    print(f"Total amenities: {len(amenities_gdf)}")

    # Save 
    print("\nSaving to", os.path.abspath(DATA_DIR))
    transit_gdf.to_csv(os.path.join(DATA_DIR, "transit_gdf.csv"), index=False)
    amenities_gdf.to_csv(os.path.join(DATA_DIR, "all_amenities.csv"), index=False)


    print("DONE! Output files:")
    print(f"  data/raw/transit_gdf.csv        ({len(transit_gdf)} rows)")
    print(f"  data/raw/all_amenities.csv      ({len(amenities_gdf)} rows)")


if __name__ == "__main__":
    main()
